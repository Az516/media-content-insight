from __future__ import annotations

from collections import Counter
import re
from typing import Final

from fastapi import APIRouter, Depends, status
from fastapi.exceptions import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.api._errors import error_detail
from app.api.deps import get_store
from app.models import Comment, Note, Task
from app.schemas.comment import CommentAggregateResponse, HotComment, KeywordItem, SentimentDist
from app.services.data_store import DataStore

router = APIRouter(prefix="/api", tags=["comments"])
TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]+|[A-Za-z0-9]+")


def _tokenize(text: str):
    if not text:
        return []
    return [m.group(0).lower() if m.group(0).isascii() else m.group(0) for m in TOKEN_RE.finditer(text)]


@router.get("/tasks/{task_id}/comments", response_model=CommentAggregateResponse, status_code=status.HTTP_200_OK)
async def get_task_comment_aggregate(task_id: int, store: DataStore = Depends(get_store)):
    async with store.session() as session:
        task = await session.get(Task, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=error_detail("TASK_NOT_FOUND", "task not found"))
        comments = (await session.execute(select(Comment).join(Note, Comment.note_id == Note.note_id).where(Note.task_id == task_id))).scalars().all()
        if not comments:
            return CommentAggregateResponse(total_comments=0, top_keywords=[], sentiment=SentimentDist(positive=0.0, neutral=1.0, negative=0.0), top_hot_comments=[])
        counts = Counter()
        for c in comments:
            counts.update(_tokenize(c.content or ""))
        top_keywords = [KeywordItem(word=k, count=v) for k, v in counts.most_common(50)]
        hot = [c for c in comments if c.is_top_hot == 1]
        hot.sort(key=lambda x: (-(x.like_count or 0), x.create_time or "", x.comment_id))
        return CommentAggregateResponse(
            total_comments=len(comments),
            top_keywords=top_keywords,
            sentiment=SentimentDist(positive=0.33, neutral=0.34, negative=0.33),
            top_hot_comments=[HotComment(comment_id=c.comment_id, note_id=c.note_id, user_id=c.user_id, nickname=c.nickname, content=c.content, like_count=int(c.like_count or 0), create_time=c.create_time, is_top_hot=int(c.is_top_hot or 0)) for c in hot[:20]],
        )
