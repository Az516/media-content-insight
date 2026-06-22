"""CrawlerService -- thin wrapper around the MediaCrawler subprocess.

This module owns the launching and lifecycle management of the
MediaCrawler subprocess that produces the raw notes / comments fed
into :mod:`app.services.data_store`. It is split into a small number
of cohesive pieces so that each task in the M2 milestone can land
independently:

* Module-level exceptions (:class:`CrawlerError`,
  :class:`LoginExpiredError`, :class:`RiskControlError`) describe the
  failure modes downstream callers must distinguish (requirements
  6.6, 8.1, 8.2, 8.3, 8.4).
* :class:`CrawlResult` is the success-path return type carried
  through :meth:`CrawlerService.run_keyword_search` (task 3.3, future
  work).
* :class:`SubprocessOutcome` is the internal hand-off type produced
  by :meth:`CrawlerService._invoke_subprocess` (this task, 3.1) and
  consumed by the error-classification + read-output logic in tasks
  3.2 / 3.3.
* :meth:`CrawlerService._invoke_subprocess` wraps
  ``asyncio.create_subprocess_exec`` with the start-up validation and
  timeout-with-kill semantics mandated by requirements 6.3 / 6.4 /
  6.5 / 6.6 / 8.3 / 19.2.

What is intentionally NOT in this task
--------------------------------------

The error classification (login / risk / verify), the read-back of
MediaCrawler's on-disk output, and the orchestration of the full
``run_keyword_search`` lifecycle land in tasks 3.2 and 3.3. The dataclass
hand-off (:class:`SubprocessOutcome`) is shaped to make that follow-on
work a one-liner: tasks 3.2 / 3.3 only need to inspect ``returncode``
/ ``stderr_bytes`` and call ``_read_mc_output(raw_dir)`` to decode
MediaCrawler's on-disk output.

Compliance notes
----------------

* The implementation never writes to or deletes any file inside
  ``third_party/MediaCrawler``. The MediaCrawler subprocess itself is
  free to manage its own state under that directory; this service is
  read-only against the submodule (requirements 6.5, 19.2).
* Subprocess command lines are emitted through the structured logger
  so the audit trail records exactly which arguments were dispatched.
  The only configuration we expose at this layer is the ``keyword``,
  ``max_notes``, and the interpreter path -- API keys live in
  :mod:`app.services.ai_analyzer`, not here, so there are no secrets
  to redact in the spawn log line.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Optional

from app.core.config import settings
from app.core.logger import audit_logger, logger
from app.models import Task
from app.services.data_store import (
    DataStore,
    _normalise_comment_row,
    _normalise_note_row,
)


# ---------------------------------------------------------------------------
# Module-level exceptions
# ---------------------------------------------------------------------------


class CrawlerError(Exception):
    """Base class for any failure originating in :mod:`crawler_service`.

    The string form of the exception is what eventually lands in
    ``tasks.error_msg`` after the orchestration layer in task 3.3
    prefixes it with the appropriate classification token (requirement
    8.4: ``error_msg = "unexpected: <stderr[:500]>"`` for the
    catch-all path).
    """


class LoginExpiredError(CrawlerError):
    """MediaCrawler exited because its login cookie was rejected.

    Raised in task 3.2 when the subprocess stderr contains the literal
    substring ``"login"`` (case-insensitive). Used by task 3.3 to
    populate ``error_msg = "login_expired: ..."`` per requirement 8.1.
    Defined here in task 3.1 for module self-containment so 3.2 can
    import it without introducing a new module.
    """


class RiskControlError(CrawlerError):
    """MediaCrawler exited because the platform tripped its risk control.

    Raised in task 3.2 when stderr contains ``"risk"`` or ``"verify"``
    (case-insensitive). Mapped to ``error_msg = "risk_control: ..."``
    by task 3.3 (requirement 8.2). The system MUST NOT auto-retry on
    this failure mode (requirement 8.5); see task 3.5 for the matching
    test.
    """


# ---------------------------------------------------------------------------
# Public success-path result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CrawlResult:
    """Outcome returned by :meth:`CrawlerService.run_keyword_search` on success.

    ``error_msg`` is reserved for callers who choose to surface a
    non-fatal warning alongside an otherwise-successful crawl; the
    happy path leaves it ``None``. The remaining fields map 1:1 to
    the ``tasks`` columns updated by
    :meth:`DataStore.mark_task_success` (requirements 7.5, 7.7).
    """

    task_id: int
    note_count: int
    json_path: str
    error_msg: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal hand-off type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubprocessOutcome:
    """Internal payload handed from :meth:`_invoke_subprocess` to its callers.

    Tasks 3.2 / 3.3 inspect ``returncode`` / ``stderr_bytes`` to
    classify failures and pass ``raw_dir`` to ``_read_mc_output`` to
    decode the on-disk MediaCrawler output. Keeping the shape small
    and frozen makes the hand-off contract obvious and prevents
    accidental mutation downstream.

    Notes
    -----
    ``raw_dir`` is provided regardless of ``returncode`` so a caller
    classifying a non-zero exit can still inspect any partial output
    MediaCrawler may have left behind for diagnostics. This service
    does not itself read or write that directory -- requirement 6.5
    forbids any write inside ``third_party/MediaCrawler``.
    """

    returncode: int
    stdout_bytes: bytes
    stderr_bytes: bytes
    raw_dir: Path
    started_ms: int


# ---------------------------------------------------------------------------
# CrawlerService
# ---------------------------------------------------------------------------


#: Time we are willing to wait for the OS to actually release a killed
#: subprocess. Requirement 8.3 mandates "10 秒内子进程释放".
_KILL_WAIT_SECONDS: Final[int] = 10

SUPPORTED_CRAWL_PLATFORMS: Final[tuple[str, ...]] = (
    "xhs",
    "dy",
    "ks",
    "bili",
    "wb",
    "tieba",
    "zhihu",
)

_PLATFORM_NOTE_TABLES: Final[dict[str, tuple[str, ...]]] = {
    "xhs": ("xhs_note", "xhs_note_content", "xhs_search_note", "note", "contents", "notes"),
    "dy": ("douyin_aweme",),
    "bili": ("bilibili_video",),
    "ks": ("kuaishou_video",),
    "wb": ("weibo_note",),
    "tieba": ("tieba_note",),
    "zhihu": ("zhihu_content",),
}

_PLATFORM_COMMENT_TABLES: Final[dict[str, tuple[str, ...]]] = {
    "xhs": ("xhs_note_comment", "xhs_comment", "comment", "comments"),
    "dy": ("douyin_aweme_comment",),
    "bili": ("bilibili_video_comment",),
    "ks": ("kuaishou_video_comment",),
    "wb": ("weibo_note_comment",),
    "tieba": ("tieba_comment",),
    "zhihu": ("zhihu_comment",),
}


def normalise_platform(value: str | None) -> str:
    """Return a supported MediaCrawler platform key or raise CrawlerError."""
    platform = (value or "xhs").strip().lower()
    aliases = {
        "douyin": "dy",
        "bilibili": "bili",
        "weibo": "wb",
        "kuaishou": "ks",
    }
    platform = aliases.get(platform, platform)
    if platform not in SUPPORTED_CRAWL_PLATFORMS:
        supported = ", ".join(SUPPORTED_CRAWL_PLATFORMS)
        raise CrawlerError(f"unsupported_platform: {platform}; supported: {supported}")
    return platform


class CrawlerService:
    """Wraps the MediaCrawler subprocess and the surrounding lifecycle.

    Only :meth:`_invoke_subprocess` is implemented in task 3.1. The
    public entry point :meth:`run_keyword_search` and the error
    classification helpers / on-disk reader land in tasks 3.2 and 3.3
    respectively. The constructor and instance attributes are designed
    to support both sets of tasks so later work only needs to add
    methods on this class.
    """

    def __init__(self, store: DataStore) -> None:
        self.store = store
        # Resolve once at construction time so repeated invocations
        # do not re-stat ``settings`` on every call.
        # ``MEDIA_CRAWLER_ROOT`` is already an absolute, ``.resolve()``-d
        # ``Path`` thanks to ``Settings._resolve_paths``; we wrap it
        # in ``Path(...)`` to guard against accidental string overrides
        # in tests.
        self.mc_root: Path = Path(settings.MEDIA_CRAWLER_ROOT)
        self.mc_python: str = settings.MEDIA_CRAWLER_PYTHON
        self.timeout_s: int = settings.CRAWL_TIMEOUT_SECONDS

    # ------------------------------------------------------------------
    # Subprocess launch -- task 3.1
    # ------------------------------------------------------------------

    async def _invoke_subprocess(
        self,
        platform: str,
        keyword: str,
        max_notes: int,
        max_comments_per_note: int,
    ) -> SubprocessOutcome:
        """Launch the MediaCrawler subprocess and wait for it to finish.

        The flow is:

        1. **Pre-flight validation** (requirement 6.6). Resolve
           :data:`mc_root` to an absolute path and assert that it
           exists, is a directory, and contains a ``main.py`` file. If
           any of those fail we raise
           :class:`CrawlerError` with the literal message
           ``"media_crawler_not_ready"`` so the orchestration layer
           in task 3.3 can flip the task to ``failed`` with the
           expected ``error_msg`` prefix.
        2. **Spawn** the subprocess via
           ``asyncio.create_subprocess_exec`` with the exact argv
           prescribed by requirement 6.4 (``--platform xhs --type
           search --keywords <keyword> --save_data_option db
           --get_comment yes --get_sub_comment yes --max_notes
           <max_notes>``). ``cwd`` is set to the absolute submodule
           path (requirement 6.3) so MediaCrawler's relative imports
           and config files resolve correctly.
        3. **Wait with timeout** (requirements 6.5, 8.3). Wrap
           ``proc.communicate()`` in
           ``asyncio.wait_for(..., timeout=self.timeout_s)``. On
           :class:`asyncio.TimeoutError` we kill the subprocess, give
           it up to :data:`_KILL_WAIT_SECONDS` (10 s) to release, and
           re-raise the original timeout so callers in task 3.3 can
           map it to ``error_msg = "timeout"``.

        Returns a :class:`SubprocessOutcome` carrying the raw stdout
        / stderr bytes plus the directory MediaCrawler writes its
        output into (``mc_root / "data" / "xhs"`` per design §4.1).
        This service never writes or deletes inside that directory
        itself -- MediaCrawler owns its own outputs (requirement 6.5).
        """
        # ---- 1) Pre-flight validation --------------------------------
        # Resolve to an absolute path explicitly even though
        # ``settings`` already does so; this both protects against
        # test-time overrides that may pass a relative ``Path`` and
        # produces a clean canonical ``cwd`` argument for
        # ``create_subprocess_exec``.
        mc_root = self.mc_root.resolve()
        main_py = mc_root / "main.py"
        if not (mc_root.exists() and mc_root.is_dir() and main_py.exists()):
            # Log a single line carrying every fact a developer needs
            # to diagnose the failure (path, exists / is-dir / has-
            # main.py flags). The exception message is intentionally
            # the bare token so callers can do a literal string match
            # without having to parse a sentence.
            logger.error(
                "MediaCrawler submodule not ready",
                extra={
                    "event": "mc_not_ready",
                    "mc_root": str(mc_root),
                    "mc_root_exists": mc_root.exists(),
                    "mc_root_is_dir": (
                        mc_root.is_dir() if mc_root.exists() else False
                    ),
                    "main_py_exists": main_py.exists(),
                },
            )
            raise CrawlerError("media_crawler_not_ready")

        # MediaCrawler sqlite backend stores rows in
        # ``<mc_root>/database/sqlite_tables.db``. Bootstrap schema on
        # first use so crawl runs do not fail on an empty database file.
        sqlite_db = mc_root / "database" / "sqlite_tables.db"
        if (not sqlite_db.exists()) or sqlite_db.stat().st_size == 0:
            init_cmd = [self.mc_python, "main.py", "--init_db", "sqlite"]
            logger.info(
                "initialize MediaCrawler sqlite schema",
                extra={
                    "event": "mc_init_sqlite",
                    "cmd": init_cmd,
                    "cwd": str(mc_root),
                },
            )
            init_proc = await asyncio.create_subprocess_exec(
                *init_cmd,
                cwd=str(mc_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            init_stdout, init_stderr = await init_proc.communicate()
            if init_proc.returncode != 0:
                init_tail = (init_stderr or b"").decode(
                    "utf-8", errors="ignore"
                )[-_STDERR_MAX_CHARS:]
                raise CrawlerError(
                    "unexpected: media_crawler_init_db_failed: " + init_tail
                )

        # ---- 2) Build & spawn ---------------------------------------
        crawl_started_ms = int(time.time() * 1000) - 5_000
        cmd: list[str] = [
            self.mc_python,
            "main.py",
            "--platform", platform,
            "--lt", settings.MEDIA_CRAWLER_LOGIN_TYPE,
            "--type", "search",
            "--keywords", keyword,
            # MediaCrawler "db" means MySQL. We need local SQLite output
            # for the backend readback path, so force "sqlite" here.
            "--save_data_option", "sqlite",
            "--get_comment", "yes",
            "--get_sub_comment", "yes",
            # Keep crawl latency bounded so the task can reach a
            # terminal state quickly in local-dev runs.
            "--max_comments_count_singlenotes", str(max_comments_per_note),
            "--max_concurrency_num", "2",
        ]
        if settings.MEDIA_CRAWLER_COOKIES.strip():
            cmd.extend(["--cookies", settings.MEDIA_CRAWLER_COOKIES])

        logger.info(
            "spawn MediaCrawler subprocess",
            extra={
                "event": "mc_spawn",
                "cmd": _redact_command(cmd),
                "cwd": str(mc_root),
                "timeout_s": self.timeout_s,
            },
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(mc_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # ---- 3) Wait with timeout -----------------------------------
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout_s
            )
        except asyncio.TimeoutError:
            # Kill the subprocess and wait for the OS to actually
            # release it. Requirement 8.3 caps that wait at 10
            # seconds; if the kill itself somehow times out we log
            # and swallow the secondary timeout because re-raising
            # it would mask the original timeout context the caller
            # cares about.
            logger.warning(
                "MediaCrawler subprocess timed out, killing",
                extra={
                    "event": "mc_timeout",
                    "timeout_s": self.timeout_s,
                    "pid": proc.pid,
                },
            )
            proc.kill()
            try:
                await asyncio.wait_for(
                    proc.wait(), timeout=_KILL_WAIT_SECONDS
                )
            except asyncio.TimeoutError:
                # Defensive: requirement 8.3 says "确保 10 秒内子进程
                # 释放". If it still does not release we log and
                # continue so the original ``TimeoutError`` (the one
                # the caller actually wants to handle) propagates
                # unmodified.
                logger.error(
                    "MediaCrawler subprocess did not release within kill window",
                    extra={
                        "event": "mc_kill_timeout",
                        "kill_window_s": _KILL_WAIT_SECONDS,
                        "pid": proc.pid,
                    },
                )
            # Re-raise the original timeout so callers can map it to
            # ``error_msg = "timeout"`` per requirement 8.3.
            raise

        # ---- 4) Hand off to the next stage (tasks 3.2 / 3.3) --------
        # MediaCrawler sqlite output resides in ``<cwd>/database``.
        raw_dir = mc_root / "database"

        logger.info(
            "MediaCrawler subprocess finished",
            extra={
                "event": "mc_finished",
                "returncode": proc.returncode,
                "stdout_len": len(stdout_bytes or b""),
                "stderr_len": len(stderr_bytes or b""),
                "raw_dir": str(raw_dir),
            },
        )

        # ``proc.returncode`` is guaranteed non-None after a clean
        # ``communicate()``; the conditional below keeps the runtime
        # behaviour well-defined even in the (logically impossible)
        # case where ``returncode`` is somehow still ``None``.
        return SubprocessOutcome(
            returncode=proc.returncode if proc.returncode is not None else -1,
            stdout_bytes=stdout_bytes or b"",
            stderr_bytes=stderr_bytes or b"",
            raw_dir=raw_dir,
            started_ms=crawl_started_ms,
        )

    # ------------------------------------------------------------------
    # Error classification + on-disk read -- task 3.2
    # ------------------------------------------------------------------

    def _classify_subprocess_failure(
        self, outcome: SubprocessOutcome
    ) -> None:
        """Map a non-zero ``outcome`` to the matching exception class.

        Returns silently when ``outcome.returncode == 0``. Otherwise
        decodes ``outcome.stderr_bytes`` (``errors="ignore"`` so a
        malformed byte sequence cannot demote a clean classification
        to the catch-all branch), keeps the first
        :data:`_STDERR_MAX_CHARS` characters as the message body, and
        raises one of:

        * :class:`LoginExpiredError` -- stderr contains ``"login"``
          (requirement 8.1; takes precedence over the risk tokens so
          a stderr that mentions both still routes to login).
        * :class:`RiskControlError` -- stderr contains ``"risk"`` or
          ``"verify"`` (requirement 8.2). Callers MUST NOT auto-retry
          on this exception (requirement 8.5).
        * :class:`CrawlerError` whose message is prefixed with the
          literal ``"unexpected: "`` -- the catch-all branch
          (requirement 8.4). The orchestration layer in task 3.3
          stores the exception message in ``tasks.error_msg``
          verbatim, so the prefix is materialised here rather than
          assembled twice.

        The body lives in the module-level
        :func:`_classify_subprocess_failure_inline` helper so the
        same logic is reachable from unit-test harnesses without
        instantiating :class:`CrawlerService`.
        """
        _classify_subprocess_failure_inline(outcome)

    async def _read_mc_output(
        self, raw_dir: Path,
        platform: str = "xhs",
        keyword: str | None = None,
        min_timestamp_ms: int | None = None,
    ) -> tuple[list[dict], list[dict]]:
        """Read MediaCrawler's on-disk output and apply requirement 13.5.

        The strategy is documented exhaustively on
        :func:`_read_mc_output_impl`; this method is just an async
        passthrough so the orchestration layer in task 3.3 can call
        it via ``await self._read_mc_output(raw_dir)`` matching the
        design §4.1 sketch.

        Returns ``([], [])`` when ``raw_dir`` is missing or contains
        neither the SQLite nor the JSON layouts MediaCrawler emits;
        the orchestrator interprets that as ``no_notes_returned``
        (requirement 7.9). All file IO is read-only -- SQLite is
        opened with ``mode=ro`` and JSON files are opened in plain
        text read mode -- so requirement 6.5 is upheld at the OS /
        library level rather than by convention.
        """
        return await _read_mc_output_impl(
            raw_dir,
            platform=platform,
            keyword=keyword,
            min_timestamp_ms=min_timestamp_ms,
        )

    # ------------------------------------------------------------------
    # Public entry point -- task 3.3
    # ------------------------------------------------------------------

    async def run_keyword_search(
        self,
        task_id: int,
        platform: str,
        keyword: str,
        max_notes: int = 20,
        max_comments_per_note: int = 20,
    ) -> CrawlResult:
        """Drive the full ``pending → success | failed`` task lifecycle.

        Implements the orchestration sketched in design §4.1:

        1. Flip ``tasks.status`` to ``running`` via
           :meth:`DataStore.mark_task_running`. Any pre-condition
           failure (task missing, not pending) propagates as
           :class:`AssertionError` so the API layer can surface a
           clean ``500`` and the row stays untouched (requirement
           3.2).
        2. Spawn the MediaCrawler subprocess
           (:meth:`_invoke_subprocess`) and translate its exit status
           through :meth:`_classify_subprocess_failure` -- this is
           where ``LoginExpiredError`` / ``RiskControlError`` /
           ``CrawlerError("unexpected: ...")`` originate.
        3. Read the on-disk output (:meth:`_read_mc_output`). When
           the read returns zero notes, route the task to ``failed``
           with ``error_msg = "no_notes_returned"`` and write the
           AuditLog (requirement 7.9). Notes / comments / authors /
           archive are deliberately **not** written in this branch
           so a "no result" run leaves the database byte-identical
           to its pre-run snapshot.
        4. Otherwise, in strict order: upsert authors → upsert
           notes (capped to ``min(len(raw_notes), max_notes)``) →
           upsert comments → archive JSON → ``mark_task_success``.
           This matches the dependency graph in requirement 7.3.
        5. Whatever path is taken, write a single AuditLog line at
           the terminal state carrying ``{keyword, started_at,
           finished_at, note_count, status}`` per requirement 20.5.

        Error handling
        --------------

        Each exception class maps to a specific ``error_msg`` prefix
        per requirements 8.1 - 8.4:

        * :class:`LoginExpiredError` → ``"login_expired: <e>"``
        * :class:`RiskControlError`  → ``"risk_control: <e>"``
          (no auto-retry, requirement 8.5)
        * :class:`asyncio.TimeoutError` → ``"timeout"``
          (requirement 8.3)
        * :class:`CrawlerError("media_crawler_not_ready")` → wrapped
          as ``"unexpected: media_crawler_not_ready"`` so the
          requirement 6.6 / 8.4 catch-all branch carries the
          mandated prefix.
        * :class:`CrawlerError("unexpected: ...")` from
          :meth:`_classify_subprocess_failure` is passed through
          verbatim (the prefix is already there).
        * Any other :class:`Exception` falls through to the
          catch-all and is stored as ``"unexpected: <e>"``
          truncated to 500 characters.

        On every error path we re-raise the original exception
        after recording it so the API layer's BackgroundTasks /
        logging machinery still sees the failure -- the
        orchestrator (`POST /api/tasks` background worker, task
        5.1) is the layer that decides whether to surface it to
        the client.

        Defensive transitions
        ---------------------

        ``mark_task_failed`` itself can raise (e.g. if the row was
        already moved to a terminal state by a parallel transition);
        we guard the call with :meth:`_safe_mark_failed` so that
        secondary failure cannot mask the original exception. The
        same defensive pattern guards the AuditLog write.
        """
        # Step 1: pending → running. We deliberately let any
        # ``AssertionError`` bubble unmodified -- it indicates a
        # programmer / API-layer bug (task not in ``pending``
        # state), not a runtime crawl failure, and the row remains
        # untouched on rejection (requirement 3.2).
        platform = normalise_platform(platform)
        await self.store.mark_task_running(task_id)

        try:
            # Step 2a: spawn MediaCrawler. Any pre-flight failure
            # surfaces as ``CrawlerError("media_crawler_not_ready")``
            # which is caught below; ``asyncio.TimeoutError`` from
            # ``asyncio.wait_for`` is handled by its dedicated
            # except branch.
            outcome = await self._invoke_subprocess(
                platform,
                keyword,
                max_notes,
                max_comments_per_note,
            )

            # Step 2b: translate non-zero exits into the right
            # exception subclass. A clean exit (returncode == 0)
            # returns silently.
            self._classify_subprocess_failure(outcome)

            # Step 3: read on-disk output. Read-only by construction.
            raw_notes, raw_comments = await self._read_mc_output(
                outcome.raw_dir,
                platform=platform,
                keyword=keyword,
                min_timestamp_ms=outcome.started_ms,
            )

            # Step 3a: requirement 7.9 -- a 0-return-code crawl
            # that produced no notes is treated as a soft failure.
            # We must NOT write any rows or generate the JSON
            # archive in this branch.
            if len(raw_notes) == 0:
                logger.warning(
                    "MediaCrawler returned zero notes",
                    extra={
                        "event": "mc_no_notes",
                        "task_id": task_id,
                        "platform": platform,
                        "keyword": keyword,
                    },
                )
                await self._safe_mark_failed(task_id, "no_notes_returned")
                await self._emit_audit_log(task_id, keyword, status="failed")
                return CrawlResult(
                    task_id=task_id,
                    note_count=0,
                    json_path="",
                    error_msg="no_notes_returned",
                )

            # Step 4: writes happen in the order required by
            # requirement 7.3 (authors → notes → comments →
            # archive). The slice math caps writes at ``max_notes``
            # even when MediaCrawler over-produces (requirements
            # 7.2, 7.6, 7.7).
            note_count = min(len(raw_notes), max_notes)
            effective_notes = raw_notes[:note_count]
            effective_comments = _filter_comments_for_effective_notes(
                raw_comments,
                effective_notes,
            )

            await self.store.upsert_authors_from_raw(effective_notes)
            await self.store.upsert_notes(task_id, effective_notes)
            await self.store.upsert_comments(effective_comments)
            await self.store.archive_json(task_id)

            # ``archive_json`` already wrote ``tasks.json_path`` to
            # the relative form; we recompute the same value here
            # for ``mark_task_success`` so the two updates agree
            # without an extra round-trip to read it back.
            json_path_relative = f"data/json/{task_id}.json"

            await self.store.mark_task_success(
                task_id=task_id,
                note_count=note_count,
                json_path=json_path_relative,
            )

            await self._emit_audit_log(task_id, keyword, status="success")

            logger.info(
                "crawl task completed",
                extra={
                    "event": "task_completed",
                    "task_id": task_id,
                    "keyword": keyword,
                    "platform": platform,
                    "note_count": note_count,
                    "json_path": json_path_relative,
                },
            )

            return CrawlResult(
                task_id=task_id,
                note_count=note_count,
                json_path=json_path_relative,
            )

        except LoginExpiredError:
            # Requirement 8.1: stderr contained ``"login"``. The
            # third-party traceback is rarely actionable for users, so
            # persist a stable remediation hint instead.
            error_msg = f"login_expired: {_LOGIN_EXPIRED_HINT}"
            await self._safe_mark_failed(task_id, error_msg)
            await self._emit_audit_log(task_id, keyword, status="failed")
            raise
        except RiskControlError as e:
            # Requirement 8.2 + 8.5: risk control / verify. The
            # NO-AUTO-RETRY contract is enforced by the structure
            # of this method -- ``_invoke_subprocess`` is called
            # exactly once and there is no surrounding loop.
            error_msg = f"risk_control: {str(e)[:_STDERR_MAX_CHARS]}"
            await self._safe_mark_failed(task_id, error_msg)
            await self._emit_audit_log(task_id, keyword, status="failed")
            raise
        except asyncio.TimeoutError:
            # Requirement 8.3: the spawn helper already killed the
            # subprocess; we just record the terminal state.
            await self._safe_mark_failed(task_id, "timeout")
            await self._emit_audit_log(task_id, keyword, status="failed")
            raise
        except CrawlerError as e:
            # Requirement 8.4 + 6.6: catch-all for any
            # ``CrawlerError`` raised by ``_invoke_subprocess`` or
            # ``_classify_subprocess_failure``. The two literal
            # message shapes we expect are:
            #   * ``"media_crawler_not_ready"`` (requirement 6.6)
            #   * ``"unexpected: <stderr[:500]>"`` (requirement 8.4)
            # Both must end up under the ``"unexpected: "`` prefix
            # in ``tasks.error_msg`` per requirement 8.4 wording
            # ("其他 → unexpected: ...").
            message = str(e)
            if message.startswith("unexpected:"):
                error_msg = message[:_STDERR_MAX_CHARS + len("unexpected: ")]
            else:
                # ``media_crawler_not_ready`` and any other
                # CrawlerError variants get the prefix attached.
                error_msg = f"unexpected: {message[:_STDERR_MAX_CHARS]}"
            await self._safe_mark_failed(task_id, error_msg)
            await self._emit_audit_log(task_id, keyword, status="failed")
            raise
        except Exception as e:
            # Final safety net for anything not classified above
            # (database errors, OS-level failures, etc.).
            logger.exception(
                "unexpected error during crawl",
                extra={
                    "event": "task_unexpected",
                    "task_id": task_id,
                    "keyword": keyword,
                },
            )
            error_msg = f"unexpected: {str(e)[:_STDERR_MAX_CHARS]}"
            await self._safe_mark_failed(task_id, error_msg)
            await self._emit_audit_log(task_id, keyword, status="failed")
            raise

    # ------------------------------------------------------------------
    # Defensive helpers used by ``run_keyword_search`` -- task 3.3
    # ------------------------------------------------------------------

    async def _safe_mark_failed(self, task_id: int, error_msg: str) -> None:
        """Best-effort wrapper around :meth:`DataStore.mark_task_failed`.

        ``mark_task_failed`` raises :class:`AssertionError` when the
        row is not in ``{pending, running}``. That can legitimately
        happen if a parallel transition (or a buggy caller) already
        moved the task to a terminal state. In that case we want to
        log and continue so the original exception we are unwinding
        from is not masked by a secondary assertion failure.
        """
        try:
            await self.store.mark_task_failed(task_id, error_msg)
        except Exception:
            # ``BaseException`` would also catch ``KeyboardInterrupt``;
            # we deliberately let that one through so a user-driven
            # cancel still aborts the process. Anything else (most
            # commonly ``AssertionError`` from the state-machine
            # precondition) is logged and swallowed.
            logger.exception(
                "secondary failure during mark_task_failed",
                extra={
                    "event": "mark_task_failed_secondary_error",
                    "task_id": task_id,
                    "error_msg": error_msg,
                },
            )

    async def _emit_audit_log(
        self,
        task_id: int,
        keyword: str,
        *,
        status: str,
    ) -> None:
        """Write the requirement 20.5 AuditLog line for ``task_id``.

        The five-tuple required by the spec is
        ``{keyword, started_at, finished_at, note_count, status}``
        with ISO-8601 timestamps at second precision. We read the
        actual ``started_at`` / ``finished_at`` / ``note_count``
        values straight off the ``tasks`` row so the log line
        matches the database state byte-for-byte rather than
        recomputing them.

        ``status`` MUST be one of ``{"success", "failed"}`` per
        requirement 20.5. We assert the constraint locally so a
        future refactor cannot silently broaden it.

        Failures inside this method are logged but never re-raised:
        AuditLog is observability infrastructure, and a logging
        failure should not cascade into a crawl failure that has
        otherwise completed cleanly.
        """
        assert status in ("success", "failed"), (
            f"_emit_audit_log: invalid status {status!r}"
        )
        try:
            async with self.store.session() as session:
                task = await session.get(Task, task_id)
                if task is None:
                    logger.warning(
                        "audit log skipped: task not found",
                        extra={
                            "event": "audit_log_skip",
                            "task_id": task_id,
                            "status": status,
                        },
                    )
                    return
                started_at = task.started_at
                finished_at = task.finished_at
                note_count = task.note_count
                row_keyword = task.keyword

            # The keyword on the task row is the source of truth;
            # we still pass through ``keyword`` from the caller
            # because tests may stub the row, but we prefer the
            # persisted value when present.
            audit_logger.info(
                "task_done",
                extra={
                    "channel": "AuditLog",
                    "event": "task_done",
                    "task_id": task_id,
                    "keyword": row_keyword if row_keyword else keyword,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "note_count": note_count,
                    "status": status,
                },
            )
        except Exception:
            logger.exception(
                "audit log emission failed",
                extra={
                    "event": "audit_log_error",
                    "task_id": task_id,
                    "status": status,
                },
            )


# ---------------------------------------------------------------------------
# Constants for error classification & MediaCrawler output reading -- task 3.2
# ---------------------------------------------------------------------------
#
# Requirement 8.1 / 8.2 / 8.4 specify the trio of stderr substrings that
# carve up the failure space and the prefix the resulting ``error_msg``
# carries. The spec also mandates the message be the first 500 stderr
# characters, so we centralise both numbers as named constants.

#: Maximum number of stderr characters retained for ``tasks.error_msg``
#: (requirements 8.1, 8.2, 8.4: ``stderr[:500]``).
_STDERR_MAX_CHARS: Final[int] = 500
_LOGIN_EXPIRED_HINT: Final[str] = (
    "小红书登录态失效或未配置 Cookie，请在 backend/.env 填写 "
    "MEDIA_CRAWLER_COOKIES 后重启后端。"
)

#: Substrings (case-insensitive) used to classify a non-zero exit. Order
#: matters: requirement 8.1 prioritises ``"login"`` over the risk/verify
#: tokens, so a stderr payload that happens to contain both is mapped to
#: :class:`LoginExpiredError`. Requirement 8.2 then catches ``"risk"`` or
#: ``"verify"``.
_LOGIN_TOKEN: Final[str] = "login"
_RISK_TOKENS: Final[tuple[str, ...]] = ("risk", "verify")

#: SQLite filename probed inside ``raw_dir`` for the notes table. Newer
#: MediaCrawler builds emit one ``contents.db`` and one ``comments.db``;
#: older builds emit a single combined sqlite. We try both layouts.
_CONTENTS_DB_NAMES: Final[tuple[str, ...]] = (
    "contents.db",
    "xhs_contents.db",
    "sqlite_tables.db",
)
_COMMENTS_DB_NAMES: Final[tuple[str, ...]] = (
    "comments.db",
    "xhs_comments.db",
    "sqlite_tables.db",
)

#: JSON filename candidates tried when ``raw_dir`` does not contain a
#: SQLite file. We accept several spellings because MediaCrawler's
#: ``json`` storage backend has used different layouts over time.
_NOTE_JSON_NAMES: Final[tuple[str, ...]] = (
    "raw_notes.json",
    "notes.json",
    "contents.json",
    "search_contents.json",
)
_COMMENT_JSON_NAMES: Final[tuple[str, ...]] = (
    "raw_comments.json",
    "comments.json",
    "search_comments.json",
)


# ---------------------------------------------------------------------------
# Module-level helpers backing the task-3.2 methods on CrawlerService
# ---------------------------------------------------------------------------
#
# Both :meth:`CrawlerService._classify_subprocess_failure` and
# :meth:`CrawlerService._read_mc_output` delegate to the helpers in
# this section. Keeping the bodies at module scope makes them
# trivially unit-testable in isolation (a future test harness can call
# the helpers directly without standing up a :class:`CrawlerService`)
# and prevents the class definition from dragging the SQLite probing
# logic, table-name whitelists, and JSON fallback heuristics inline
# with the high-level lifecycle code.


def _classify_subprocess_failure_inline(
    outcome: SubprocessOutcome,
) -> None:
    """Module-level shim used by :meth:`CrawlerService._classify_subprocess_failure`.

    Implementing the body once at module scope lets us share the logic
    with future call sites (e.g. unit-test harnesses that want to drive
    the classifier without instantiating :class:`CrawlerService`)
    without duplicating the substring tables.
    """
    if outcome.returncode == 0:
        return

    # Requirement 8.1 / 8.2: decode stderr with ``errors="ignore"`` so a
    # malformed byte stream cannot mask the classification (we do not
    # want a single invalid UTF-8 sequence to demote a clean
    # "login expired" message to the catch-all branch). The full
    # decoded string drives matching (requirement 8.1 reads "stderr
    # 忽略大小写 包含 login" against the entire stderr); the first 500
    # characters become the exception message body that downstream
    # callers store in ``tasks.error_msg`` (requirements 8.1 / 8.2 /
    # 8.4 all say ``error_msg = "<prefix>: <stderr[:500]>"``).
    stderr_text = (outcome.stderr_bytes or b"").decode(
        "utf-8", errors="ignore"
    )
    # Keep the tail instead of the head: MediaCrawler prints a lot of
    # progress logs first and the actionable traceback near the end.
    stderr_excerpt = stderr_text[-_STDERR_MAX_CHARS:]
    lowered_full = stderr_text.lower()

    # Avoid false positives from benign log lines like "check login state"
    # while still catching real unauthenticated states.
    login_markers = (
        "login state result: false",
        "please login",
        "login required",
        "cookie expired",
        "未登录",
        "登录失效",
    )
    if any(marker in lowered_full for marker in login_markers):
        # Requirement 8.1: stderr containing ``"login"`` (case-insensitive)
        # is unambiguously a stale cookie / expired session.
        raise LoginExpiredError(stderr_excerpt)

    if any(token in lowered_full for token in _RISK_TOKENS):
        # Requirement 8.2: ``"risk"`` or ``"verify"`` indicates the
        # platform tripped its risk control. The orchestrator must NOT
        # auto-retry (requirement 8.5).
        raise RiskControlError(stderr_excerpt)

    # Requirement 8.4 catch-all. The orchestration layer prefixes the
    # resulting message with ``"unexpected: "`` itself, so we encode
    # the prefix in the exception message here too -- task 3.3 wants
    # ``error_msg = "unexpected: <stderr[:500]>"`` and surfacing the
    # prefix at this layer keeps that mapping a literal pass-through.
    raise CrawlerError("unexpected: " + stderr_excerpt)


def _select_first_table(
    conn: sqlite3.Connection, whitelist: tuple[str, ...]
) -> str | None:
    """Return the first whitelist entry that exists as a table in ``conn``.

    Implementation note: we query ``sqlite_master`` rather than relying
    on PRAGMA so the lookup remains compatible with the read-only
    connection mode (PRAGMA writes are forbidden when the database is
    opened with ``mode=ro``).
    """
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    available = {row[0] for row in cursor.fetchall()}
    for candidate in whitelist:
        if candidate in available:
            return candidate
    return None


def _open_sqlite_readonly(path: Path) -> sqlite3.Connection:
    """Open ``path`` in SQLite's URI read-only mode.

    Uses the ``file:...?mode=ro`` URI form so the database engine
    rejects any accidental write attempt with ``SQLITE_READONLY``. The
    immutable=1 flag is deliberately omitted -- the file may legitimately
    be replaced by MediaCrawler between runs, and the ``ro`` mode alone
    already prevents this process from mutating it.

    The helper exists so the two places that probe SQLite files
    (``contents`` + ``comments``) share the same compliance-relevant
    flags. Requirement 6.5 forbids any write inside the MediaCrawler
    submodule; opening in ``ro`` mode is how we enforce that at the
    OS / library level rather than relying on convention.
    """
    # ``Path.as_uri()`` would also work, but the URI format SQLite
    # expects is slightly different (no ``//`` after the scheme, query
    # string appended directly). Build it by hand for clarity.
    posix = path.resolve().as_posix()
    # Windows drive letters render as ``C:/foo``; SQLite expects an
    # extra leading slash to disambiguate from a relative authority.
    if len(posix) >= 2 and posix[1] == ":":
        uri = f"file:/{posix}?mode=ro"
    else:
        uri = f"file:{posix}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _read_rows_from_sqlite(
    db_path: Path,
    table_whitelist: tuple[str, ...],
    *,
    platform: str,
) -> list[dict]:
    """Read every row of the first whitelisted table found in ``db_path``.

    Returns an empty list when the file is missing, when none of the
    whitelisted tables exist, or when the table itself is empty. Rows
    are projected through ``dict(zip(col_names, row))`` so the dicts
    mirror MediaCrawler's column layout 1:1, letting the upsert
    helpers in :mod:`app.services.data_store` pull the fields they
    recognise without an explicit translation pass at this layer.

    All file IO is read-only:

    * the SQLite file is opened in URI ``mode=ro``;
    * we never issue an INSERT / UPDATE / DELETE statement;
    * we never write or delete any sibling file in ``raw_dir``.
    """
    if not db_path.exists() or not db_path.is_file():
        return []

    rows: list[dict] = []
    conn = _open_sqlite_readonly(db_path)
    try:
        # ``Row`` factory would also work but ``dict(zip(...))`` is
        # marginally faster and produces plain dicts that are trivially
        # serialisable / mutable downstream (the upsert helpers add
        # ``task_id`` and friends in place).
        table = _select_first_table(conn, table_whitelist)
        if table is None:
            return []

        # ``sqlite_master`` was already consulted in
        # ``_select_first_table``; querying the column list separately
        # via ``PRAGMA table_info`` works in ``mode=ro`` because
        # ``PRAGMA`` reads do not require a writable database.
        cursor = conn.execute(
            f'SELECT * FROM "{table}"'
        )  # noqa: S608 - table name is from a hard-coded whitelist
        col_names = [d[0] for d in cursor.description]
        for row in cursor.fetchall():
            item = dict(zip(col_names, row))
            item["__platform"] = platform
            rows.append(item)
    finally:
        conn.close()

    return rows


def _read_rows_from_json(
    raw_dir: Path,
    candidates: tuple[str, ...],
    *,
    platform: str,
) -> list[dict]:
    """Read and concatenate JSON arrays from any candidate file in ``raw_dir``.

    Each candidate file is expected to deserialise to a JSON array of
    objects; mismatching shapes are silently skipped so a malformed
    sibling file does not poison an otherwise-valid batch. Files are
    opened with plain ``open(..., "r", encoding="utf-8")`` -- no
    writes, no deletes, in line with the read-only contract on
    ``raw_dir``.
    """
    if not raw_dir.exists() or not raw_dir.is_dir():
        return []

    rows: list[dict] = []
    for name in candidates:
        path = raw_dir / name
        if not path.exists() or not path.is_file():
            continue
        try:
            # Read-only access: plain text mode, UTF-8.
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            # Defensive: a malformed JSON file is logged and skipped
            # rather than aborting the batch -- the caller can still
            # recover usable rows from the SQLite path or other JSON
            # candidates.
            logger.warning(
                "skip malformed MediaCrawler JSON",
                extra={
                    "event": "mc_json_malformed",
                    "path": str(path),
                    "error": str(exc)[:200],
                },
            )
            continue
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    item.setdefault("__platform", platform)
                    rows.append(item)
        elif isinstance(payload, dict):
            # Some MediaCrawler versions wrap the array under a top-
            # level ``items`` / ``data`` key; flatten that case so we
            # still pick up the records.
            for key in ("items", "data", "rows"):
                inner = payload.get(key)
                if isinstance(inner, list):
                    for item in inner:
                        if isinstance(item, dict):
                            item.setdefault("__platform", platform)
                            rows.append(item)
                    break
    return rows


def _normalise_top_level_marker(value: Any) -> bool:
    """Return ``True`` when ``value`` represents a missing parent.

    MediaCrawler's various code paths emit ``parent_comment_id`` as
    ``None``, ``""``, ``"0"``, or the integer ``0`` for top-level
    comments. Any of those forms must be treated as "no parent" so
    requirement 13.5 ("二级评论" = comments with a non-empty parent)
    is applied to the same population the storage layer ultimately
    sees.
    """
    if value is None:
        return True
    if isinstance(value, str):
        # ``"0"`` is the douyin / bilibili sentinel that occasionally
        # leaks through into shared helpers; treat it as missing too.
        return value.strip() in ("", "0")
    if isinstance(value, (int, float)):
        return value == 0
    return False


def _is_top_hot_truthy(value: Any) -> bool:
    """Mirror :func:`data_store._coerce_bool_int` for the ``is_top_hot`` flag.

    Kept in sync with the storage layer so the filter applied in
    :meth:`CrawlerService._read_mc_output` accepts exactly the same
    set of truthy spellings the database round-trip would accept
    (``1``, ``True``, ``"1"``, ``"true"``, ``"yes"``, ``"y"``).
    """
    return value in (1, True, "1", "true", "True", "yes", "y")


def _filter_subcomments_by_hot_cap(
    raw_comments: list[dict], hot_cap: int
) -> list[dict]:
    """Apply requirement 13.5 to ``raw_comments`` without mutating inputs.

    The contract:

    * Top-level comments (``parent_comment_id`` is missing per
      :func:`_normalise_top_level_marker`) pass through unchanged.
    * Sub-comments with ``is_top_hot`` falsy are dropped entirely.
    * The remaining sub-comments are grouped by ``note_id``, sorted by
      ``like_count`` descending (treating missing values as ``0``),
      and truncated to the first ``hot_cap`` entries per note.

    A ``hot_cap`` of ``0`` would short-circuit to dropping every sub-
    comment; the configuration validator pins ``HOT_COMMENT_TOP_N`` to
    ``[1, 20]`` so that branch is unreachable in practice, but the
    implementation handles it gracefully for testing convenience.
    """
    top_level: list[dict] = []
    sub_by_note: dict[Any, list[dict]] = {}

    for raw in raw_comments:
        parent = raw.get("parent_comment_id")
        if _normalise_top_level_marker(parent):
            top_level.append(raw)
            continue

        # Sub-comment branch. Drop everything that is not flagged hot
        # (requirement 13.5 first half: 「只采集热门部分」).
        if not _is_top_hot_truthy(raw.get("is_top_hot")):
            continue

        note_id = raw.get("note_id")
        sub_by_note.setdefault(note_id, []).append(raw)

    # Sort each note's hot subset by ``like_count`` desc and cap.
    capped_subs: list[dict] = []
    for note_id, subs in sub_by_note.items():
        subs.sort(
            key=lambda r: _coerce_like_count(r.get("like_count")),
            reverse=True,
        )
        if hot_cap > 0:
            capped_subs.extend(subs[:hot_cap])
        # Else: ``hot_cap == 0`` drops every sub-comment, matching the
        # natural behaviour of ``subs[:0]``.

    return top_level + capped_subs


def _filter_comments_for_effective_notes(
    raw_comments: list[dict],
    effective_notes: list[dict],
) -> list[dict]:
    """Keep only comments whose note and parent comment will exist.

    MediaCrawler's SQLite database is cumulative, while each task only
    imports the capped ``effective_notes`` subset. Comments for notes
    outside that subset would violate ``comments.note_id``. Hot replies
    whose parent comment is absent would also violate the self-FK on
    ``comments.parent_comment_id``.
    """
    note_ids: set[str] = set()
    for raw_note in effective_notes:
        note = _normalise_note_row(-1, raw_note)
        if note is not None:
            note_ids.add(note["note_id"])

    if not note_ids:
        return []

    eligible: list[tuple[dict, dict[str, Any]]] = []
    comment_ids: set[str] = set()
    for raw_comment in raw_comments:
        comment = _normalise_comment_row(raw_comment)
        if comment is None or comment["note_id"] not in note_ids:
            continue
        eligible.append((raw_comment, comment))
        comment_ids.add(comment["comment_id"])

    return [
        raw_comment
        for raw_comment, comment in eligible
        if comment["parent_comment_id"] is None
        or comment["parent_comment_id"] in comment_ids
    ]


def _coerce_like_count(value: Any) -> int:
    """Coerce ``like_count`` for the per-note sort key.

    ``int(value)`` works directly when MediaCrawler emits the field as
    a string of digits (its default for SQLite ``Text`` columns) and
    when it emits it as an integer. Anything else falls back to ``0``
    so a malformed row sinks to the bottom of the ranking rather than
    blowing up the whole batch.
    """
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


def _coerce_timestamp_ms(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


def _filter_notes_for_current_crawl(
    raw_notes: list[dict],
    *,
    keyword: str | None,
    min_timestamp_ms: int | None,
) -> list[dict]:
    """Filter cumulative MediaCrawler rows down to the current crawl."""
    if not raw_notes:
        return []

    filtered = list(raw_notes)
    expected_keyword = (keyword or "").strip()
    if expected_keyword and any("source_keyword" in row for row in filtered):
        filtered = [
            row
            for row in filtered
            if str(row.get("source_keyword") or "").strip() == expected_keyword
        ]

    if min_timestamp_ms is not None and any(
        "add_ts" in row or "last_modify_ts" in row for row in filtered
    ):
        filtered = [
            row
            for row in filtered
            if max(
                _coerce_timestamp_ms(row.get("add_ts")),
                _coerce_timestamp_ms(row.get("last_modify_ts")),
            )
            >= min_timestamp_ms
        ]

    filtered.sort(
        key=lambda row: max(
            _coerce_timestamp_ms(row.get("add_ts")),
            _coerce_timestamp_ms(row.get("last_modify_ts")),
        ),
        reverse=True,
    )
    return filtered


def _redact_command(cmd: list[str]) -> list[str]:
    """Return a log-safe copy of a subprocess command."""
    redacted = list(cmd)
    for index, value in enumerate(redacted[:-1]):
        if value == "--cookies":
            redacted[index + 1] = "***"
    return redacted


async def _read_mc_output_impl(
    raw_dir: Path,
    *,
    platform: str = "xhs",
    keyword: str | None = None,
    min_timestamp_ms: int | None = None,
) -> tuple[list[dict], list[dict]]:
    """Module-level implementation of :meth:`CrawlerService._read_mc_output`.

    Strategy (matches the task description verbatim):

    1. **Probe SQLite first.** For each SQLite filename in the
       respective whitelist, attempt a read-only open and project the
       first whitelisted table to a list of column-keyed dicts. The
       same physical file can satisfy both probes when MediaCrawler
       emits a single combined sqlite (e.g. ``sqlite_tables.db``).
    2. **Fall back to JSON** when the SQLite probe came up empty for
       a given dataset. Multiple JSON filenames are tried in order
       and concatenated when more than one match.
    3. **Apply requirement 13.5** to the resulting comments list via
       :func:`_filter_subcomments_by_hot_cap`.
    4. **Return ``([], [])``** when the directory is empty or
       missing -- the orchestrator interprets that as "no notes
       returned" and routes the task to ``failed`` (requirement 7.9).

    All file IO is strictly read-only: SQLite is opened in URI
    ``mode=ro``, JSON files are opened with ``open(..., "r")``, and
    no helper anywhere in this module writes / deletes inside
    ``raw_dir``. This satisfies requirements 6.5 and 19.2 -- the
    MediaCrawler submodule remains an immutable artefact from the
    backend's perspective.
    """
    # ---- Step 0: graceful empty-dir handling ----------------------
    if not raw_dir.exists() or not raw_dir.is_dir():
        logger.info(
            "MediaCrawler raw_dir missing -- treating as empty",
            extra={
                "event": "mc_raw_dir_missing",
                "raw_dir": str(raw_dir),
            },
        )
        return [], []

    # ---- Step 1: SQLite probes -------------------------------------
    platform = normalise_platform(platform)
    note_tables = _PLATFORM_NOTE_TABLES[platform]
    comment_tables = _PLATFORM_COMMENT_TABLES[platform]

    raw_notes: list[dict] = []
    for name in _CONTENTS_DB_NAMES:
        rows = _read_rows_from_sqlite(
            raw_dir / name,
            note_tables,
            platform=platform,
        )
        if rows:
            raw_notes = rows
            logger.info(
                "loaded notes from MediaCrawler SQLite",
                extra={
                    "event": "mc_notes_sqlite",
                    "path": str(raw_dir / name),
                    "rows": len(rows),
                },
            )
            break

    raw_comments: list[dict] = []
    for name in _COMMENTS_DB_NAMES:
        rows = _read_rows_from_sqlite(
            raw_dir / name,
            comment_tables,
            platform=platform,
        )
        if rows:
            raw_comments = rows
            logger.info(
                "loaded comments from MediaCrawler SQLite",
                extra={
                    "event": "mc_comments_sqlite",
                    "path": str(raw_dir / name),
                    "rows": len(rows),
                },
            )
            break

    # ---- Step 2: JSON fallback per dataset -------------------------
    if not raw_notes:
        json_notes = _read_rows_from_json(raw_dir, _NOTE_JSON_NAMES, platform=platform)
        if json_notes:
            raw_notes = json_notes
            logger.info(
                "loaded notes from MediaCrawler JSON",
                extra={
                    "event": "mc_notes_json",
                    "raw_dir": str(raw_dir),
                    "rows": len(json_notes),
                },
            )

    if not raw_comments:
        json_comments = _read_rows_from_json(raw_dir, _COMMENT_JSON_NAMES, platform=platform)
        if json_comments:
            raw_comments = json_comments
            logger.info(
                "loaded comments from MediaCrawler JSON",
                extra={
                    "event": "mc_comments_json",
                    "raw_dir": str(raw_dir),
                    "rows": len(json_comments),
                },
            )

    # ---- Step 3: apply requirement 13.5 ---------------------------
    if raw_notes:
        before_count = len(raw_notes)
        raw_notes = _filter_notes_for_current_crawl(
            raw_notes,
            keyword=keyword,
            min_timestamp_ms=min_timestamp_ms,
        )
        if keyword or min_timestamp_ms is not None:
            logger.info(
                "filtered MediaCrawler notes for current crawl",
                extra={
                    "event": "mc_notes_filtered",
                    "platform": platform,
                    "keyword": keyword,
                    "min_timestamp_ms": min_timestamp_ms,
                    "before": before_count,
                    "after": len(raw_notes),
                },
            )

    if raw_comments:
        raw_comments = _filter_subcomments_by_hot_cap(
            raw_comments, hot_cap=settings.HOT_COMMENT_TOP_N
        )

    return raw_notes, raw_comments

