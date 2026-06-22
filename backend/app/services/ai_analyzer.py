"""AI insight-report analyzer abstraction.

This module owns the *abstract* half of the AI report pipeline. Task
11.1 implements three pieces here:

* :data:`PROMPT_V1` -- the frozen Markdown prompt template
  (``v1`` matching ``ai_reports.prompt_version``) with two named
  slots, ``{keyword}`` and ``{materials}``.
* :class:`AIAnalyzer` -- the abstract base class that all LLM
  providers (task 11.2) inherit from. It owns the read-only
  orchestration of ``load_for_ai`` -> :meth:`build_prompt` ->
  ``_call_llm`` -> ``save_ai_report``, leaving subclasses with the
  single responsibility of implementing :meth:`_call_llm`.
* :class:`AIReport` -- a frozen dataclass mirroring the columns
  written into ``ai_reports``. The analyser layer returns instances
  of this type to the API layer (task 11.3) which is then free to
  surface the row id alongside.

Concrete provider classes (``OpenAIAnalyzer`` / ``DeepSeekAnalyzer`` /
``GeminiAnalyzer``) and the ``make_analyzer`` factory live in task
11.2 and are not imported here to keep this module dependency-light.

Read-only invariant (requirements 15.1-15.7)
--------------------------------------------

:meth:`AIAnalyzer.analyze` must NEVER touch ``notes`` /
``comments`` / ``authors`` / ``tasks`` directly. The contract is
enforced architecturally by funnelling all reads through
:meth:`DataStore.load_for_ai` and all writes through
:meth:`DataStore.save_ai_report`. Task 11.4's property test exercises
this invariant by snapshotting the four read-only tables before and
after :meth:`analyze` and comparing them byte-for-byte.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any, ClassVar, Sequence

from app.core.config import settings
from app.core.logger import logger
from app.services.data_store import AIReportInput, DataStore
from app.utils.token_count import estimate_tokens


# ---------------------------------------------------------------------------
# Public exceptions
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Raised by provider implementations when an LLM call fails.

    Subclasses of :class:`AIAnalyzer` translate transport-level
    failures (timeout, network error, authentication / rate-limit
    error) into this single type so that the API layer (task 11.3) can
    map every failure mode onto a single ``HTTP 502 AI_FAILED``
    response without having to know about provider-specific exception
    hierarchies (requirement 14.10).

    The class deliberately stays a thin :class:`Exception` subclass --
    structured detail belongs in the message string and in the audit
    log, not in additional attributes.
    """


# ---------------------------------------------------------------------------
# Public dataclass returned to the API layer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AIReport:
    """In-memory representation of a freshly generated AI report.

    The fields mirror the writable columns on the ``ai_reports`` table
    (design §2) and the shape expected by
    :meth:`DataStore.save_ai_report`. The dataclass is :data:`frozen`
    so that callers cannot accidentally mutate a report after it has
    been persisted -- once :meth:`AIAnalyzer.analyze` returns, the
    object is effectively a read-only handle on the row that lives in
    the database.

    Note that ``id`` and ``created_at`` are *not* fields here: they
    are populated by the database during :meth:`save_ai_report` and
    surfaced separately as the second element of the
    :meth:`AIAnalyzer.analyze` return tuple.
    """

    task_id: int
    provider: str
    model: str
    prompt_version: str
    report_md: str


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------


#: Frozen prompt template for ``prompt_version='v1'`` (requirement
#: 14.6). Two ``str.format`` slots are exposed:
#:
#: * ``{keyword}`` -- the task's original search keyword;
#: * ``{materials}`` -- the prebuilt note / hot-comment digest
#:   produced by :meth:`AIAnalyzer.build_prompt`.
#:
#: Any future change to the template MUST bump the ``prompt_version``
#: string so that historical reports remain reproducible
#: (requirement 14.11).
PROMPT_V1: str = (
    "你是一名资深内容运营分析师。以下是关于关键词「{keyword}」"
    "的平台内容与评论摘要。\n"
    "请输出一份 Markdown 格式的内容洞察报告,包含:\n"
    "1. 选题方向与高频主题\n"
    "2. 用户画像与情感倾向\n"
    "3. 互动数据 Top 笔记拆解\n"
    "4. 内容创作建议(标题/封面/选题/发布时间)\n"
    "5. 风险提示(请勿违规营销/虚假宣传)\n"
    "\n"
    "【素材】\n"
    "{materials}\n"
)


#: Top-N caps used by :meth:`AIAnalyzer.build_prompt`. They mirror the
#: numbers locked down by requirement 14.7 (笔记 Top 20, 评论 Top 50).
_TOP_NOTES: int = 20
_TOP_COMMENTS: int = 50

#: Per-row truncation limits for the same requirement: laptops and
#: lighter LLM context windows benefit from aggressive truncation, and
#: the captions / comment bodies on small-red-book are typically much
#: longer than the prompt budget allows.
_DESC_TRUNC: int = 80
_CONTENT_TRUNC: int = 120


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class AIAnalyzer(ABC):
    """Abstract base for every LLM provider.

    Subclasses implement :meth:`_call_llm` and override the
    :data:`provider` class attribute to one of the values allowed by
    the ``ai_reports.provider`` CHECK constraint
    (``{openai, deepseek, gemini}``). Everything else -- prompt
    assembly, token-budget guard, persistence -- is shared and
    enforced here so the read-only invariant (requirement 15.x) cannot
    be subverted by a buggy provider.
    """

    #: Provider tag stored verbatim in ``ai_reports.provider``.
    #: Subclasses MUST override this to one of
    #: ``{"openai", "deepseek", "gemini"}``; the literal
    #: ``"abstract"`` only exists so that introspection on the base
    #: class itself does not blow up.
    provider: ClassVar[str] = "abstract"

    def __init__(
        self,
        store: DataStore,
        model: str,
        display_model: str | None = None,
    ) -> None:
        self.store = store
        self.model = model
        self.display_model = display_model or model
        # Cache the configurable knobs at construction time so that a
        # mid-flight settings reload cannot change the budget halfway
        # through :meth:`analyze`.
        self.timeout_s: int = settings.LLM_API_TIMEOUT_SECONDS
        self.context_limit: int = settings.MODEL_CONTEXT_LIMIT

    # ------------------------------------------------------------------
    # Subclass hook
    # ------------------------------------------------------------------

    @abstractmethod
    async def _call_llm(self, prompt: str) -> str:
        """Issue the actual LLM API call and return the markdown body.

        Implementations MUST:

        * Honour ``self.timeout_s`` (requirement 14.10);
        * Translate every transport-level failure -- network error,
          authentication failure, rate limit, content filter, timeout
          -- into :class:`LLMError`;
        * Return a non-empty string. An empty / whitespace-only return
          is treated as a provider bug and propagates upward as a
          :class:`LLMError` from :meth:`analyze`.
        """

    # ------------------------------------------------------------------
    # Prompt assembly (requirement 14.7)
    # ------------------------------------------------------------------

    def build_prompt(
        self,
        keyword: str,
        notes: Sequence[Any],
        comments: Sequence[Any],
    ) -> str:
        """Assemble the ``{materials}`` block for :data:`PROMPT_V1`.

        The exact contract (requirement 14.7):

        * Notes are sorted by ``liked_count`` descending, the top 20
          are kept, and each row's ``desc`` is truncated to the first
          80 characters before being formatted.
        * Comments are sorted by ``like_count`` descending, the top
          50 are kept, and each row's ``content`` is truncated to the
          first 120 characters before being formatted.
        * The output is the concatenation of two Markdown sections,
          ``## 笔记 Top`` followed by ``## 热门评论 Top``, separated
          by a blank line so downstream Markdown renderers visibly
          split the two lists.

        ``None`` values for ``liked_count`` / ``like_count`` /
        ``title`` / ``desc`` / ``content`` are coerced to safe
        defaults (``0`` for counts, ``"-"`` / ``""`` for text) so the
        method never raises on partially-populated ORM rows.

        Parameters
        ----------
        keyword:
            Task keyword. Currently unused inside the materials body
            but accepted as the first positional argument so the
            signature matches the design pseudocode and so future
            templates can include it without breaking callers.
        notes:
            Iterable of note-like objects exposing ``liked_count``,
            ``comment_count``, ``title`` and ``desc`` attributes.
            :class:`app.models.note.Note` ORM rows satisfy this
            contract, but any duck-typed object works (handy for
            tests).
        comments:
            Iterable of comment-like objects exposing ``like_count``
            and ``content`` attributes.
        """
        # ``keyword`` is intentionally part of the signature even
        # though the v1 template embeds it via the outer
        # :data:`PROMPT_V1` ``{keyword}`` slot rather than inside the
        # materials block. Keeping it here lets future prompt versions
        # surface keyword in the materials section without having to
        # refactor every caller.
        del keyword  # noqa: F841 -- kept for forward compatibility

        # Sort + slice notes. ``liked_count or 0`` handles both
        # ``None`` (legacy partial rows) and a missing attribute via
        # ``getattr(..., 0)``.
        top_notes = sorted(
            notes,
            key=lambda n: getattr(n, "liked_count", 0) or 0,
            reverse=True,
        )[:_TOP_NOTES]
        top_comments = sorted(
            comments,
            key=lambda c: getattr(c, "like_count", 0) or 0,
            reverse=True,
        )[:_TOP_COMMENTS]

        note_lines: list[str] = []
        for n in top_notes:
            liked = getattr(n, "liked_count", 0) or 0
            comment_cnt = getattr(n, "comment_count", 0) or 0
            title = getattr(n, "title", None) or "-"
            desc = (getattr(n, "desc", None) or "")[:_DESC_TRUNC]
            note_lines.append(f"- [{liked}赞/{comment_cnt}评] {title} | {desc}")

        comment_lines: list[str] = []
        for c in top_comments:
            liked = getattr(c, "like_count", 0) or 0
            content = (getattr(c, "content", None) or "")[:_CONTENT_TRUNC]
            comment_lines.append(f"- [{liked}赞] {content}")

        # Two Markdown sections separated by a blank line. Empty
        # sections are still rendered (with no list items below the
        # heading) so downstream LLMs can recognise that the section
        # exists rather than guessing whether it was omitted.
        parts: list[str] = ["## 笔记 Top", *note_lines, "", "## 热门评论 Top", *comment_lines]
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def analyze(self, task_id: int) -> tuple[AIReport, int]:
        """Run the full analyse pipeline for ``task_id``.

        The flow:

        1. Load ``(keyword, notes, comments)`` via
           :meth:`DataStore.load_for_ai`. This is the only allowed
           read path against ``tasks`` / ``notes`` / ``comments`` /
           ``authors`` (requirement 15.5) and is itself read-only.
        2. Build the materials block via :meth:`build_prompt` and
           interpolate it into :data:`PROMPT_V1`.
        3. Assert the estimated token count of the final prompt is
           strictly below ``settings.MODEL_CONTEXT_LIMIT``
           (requirement 14.8). This happens *before* any LLM round
           trip so we never burn quota on an oversized prompt.
        4. Delegate to :meth:`_call_llm` to produce the markdown body.
        5. Persist the report via :meth:`DataStore.save_ai_report` --
           the only allowed write path (requirement 15.6) -- and
           return both the in-memory :class:`AIReport` plus the
           autoincrement ``id`` of the inserted row so the API layer
           in task 11.3 can construct the ``{report_id, status}``
           response without an extra query.

        Parameters
        ----------
        task_id:
            Identifier of a task whose ``status`` is ``'success'``.
            Validation that the task is *eligible* for analysis is
            the API layer's responsibility (requirement 14.2);
            :meth:`load_for_ai` will assert the task at least exists.

        Returns
        -------
        tuple[AIReport, int]
            ``(report, report_id)`` where ``report_id`` is the new
            ``ai_reports.id`` value.

        Raises
        ------
        AssertionError
            If the assembled prompt's estimated token count meets or
            exceeds ``settings.MODEL_CONTEXT_LIMIT``. The assertion
            triggers *before* :meth:`_call_llm` is invoked so no
            ``ai_reports`` row is created.
        LLMError
            Re-raised from :meth:`_call_llm` when the provider call
            fails. No ``ai_reports`` row is created.
        """
        # 1) Read-only fetch.
        keyword, notes, comments = await self.store.load_for_ai(task_id)

        # 2) Materials + final prompt.
        materials = self.build_prompt(keyword, notes, comments)
        prompt = PROMPT_V1.format(keyword=keyword, materials=materials)

        # 3) Token-budget guard (requirement 14.8). The strict ``<``
        # comparison matches the algebraic post-condition documented
        # in design §4.2.
        token_estimate = estimate_tokens(prompt)
        assert token_estimate < self.context_limit, (
            f"prompt too long for provider={self.provider} model={self.model}: "
            f"estimated_tokens={token_estimate} >= "
            f"MODEL_CONTEXT_LIMIT={self.context_limit}"
        )

        logger.info(
            "ai_analyze_start",
            extra={
                "event": "ai_analyze_start",
                "task_id": task_id,
                "provider": self.provider,
                "model": self.model,
                "prompt_version": "v1",
                "token_estimate": token_estimate,
                "note_count": len(notes),
                "comment_count": len(comments),
            },
        )

        # 4) Provider-specific LLM call. Errors propagate as
        # ``LLMError`` and the surrounding API layer maps them to a
        # 502 response (requirement 14.10).
        report_md = await self._call_llm(prompt)

        # Defensive: an empty report is indistinguishable from a
        # provider bug, and the ``ai_reports.report_md`` column is
        # ``NOT NULL``. Surface the failure as ``LLMError`` so the API
        # layer's existing error path handles it without a 500.
        if not isinstance(report_md, str) or not report_md.strip():
            raise LLMError(
                f"provider={self.provider} model={self.model} returned an "
                "empty report body"
            )

        # 5) Persist & return. Building ``AIReport`` first and then
        # passing it through ``AIReportInput`` keeps the public return
        # type stable while reusing the storage-layer payload shape.
        report = AIReport(
            task_id=task_id,
            provider=self.provider,
            model=self.display_model,
            prompt_version="v1",
            report_md=report_md,
        )
        report_id = await self.store.save_ai_report(AIReportInput(**asdict(report)))

        logger.info(
            "ai_analyze_done",
            extra={
                "event": "ai_analyze_done",
                "task_id": task_id,
                "report_id": report_id,
                "provider": self.provider,
                "model": self.model,
                "prompt_version": "v1",
            },
        )
        return report, report_id


__all__ = [
    "AIAnalyzer",
    "AIReport",
    "LLMError",
    "PROMPT_V1",
]
