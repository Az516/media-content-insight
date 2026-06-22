from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Mapping

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.logger import logger
from app.models import AIReport, Author, Comment, Note, Task


@dataclass(frozen=True)
class AIReportInput:
    task_id: int
    provider: str
    model: str
    prompt_version: str
    report_md: str


@dataclass(frozen=True)
class AIReportSummary:
    id: int
    provider: str
    model: str
    prompt_version: str
    created_at: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def _coerce_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def _coerce_bool_int(value: Any) -> int:
    if value in (1, True):
        return 1
    if isinstance(value, str):
        if value.strip().lower() in {"1", "true", "yes", "y"}:
            return 1
    return 0


def _as_str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _as_json_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text if text else None
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return _as_str_or_none(value)


def _first_url_from_media_list(value: Any) -> str | None:
    """Extract the first usable media URL from MediaCrawler list fields."""
    if value is None:
        return None

    items: list[Any]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            items = parsed if isinstance(parsed, list) else [text]
        else:
            items = [part.strip() for part in text.split(",")]
    elif isinstance(value, list):
        items = value
    else:
        items = [value]

    for item in items:
        if isinstance(item, str):
            url = _as_str_or_none(item.strip().strip("\"'"))
            if url:
                return url
        elif isinstance(item, Mapping):
            for key in ("url", "src", "image_url", "cover_url", "original", "thumbnail"):
                url = _as_str_or_none(item.get(key))
                if url:
                    return url
    return None


def _normalise_platform(raw: Mapping[str, Any]) -> str:
    return _as_str_or_none(raw.get("__platform") or raw.get("platform")) or "xhs"


def _platform_scoped_id(platform: str, value: Any) -> str | None:
    raw_id = _as_str_or_none(value)
    if not raw_id:
        return None
    if platform == "xhs" or raw_id.startswith(f"{platform}:"):
        return raw_id
    return f"{platform}:{raw_id}"


def _extract_note_source_id(raw: Mapping[str, Any]) -> Any:
    return (
        raw.get("note_id")
        or raw.get("aweme_id")
        or raw.get("video_id")
        or raw.get("content_id")
        or raw.get("dynamic_id")
        or raw.get("id")
    )


def _extract_cover_url(raw: Mapping[str, Any]) -> str | None:
    for key in ("cover_url", "video_cover_url", "thumbnail_url"):
        url = _as_str_or_none(raw.get(key))
        if url:
            return url
    return _first_url_from_media_list(
        raw.get("image_list") or raw.get("images_list") or raw.get("images")
    )


def _extract_title(raw: Mapping[str, Any]) -> str | None:
    if "title" in raw:
        value = raw.get("title")
        return None if value is None else str(value)
    return _as_str_or_none(
        raw.get("content")
        or raw.get("content_text")
        or raw.get("desc")
    )


def _extract_desc(raw: Mapping[str, Any]) -> str | None:
    if "desc" in raw:
        value = raw.get("desc")
        return None if value is None else str(value)
    return _as_str_or_none(
        raw.get("content")
        or raw.get("content_text")
        or raw.get("title")
    )


def _extract_note_type(platform: str, raw: Mapping[str, Any]) -> str | None:
    note_type = _as_str_or_none(
        raw.get("type")
        or raw.get("video_type")
        or raw.get("aweme_type")
        or raw.get("content_type")
    )
    if platform in {"dy", "bili", "ks"}:
        return "video"
    if note_type:
        note_type = note_type.lower()
        if note_type in {"normal", "video"}:
            return note_type
    return None


def _extract_video_url(raw: Mapping[str, Any]) -> str | None:
    """Return a direct playable video URL, not a platform page URL."""
    return _as_str_or_none(
        raw.get("video_url")
        or raw.get("video_download_url")
        or raw.get("video_play_url")
        or raw.get("video_addr")
        or raw.get("play_url")
    )


def _normalise_parent_comment_id(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and value == 0:
        return None
    text = str(value).strip()
    if text in {"", "0"}:
        return None
    return text


def _normalise_note_row(task_id: int, raw: Mapping[str, Any]) -> dict[str, Any] | None:
    platform = _normalise_platform(raw)
    note_id = _platform_scoped_id(platform, _extract_note_source_id(raw))
    if not note_id:
        return None
    return {
        "note_id": note_id,
        "task_id": task_id,
        "title": _extract_title(raw),
        "desc": _extract_desc(raw),
        "type": _extract_note_type(platform, raw),
        "cover_url": _extract_cover_url(raw),
        "video_url": _extract_video_url(raw),
        "liked_count": _coerce_int(raw.get("liked_count") or raw.get("voteup_count")),
        "collected_count": _coerce_int(
            raw.get("collected_count") or raw.get("video_favorite_count")
        ),
        "comment_count": _coerce_int(
            raw.get("comment_count")
            or raw.get("comments_count")
            or raw.get("video_comment")
            or raw.get("total_replay_num")
        ),
        "share_count": _coerce_int(raw.get("share_count") or raw.get("shared_count") or raw.get("video_share_count")),
        "author_user_id": _as_str_or_none(
            raw.get("author_user_id")
            or raw.get("user_id")
            or raw.get("user_url_token")
            or raw.get("user_link")
        ),
        "publish_time": _as_str_or_none(
            raw.get("publish_time")
            or raw.get("time")
            or raw.get("create_time")
            or raw.get("created_time")
            or raw.get("create_date_time")
            or raw.get("last_update_time")
        ),
        "ip_location": _as_str_or_none(raw.get("ip_location")),
        "tag_list": _as_json_text(raw.get("tag_list")),
        "raw_json": _as_json_text(raw),
    }


def _normalise_comment_row(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    platform = _normalise_platform(raw)
    comment_id = _platform_scoped_id(platform, raw.get("comment_id") or raw.get("id"))
    note_id = _platform_scoped_id(
        platform,
        raw.get("note_id")
        or raw.get("aweme_id")
        or raw.get("video_id")
        or raw.get("content_id"),
    )
    if not comment_id or not note_id:
        return None
    parent_comment_id = _normalise_parent_comment_id(raw.get("parent_comment_id"))
    if parent_comment_id and platform != "xhs":
        parent_comment_id = _platform_scoped_id(platform, parent_comment_id)
    return {
        "comment_id": comment_id,
        "note_id": note_id,
        "parent_comment_id": parent_comment_id,
        "user_id": _as_str_or_none(raw.get("user_id") or raw.get("user_link")),
        "nickname": _as_str_or_none(raw.get("nickname") or raw.get("user_nickname")),
        "content": _as_str_or_none(raw.get("content")),
        "like_count": _coerce_int(raw.get("like_count") or raw.get("comment_like_count")),
        "sub_comment_count": _coerce_int(raw.get("sub_comment_count")),
        "create_time": _as_str_or_none(raw.get("create_time") or raw.get("publish_time") or raw.get("time")),
        "is_top_hot": _coerce_bool_int(raw.get("is_top_hot")),
    }


class DataStore:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker = session_maker
        self.json_dir: Path = settings.JSON_ARCHIVE_DIR
        self.json_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_maker() as s:
            yield s

    async def mark_task_running(self, task_id: int) -> None:
        async with self._session_maker() as session:
            task = await session.get(Task, task_id)
            assert task is not None
            assert task.status == "pending"
            task.status = "running"
            task.started_at = _utc_now_iso()
            await session.commit()

    async def mark_task_success(self, task_id: int, note_count: int, json_path: str) -> None:
        async with self._session_maker() as session:
            task = await session.get(Task, task_id)
            assert task is not None
            assert task.status == "running"
            task.status = "success"
            task.note_count = note_count
            task.json_path = json_path
            task.finished_at = _utc_now_iso()
            task.error_msg = None
            await session.commit()

    async def mark_task_failed(self, task_id: int, error_msg: str) -> None:
        async with self._session_maker() as session:
            task = await session.get(Task, task_id)
            assert task is not None
            assert task.status in {"pending", "running"}
            task.status = "failed"
            task.error_msg = error_msg[:1000]
            task.finished_at = _utc_now_iso()
            await session.commit()

    async def upsert_authors_from_raw(self, raw_notes: list[dict[str, Any]]) -> int:
        rows: dict[str, dict[str, Any]] = {}
        now = _utc_now_iso()
        for row in raw_notes:
            user_id = _as_str_or_none(row.get("user_id") or row.get("author_user_id"))
            if not user_id:
                continue
            rows[user_id] = {
                "user_id": user_id,
                "nickname": _as_str_or_none(row.get("nickname") or row.get("user_nickname")),
                "avatar": _as_str_or_none(row.get("avatar") or row.get("user_avatar")),
                "gender": _as_str_or_none(row.get("gender")),
                "ip_location": _as_str_or_none(row.get("ip_location")),
                "fans_count": _coerce_int(row.get("fans_count") or row.get("fans")),
                "follow_count": _coerce_int(
                    row.get("follow_count") or row.get("follows")
                ),
                "updated_at": now,
            }
        if not rows:
            return 0
        async with self._session_maker() as session:
            stmt = sqlite_insert(Author).values(list(rows.values()))
            stmt = stmt.on_conflict_do_update(index_elements=[Author.user_id], set_={
                "nickname": stmt.excluded.nickname,
                "avatar": stmt.excluded.avatar,
                "gender": stmt.excluded.gender,
                "ip_location": stmt.excluded.ip_location,
                "fans_count": stmt.excluded.fans_count,
                "follow_count": stmt.excluded.follow_count,
                "updated_at": stmt.excluded.updated_at,
            })
            await session.execute(stmt)
            await session.commit()
        return len(rows)

    async def upsert_notes(self, task_id: int, raw_notes: list[dict[str, Any]]) -> int:
        rows: list[dict[str, Any]] = []
        for raw in raw_notes:
            row = _normalise_note_row(task_id, raw)
            if row is not None:
                rows.append(row)
        if not rows:
            return 0
        async with self._session_maker() as session:
            stmt = sqlite_insert(Note).values(rows)
            stmt = stmt.on_conflict_do_update(index_elements=[Note.note_id], set_={
                "task_id": stmt.excluded.task_id,
                "title": stmt.excluded.title,
                "desc": stmt.excluded.desc,
                "type": stmt.excluded.type,
                "cover_url": stmt.excluded.cover_url,
                "video_url": stmt.excluded.video_url,
                "liked_count": stmt.excluded.liked_count,
                "collected_count": stmt.excluded.collected_count,
                "comment_count": stmt.excluded.comment_count,
                "share_count": stmt.excluded.share_count,
                "author_user_id": stmt.excluded.author_user_id,
                "publish_time": stmt.excluded.publish_time,
                "ip_location": stmt.excluded.ip_location,
                "tag_list": stmt.excluded.tag_list,
                "raw_json": stmt.excluded.raw_json,
            })
            await session.execute(stmt)
            await session.commit()
        return len(rows)

    async def upsert_comments(self, raw_comments: list[dict[str, Any]]) -> int:
        rows: list[dict[str, Any]] = []
        for raw in raw_comments:
            row = _normalise_comment_row(raw)
            if row is not None:
                rows.append(row)
        if not rows:
            return 0
        async with self._session_maker() as session:
            stmt = sqlite_insert(Comment).values(rows)
            stmt = stmt.on_conflict_do_update(index_elements=[Comment.comment_id], set_={
                "note_id": stmt.excluded.note_id,
                "parent_comment_id": stmt.excluded.parent_comment_id,
                "user_id": stmt.excluded.user_id,
                "nickname": stmt.excluded.nickname,
                "content": stmt.excluded.content,
                "like_count": stmt.excluded.like_count,
                "sub_comment_count": stmt.excluded.sub_comment_count,
                "create_time": stmt.excluded.create_time,
                "is_top_hot": stmt.excluded.is_top_hot,
            })
            await session.execute(stmt)
            await session.commit()
        return len(rows)

    async def archive_json(self, task_id: int) -> Path:
        async with self._session_maker() as session:
            notes = (await session.execute(select(Note).where(Note.task_id == task_id))).scalars().all()
            comments = (await session.execute(select(Comment).join(Note, Comment.note_id == Note.note_id).where(Note.task_id == task_id))).scalars().all()
        payload = {
            "task_id": task_id,
            "exported_at": _utc_now_iso(),
            "notes": [
                {
                    "note_id": n.note_id,
                    "task_id": n.task_id,
                    "title": n.title,
                    "desc": n.desc,
                    "type": n.type,
                    "cover_url": n.cover_url,
                    "video_url": n.video_url,
                    "liked_count": n.liked_count,
                    "collected_count": n.collected_count,
                    "comment_count": n.comment_count,
                    "share_count": n.share_count,
                    "author_user_id": n.author_user_id,
                    "publish_time": n.publish_time,
                    "ip_location": n.ip_location,
                    "tag_list": n.tag_list,
                    "raw_json": n.raw_json,
                    "created_at": n.created_at,
                }
                for n in notes
            ],
            "comments": [
                {
                    "comment_id": c.comment_id,
                    "note_id": c.note_id,
                    "parent_comment_id": c.parent_comment_id,
                    "user_id": c.user_id,
                    "nickname": c.nickname,
                    "content": c.content,
                    "like_count": c.like_count,
                    "sub_comment_count": c.sub_comment_count,
                    "create_time": c.create_time,
                    "is_top_hot": c.is_top_hot,
                    "created_at": c.created_at,
                }
                for c in comments
            ],
        }
        path = self.json_dir / f"{task_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return path

    async def load_for_ai(self, task_id: int):
        async with self._session_maker() as session:
            task = await session.get(Task, task_id)
            assert task is not None
            notes = (await session.execute(select(Note).where(Note.task_id == task_id))).scalars().all()
            comments = (await session.execute(select(Comment).join(Note, Comment.note_id == Note.note_id).where(Note.task_id == task_id))).scalars().all()
            return task.keyword, list(notes), list(comments)

    async def save_ai_report(self, report: AIReportInput) -> int:
        async with self._session_maker() as session:
            row = AIReport(task_id=report.task_id, provider=report.provider, model=report.model, prompt_version=report.prompt_version, report_md=report.report_md, created_at=_utc_now_iso())
            session.add(row)
            await session.commit()
            return int(row.id)

    async def list_ai_reports(self, task_id: int) -> list[AIReportSummary]:
        async with self._session_maker() as session:
            rows = (await session.execute(select(AIReport).where(AIReport.task_id == task_id).order_by(AIReport.created_at.desc(), AIReport.id.desc()))).scalars().all()
            return [AIReportSummary(id=r.id, provider=r.provider, model=r.model, prompt_version=r.prompt_version, created_at=r.created_at) for r in rows]

    async def get_ai_report(self, report_id: int) -> AIReport | None:
        """Read-only fetch of one AI report by id.

        Returns ``None`` when no row matches so the API layer can map
        the absence to ``HTTP 404 REPORT_NOT_FOUND`` (requirement 16.1)
        without leaking SQLAlchemy exceptions.
        """
        async with self._session_maker() as session:
            return await session.get(AIReport, report_id)
