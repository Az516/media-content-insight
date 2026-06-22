from __future__ import annotations

import json
from urllib.parse import urlparse
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Query, status
from fastapi.exceptions import HTTPException
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.api._errors import error_detail
from app.api.deps import get_store
from app.models import Author, Comment, Note, Task
from app.schemas.note import (
    AuthorBrief,
    AuthorDetail,
    CommentNode,
    NoteDetail,
    NoteDetailResponse,
    NoteListItem,
    NoteListResponse,
)
from app.services.data_store import DataStore

router = APIRouter(prefix="/api", tags=["notes"])

LIMIT_DEFAULT = 20
LIMIT_MIN = 1
LIMIT_MAX = 100
OFFSET_DEFAULT = 0
OFFSET_MIN = 0
OFFSET_MAX = 1_000_000
MEDIA_PROXY_ALLOWED_SUFFIXES = (
    "xhscdn.com",
    "bilibili.com",
    "bilivideo.com",
    "douyin.com",
    "douyinpic.com",
    "byteimg.com",
    "kuaishou.com",
    "sinaimg.cn",
    "zhimg.com",
)


@router.get("/media/proxy")
async def proxy_media(url: str = Query(..., min_length=8, max_length=2048)) -> Response:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not any(
        host == suffix or host.endswith("." + suffix)
        for suffix in MEDIA_PROXY_ALLOWED_SUFFIXES
    ):
        raise HTTPException(
            status_code=422,
            detail=error_detail("INVALID_MEDIA_URL", "media url is not allowed"),
        )

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            upstream = await client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0 Safari/537.36"
                    ),
                    "Referer": "https://www.xiaohongshu.com/",
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=error_detail("MEDIA_FETCH_FAILED", "media fetch failed"),
        ) from exc

    content_type = upstream.headers.get("content-type", "application/octet-stream")
    if upstream.status_code >= 400 or not content_type.lower().startswith("image/"):
        raise HTTPException(
            status_code=upstream.status_code if upstream.status_code >= 400 else 502,
            detail=error_detail("MEDIA_FETCH_FAILED", "media fetch failed"),
        )

    return Response(
        content=upstream.content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/tasks/{task_id}/notes", response_model=NoteListResponse, status_code=status.HTTP_200_OK)
async def list_task_notes(task_id: int, limit: int = Query(default=LIMIT_DEFAULT), offset: int = Query(default=OFFSET_DEFAULT), store: DataStore = Depends(get_store)):
    if not (LIMIT_MIN <= limit <= LIMIT_MAX) or not (OFFSET_MIN <= offset <= OFFSET_MAX):
        raise HTTPException(status_code=422, detail=error_detail("INVALID_QUERY_PARAM", "invalid query param"))
    async with store.session() as session:
        task = await session.get(Task, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=error_detail("TASK_NOT_FOUND", "task not found"))
        total = (await session.execute(select(func.count()).select_from(Note).where(Note.task_id == task_id))).scalar_one()
        rows = (await session.execute(
            select(Note, Author.user_id, Author.nickname)
            .join(Author, Note.author_user_id == Author.user_id, isouter=True)
            .where(Note.task_id == task_id)
            .order_by(Note.publish_time.is_(None).asc(), Note.publish_time.desc(), Note.note_id.asc())
            .offset(offset).limit(limit)
        )).all()
        items = [
            NoteListItem(
                note_id=n.note_id, title=n.title, type=n.type, cover_url=n.cover_url,
                liked_count=int(n.liked_count or 0), collected_count=int(n.collected_count or 0), comment_count=int(n.comment_count or 0),
                author=AuthorBrief(user_id=a_user_id, nickname=a_nickname),
            )
            for n, a_user_id, a_nickname in rows
        ]
        return NoteListResponse(items=items, total=int(total))


def _comment_tree(rows: list[Comment]) -> list[CommentNode]:
    children: dict[str, list[CommentNode]] = {}
    top: list[CommentNode] = []
    lookup: dict[str, CommentNode] = {}
    for c in rows:
        node = CommentNode(
            comment_id=c.comment_id,
            user_id=c.user_id,
            nickname=c.nickname,
            content=c.content,
            like_count=int(c.like_count or 0),
            sub_comment_count=int(c.sub_comment_count or 0),
            create_time=c.create_time,
            is_top_hot=int(c.is_top_hot or 0),
            sub_comments=[],
        )
        lookup[c.comment_id] = node
        if c.parent_comment_id is None:
            top.append(node)
        else:
            children.setdefault(c.parent_comment_id, []).append(node)
    for node in top:
        node.sub_comments = sorted(children.get(node.comment_id, []), key=lambda x: (x.create_time or "", x.comment_id))
    return sorted(top, key=lambda x: (-(x.like_count or 0), x.create_time or "", x.comment_id))


@router.get("/notes/{note_id}", response_model=NoteDetailResponse)
async def get_note_detail(note_id: str, store: DataStore = Depends(get_store)):
    async with store.session() as session:
        note = await session.get(Note, note_id)
        if note is None:
            raise HTTPException(status_code=404, detail=error_detail("NOTE_NOT_FOUND", "note not found"))
        author = await session.get(Author, note.author_user_id) if note.author_user_id else None
        rows = (await session.execute(select(Comment).where(Comment.note_id == note_id))).scalars().all()
        return NoteDetailResponse(
            note=NoteDetail(
                note_id=note.note_id,
                title=note.title,
                desc=note.desc,
                type=note.type,
                cover_url=note.cover_url,
                video_url=note.video_url,
                liked_count=int(note.liked_count or 0),
                collected_count=int(note.collected_count or 0),
                comment_count=int(note.comment_count or 0),
                share_count=int(note.share_count or 0),
                publish_time=note.publish_time,
                ip_location=note.ip_location,
                tag_list=note.tag_list,
            ),
            author=(
                AuthorDetail(
                    user_id=author.user_id,
                    nickname=author.nickname,
                    avatar=author.avatar,
                    gender=author.gender,
                    ip_location=author.ip_location,
                    fans_count=int(author.fans_count or 0),
                    follow_count=int(author.follow_count or 0),
                )
                if author
                else None
            ),
            comments=_comment_tree(rows),
        )
