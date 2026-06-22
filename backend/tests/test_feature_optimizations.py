from __future__ import annotations

import sqlite3

import pytest

from app.services import ai_providers
from app.services.crawler_service import (
    _filter_comments_for_effective_notes,
    _read_mc_output_impl,
    _redact_command,
    normalise_platform,
)
from app.services.data_store import _normalise_comment_row, _normalise_note_row


def test_xhs_image_list_backfills_cover_url() -> None:
    row = _normalise_note_row(
        17,
        {
            "__platform": "xhs",
            "note_id": "abc",
            "title": "封面测试",
            "image_list": "https://cdn.example.com/a.webp,https://cdn.example.com/b.webp",
        },
    )

    assert row is not None
    assert row["note_id"] == "abc"
    assert row["cover_url"] == "https://cdn.example.com/a.webp"


def test_non_xhs_ids_are_platform_scoped() -> None:
    note = _normalise_note_row(
        1,
        {
            "__platform": "bili",
            "video_id": 123,
            "title": "B 站视频",
            "video_cover_url": "https://example.com/cover.jpg",
        },
    )
    comment = _normalise_comment_row(
        {
            "__platform": "bili",
            "comment_id": 456,
            "video_id": 123,
            "content": "想看更多",
        }
    )

    assert note is not None
    assert comment is not None
    assert note["note_id"] == "bili:123"
    assert comment["comment_id"] == "bili:456"
    assert comment["note_id"] == "bili:123"


def test_comments_are_limited_to_effective_notes_and_existing_parents() -> None:
    comments = _filter_comments_for_effective_notes(
        [
            {
                "__platform": "xhs",
                "comment_id": "top-kept",
                "note_id": "note-kept",
                "content": "top",
            },
            {
                "__platform": "xhs",
                "comment_id": "reply-kept",
                "note_id": "note-kept",
                "parent_comment_id": "top-kept",
                "content": "reply",
            },
            {
                "__platform": "xhs",
                "comment_id": "reply-dropped",
                "note_id": "note-kept",
                "parent_comment_id": "missing-parent",
                "content": "orphan",
            },
            {
                "__platform": "xhs",
                "comment_id": "other-note",
                "note_id": "note-dropped",
                "content": "outside cap",
            },
        ],
        [{"__platform": "xhs", "note_id": "note-kept", "title": "kept"}],
    )

    assert [row["comment_id"] for row in comments] == ["top-kept", "reply-kept"]


def test_media_crawler_command_redacts_cookies() -> None:
    assert _redact_command(["python", "main.py", "--cookies", "web_session=secret"]) == [
        "python",
        "main.py",
        "--cookies",
        "***",
    ]


@pytest.mark.asyncio
async def test_read_mc_output_uses_platform_specific_tables(tmp_path) -> None:
    db_path = tmp_path / "sqlite_tables.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE xhs_note (note_id TEXT, title TEXT)")
        conn.execute("INSERT INTO xhs_note VALUES ('xhs-old', 'old')")
        conn.execute("CREATE TABLE bilibili_video (video_id INTEGER, title TEXT, video_cover_url TEXT)")
        conn.execute("INSERT INTO bilibili_video VALUES (42, 'bili-new', 'https://example.com/bili.jpg')")
        conn.commit()
    finally:
        conn.close()

    notes, comments = await _read_mc_output_impl(tmp_path, platform="bili")

    assert comments == []
    assert len(notes) == 1
    assert notes[0]["__platform"] == "bili"
    assert notes[0]["video_id"] == 42


@pytest.mark.asyncio
async def test_read_mc_output_filters_cumulative_rows_to_current_keyword_and_time(tmp_path) -> None:
    db_path = tmp_path / "sqlite_tables.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE xhs_note (
                note_id TEXT,
                title TEXT,
                source_keyword TEXT,
                add_ts INTEGER,
                last_modify_ts INTEGER
            )
            """
        )
        conn.execute(
            "INSERT INTO xhs_note VALUES ('old-topic', 'old 体育', '体育', 1000, 1000)"
        )
        conn.execute(
            "INSERT INTO xhs_note VALUES ('other-topic', '智能教学', '智能教学', 5000, 5000)"
        )
        conn.execute(
            "INSERT INTO xhs_note VALUES ('current-topic', 'new 体育', '体育', 6000, 6000)"
        )
        conn.commit()
    finally:
        conn.close()

    notes, comments = await _read_mc_output_impl(
        tmp_path,
        platform="xhs",
        keyword="体育",
        min_timestamp_ms=5000,
    )

    assert comments == []
    assert [row["note_id"] for row in notes] == ["current-topic"]


def test_ai_provider_config_error_is_actionable(monkeypatch) -> None:
    monkeypatch.setattr(ai_providers.settings, "MOCK_AI_REPORT", False)
    monkeypatch.setattr(ai_providers.settings, "DEEPSEEK_API_KEY", "")

    message = ai_providers.provider_config_error("deepseek")

    assert message is not None
    assert "DEEPSEEK_API_KEY" in message


def test_platform_aliases_are_normalised() -> None:
    assert normalise_platform("douyin") == "dy"
    assert normalise_platform("bilibili") == "bili"
