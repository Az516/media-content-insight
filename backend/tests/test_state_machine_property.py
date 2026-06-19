"""Property test 5 — task state machine monotonic progression.

Validates requirements 3.1 / 3.2:

* Allowed transitions are ``pending -> running``, ``running -> success``
  and ``pending|running -> failed``. Every other transition MUST raise
  :class:`AssertionError` and leave ``status``, ``started_at``,
  ``finished_at`` and ``error_msg`` untouched.
* Once a task lands in a terminal state (``success`` / ``failed``) the
  machine never moves back to ``pending`` or ``running``.

The property exhaustively explores random transition sequences over the
four-state alphabet by composing ``mark_running``, ``mark_success`` and
``mark_failed`` arbitrarily and asserting both the success / failure
contract and the field-immutability invariant on rejected transitions.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from sqlalchemy import select

from app.models import Task

ALLOWED = {
    ("pending", "mark_running"): "running",
    ("running", "mark_success"): "success",
    ("pending", "mark_failed"): "failed",
    ("running", "mark_failed"): "failed",
}

OPERATIONS = ("mark_running", "mark_success", "mark_failed")


@pytest.mark.asyncio
@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    ops=st.lists(st.sampled_from(OPERATIONS), min_size=1, max_size=8),
)
async def test_state_machine_monotonic(store, ops):
    """Random sequences of state-machine calls never violate the contract."""

    # Seed a fresh ``pending`` task for each example.
    async with store.session() as session:
        task = Task(keyword="state-machine-prop", status="pending", max_notes=20)
        session.add(task)
        await session.flush()
        task_id = int(task.id)
        await session.commit()

    current = "pending"

    for op in ops:
        # Snapshot the four state-machine fields BEFORE invoking the op
        # so we can compare them byte-for-byte after a rejected call.
        async with store.session() as session:
            row = (await session.execute(select(Task).where(Task.id == task_id))).scalar_one()
            before = (row.status, row.started_at, row.finished_at, row.error_msg)

        expected_next = ALLOWED.get((current, op))

        try:
            if op == "mark_running":
                await store.mark_task_running(task_id)
            elif op == "mark_success":
                await store.mark_task_success(task_id, note_count=1, json_path="x.json")
            else:
                await store.mark_task_failed(task_id, "boom")
        except AssertionError:
            # Rejected transition: the four fields must be unchanged
            # and we MUST be hitting a non-allowed pair.
            assert expected_next is None, (
                f"transition ({current!r}, {op!r}) is allowed but raised"
            )
            async with store.session() as session:
                row = (await session.execute(select(Task).where(Task.id == task_id))).scalar_one()
                after = (row.status, row.started_at, row.finished_at, row.error_msg)
            assert before == after, "rejected transition mutated state fields"
            continue

        # Successful transition: target status MUST be in the allowed set.
        assert expected_next is not None, (
            f"transition ({current!r}, {op!r}) is NOT allowed but succeeded"
        )
        async with store.session() as session:
            row = (await session.execute(select(Task).where(Task.id == task_id))).scalar_one()
        assert row.status == expected_next
        assert row.status in {"pending", "running", "success", "failed"}
        current = expected_next
