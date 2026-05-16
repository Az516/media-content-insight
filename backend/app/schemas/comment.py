"""Wire schemas for comment-related endpoints.

Currently scoped to the response body of
``GET /api/tasks/{task_id}/comments`` (task 6.3 / requirement 13). The
shapes mirror design §3.6 verbatim so the wire contract is decoupled
from how the aggregation is computed: a future swap from the MVP
rule-based scorer + regex tokenizer to a real model + ``jieba``
tokenizer can ship without touching this module.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class KeywordItem(BaseModel):
    """One bucket in the ``top_keywords`` list (requirement 13.2).

    The ``word`` is the keyword token (Chinese run or lower-cased
    alphanumeric run); ``count`` is the number of times it occurred
    across the comments belonging to the task. The list is capped at
    50 buckets and ordered ``(count DESC, word ASC)``.
    """

    model_config = ConfigDict(extra="forbid")

    word: str = Field(..., description="Keyword token, raw casing for Chinese.")
    count: int = Field(
        ...,
        ge=1,
        description="Number of occurrences across all comments of the task.",
    )


class SentimentDist(BaseModel):
    """Three-way sentiment distribution (requirement 13.3).

    Each field is a float in ``[0.0, 1.0]`` and the three values sum to
    ``1.0`` within ±0.01 tolerance. The empty-comment defaults are
    ``{positive: 0.0, neutral: 1.0, negative: 0.0}`` (requirement 13.8).
    """

    model_config = ConfigDict(extra="forbid")

    positive: float = Field(..., ge=0.0, le=1.0)
    neutral: float = Field(..., ge=0.0, le=1.0)
    negative: float = Field(..., ge=0.0, le=1.0)


class HotComment(BaseModel):
    """One row in ``top_hot_comments`` (requirement 13.4).

    Only ``is_top_hot = 1`` comments make it into the response, and
    they are ordered ``(like_count DESC, create_time DESC)``. The
    ``is_top_hot`` field is therefore always ``1`` in practice but we
    keep it on the wire shape so the shape matches the underlying ORM
    row 1:1 (and a future relaxation -- e.g. surfacing the flag
    alongside non-hot comments -- does not require a schema bump).
    """

    model_config = ConfigDict(extra="forbid")

    comment_id: str
    note_id: str
    user_id: str | None = None
    nickname: str | None = None
    content: str | None = None
    like_count: int = Field(default=0, ge=0)
    create_time: str | None = None
    is_top_hot: int = Field(default=1, ge=0, le=1)


class CommentAggregateResponse(BaseModel):
    """Response body for ``GET /api/tasks/{task_id}/comments``.

    Fields and semantics come from requirements 13.1, 13.2, 13.3, 13.4
    and 13.8 (the empty-comment default branch). The schema does NOT
    impose a maximum length on ``top_keywords`` / ``top_hot_comments``
    -- those caps live in the endpoint handler so the schema can be
    reused unchanged should the limits ever become configurable.
    """

    model_config = ConfigDict(extra="forbid")

    total_comments: int = Field(
        ..., ge=0, description="Number of comments belonging to the task."
    )
    top_keywords: list[KeywordItem] = Field(default_factory=list)
    sentiment: SentimentDist
    top_hot_comments: list[HotComment] = Field(default_factory=list)
