"""HTTP routes for the ``/api/tasks`` family.

This module is built incrementally across tasks 5.1 -- 5.5. Task 5.1
(the only sub-task implemented in this commit) registers
``POST /api/tasks``: create a new crawl task, run the global
single-task concurrency check inside a serialised transaction, then
hand control off to :class:`CrawlerService.run_xhs_search` via
FastAPI's ``BackgroundTasks`` so the HTTP response can return inside
two seconds (requirement 1.3).

Validation strategy
-------------------

Pydantic ships generic 422 ``VALIDATION_ERROR`` responses whenever a
``Field(..., ge=..., le=...)`` constraint fails. The project-wide
error contract requires this endpoint to surface the literal
``INVALID_KEYWORD`` (1.4) and ``OVER_LIMIT`` (1.5) codes, so the
schema in :mod:`app.schemas.task` keeps range validation off and the
route handler re-implements it explicitly. We rely on Pydantic for
*type* coercion (so ``max_notes`` is guaranteed to be an ``int``
before the range check) but never for *range* validation.

Concurrency strategy
--------------------

Requirement 2.4 mandates that the running-task check and the new-row
INSERT happen inside a single serialised transaction so two
concurrent ``POST /api/tasks`` cannot both observe zero running tasks
and then both insert. SQLite's standard write transaction already
serialises writers, but the default ``DEFERRED`` mode upgrades to
write-locked only on the first write. We therefore upgrade explicitly
to ``BEGIN IMMEDIATE`` *before* the ``SELECT COUNT(*)`` so the second
caller blocks (or fails) on the lock acquisition rather than slipping
through with a stale read. See ``requirements.md`` 2.1 / 2.2 / 2.4 /
2.6 for the full contract.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, status
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.api._errors import error_detail as _error_detail
from app.api.deps import get_crawler, get_store
from app.core.logger import logger
from app.models import Task
from app.schemas.task import TaskCreateRequest
from app.services.crawler_service import CrawlerService
from app.services.data_store import DataStore


# ``prefix="/api"`` lifts the shared ``/api`` segment out of every
# decorator below and keeps requirement 19.1's nine-route contract
# easy to audit in one place.
router = APIRouter(prefix="/api", tags=["tasks"])


# ---------------------------------------------------------------------------
# Validation bounds (kept as module constants so tests can import them
# without hard-coding the numbers in two places).
# ---------------------------------------------------------------------------

#: Minimum trimmed length of ``keyword`` accepted by ``POST /api/tasks``.
KEYWORD_MIN_LEN: int = 1

#: Maximum trimmed length of ``keyword`` accepted by ``POST /api/tasks``.
KEYWORD_MAX_LEN: int = 50

#: Lower bound (inclusive) on ``max_notes``; matches requirement 1.5.
MAX_NOTES_MIN: int = 1

#: Upper bound (inclusive) on ``max_notes``; matches requirement 1.5
#: and the design's "≤ 20" hard cap.
MAX_NOTES_MAX: int = 20


# ``_error_detail`` is re-exported as a local alias above (imported as
# ``error_detail as _error_detail``) so existing references in this
# module keep working unchanged. Defining it here is no longer
# necessary -- the shared helper in :mod:`app.api._errors` is the
# single source of truth.


@router.post(
    "/tasks",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a crawl task",
    response_class=JSONResponse,
)
async def create_task(
    request: TaskCreateRequest,
    background_tasks: BackgroundTasks,
    store: DataStore = Depends(get_store),
    crawler: CrawlerService = Depends(get_crawler),
) -> JSONResponse:
    """Create a new crawl task and schedule the background crawler.

    The handler is split into clearly labelled steps so each
    requirement can be traced to a single block:

    1. **Validate ``keyword``** (requirement 1.4). Strip leading /
       trailing whitespace then enforce the closed range
       ``[KEYWORD_MIN_LEN, KEYWORD_MAX_LEN]`` on the trimmed length.
       Any violation raises HTTP 422 with the literal
       ``INVALID_KEYWORD`` code and *does not* touch the database.
    2. **Validate ``max_notes``** (requirement 1.5). The Pydantic
       schema already coerced the field to ``int``; we only need the
       range check. Out-of-range values raise HTTP 422 with the
       literal ``OVER_LIMIT`` code.
    3. **Concurrency check + INSERT in a single transaction**
       (requirements 2.1 / 2.2 / 2.4 / 2.6). Open a session, escalate
       to a write lock with ``BEGIN IMMEDIATE``, run
       ``SELECT COUNT(*) WHERE status='running'``, then either
       reject with HTTP 409 ``TASK_BUSY`` (no row touched) or
       ``INSERT`` the new task. Any unexpected SQL failure inside
       this block surfaces as HTTP 500 ``INTERNAL_ERROR`` with the
       transaction rolled back.
    4. **Schedule the crawler** via ``BackgroundTasks`` so the HTTP
       response lands inside the two-second budget required by
       requirement 1.3.
    5. **Return** ``202`` + ``{"task_id": ..., "status": "pending"}``.
    """
    # --- 1) Validate keyword ---------------------------------------
    raw_keyword = request.keyword
    keyword = raw_keyword.strip()
    if not (KEYWORD_MIN_LEN <= len(keyword) <= KEYWORD_MAX_LEN):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_detail(
                code="INVALID_KEYWORD",
                message=(
                    f"keyword length after strip must be in "
                    f"[{KEYWORD_MIN_LEN}, {KEYWORD_MAX_LEN}]"
                ),
                # Echo back the original (untrimmed) value so the
                # client can correlate the rejection with their
                # input. Length is included to make the most common
                # cause of failure (excess length) trivially
                # diagnosable client-side.
                detail={
                    "keyword": raw_keyword,
                    "stripped_length": len(keyword),
                },
            ),
        )

    # --- 2) Validate max_notes -------------------------------------
    # Pydantic already guaranteed ``request.max_notes`` is an ``int``;
    # we only need to range-check it here.
    max_notes = request.max_notes
    if not (MAX_NOTES_MIN <= max_notes <= MAX_NOTES_MAX):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_detail(
                code="OVER_LIMIT",
                message=(
                    f"max_notes must be in "
                    f"[{MAX_NOTES_MIN}, {MAX_NOTES_MAX}]"
                ),
                detail={"max_notes": max_notes},
            ),
        )

    # --- 3) Concurrency check + INSERT in one transaction ----------
    # We open the session manually (rather than using
    # ``async with session.begin():``) so the explicit
    # ``BEGIN IMMEDIATE`` is the *first* statement issued -- otherwise
    # SQLAlchemy's autobegin would fire a ``BEGIN DEFERRED`` first and
    # we would lose the eager write-lock semantics that requirement
    # 2.4 ("显式开启串行隔离的事务") asks for.
    try:
        async with store.session() as session:
            try:
                # Upgrade the still-pending autobegin transaction to
                # an immediate write lock. Concurrent callers attempting
                # the same ``BEGIN IMMEDIATE`` will block on
                # SQLITE_BUSY (or fail outright once the busy timeout
                # elapses), which is exactly the serialisation
                # requirement 2.4 mandates.
                await session.execute(text("BEGIN IMMEDIATE"))

                running_count = (
                    await session.execute(
                        select(func.count())
                        .select_from(Task)
                        .where(Task.status == "running")
                    )
                ).scalar_one()

                if running_count > 0:
                    # Requirement 2.2: do not modify any field on the
                    # currently-running task. The rollback below
                    # discards the implicit ``BEGIN IMMEDIATE`` lock
                    # without touching any row.
                    await session.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=_error_detail(
                            code="TASK_BUSY",
                            message=(
                                "another crawl task is currently running"
                            ),
                            detail={"running_count": int(running_count)},
                        ),
                    )

                # Insert the new task in the same transaction so
                # neither the count nor the INSERT can be observed
                # alone by a concurrent reader.
                new_task = Task(
                    keyword=keyword,
                    max_notes=max_notes,
                    status="pending",
                )
                session.add(new_task)
                await session.flush()
                # ``new_task.id`` is populated after ``flush()`` even
                # though the session has ``expire_on_commit=False``;
                # we capture it before commit so a subsequent commit
                # failure cannot leave the variable unset.
                task_id: int = int(new_task.id)
                await session.commit()
            except HTTPException:
                # Propagate domain-level HTTP errors (TASK_BUSY) as-is
                # so the unified error handler in ``app.main`` can
                # render them into the {code, message, detail}
                # envelope. The session has already been rolled back
                # above on this branch.
                raise
            except (DBAPIError, SQLAlchemyError):
                # Any database-driver failure during the read or
                # the INSERT must roll back so no partial row
                # survives (requirements 1.7 / 2.6). We log the
                # exception here so the underlying SQL error is
                # captured in the server log even though the client
                # never sees it.
                logger.exception(
                    "POST /api/tasks: database error",
                    extra={
                        "event": "create_task_db_error",
                        "keyword": keyword,
                        "max_notes": max_notes,
                    },
                )
                try:
                    await session.rollback()
                except Exception:  # pragma: no cover - defensive
                    logger.exception(
                        "POST /api/tasks: rollback also failed"
                    )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=_error_detail(
                        code="INTERNAL_ERROR",
                        message="database error while creating task",
                    ),
                )
    except HTTPException:
        # Re-raise domain HTTP errors (INVALID_KEYWORD / OVER_LIMIT
        # never reach here -- they are raised before the ``try``
        # block opens; the only HTTPException that flows through
        # here is TASK_BUSY or the INTERNAL_ERROR re-raised above).
        raise
    except Exception:
        # Any non-SQLAlchemy exception escaping the session block
        # (e.g. an OS-level failure obtaining a connection) is
        # treated as INTERNAL_ERROR. The session context manager
        # closes / rolls back the connection on its way out, so no
        # partial row can survive into ``tasks``.
        logger.exception(
            "POST /api/tasks: unexpected error before commit",
            extra={
                "event": "create_task_unexpected",
                "keyword": keyword,
                "max_notes": max_notes,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_error_detail(
                code="INTERNAL_ERROR",
                message="internal error while creating task",
            ),
        )

    # --- 4) Schedule the crawler in the background ----------------
    # ``BackgroundTasks.add_task`` enqueues the coroutine to run
    # *after* the response has been sent, which keeps the synchronous
    # path well inside the two-second budget (requirement 1.3).
    background_tasks.add_task(
        crawler.run_xhs_search, task_id, keyword, max_notes
    )

    logger.info(
        "POST /api/tasks: task created",
        extra={
            "event": "create_task_accepted",
            "task_id": task_id,
            "keyword": keyword,
            "max_notes": max_notes,
        },
    )

    # --- 5) Return 202 + the canonical body -----------------------
    # We construct the JSONResponse manually rather than relying on
    # ``response_model=TaskCreateResponse`` so the HTTP status code
    # is unambiguous and the body shape matches the literal contract
    # ``{"task_id": <int>, "status": "pending"}`` from requirement
    # 1.3 byte-for-byte.
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"task_id": task_id, "status": "pending"},
    )
