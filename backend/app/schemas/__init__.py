"""Pydantic request / response schemas backing :mod:`app.api`.

Schema modules in this package are intentionally thin -- they only
declare the wire shape of HTTP request / response bodies. All
domain-level validation (range checks, business invariants, error-code
mapping to ``INVALID_KEYWORD`` / ``OVER_LIMIT`` / ``TASK_BUSY`` etc.)
lives in :mod:`app.api` so the project-specific error envelope stays
under our control rather than being preempted by Pydantic's generic
``VALIDATION_ERROR``.
"""

from app.schemas.comment import (
    CommentAggregateResponse,
    HotComment,
    KeywordItem,
    SentimentDist,
)
from app.schemas.note import AuthorBrief, NoteListItem, NoteListResponse
from app.schemas.task import TaskCreateRequest, TaskCreateResponse

__all__ = [
    "AuthorBrief",
    "CommentAggregateResponse",
    "HotComment",
    "KeywordItem",
    "NoteListItem",
    "NoteListResponse",
    "SentimentDist",
    "TaskCreateRequest",
    "TaskCreateResponse",
]
