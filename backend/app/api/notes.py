"""HTTP routes for the ``/api/.../notes`` family.

This module currently registers a single endpoint -- ``GET
/api/tasks/{task_id}/notes`` (task 6.1) -- which returns a paginated
list of notes attached to ``task_id`` along with a compact author
projection. ``GET /api/notes/{note_id}`` (task 6.2) will land in this
file later; keeping both behind a single router prevents the public
route surface from drifting away from the 9-endpoint contract locked
down by requirement 19.1.

Validation strategy
-------------------

Requirement 11.4 mandates the literal ``INVALID_QUERY_PARAM`` error
code for out-of-range ``limit`` / ``offset`` values, but FastAPI's
built-in :class:`Query` constraints would surface a generic
``VALIDATION_ERROR`` instead. We therefore declare the query params
with type ``int`` (so non-integer input is still rejected with 422
VALIDATION_ERROR by Pydantic) and re-implement the range check inside
the handler so out-of-range values get the project-specific code.

Ordering strategy
-----------------

Requirement 11.1 mandates ``items`` be ordered by note publish time
descending. ``notes.publish_time`` is nullable, so a naïve
``Note.publish_time.desc()`` would let SQLite place ``NULL`` rows
*first* (SQLite's default for descending order). To guarantee
``NULL`` rows surface at the *end* of the page -- and to make the
ordering deterministic across runs -- we sort by:

    1. ``Note.publish_time.is_(None)`` ascending (non-NULL before NULL),
    2. ``Note.publish_time`` descending (newest first within non-NULL),
    3. ``Note.note_id`` ascending (deterministic tiebreaker).

This pattern works on SQLite without requiring NULLS LAST support and
extends cleanly to any other engine the project might target later.
"""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter, Depends, Query, status
from fastapi.exceptions import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.api._errors import error_detail
from app.api.deps import get_store
from app.core.logger import logger
from app.models import Author, Note, Task
from app.schemas.note import AuthorBrief, NoteListItem, NoteListResponse
from app.services.data_store import DataStore


# ``prefix="/api"`` lifts the shared ``/api`` segment out of every
# decorator below. Combined with the prefix on
# :data:`app.api.tasks.router`, this keeps the requirement 19.1
# nine-route contract auditable in one glance across the api package.
router = APIRouter(prefix="/api", tags=["notes"])


# ---------------------------------------------------------------------------
# Query-parameter bounds (kept as module constants so tests / future
# routes can import them without restating the numbers).
# ---------------------------------------------------------------------------

#: Default value for ``limit`` when the client omits it (requirement 11.2).
LIMIT_DEFAULT: Final[int] = 20

#: Lower bound (inclusive) on ``limit`` (requirement 11.2).
LIMIT_MIN: Final[int] = 1

#: Upper bound (inclusive) on ``limit`` (requirement 11.2).
LIMIT_MAX: Final[int] = 100

#: Default value for ``offset`` when the client omits it (requirement 11.2).
OFFSET_DEFAULT: Final[int] = 0

#: Lower bound (inclusive) on ``offset`` (requirement 11.2).
OFFSET_MIN: Final[int] = 0

#: Upper bound (inclusive) on ``offset`` (requirement 11.2). The
#: million-row ceiling is generous enough for any plausible local
#: workload while still defending against malicious clients trying to
#: paginate past ``INT_MAX``.
OFFSET_MAX: Final[int] = 1_000_000


@router.get(
    "/tasks/{task_id}/notes",
    response_model=NoteListResponse,
    status_code=status.HTTP_200_OK,
    summary="List notes attached to a task (paginated)",
)
async def list_task_notes(
    task_id: int,
    limit: int = Query(
        default=LIMIT_DEFAULT,
        description=(
            "Max number of notes to return. Must be an integer in "
            "[1, 100]. Out-of-range values are rejected with the "
            "``INVALID_QUERY_PARAM`` error code (requirement 11.4)."
        ),
    ),
    offset: int = Query(
        default=OFFSET_DEFAULT,
        description=(
            "Number of leading notes to skip. Must be an integer in "
            "[0, 1_000_000]."
        ),
    ),
    store: DataStore = Depends(get_store),
) -> NoteListResponse:
    """Return a page of notes attached to ``task_id``.

    The handler is split into clearly labelled steps so each
    requirement can be traced to a single block:

    1. **Validate query parameters** (requirement 11.4). Pydantic has
       already coerced ``limit`` / ``offset`` to ``int``; we only need
       the range check. Out-of-range values raise HTTP 422 with the
       literal ``INVALID_QUERY_PARAM`` code.
    2. **Confirm the task exists** (requirement 11.3). A missing
       ``task_id`` raises HTTP 404 with the ``TASK_NOT_FOUND`` code.
    3. **Run the SELECT** with a left-join onto ``authors`` so notes
       missing an author row still surface (the FK is nullable). The
       ordering is described in the module docstring.
    4. **Run a separate COUNT** to populate ``total`` -- LIMIT/OFFSET
       reduces the live page but the client still needs the
       full-task count to drive pagination (requirement 11.1).
    5. **Build and return** the :class:`NoteListResponse`. Counter
       fields fall back to ``0`` if the underlying column is
       unexpectedly ``None`` so the response model never rejects an
       otherwise-valid row.
    """
    # --- 1) Validate query parameters ------------------------------
    if not (LIMIT_MIN <= limit <= LIMIT_MAX):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_detail(
                code="INVALID_QUERY_PARAM",
                message=(
                    f"limit must be an integer in "
                    f"[{LIMIT_MIN}, {LIMIT_MAX}]"
                ),
                detail={"limit": limit},
            ),
        )
    if not (OFFSET_MIN <= offset <= OFFSET_MAX):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_detail(
                code="INVALID_QUERY_PARAM",
                message=(
                    f"offset must be an integer in "
                    f"[{OFFSET_MIN}, {OFFSET_MAX}]"
                ),
                detail={"offset": offset},
            ),
        )

    # --- 2) Look up the task / 3) Run the SELECT / 4) Run COUNT ----
    try:
        async with store.session() as session:
            task = await session.get(Task, task_id)
            if task is None:
                # Requirement 11.3: missing task -> 404 with the
                # ``TASK_NOT_FOUND`` literal code so the frontend can
                # branch on it.
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=error_detail(
                        code="TASK_NOT_FOUND",
                        message=f"task id={task_id} not found",
                        detail={"task_id": task_id},
                    ),
                )

            # ``total`` reflects every note attached to the task,
            # regardless of the current page. We compute it as a
            # standalone COUNT(*) (rather than overcounting from the
            # page query) so adding ORDER BY / LIMIT / OFFSET cannot
            # accidentally skew the value.
            total = (
                await session.execute(
                    select(func.count())
                    .select_from(Note)
                    .where(Note.task_id == task_id)
                )
            ).scalar_one()

            # Page query: left-join onto authors so notes whose
            # ``author_user_id`` is ``NULL`` (or whose linked author row
            # has been deleted via ``ON DELETE SET NULL``) still appear
            # in the results, with both author fields rendered as
            # ``None``. We project ``Author.user_id`` / ``nickname``
            # alongside the ORM ``Note`` row so the handler does not
            # need a second roundtrip per note to materialise the
            # author summary.
            stmt = (
                select(
                    Note,
                    Author.user_id.label("a_user_id"),
                    Author.nickname.label("a_nickname"),
                )
                .outerjoin(Author, Note.author_user_id == Author.user_id)
                .where(Note.task_id == task_id)
                # See module docstring: NULL publish_time goes last,
                # then publish_time DESC, then note_id ASC for
                # determinism across rows that share a publish_time
                # (or share NULL).
                .order_by(
                    Note.publish_time.is_(None).asc(),
                    Note.publish_time.desc(),
                    Note.note_id.asc(),
                )
                .offset(offset)
                .limit(limit)
            )

            rows = (await session.execute(stmt)).all()
    except HTTPException:
        # Domain-level HTTP errors (TASK_NOT_FOUND) propagate as-is
        # so the unified handler in :mod:`app.main` renders them into
        # the standard envelope.
        raise
    except (DBAPIError, SQLAlchemyError):
        logger.exception(
            "GET /api/tasks/{task_id}/notes: database error",
            extra={
                "event": "list_task_notes_db_error",
                "task_id": task_id,
                "limit": limit,
                "offset": offset,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail(
                code="INTERNAL_ERROR",
                message="database error while listing notes",
            ),
        )

    # --- 5) Build the response model -------------------------------
    items: list[NoteListItem] = []
    for note, a_user_id, a_nickname in rows:
        items.append(
            NoteListItem(
                note_id=note.note_id,
                title=note.title,
                type=note.type,
                cover_url=note.cover_url,
                # ``Note`` columns declare NOT NULL DEFAULT 0 in the
                # ORM, but we coalesce defensively in case a future
                # migration loosens the constraint -- the response
                # model rejects ``None`` for these fields.
                liked_count=int(note.liked_count or 0),
                collected_count=int(note.collected_count or 0),
                comment_count=int(note.comment_count or 0),
                author=AuthorBrief(
                    user_id=a_user_id,
                    nickname=a_nickname,
                ),
            )
        )

    return NoteListResponse(items=items, total=int(total))
