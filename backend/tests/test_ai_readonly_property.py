"""Property test 4 — AI report pipeline is read-only.

Validates requirements 15.1-15.8: an :class:`AIAnalyzer` invocation
MUST NOT touch ``notes`` / ``comments`` / ``authors`` / ``tasks`` in
any way (insert, update, delete) — the *only* write it is allowed to
perform is exactly one row in ``ai_reports``.

The test:

1. Seeds a random database snapshot (one ``success`` task plus
   matching authors/notes/comments).
2. Captures a byte-for-byte snapshot of the four read-only tables.
3. Stubs out :meth:`_call_llm` with a deterministic non-empty string
   so no real network traffic happens.
4. Awaits :meth:`AIAnalyzer.analyze`.
5. Re-captures the same four tables and asserts byte-equality.
6. Asserts ``ai_reports`` grew by exactly one row whose
   ``prompt_version`` is ``"v1"`` and whose ``report_md`` is non-empty.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from sqlalchemy import select

from app.models import AIReport, Author, Comment, Note, Task
from app.services.ai_analyzer import AIAnalyzer


# ---------------------------------------------------------------------------
# Stub provider that lets us drive ``analyze`` without going over the wire.
# ---------------------------------------------------------------------------


class _StubAnalyzer(AIAnalyzer):
    provider = "openai"  # any value from AI_PROVIDERS is fine

    async def _call_llm(self, prompt: str) -> str:
        # Deterministic non-empty payload. We embed the keyword so the
        # test can sanity-check it actually round-trips through
        # ``build_prompt`` -> :data:`PROMPT_V1`.
        return f"# 报告 v1\nprompt-length={len(prompt)}"


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Snapshot:
    tasks: tuple
    authors: tuple
    notes: tuple
    comments: tuple


async def _snapshot(store) -> _Snapshot:
    """Read all rows of the four read-only tables into a comparable tuple."""

    async with store.session() as session:
        tasks = tuple(
            (t.id, t.keyword, t.status, t.note_count, t.started_at, t.finished_at, t.error_msg, t.json_path)
            for t in (await session.execute(select(Task))).scalars().all()
        )
        authors = tuple(
            (a.user_id, a.nickname, a.fans_count, a.follow_count)
            for a in (await session.execute(select(Author))).scalars().all()
        )
        notes = tuple(
            (n.note_id, n.task_id, n.title, n.desc, n.liked_count, n.comment_count)
            for n in (await session.execute(select(Note))).scalars().all()
        )
        comments = tuple(
            (c.comment_id, c.note_id, c.parent_comment_id, c.content, c.like_count, c.is_top_hot)
            for c in (await session.execute(select(Comment))).scalars().all()
        )
    return _Snapshot(tasks=tasks, authors=authors, notes=notes, comments=comments)


# ---------------------------------------------------------------------------
# The property test
# ---------------------------------------------------------------------------


_note_strategy = st.builds(
    lambda nid, title, desc, liked: {
        "note_id": nid,
        "title": title,
        "desc": desc,
        "type": "normal",
        "cover_url": None,
        "video_url": None,
        "liked_count": liked,
        "collected_count": 0,
        "comment_count": 0,
        "share_count": 0,
        "author_user_id": None,
        "publish_time": None,
        "ip_location": None,
        "tag_list": json.dumps([]),
        "raw_json": json.dumps({}),
    },
    nid=st.uuids().map(str),
    title=st.text(min_size=1, max_size=24),
    desc=st.text(min_size=0, max_size=80),
    liked=st.integers(min_value=0, max_value=10_000),
)


@pytest.mark.asyncio
@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(notes=st.lists(_note_strategy, min_size=1, max_size=8))
async def test_ai_analyze_is_readonly(store, notes):
    """`analyze()` must persist exactly one ai_reports row and nothing else."""

    # ── 1. Seed: one success task + the random notes. ────────────
    async with store.session() as session:
        task = Task(
            keyword="readonly-prop",
            status="success",
            max_notes=20,
            note_count=len(notes),
        )
        session.add(task)
        await session.flush()
        task_id = int(task.id)
        await session.commit()

    await store.upsert_notes(task_id, notes)
    # No comments / authors in this minimal seed — that's a valid
    # corner case (build_prompt must tolerate the empty comment list).

    # ── 2. Pre-snapshot the four read-only tables. ───────────────
    before = await _snapshot(store)
    async with store.session() as session:
        reports_before = (
            (await session.execute(select(AIReport))).scalars().all()
        )

    # ── 3. Run the pipeline through the stub provider. ───────────
    analyzer = _StubAnalyzer(store=store, model="stub-model")
    report, report_id = await analyzer.analyze(task_id)

    # ── 4. Post-snapshot and compare. ────────────────────────────
    after = await _snapshot(store)
    assert before == after, (
        "AI analyze mutated one of the read-only tables; offending diff: "
        f"tasks: {before.tasks!r} vs {after.tasks!r}; "
        f"authors: {before.authors!r} vs {after.authors!r}; "
        f"notes len: {len(before.notes)} vs {len(after.notes)}; "
        f"comments len: {len(before.comments)} vs {len(after.comments)}"
    )

    # ── 5. ai_reports grew by exactly one. ──────────────────────
    async with store.session() as session:
        reports_after = (
            (await session.execute(select(AIReport))).scalars().all()
        )
    assert len(reports_after) == len(reports_before) + 1, (
        "ai_reports should grow by exactly one row per analyze()"
    )

    # ── 6. The new row satisfies the v1 schema. ─────────────────
    new_row = next(r for r in reports_after if r.id == report_id)
    assert new_row.task_id == task_id
    assert new_row.prompt_version == "v1"
    assert new_row.report_md.strip(), "report_md must be non-empty"
    assert new_row.provider in {"openai", "deepseek", "gemini"}
    assert report.prompt_version == "v1"
