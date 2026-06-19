"""Property test 1 — note_id uniqueness under repeated upsert.

Validates requirements 9.1 / 9.2:

* The ``notes`` table treats ``note_id`` as a primary key, so any
  random batch of raw notes (with arbitrary duplicates) must leave the
  table with each ``note_id`` appearing **exactly once** after
  ``upsert_notes``.
* When the same ``note_id`` appears more than once in the input batch,
  the row stored at the end of the batch MUST reflect the *last*
  occurrence's payload (last-write-wins on every non-PK field).
"""

from __future__ import annotations

import json

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from sqlalchemy import func, select

from app.models import Task, Note


# Hypothesis strategy that produces a single raw-note payload. ``note_id``
# is drawn from a tiny alphabet so the property meaningfully exercises
# the duplicate case (Hypothesis would almost never collide on a wide
# space).
_NOTE_ID_ALPHABET = ["a", "b", "c", "d"]

_raw_note = st.builds(
    lambda nid, title, liked: {
        "note_id": nid,
        "title": title,
        "desc": f"desc-{title}",
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
    nid=st.sampled_from(_NOTE_ID_ALPHABET),
    title=st.text(min_size=0, max_size=24),
    liked=st.integers(min_value=0, max_value=10_000),
)


@pytest.mark.asyncio
@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(raw_notes=st.lists(_raw_note, min_size=1, max_size=12))
async def test_note_id_unique(store, raw_notes):
    """All `note_id`s are unique after upsert, last-write-wins on duplicates."""

    # Each example gets a fresh task so the per-test DB stays small.
    async with store.session() as session:
        task = Task(keyword="note-unique-prop", status="pending", max_notes=20)
        session.add(task)
        await session.flush()
        task_id = int(task.id)
        await session.commit()

    await store.upsert_notes(task_id, raw_notes)

    # ── Invariant 1: every note_id appears exactly once. ──────────
    async with store.session() as session:
        counts = (
            await session.execute(
                select(Note.note_id, func.count("*").label("c"))
                .where(Note.task_id == task_id)
                .group_by(Note.note_id)
            )
        ).all()
    for note_id, c in counts:
        assert c == 1, f"duplicate row for note_id={note_id!r}: count={c}"

    # ── Invariant 2: last-write-wins on duplicated note_ids. ──────
    # Rebuild expected snapshot in Python: for each note_id, keep the
    # payload of the LAST occurrence in the batch.
    expected_last: dict[str, dict] = {}
    for row in raw_notes:
        expected_last[row["note_id"]] = row

    async with store.session() as session:
        persisted = {
            r.note_id: r
            for r in (
                await session.execute(select(Note).where(Note.task_id == task_id))
            ).scalars()
        }

    assert set(persisted.keys()) == set(expected_last.keys())
    for nid, exp in expected_last.items():
        row = persisted[nid]
        assert row.title == exp["title"], f"title mismatch for {nid}"
        assert row.liked_count == exp["liked_count"], f"liked_count mismatch for {nid}"
        assert row.desc == exp["desc"], f"desc mismatch for {nid}"
