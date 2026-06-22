from __future__ import annotations

from pathlib import Path

import pytest

from app.core import db as db_module


@pytest.mark.asyncio
async def test_init_db_marks_orphaned_active_tasks_failed(tmp_path: Path) -> None:
    db_module.configure_engine(tmp_path / "test.db")
    try:
        await db_module.init_db()
        engine = db_module.get_engine()

        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                """
                INSERT INTO tasks (keyword, status, max_notes)
                VALUES
                    ('pending-keyword', 'pending', 20),
                    ('running-keyword', 'running', 20),
                    ('done-keyword', 'success', 20),
                    ('failed-keyword', 'failed', 20)
                """
            )

        await db_module.init_db()

        async with engine.connect() as conn:
            rows = (
                await conn.exec_driver_sql(
                    """
                    SELECT keyword, status, error_msg, finished_at
                    FROM tasks
                    ORDER BY id
                    """
                )
            ).all()

        by_keyword = {row[0]: row for row in rows}
        assert by_keyword["pending-keyword"].status == "failed"
        assert by_keyword["running-keyword"].status == "failed"
        assert by_keyword["pending-keyword"].error_msg.startswith("interrupted:")
        assert by_keyword["running-keyword"].finished_at is not None
        assert by_keyword["done-keyword"].status == "success"
        assert by_keyword["failed-keyword"].status == "failed"
    finally:
        await db_module.dispose_engine()
