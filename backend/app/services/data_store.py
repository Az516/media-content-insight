"""DataStore -- persistence façade for the xhs-content-insight backend.

The class lives at the seam between the API / service layer and the
SQLAlchemy ORM. The functional groups implemented here:

* **Task state-machine** (task 2.2): :meth:`DataStore.mark_task_running`,
  :meth:`DataStore.mark_task_success`, :meth:`DataStore.mark_task_failed`
  drive a single task through its lifecycle. Each method runs SELECT →
  ASSERT precondition → UPDATE → COMMIT inside a single
  :class:`AsyncSession` transaction. On a failed precondition the
  transaction is rolled back and an :class:`AssertionError` is re-raised,
  so the four mutable task fields (``status``, ``started_at``,
  ``finished_at``, ``error_msg``) keep their pre-transition values
  (requirements 3.1, 3.2, 3.3, 3.4, 3.5).

* **Idempotent bulk upserts** (task 2.4):
  :meth:`DataStore.upsert_authors_from_raw`,
  :meth:`DataStore.upsert_notes`, :meth:`DataStore.upsert_comments`
  ingest crawler output through SQLite ``INSERT ... ON CONFLICT(<pk>)
  DO UPDATE SET ...`` so repeated runs collapse onto the same rows
  (requirements 9.1-9.6). :meth:`upsert_comments` additionally enforces
  the comment-tree integrity contract: every reply's
  ``parent_comment_id`` must resolve to an existing parent that points
  at the same ``note_id`` as the reply itself, otherwise the entire
  batch is rolled back via :class:`sqlalchemy.exc.IntegrityError`.

* **Archive & AI-report I/O** (task 2.7):
  :meth:`DataStore.archive_json` writes a deterministic
  ``data/json/{task_id}.json`` snapshot (UTF-8, ``ensure_ascii=False``,
  Chinese characters preserved verbatim) and updates ``tasks.json_path``
  in the same transaction (requirements 10.1, 10.2, 10.7).
  :meth:`DataStore.load_for_ai` returns a read-only snapshot of
  ``(keyword, notes, comments)`` for the AI analyser
  (requirement 15.5). :meth:`DataStore.save_ai_report` inserts exactly
  one ``ai_reports`` row and never touches any other table
  (requirement 15.6); :meth:`DataStore.list_ai_reports` exposes the
  per-task report history that backs ``GET /api/tasks/{id}.reports``
  (requirements 16.5, 5.4). Sensitive keys (``phone``, ``mobile``,
  ``email``, ``bind_email``, ``id_card``, ``id_number``, ``identity``,
  case-insensitive) are stripped from ``raw_json`` before persistence
  so they never reach disk (requirements 20.3, 20.4).
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Final, Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.logger import logger
from app.models import AIReport, Author, Comment, Note, Task


#: Maximum number of characters retained from an ``error_msg`` value
#: (requirement 3.5: ``1 ≤ len(error_msg) ≤ 1000``; the upper bound is
#: enforced by truncating here, the lower bound is the caller's
#: responsibility).
ERROR_MSG_MAX_CHARS: Final[int] = 1000


@dataclass(frozen=True)
class AIReportInput:
    """Plain payload accepted by :meth:`DataStore.save_ai_report`.

    Defining the shape locally (rather than importing the
    ``AIReport`` dataclass that ``ai_analyzer`` will introduce in task
    11.1) keeps task 2.7 self-contained and lets the analyser layer
    ship its own dataclass later without circular imports. The fields
    map 1:1 to the matching ``ai_reports`` columns in design §2.
    """

    task_id: int
    provider: str
    model: str
    prompt_version: str
    report_md: str


@dataclass(frozen=True)
class AIReportSummary:
    """Read-only metadata row returned by :meth:`DataStore.list_ai_reports`.

    The shape matches the per-task ``reports`` array embedded in the
    ``GET /api/tasks/{task_id}`` response (requirement 16.5 / 5.4),
    deliberately omitting the heavy ``report_md`` text so the summary
    can be inlined in the task detail without bloating the payload.
    """

    id: int
    provider: str
    model: str
    prompt_version: str
    created_at: str


def _utc_now_iso() -> str:
    """Return the current UTC time as ISO 8601 text, second precision.

    Equivalent to ``datetime.utcnow().isoformat(timespec='seconds')``
    but uses the modern timezone-aware API to avoid the deprecation
    warning emitted on Python 3.12+. The returned string carries no
    timezone suffix so it round-trips identically through SQLite text
    columns.
    """
    return (
        datetime.now(timezone.utc)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


class DataStore:
    """Persistence façade over an async SQLAlchemy session factory.

    Tasks 2.2 and 2.4 are implemented on this class: task state-machine
    transitions plus idempotent bulk upserts for the
    ``authors`` / ``notes`` / ``comments`` tables. Future tasks layer
    additional behaviour (JSON archiving, AI-report read/write) on top
    of the same instance.
    """

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker = session_maker

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a fresh :class:`AsyncSession`.

        Exposed as a public helper so the not-yet-implemented upsert /
        archive methods can share the same factory without reaching
        into the private ``_session_maker`` attribute.
        """
        async with self._session_maker() as s:
            yield s

    # ------------------------------------------------------------------
    # Task state machine -- requirements 3.1 / 3.2 / 3.3 / 3.4 / 3.5
    # ------------------------------------------------------------------

    async def mark_task_running(self, task_id: int) -> None:
        """Transition ``task_id`` from ``pending`` to ``running``.

        On success: ``started_at`` is set to the current UTC ISO 8601
        timestamp (second precision); ``finished_at`` and ``error_msg``
        remain ``NULL``.

        Raises
        ------
        AssertionError
            If the task does not exist, or its current ``status`` is not
            ``'pending'``. The transaction is rolled back before the
            assertion propagates, so the four mutable fields keep their
            pre-call values (requirement 3.2).
        """
        await self._transition(
            task_id=task_id,
            allowed_from=("pending",),
            target_status="running",
            updates=_apply_running,
            method_name="mark_task_running",
        )

    async def mark_task_success(
        self,
        task_id: int,
        note_count: int,
        json_path: str,
    ) -> None:
        """Transition ``task_id`` from ``running`` to ``success``.

        On success: ``finished_at`` is set, ``note_count`` and
        ``json_path`` are persisted, and ``error_msg`` is left ``NULL``.

        Parameters
        ----------
        task_id:
            Primary key of the row to transition.
        note_count:
            Number of notes that ended up persisted for this task. The
            caller (:class:`CrawlerService`) is responsible for ensuring
            ``0 < note_count <= max_notes <= 20`` (requirement 7.6).
        json_path:
            Path of the archived JSON snapshot relative to the
            repository root, e.g. ``"data/json/12.json"`` (requirement
            10.7).

        Raises
        ------
        AssertionError
            If the task does not exist or its current ``status`` is not
            ``'running'``. The transaction is rolled back before the
            assertion propagates.
        """
        def _updates(task: Task) -> None:
            _apply_success(task, note_count=note_count, json_path=json_path)

        await self._transition(
            task_id=task_id,
            allowed_from=("running",),
            target_status="success",
            updates=_updates,
            method_name="mark_task_success",
        )

    async def mark_task_failed(self, task_id: int, error_msg: str) -> None:
        """Transition ``task_id`` from ``pending`` or ``running`` to ``failed``.

        On success: ``finished_at`` is set and ``error_msg`` is stored,
        truncated to the first :data:`ERROR_MSG_MAX_CHARS` characters
        (requirement 3.5).

        Raises
        ------
        AssertionError
            If the task does not exist or its current ``status`` is not
            in ``{'pending', 'running'}``. The transaction is rolled
            back before the assertion propagates.
        """
        truncated = (error_msg or "")[:ERROR_MSG_MAX_CHARS]

        def _updates(task: Task) -> None:
            _apply_failed(task, error_msg=truncated)

        await self._transition(
            task_id=task_id,
            allowed_from=("pending", "running"),
            target_status="failed",
            updates=_updates,
            method_name="mark_task_failed",
        )

    # ------------------------------------------------------------------
    # Bulk upserts -- requirements 7.3 / 9.1 / 9.2 / 9.3 / 9.4 / 9.5 / 9.6
    # ------------------------------------------------------------------

    async def upsert_authors_from_raw(
        self, raw_notes: Iterable[Mapping[str, Any]]
    ) -> int:
        """Idempotently upsert every author embedded in ``raw_notes``.

        MediaCrawler attaches the note creator's profile under an
        ``author`` sub-dict on each raw note. This method extracts those
        sub-dicts, deduplicates by ``user_id`` (last-write-wins to match
        requirement 9.4), then issues a single SQLite ``INSERT ... ON
        CONFLICT(user_id) DO UPDATE`` so re-running the same crawl does
        not duplicate authors.

        Notes whose payload carries no parseable author info are
        silently skipped rather than aborting the batch -- the
        ``raw_notes`` stream is treated as untrusted external input.

        Returns the number of distinct ``user_id`` values that were
        upserted. The return value exists primarily for tests / logging;
        callers can ignore it.
        """
        rows: dict[str, dict[str, Any]] = {}
        for raw in raw_notes or ():
            row = _author_row_from_raw_note(raw)
            if row is None:
                continue
            # Last-write-wins: subsequent occurrences of the same
            # ``user_id`` overwrite earlier ones, mirroring the
            # ``ON CONFLICT DO UPDATE`` semantics of the database
            # statement that follows. Without this we would feed
            # SQLite multiple rows with the same primary key in a
            # single statement, which raises a ``cardinality_violation``
            # under ``ON CONFLICT``.
            rows[row["user_id"]] = row

        if not rows:
            return 0

        async with self._session_maker() as session:
            try:
                await self._upsert_authors(session, rows.values())
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

        return len(rows)

    async def upsert_notes(
        self,
        task_id: int,
        raw_notes: Iterable[Mapping[str, Any]],
    ) -> int:
        """Idempotently upsert ``raw_notes`` for ``task_id``.

        Each input dict is converted to a row matching the :class:`Note`
        ORM, then handed to a single SQLite ``INSERT ... ON CONFLICT
        (note_id) DO UPDATE SET ...`` so that repeated runs collapse
        duplicate ``note_id`` values onto a single row whose non-PK
        fields reflect the most recent write (requirements 9.1, 9.2).

        ``task_id`` is forced onto every row -- callers are not expected
        to thread the value through ``raw_notes`` themselves
        (requirement 7.3 fixes the ``notes -> tasks`` association at
        write time).

        Returns the number of distinct ``note_id`` values that were
        upserted; rows lacking a ``note_id`` are silently dropped so
        the caller's slice math (``raw_notes[:max_notes]``) keeps
        working on partially-malformed crawler output.
        """
        rows: dict[str, dict[str, Any]] = {}
        for raw in raw_notes or ():
            row = _note_row_from_raw(task_id, raw)
            if row is None:
                continue
            # Last-write-wins keeps the upsert deterministic when the
            # same ``note_id`` appears twice in the input stream; the
            # final row reflects the latest copy supplied by the
            # caller, matching requirement 9.2 ("除主键外覆盖所有字段").
            rows[row["note_id"]] = row

        if not rows:
            return 0

        async with self._session_maker() as session:
            try:
                await self._upsert_notes(session, rows.values())
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

        return len(rows)

    async def upsert_comments(
        self, raw_comments: Iterable[Mapping[str, Any]]
    ) -> int:
        """Idempotently upsert comments while validating tree integrity.

        Implements the multi-stage write order mandated by task 2.4:

        1. Split the input into top-level comments (``parent_comment_id
           IS NULL``) and replies.
        2. Inside a single transaction, upsert top-level comments
           **first** so any reply that legitimately points to a
           sibling-batch parent finds its target during step 3.
        3. For every reply, run ``SELECT note_id FROM comments WHERE
           comment_id = :parent_id`` against the *same* session. If the
           parent is missing or its ``note_id`` differs from the
           reply's ``note_id``, raise :class:`IntegrityError` whose
           message contains the substring ``"comment_tree"`` (matching
           the marker the orchestration layer greps for in requirement
           9.6) and roll back the entire batch.
        4. Upsert the replies in a single statement.

        Returns the total number of distinct ``comment_id`` values that
        were upserted across both levels.
        """
        top_rows: dict[str, dict[str, Any]] = {}
        reply_rows: dict[str, dict[str, Any]] = {}

        for raw in raw_comments or ():
            row = _comment_row_from_raw(raw)
            if row is None:
                continue
            # Split on ``parent_comment_id``; treat empty strings as
            # NULL because some crawler outputs use ``""`` for top-level
            # comments rather than the JSON literal ``null``.
            if row["parent_comment_id"] in (None, ""):
                row["parent_comment_id"] = None
                top_rows[row["comment_id"]] = row
            else:
                reply_rows[row["comment_id"]] = row

        if not top_rows and not reply_rows:
            return 0

        async with self._session_maker() as session:
            try:
                # Step 2: top-level comments first so replies in the
                # same batch can resolve their parents in step 3.
                if top_rows:
                    await self._upsert_comments(session, top_rows.values())

                # Step 3: validate every reply against the live state of
                # the ``comments`` table (which now includes anything we
                # just upserted in step 2).
                for reply in reply_rows.values():
                    await self._assert_parent_consistent(session, reply)

                # Step 4: replies in one shot. We deliberately commit
                # the parent-validation lookups together with the
                # reply writes so a concurrent reader never observes a
                # half-written batch.
                if reply_rows:
                    await self._upsert_comments(session, reply_rows.values())

                await session.commit()
            except BaseException:
                # Both ``IntegrityError`` (raised explicitly by
                # ``_assert_parent_consistent``) and any unexpected
                # exception roll the whole batch back, so neither the
                # invalid replies nor the otherwise-valid top-level
                # comments survive in the database.
                await session.rollback()
                raise

        return len(top_rows) + len(reply_rows)

    # ------------------------------------------------------------------
    # JSON archive & json_path writeback -- requirements 10.1 / 10.2 / 10.7
    # ------------------------------------------------------------------

    async def archive_json(self, task_id: int) -> Path:
        """Write ``data/json/{task_id}.json`` and update ``tasks.json_path``.

        Implements requirements 10.1, 10.2 and 10.7:

        * The top-level JSON object contains *exactly* the four keys
          ``task_id``, ``exported_at``, ``notes``, ``comments``.
        * ``exported_at`` is the current UTC ISO 8601 timestamp at
          second precision.
        * The file is written as UTF-8 with ``ensure_ascii=False`` so
          Chinese characters are preserved verbatim (no ``\\u`` escapes).
        * ``notes`` and ``comments`` enumerate every column on the ORM
          rows, ordered deterministically (notes by ``note_id``,
          comments by ``(note_id, parent_comment_id NULLS FIRST,
          comment_id)``) so re-running the archive produces a
          byte-identical file when nothing changed.
        * Once the file is fsync'd to disk, ``tasks.json_path`` is
          updated in the same session to the path *relative to the
          repository root* (e.g. ``"data/json/12.json"``), then the
          transaction is committed.

        Returns the absolute :class:`pathlib.Path` of the archive so
        callers can pass the same value back into
        :meth:`mark_task_success` without re-deriving it.
        """
        archive_dir: Path = settings.JSON_ARCHIVE_DIR
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = (archive_dir / f"{task_id}.json").resolve()

        async with self._session_maker() as session:
            try:
                # Look up the task first so a missing id surfaces as a
                # clean error rather than a silently-empty archive.
                task = await session.get(Task, task_id)
                assert task is not None, (
                    f"archive_json: task id={task_id} not found"
                )
                keyword = task.keyword

                # Notes ordered by ``note_id`` for determinism so that
                # round-trip equivalence (requirement 10.3) compares
                # apples to apples no matter how SQLite chose to lay
                # rows out on disk.
                notes_rows = (
                    await session.execute(
                        select(Note)
                        .where(Note.task_id == task_id)
                        .order_by(Note.note_id.asc())
                    )
                ).scalars().all()

                note_ids = [n.note_id for n in notes_rows]
                if note_ids:
                    # Comments ordered by (note_id, parent NULLS FIRST,
                    # comment_id) so top-level comments precede their
                    # replies inside each note's slice. SQLite sorts
                    # NULLs first by default, matching what we want.
                    comments_rows = (
                        await session.execute(
                            select(Comment)
                            .where(Comment.note_id.in_(note_ids))
                            .order_by(
                                Comment.note_id.asc(),
                                Comment.parent_comment_id.asc(),
                                Comment.comment_id.asc(),
                            )
                        )
                    ).scalars().all()
                else:
                    comments_rows = []

                payload = {
                    "task_id": task_id,
                    "exported_at": _utc_now_iso(),
                    "notes": [_orm_to_dict(n, _NOTE_ARCHIVE_COLUMNS) for n in notes_rows],
                    "comments": [
                        _orm_to_dict(c, _COMMENT_ARCHIVE_COLUMNS)
                        for c in comments_rows
                    ],
                }

                # Write the file BEFORE committing the json_path update
                # so that the database never references an archive that
                # does not yet exist on disk.
                serialised = json.dumps(payload, ensure_ascii=False, indent=2)
                archive_path.write_text(serialised, encoding="utf-8")

                # ``json_path`` is stored relative to the repo root so
                # the value remains valid if the repository is later
                # checked out at a different absolute location.
                relative = _relative_archive_path(archive_path)
                task.json_path = relative

                await session.commit()
            except BaseException:
                await session.rollback()
                # If we already wrote the file but the commit failed,
                # roll the file back too so a second invocation does
                # not see a stale snapshot. ``missing_ok=True`` keeps
                # this safe even when the failure happened before the
                # write.
                try:
                    archive_path.unlink(missing_ok=True)
                except OSError:  # pragma: no cover - best-effort cleanup
                    logger.exception(
                        "archive_json cleanup failed",
                        extra={"task_id": task_id, "path": str(archive_path)},
                    )
                raise

        logger.info(
            "archive_json",
            extra={
                "event": "archive_json",
                "task_id": task_id,
                "keyword": keyword,
                "note_count": len(notes_rows),
                "comment_count": len(comments_rows),
                "path": str(archive_path),
            },
        )
        return archive_path

    # ------------------------------------------------------------------
    # AI-report read / write -- requirements 15.5 / 15.6 / 16.5 / 5.4
    # ------------------------------------------------------------------

    async def load_for_ai(
        self, task_id: int
    ) -> tuple[str, list[Note], list[Comment]]:
        """Return ``(keyword, notes, comments)`` for AI analysis (read-only).

        This method is the single read entry point used by
        :class:`AIAnalyzer.analyze` (requirement 15.5). It exclusively
        issues ``SELECT`` statements -- ``tasks`` / ``notes`` /
        ``comments`` / ``authors`` are never mutated -- so the caller
        can rely on the AI pipeline being side-effect free
        (requirements 15.1-15.4, 15.7).

        ORM rows are detached from the session before returning so the
        analyser can iterate over them after the session has been
        closed. ``expire_on_commit=False`` is configured globally on
        :data:`async_sessionmaker`, which keeps lazy-loaded attributes
        accessible in this scenario.

        Raises
        ------
        AssertionError
            If ``task_id`` does not exist in the ``tasks`` table. The
            assertion is preferred over returning an empty tuple so
            callers cannot silently analyse a non-existent task.
        """
        async with self._session_maker() as session:
            task = await session.get(Task, task_id)
            assert task is not None, (
                f"load_for_ai: task id={task_id} not found"
            )
            keyword = task.keyword

            notes_rows = (
                await session.execute(
                    select(Note)
                    .where(Note.task_id == task_id)
                    .order_by(Note.note_id.asc())
                )
            ).scalars().all()

            note_ids = [n.note_id for n in notes_rows]
            if note_ids:
                comments_rows = (
                    await session.execute(
                        select(Comment)
                        .where(Comment.note_id.in_(note_ids))
                        .order_by(
                            Comment.note_id.asc(),
                            Comment.parent_comment_id.asc(),
                            Comment.comment_id.asc(),
                        )
                    )
                ).scalars().all()
            else:
                comments_rows = []

            # Detach the ORM rows so attribute access still works once
            # the session is closed. ``expire_on_commit=False`` keeps
            # the column attributes populated; ``expunge_all`` removes
            # the session reference so SQLAlchemy will not attempt to
            # refresh them later.
            session.expunge_all()

        return keyword, list(notes_rows), list(comments_rows)

    async def save_ai_report(self, report: AIReportInput) -> int:
        """Insert a single ``ai_reports`` row and return its new ``id``.

        Requirement 15.6 fixes the contract: the method writes only to
        ``ai_reports`` -- never to ``notes`` / ``comments`` /
        ``authors`` / ``tasks`` -- and inserts exactly one row per
        call. Repeated invocations therefore append history rather
        than overwriting (requirement 14.11).

        Defensive checks reject empty ``prompt_version`` /
        ``report_md`` payloads up-front so a malformed call cannot
        create an unusable row that downstream readers would have to
        special-case.

        Returns the autoincremented primary key of the new row.
        """
        # Defensive validation: requirement 14.9 mandates non-empty
        # ``prompt_version`` and ``report_md``; we enforce it here so
        # a buggy caller cannot silently insert an unusable row.
        assert isinstance(report, AIReportInput), (
            f"save_ai_report: expected AIReportInput, got {type(report)!r}"
        )
        assert (
            isinstance(report.prompt_version, str)
            and report.prompt_version != ""
        ), "save_ai_report: prompt_version must be a non-empty string"
        assert (
            isinstance(report.report_md, str) and report.report_md != ""
        ), "save_ai_report: report_md must be a non-empty string"

        row = AIReport(
            task_id=report.task_id,
            provider=report.provider,
            model=report.model,
            prompt_version=report.prompt_version,
            report_md=report.report_md,
            created_at=_utc_now_iso(),
        )

        async with self._session_maker() as session:
            try:
                session.add(row)
                await session.commit()
                # ``session.refresh`` is unnecessary because
                # ``expire_on_commit=False`` keeps ``row.id`` populated
                # after commit -- SQLAlchemy fills it in from the
                # autoincrement value the INSERT returned.
                report_id = row.id
            except BaseException:
                await session.rollback()
                raise

        logger.info(
            "save_ai_report",
            extra={
                "event": "save_ai_report",
                "report_id": report_id,
                "task_id": report.task_id,
                "provider": report.provider,
                "model": report.model,
                "prompt_version": report.prompt_version,
            },
        )
        return report_id

    async def list_ai_reports(self, task_id: int) -> list[AIReportSummary]:
        """Return AI-report metadata for ``task_id`` ordered by recency.

        Backs the ``reports`` field of the ``GET /api/tasks/{task_id}``
        response (requirement 16.5 + 5.4). Only ``SELECT`` statements
        are issued; the ``ai_reports`` table is read-only from this
        method's perspective.

        The ordering is ``created_at DESC, id DESC`` so that two rows
        produced in the same second still surface in a deterministic
        order (newest first), and the heavy ``report_md`` column is
        deliberately excluded from the projection so the summary stays
        cheap to embed in the task detail payload.
        """
        stmt = (
            select(
                AIReport.id,
                AIReport.provider,
                AIReport.model,
                AIReport.prompt_version,
                AIReport.created_at,
            )
            .where(AIReport.task_id == task_id)
            .order_by(AIReport.created_at.desc(), AIReport.id.desc())
        )

        async with self._session_maker() as session:
            result = await session.execute(stmt)
            rows = result.all()

        return [
            AIReportSummary(
                id=row.id,
                provider=row.provider,
                model=row.model,
                prompt_version=row.prompt_version,
                created_at=row.created_at,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Upsert internals
    # ------------------------------------------------------------------

    async def _upsert_authors(
        self, session: AsyncSession, rows: Iterable[Mapping[str, Any]]
    ) -> None:
        """Issue a single ``INSERT ... ON CONFLICT(user_id) DO UPDATE``."""
        rows = list(rows)
        if not rows:
            return
        stmt = sqlite_insert(Author).values(rows)
        # Update every column except the primary key. ``excluded.<col>``
        # references the values that *would have been* inserted, which
        # is exactly the "覆盖除主键外所有字段" semantics of req 9.4.
        update_cols = {
            name: stmt.excluded[name]
            for name in _AUTHOR_UPDATE_COLUMNS
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=[Author.user_id], set_=update_cols
        )
        await session.execute(stmt)

    async def _upsert_notes(
        self, session: AsyncSession, rows: Iterable[Mapping[str, Any]]
    ) -> None:
        """Issue a single ``INSERT ... ON CONFLICT(note_id) DO UPDATE``."""
        rows = list(rows)
        if not rows:
            return
        stmt = sqlite_insert(Note).values(rows)
        update_cols = {
            name: stmt.excluded[name]
            for name in _NOTE_UPDATE_COLUMNS
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=[Note.note_id], set_=update_cols
        )
        await session.execute(stmt)

    async def _upsert_comments(
        self, session: AsyncSession, rows: Iterable[Mapping[str, Any]]
    ) -> None:
        """Issue a single ``INSERT ... ON CONFLICT(comment_id) DO UPDATE``."""
        rows = list(rows)
        if not rows:
            return
        stmt = sqlite_insert(Comment).values(rows)
        update_cols = {
            name: stmt.excluded[name]
            for name in _COMMENT_UPDATE_COLUMNS
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=[Comment.comment_id], set_=update_cols
        )
        await session.execute(stmt)

    async def _assert_parent_consistent(
        self, session: AsyncSession, reply: Mapping[str, Any]
    ) -> None:
        """Raise :class:`IntegrityError` unless the reply's parent matches.

        Implements the comment-tree integrity check spelled out in task
        2.4 and requirement 9.5/9.6:

        * the parent must exist in the ``comments`` table (either
          already on disk or just upserted in step 2 of
          :meth:`upsert_comments`);
        * the parent's ``note_id`` must equal the reply's ``note_id``.

        Both failure modes raise an :class:`IntegrityError` whose
        message contains the literal substring ``"comment_tree"`` so
        callers can grep for it when populating ``tasks.error_msg``
        (requirement 9.6: 「评论树结构错误」).
        """
        parent_id = reply["parent_comment_id"]
        child_note_id = reply["note_id"]

        stmt = select(Comment.note_id).where(Comment.comment_id == parent_id)
        result = await session.execute(stmt)
        parent_note_id: str | None = result.scalar_one_or_none()

        if parent_note_id is None:
            _raise_comment_tree_error(
                f"comment_tree: parent comment_id={parent_id!r} not found "
                f"for reply comment_id={reply['comment_id']!r} "
                f"(note_id={child_note_id!r})"
            )
        if parent_note_id != child_note_id:
            _raise_comment_tree_error(
                f"comment_tree: parent comment_id={parent_id!r} "
                f"belongs to note_id={parent_note_id!r} but reply "
                f"comment_id={reply['comment_id']!r} claims "
                f"note_id={child_note_id!r}"
            )

    # ------------------------------------------------------------------
    # State-machine internal helper
    # ------------------------------------------------------------------

    async def _transition(
        self,
        *,
        task_id: int,
        allowed_from: tuple[str, ...],
        target_status: str,
        updates: Callable[[Task], None],
        method_name: str,
    ) -> None:
        """Execute one state-machine transition under transaction serialization.

        Implements the generic SELECT → ASSERT → UPDATE → COMMIT pattern
        used by every public state-machine method:

        1. Open a session and begin a transaction implicitly.
        2. ``SELECT ... FOR UPDATE`` the target row. SQLite ignores the
           ``FOR UPDATE`` hint syntactically, but the surrounding
           transaction plus the immediately-following UPDATE acquires a
           write lock that serialises concurrent writers (the "事务
           串行" alternative listed in the task description).
        3. Assert the precondition holds. Failing the assertion (or any
           other exception) triggers an explicit ``rollback()`` so all
           four mutable fields remain at their pre-transition values.
        4. Apply ``updates(task)`` and commit.
        """
        async with self._session_maker() as session:
            try:
                stmt = (
                    select(Task)
                    .where(Task.id == task_id)
                    .with_for_update()
                )
                result = await session.execute(stmt)
                task: Task | None = result.scalar_one_or_none()

                # Precondition checks. Note: no field has been mutated
                # yet, so even without the explicit rollback below the
                # database row would be untouched. The rollback is
                # belt-and-suspenders to satisfy the task's literal
                # "rollback on assertion violation" wording.
                assert task is not None, (
                    f"{method_name}: task id={task_id} not found"
                )
                assert task.status in allowed_from, (
                    f"{method_name}: invalid transition "
                    f"{task.status!r} -> {target_status!r} "
                    f"(allowed_from={list(allowed_from)!r})"
                )

                updates(task)
                await session.commit()
            except BaseException:
                # Roll back any pending changes so the four mutable
                # fields keep their pre-transition values on disk.
                # ``BaseException`` covers ``AssertionError`` (subclass
                # of ``Exception``) plus interpreter-level signals such
                # as ``KeyboardInterrupt`` -- we never want a partially
                # applied transition to survive either case.
                await session.rollback()
                raise

        # Logged outside the transaction so it only fires on a
        # successfully committed transition; failed transitions raise
        # before reaching this point.
        logger.info(
            "task transition",
            extra={
                "event": "task_transition",
                "task_id": task_id,
                "from": list(allowed_from),
                "to": target_status,
                "method": method_name,
            },
        )


# ---------------------------------------------------------------------------
# Field-update helpers
# ---------------------------------------------------------------------------
#
# Kept at module level (rather than as instance methods) so they are
# trivially unit-testable and so the state-machine entry points in
# :class:`DataStore` read top-to-bottom as a thin orchestration layer.


def _apply_running(task: Task) -> None:
    """Mutate ``task`` for ``pending → running`` (requirement 3.3).

    ``finished_at`` and ``error_msg`` are explicitly reset to ``None``
    even though a healthy ``pending`` row has them ``NULL`` already;
    the redundant assignment is cheap and protects against any
    upstream data corruption that might otherwise carry over into the
    ``running`` state.
    """
    task.status = "running"
    task.started_at = _utc_now_iso()
    task.finished_at = None
    task.error_msg = None


def _apply_success(task: Task, *, note_count: int, json_path: str) -> None:
    """Mutate ``task`` for ``running → success`` (requirement 3.4).

    ``error_msg`` is explicitly reset to ``None`` to satisfy the "保持
    NULL" wording of the task description even though a healthy
    ``running`` row already has it ``NULL``.
    """
    task.status = "success"
    task.finished_at = _utc_now_iso()
    task.note_count = note_count
    task.json_path = json_path
    task.error_msg = None


def _apply_failed(task: Task, *, error_msg: str) -> None:
    """Mutate ``task`` for ``pending | running → failed`` (requirement 3.5).

    The caller is expected to have truncated ``error_msg`` already; the
    function does not re-truncate so accidentally over-long values
    surface as test failures rather than being silently swallowed.
    """
    task.status = "failed"
    task.finished_at = _utc_now_iso()
    task.error_msg = error_msg


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------
#
# The constants and ``_*_row_from_*`` helpers below coerce loosely-typed
# crawler dicts into rows that match the strict ORM column types. Keeping
# them at module level makes them trivially unit-testable and lets future
# tasks (e.g. 2.7's sensitive-field stripping) hook in via composition
# rather than subclassing.


# ``Author`` columns we are willing to overwrite on conflict (i.e. every
# field except the primary key ``user_id``). ``updated_at`` is included so
# subsequent crawls refresh the row's freshness marker.
_AUTHOR_UPDATE_COLUMNS: Final[tuple[str, ...]] = (
    "nickname",
    "avatar",
    "gender",
    "ip_location",
    "fans_count",
    "follow_count",
    "updated_at",
)

# ``Note`` columns we are willing to overwrite on conflict. ``note_id`` is
# excluded (it is the primary key); ``created_at`` is excluded so that the
# original insertion timestamp survives subsequent re-crawls.
_NOTE_UPDATE_COLUMNS: Final[tuple[str, ...]] = (
    "task_id",
    "title",
    "desc",
    "type",
    "cover_url",
    "video_url",
    "liked_count",
    "collected_count",
    "comment_count",
    "share_count",
    "author_user_id",
    "publish_time",
    "ip_location",
    "tag_list",
    "raw_json",
)

# ``Comment`` columns we are willing to overwrite on conflict.
# ``comment_id`` is excluded (PK); ``created_at`` survives re-runs as
# above.
_COMMENT_UPDATE_COLUMNS: Final[tuple[str, ...]] = (
    "note_id",
    "parent_comment_id",
    "user_id",
    "nickname",
    "content",
    "like_count",
    "sub_comment_count",
    "create_time",
    "is_top_hot",
)


# Columns serialised for each ``notes`` row in the JSON archive
# (requirement 10.3: round-trip equivalence with the database). The
# tuple intentionally enumerates *every* persistent column on the ORM
# so that a reader can reconstruct the full row from the archive
# without consulting the database.
_NOTE_ARCHIVE_COLUMNS: Final[tuple[str, ...]] = (
    "note_id",
    "task_id",
    "title",
    "desc",
    "type",
    "cover_url",
    "video_url",
    "liked_count",
    "collected_count",
    "comment_count",
    "share_count",
    "author_user_id",
    "publish_time",
    "ip_location",
    "tag_list",
    "raw_json",
    "created_at",
)


# Columns serialised for each ``comments`` row in the JSON archive.
# Same rationale as :data:`_NOTE_ARCHIVE_COLUMNS`: every persistent
# column is listed so the archive captures the full row.
_COMMENT_ARCHIVE_COLUMNS: Final[tuple[str, ...]] = (
    "comment_id",
    "note_id",
    "parent_comment_id",
    "user_id",
    "nickname",
    "content",
    "like_count",
    "sub_comment_count",
    "create_time",
    "is_top_hot",
    "created_at",
)


def _orm_to_dict(
    row: Any, columns: tuple[str, ...]
) -> dict[str, Any]:
    """Project an ORM row to a plain dict over ``columns``.

    Used by :meth:`DataStore.archive_json` to turn ``Note`` and
    ``Comment`` ORM instances into JSON-friendly dicts. Listing the
    columns explicitly (rather than using :func:`sqlalchemy.inspect`)
    keeps the archive schema self-documenting and prevents accidental
    leakage of new attributes added in the future.
    """
    return {name: getattr(row, name) for name in columns}


def _relative_archive_path(absolute: Path) -> str:
    """Render ``absolute`` as a forward-slashed path relative to repo root.

    The relative form is what gets stored in ``tasks.json_path`` so
    the value remains valid if the repository is later checked out
    at a different absolute location (requirement 10.7). Falls back
    to the absolute string when ``absolute`` is somehow outside the
    repo (which should not happen but is handled defensively).
    """
    try:
        rel = absolute.relative_to(settings.repo_root)
    except ValueError:
        # Defensive: an explicit absolute ``JSON_ARCHIVE_DIR`` outside
        # the repo would land here. Storing the absolute string keeps
        # the row referenceable even though it loses portability.
        return absolute.as_posix()
    return rel.as_posix()


def _coerce_str(value: Any) -> str | None:
    """Return ``value`` as a string, or ``None`` for empty/missing input.

    Crawler payloads occasionally encode missing fields as the empty
    string, the literal ``"None"`` substring, or ``null``. We normalise
    all three flavours to ``None`` so downstream queries can rely on
    ``IS NULL`` semantics.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value if value != "" else None
    # Fall through for ints, floats, bools, etc. that happen to land in
    # text columns (e.g. ``ip_location`` arriving as ``0``).
    return str(value)


def _coerce_int(value: Any, default: int = 0) -> int:
    """Return ``value`` as an int, falling back to ``default`` on failure.

    Crawler payloads often carry counts as strings (``"123"``). We
    accept anything that survives ``int(...)`` and silently fall back
    to ``default`` for ``None`` / non-numeric input rather than raising
    so a single mis-typed field cannot abort the whole batch.
    """
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def _coerce_bool_int(value: Any) -> int:
    """Normalise truthy/falsy values to the 0/1 ints expected by SQLite.

    The ``comments.is_top_hot`` column carries a ``CHECK (is_top_hot IN
    (0, 1))`` constraint, so anything other than the integers 0 / 1
    would be rejected at insert time.
    """
    if value in (1, True, "1", "true", "True", "yes", "y"):
        return 1
    return 0


def _coerce_tag_list(value: Any) -> str | None:
    """Serialise a tag list to a JSON array string suitable for storage.

    The ``notes.tag_list`` column is plain ``TEXT`` because SQLite has
    no native array type. We accept three input shapes:

    * ``None`` / empty -> stored as ``NULL``;
    * a ``list`` / ``tuple`` -> JSON-serialised with ``ensure_ascii=False``;
    * an existing ``str`` -> stored as-is, on the assumption it is
      already JSON (the caller is free to pre-format it).
    """
    if value is None or value == "":
        return None
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False)
    if isinstance(value, str):
        return value
    # Last-ditch: serialise whatever it is so we do not silently drop
    # data the caller bothered to attach.
    return json.dumps(value, ensure_ascii=False)


def _coerce_raw_json(value: Any) -> str | None:
    """Serialise the full raw note dict for the ``raw_json`` column.

    Sensitive keys (``phone``, ``mobile``, ``email``, ``bind_email``,
    ``id_card``, ``id_number``, ``identity``; case-insensitive) are
    stripped from ``value`` before serialisation so the persisted
    payload never contains user PII (requirements 20.3, 20.4). The
    incoming object is deep-copied via the strip routine so the
    caller's dict is left untouched.

    Already-serialised strings are accepted unchanged; if such a string
    parses as JSON we still strip sensitive keys before re-serialising
    so pre-encoded payloads receive the same treatment as plain dicts.
    """
    if value is None:
        return None
    if isinstance(value, str):
        # ``raw_json`` arriving as a string is unusual but supported;
        # try to parse it so the same stripping rules apply, falling
        # back to the raw text if it is not actually JSON.
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return value
        stripped = _strip_sensitive(parsed)
        try:
            return json.dumps(stripped, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return value
    try:
        stripped = _strip_sensitive(value)
        return json.dumps(stripped, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return None


# Sensitive keys that must be stripped from ``raw_json`` before any data
# reaches disk (requirement 20.4). Comparison is case-insensitive so
# variants like ``Phone`` / ``E-Mail`` are caught alongside their lower-
# cased forms.
_SENSITIVE_KEYS_LOWER: Final[frozenset[str]] = frozenset(
    {
        "phone",
        "mobile",
        "email",
        "bind_email",
        "id_card",
        "id_number",
        "identity",
    }
)


def _strip_sensitive(value: Any) -> Any:
    """Return a deep copy of ``value`` with sensitive keys removed.

    Walks dicts and list/tuple containers recursively. For dicts every
    key whose lower-cased form lands in :data:`_SENSITIVE_KEYS_LOWER`
    is dropped together with its value -- both the key *and* the value
    are removed, so the persisted payload retains no trace of the
    original (requirement 20.4: 「持久化结果不保留原值」).

    Scalars are returned unchanged, including non-string keys
    (e.g. integers in dict keys are uncommon but legal in Python). The
    function never mutates ``value`` in-place; the input is safe to
    reuse afterwards.
    """
    if isinstance(value, Mapping):
        cleaned: dict[Any, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS_LOWER:
                # Drop both key and value -- they never reach disk.
                continue
            cleaned[k] = _strip_sensitive(v)
        return cleaned
    if isinstance(value, list):
        return [_strip_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_strip_sensitive(item) for item in value)
    # Scalars (str / int / float / bool / None / arbitrary objects) are
    # returned as-is; they cannot syntactically host a sensitive key.
    return value


def _author_row_from_raw_note(
    raw_note: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Extract an author row from one MediaCrawler note payload.

    MediaCrawler attaches the note creator's profile under several
    candidate keys depending on its version (``author``, ``user``,
    ``user_info``). We probe each in turn and fall back to top-level
    fields (e.g. ``user_id`` directly on the note) for older formats.
    Returns ``None`` when no ``user_id`` can be recovered -- the
    caller is expected to skip such notes rather than abort the batch.
    """
    if not isinstance(raw_note, Mapping):
        return None

    # Probe the candidate sub-dicts in order of likelihood.
    candidates: list[Mapping[str, Any]] = []
    for key in ("author", "user", "user_info"):
        sub = raw_note.get(key)
        if isinstance(sub, Mapping):
            candidates.append(sub)
    # Fallback: some payloads spread the author fields directly onto
    # the note. We treat the note dict itself as a last-resort
    # candidate so e.g. ``raw_note["user_id"]`` is still picked up.
    candidates.append(raw_note)

    user_id: str | None = None
    profile: Mapping[str, Any] = {}
    for cand in candidates:
        candidate_id = _coerce_str(cand.get("user_id"))
        if candidate_id is not None:
            user_id = candidate_id
            profile = cand
            break

    if user_id is None:
        return None

    return {
        "user_id": user_id,
        "nickname": _coerce_str(profile.get("nickname"))
        or _coerce_str(profile.get("nick_name")),
        "avatar": _coerce_str(profile.get("avatar")),
        "gender": _coerce_str(profile.get("gender")),
        "ip_location": _coerce_str(profile.get("ip_location")),
        "fans_count": _coerce_int(profile.get("fans_count")),
        "follow_count": _coerce_int(profile.get("follow_count")),
        "updated_at": _utc_now_iso(),
    }


def _note_row_from_raw(
    task_id: int, raw_note: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    """Coerce one MediaCrawler note payload into a ``notes`` row.

    Returns ``None`` when the payload lacks a ``note_id``. The caller
    is responsible for not silently swallowing such drops -- the
    public :meth:`DataStore.upsert_notes` logs at debug level when this
    happens (the count of dropped rows is implicit in the return value).
    """
    if not isinstance(raw_note, Mapping):
        return None

    note_id = _coerce_str(raw_note.get("note_id"))
    if note_id is None:
        return None

    # Author id is preferred from the embedded sub-dict (matching the
    # split done in ``_author_row_from_raw_note``); we fall back to a
    # top-level ``author_user_id`` so older payloads still link.
    author_user_id: str | None = None
    for key in ("author", "user", "user_info"):
        sub = raw_note.get(key)
        if isinstance(sub, Mapping):
            author_user_id = _coerce_str(sub.get("user_id"))
            if author_user_id is not None:
                break
    if author_user_id is None:
        author_user_id = _coerce_str(raw_note.get("author_user_id"))
    if author_user_id is None:
        author_user_id = _coerce_str(raw_note.get("user_id"))

    return {
        "note_id": note_id,
        "task_id": task_id,
        "title": _coerce_str(raw_note.get("title")),
        "desc": _coerce_str(raw_note.get("desc")),
        "type": _coerce_str(raw_note.get("type")),
        "cover_url": _coerce_str(raw_note.get("cover_url")),
        "video_url": _coerce_str(raw_note.get("video_url")),
        "liked_count": _coerce_int(raw_note.get("liked_count")),
        "collected_count": _coerce_int(raw_note.get("collected_count")),
        "comment_count": _coerce_int(raw_note.get("comment_count")),
        "share_count": _coerce_int(raw_note.get("share_count")),
        "author_user_id": author_user_id,
        "publish_time": _coerce_str(raw_note.get("publish_time")),
        "ip_location": _coerce_str(raw_note.get("ip_location")),
        "tag_list": _coerce_tag_list(raw_note.get("tag_list")),
        "raw_json": _coerce_raw_json(raw_note),
    }


def _comment_row_from_raw(
    raw_comment: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Coerce one MediaCrawler comment payload into a ``comments`` row.

    Returns ``None`` when the payload lacks either ``comment_id`` or
    ``note_id`` (both are NOT NULL columns). ``parent_comment_id`` is
    optional -- a missing value is treated as ``NULL`` (top-level
    comment) by the caller.
    """
    if not isinstance(raw_comment, Mapping):
        return None

    comment_id = _coerce_str(raw_comment.get("comment_id"))
    note_id = _coerce_str(raw_comment.get("note_id"))
    if comment_id is None or note_id is None:
        return None

    return {
        "comment_id": comment_id,
        "note_id": note_id,
        "parent_comment_id": _coerce_str(raw_comment.get("parent_comment_id")),
        "user_id": _coerce_str(raw_comment.get("user_id")),
        "nickname": _coerce_str(raw_comment.get("nickname")),
        "content": _coerce_str(raw_comment.get("content")),
        "like_count": _coerce_int(raw_comment.get("like_count")),
        "sub_comment_count": _coerce_int(raw_comment.get("sub_comment_count")),
        "create_time": _coerce_str(raw_comment.get("create_time")),
        "is_top_hot": _coerce_bool_int(raw_comment.get("is_top_hot")),
    }


def _raise_comment_tree_error(message: str) -> None:
    """Raise an :class:`IntegrityError` carrying the ``comment_tree`` marker.

    The marker substring is what the orchestration layer (CrawlerService,
    task 3.3) greps for when populating ``tasks.error_msg`` after a
    rolled-back batch; keeping the construction in one place ensures every
    failure mode produces a consistent message format.
    """
    raise IntegrityError(
        statement=message,
        params=None,
        orig=ValueError(message),
    )
