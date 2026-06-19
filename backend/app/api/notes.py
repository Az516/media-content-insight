from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from fastapi.exceptions import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.api._errors import error_detail
from app.api.deps import get_store
from app.models import Author, Comment, Note, Task
from app.schemas.note import (
    AuthorBrief,
    AuthorDetail,
    CommentNode,
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
            note=note,
            author=AuthorDetail(**author.__dict__) if author else None,
            comments=_comment_tree(rows),
        )
