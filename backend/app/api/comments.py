"""HTTP routes for the ``/api/.../comments`` family.

Currently registers a single endpoint -- ``GET
/api/tasks/{task_id}/comments`` (task 6.3) -- that aggregates the
comments belonging to a task into the three views the frontend
"评论洞察" page consumes:

* **top_keywords** (requirement 13.2): bag-of-words counts over the
  comment ``content`` field, ordered ``(count DESC, word ASC)`` and
  capped at 50 buckets.
* **sentiment** (requirement 13.3): a three-way ``positive`` /
  ``neutral`` / ``negative`` distribution whose components sum to
  ``1.0`` (±0.01).
* **top_hot_comments** (requirement 13.4): up to 20 ``is_top_hot=1``
  rows ordered ``(like_count DESC, create_time DESC)``.

MVP-quality NLP, future-proof wire shape
----------------------------------------

The aggregation deliberately avoids hard dependencies on
heavyweight NLP libraries:

* **Tokenization** uses a regex that captures runs of CJK characters
  *and* alphanumeric characters of length ≥ 2. We then drop tokens
  that match a small in-memory stopword set (Chinese particles,
  punctuation, common English filler). This is good enough to
  surface the topical words a frontend "high-frequency words" widget
  needs while keeping the dependency footprint flat -- task 1.4
  intentionally did not pull in ``jieba``.
* **Sentiment** is a rule-based count: each comment scores
  ``+1`` if it contains more positive lexicon hits than negative
  ones, ``-1`` if the inverse holds, and ``0`` otherwise (this also
  captures the "no signal in either direction" case). Proportions
  are rounded so the three numbers sum to exactly ``1.0`` even after
  floating-point operations.

Both pieces can be swapped for ``jieba`` + a real sentiment model
later without touching the response shape declared in
:mod:`app.schemas.comment`, which is the explicit goal called out in
the design doc.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Final, Iterable, Sequence

from fastapi import APIRouter, Depends, status
from fastapi.exceptions import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.api._errors import error_detail
from app.api.deps import get_store
from app.core.logger import logger
from app.models import Comment, Note, Task
from app.schemas.comment import (
    CommentAggregateResponse,
    HotComment,
    KeywordItem,
    SentimentDist,
)
from app.services.data_store import DataStore


# ``prefix="/api"`` keeps the route surface auditable in one place
# (requirement 19.1's nine-endpoint contract).
router = APIRouter(prefix="/api", tags=["comments"])


# ---------------------------------------------------------------------------
# Aggregation caps (kept as module constants so tests can import them
# without restating the numbers).
# ---------------------------------------------------------------------------

#: Maximum number of buckets returned in ``top_keywords`` (requirement 13.2).
TOP_KEYWORDS_LIMIT: Final[int] = 50

#: Maximum number of rows returned in ``top_hot_comments`` (requirement 13.4).
TOP_HOT_COMMENTS_LIMIT: Final[int] = 20

#: Minimum length (in code points) of a token before it is counted.
#:
#: A length-1 cap drops single-character tokens -- both lone Chinese
#: particles such as 的 / 了 (which we *also* list in the stopword
#: set, belt-and-braces) and stray ASCII letters such as `s` left
#: over from punctuation splitting -- so the bag-of-words stays
#: focused on topical content.
TOKEN_MIN_LEN: Final[int] = 2


# ---------------------------------------------------------------------------
# Tokenization & stopwords
# ---------------------------------------------------------------------------
#
# We rely on a single regex that matches either:
#
#   * a run of CJK Unified Ideographs (and the supplementary blocks),
#   * or a run of alphanumeric characters (lower-cased downstream).
#
# Anything else (whitespace, punctuation, emoji, control chars,
# Chinese punctuation) is treated as a separator. The character classes
# below mirror the Python ``re`` ``\w`` semantics for ASCII while
# explicitly listing the Unicode CJK ranges so the regex compiles
# identically across Python builds with or without the ``regex``
# extension.

# Compiled once at import time; ``re.UNICODE`` is implicit on Python 3.
_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf]+"  # CJK + extension A
    r"|"
    r"[A-Za-z0-9]+",                  # ASCII alphanumeric runs
)


# Small stopword list. We deliberately keep this hand-curated and
# tight; ``top_keywords`` is meant to surface *content* words, so any
# token that lands here is dropped before counting. Comparison is
# done after lower-casing alphanumeric tokens, so we list the
# alphanumeric stopwords in lower case only.
_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        # Chinese particles / pronouns / common verbs
        "的", "了", "我", "你", "他", "她", "它", "也", "和", "在", "是",
        "有", "就", "不", "这", "那", "啊", "嗯", "吗", "呢", "都", "还",
        "又", "或", "与", "及", "对", "把", "被", "比", "给", "向", "从",
        "要", "想", "会", "可", "能", "得", "着", "过", "已", "再", "之",
        "吧", "么", "哦", "呀", "哈", "哎", "嘛", "唉", "唔", "嗨",
        # Common Chinese function words that show up a lot in comments
        "好像", "怎么", "什么", "为什么", "可以", "但是", "因为", "所以",
        "如果", "虽然", "然后", "现在", "已经", "应该", "可能", "或者",
        "其实", "真的", "感觉", "觉得", "知道", "看到", "希望",
        # English fillers most common in xhs comments
        "the", "and", "for", "you", "your", "this", "that", "with",
        "have", "has", "was", "were", "but", "not", "are", "all",
        "any", "can", "from", "into", "more", "out", "than", "too",
        "very", "what", "when", "where", "why", "yes", "no", "so",
        # Standalone digits -- noise rather than signal in this domain
        "00", "000", "0000",
    }
)


def _tokenize(text: str) -> Iterable[str]:
    """Yield content-bearing tokens from ``text`` after dropping stopwords.

    The tokenizer is deterministic: identical input always yields the
    same token sequence. We lower-case alphanumeric runs (``"Cat"``
    and ``"cat"`` collapse to the same bucket) but leave Chinese runs
    untouched -- Chinese has no notion of case. Tokens shorter than
    :data:`TOKEN_MIN_LEN` codepoints are dropped before the stopword
    check so we save the membership lookup on noise.
    """
    if not text:
        return
    for match in _TOKEN_RE.finditer(text):
        token = match.group(0)
        # Lower-case ASCII tokens; Chinese is left as-is. ``isascii()``
        # is preferred over ``isalpha()`` here because we want to lower
        # mixed-case runs but keep Chinese runs unchanged.
        if token.isascii():
            token = token.lower()
        # Codepoint count, not byte count: a Chinese token of length 2
        # is two characters even though it occupies six UTF-8 bytes.
        if len(token) < TOKEN_MIN_LEN:
            continue
        if token in _STOPWORDS:
            continue
        yield token


# ---------------------------------------------------------------------------
# Sentiment lexicon (rule-based MVP; swappable for a model later)
# ---------------------------------------------------------------------------
#
# Each lexicon is intentionally short -- a few dozen high-signal terms
# in each polarity. We match by ``str.__contains__`` (substring) rather
# than tokenization because (a) Chinese sentiment terms often appear
# as bigrams nested inside larger phrases, and (b) the lexicon is
# small enough that scanning each comment once per term is cheap.

_POSITIVE_TERMS: Final[tuple[str, ...]] = (
    # Strong positive Chinese
    "好看", "喜欢", "推荐", "不错", "很棒", "超棒", "厉害", "牛", "赞",
    "爱", "心动", "种草", "绝绝子", "绝了", "完美", "舒服", "舒适",
    "惊艳", "可爱", "漂亮", "好用", "值得", "满意", "超值", "好评",
    "回购", "回购了", "好吃", "美味", "划算", "实用", "温柔", "治愈",
    "爱了", "爱住", "爱惨", "爱死", "心水",
    # Emoji / symbols
    "💕", "❤️", "❤", "🥰", "😍", "👍", "✨", "🌟", "💯",
    # Strong positive English
    "good", "great", "love", "nice", "amazing", "perfect", "wow",
    "cool", "awesome", "best",
)

_NEGATIVE_TERMS: Final[tuple[str, ...]] = (
    # Strong negative Chinese
    "不行", "不好", "失望", "踩雷", "拒绝", "讨厌", "难看", "难用",
    "难吃", "糟糕", "坑", "鸡肋", "翻车", "退货", "差评", "智商税",
    "后悔", "退款", "没用", "无语", "气死", "生气", "敷衍",
    "贵", "太贵", "性价比低", "假货", "山寨", "塑料感", "廉价",
    # Emoji / symbols
    "😡", "😠", "🤬", "👎", "💩",
    # Strong negative English
    "bad", "terrible", "awful", "worst", "hate", "ugly", "cheap",
    "fake", "trash", "boring",
)


def _classify_sentiment(content: str) -> int:
    """Classify a single comment into ``{+1, 0, -1}`` (rule-based MVP).

    Counts how many positive- and negative-lexicon substrings are
    present in ``content``. The classifier returns:

    * ``+1`` when the positive count is *strictly* greater than the
      negative count;
    * ``-1`` when the negative count is strictly greater;
    * ``0`` otherwise -- both for "neither lexicon hit" *and* for ties
      (a comment that mixes praise and complaint is genuinely
      ambiguous and the neutral bucket is the safer landing site).

    The function is intentionally O(|content| × |lexicon|); the
    lexicon is small (a few dozen entries) so the cost is dominated
    by the single ``in`` call and stays well below the I/O cost of
    fetching the comments themselves.
    """
    if not content:
        return 0
    pos = sum(1 for term in _POSITIVE_TERMS if term in content)
    neg = sum(1 for term in _NEGATIVE_TERMS if term in content)
    if pos > neg:
        return 1
    if neg > pos:
        return -1
    return 0


def _compute_sentiment_distribution(
    contents: Sequence[str],
) -> SentimentDist:
    """Return the three-way distribution for ``contents``.

    Implements requirement 13.3 (proportions in ``[0, 1]`` summing to
    ``1.0`` ±0.01) and requirement 13.8 (empty-input default of
    ``{positive: 0.0, neutral: 1.0, negative: 0.0}``). Rounding is
    performed so the three components sum *exactly* to ``1.0`` even
    when the raw proportions land on values like ``0.333...`` -- we
    round positive and negative to two decimal places, then derive
    neutral as ``1 - positive - negative`` so any residual delta
    lands in the neutral bucket without breaking the sum.
    """
    if not contents:
        # Requirement 13.8: empty case has a deterministic default.
        return SentimentDist(positive=0.0, neutral=1.0, negative=0.0)

    pos = neg = neu = 0
    for c in contents:
        score = _classify_sentiment(c or "")
        if score > 0:
            pos += 1
        elif score < 0:
            neg += 1
        else:
            neu += 1

    total = pos + neg + neu
    # Defensive: ``total`` cannot legitimately be zero here (we only
    # reach this branch when ``contents`` is non-empty), but the check
    # protects against a future caller passing an iterator that
    # happens to be empty after an upstream filter.
    if total == 0:
        return SentimentDist(positive=0.0, neutral=1.0, negative=0.0)

    # Round positive and negative independently to two decimals, then
    # derive neutral as the residual so the three components sum to
    # exactly ``1.0``. Using ``round(..., 2)`` matches the ±0.01
    # tolerance the requirement allows; deriving neutral last absorbs
    # the rounding error so the response never violates the sum.
    p = round(pos / total, 2)
    n = round(neg / total, 2)
    # Clamp to the unit interval so a perverse rounding accident
    # (e.g. ``p + n > 1.0`` after both round up) cannot push neutral
    # below zero.
    if p + n > 1.0:
        n = max(0.0, round(1.0 - p, 2))
    neutral_val = round(1.0 - p - n, 2)
    if neutral_val < 0.0:
        neutral_val = 0.0
    return SentimentDist(positive=p, neutral=neutral_val, negative=n)


# ---------------------------------------------------------------------------
# Top-keywords aggregation
# ---------------------------------------------------------------------------


def _compute_top_keywords(
    contents: Sequence[str],
) -> list[KeywordItem]:
    """Return up to :data:`TOP_KEYWORDS_LIMIT` keyword buckets.

    The buckets are ordered ``(count DESC, word ASC)`` per
    requirement 13.2. We use :class:`collections.Counter` for the
    counting pass and then a stable secondary sort for the tiebreak
    -- ``Counter.most_common`` is unstable for ties on CPython, so
    relying on it would produce non-deterministic responses in tests
    and real frontends.
    """
    counts: Counter[str] = Counter()
    for content in contents:
        if not content:
            continue
        counts.update(_tokenize(content))

    if not counts:
        return []

    # Sort by ``(-count, word)`` so descending-by-count meets the
    # primary requirement and ascending-by-word breaks ties
    # deterministically (Python's tuple comparison handles the rest).
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    capped = ordered[:TOP_KEYWORDS_LIMIT]
    return [KeywordItem(word=word, count=int(count)) for word, count in capped]


# ---------------------------------------------------------------------------
# HTTP route
# ---------------------------------------------------------------------------


@router.get(
    "/tasks/{task_id}/comments",
    response_model=CommentAggregateResponse,
    status_code=status.HTTP_200_OK,
    summary="Aggregate comment-level insight for a task",
)
async def get_task_comment_aggregate(
    task_id: int,
    store: DataStore = Depends(get_store),
) -> CommentAggregateResponse:
    """Aggregate the comments under ``task_id`` into the insight payload.

    The handler is split into clearly labelled steps so each
    requirement can be traced to a single block:

    1. **Confirm the task exists** (requirement 13.7). Missing
       ``task_id`` raises HTTP 404 with the literal ``TASK_NOT_FOUND``
       code.
    2. **Count comments** belonging to this task by joining
       ``comments`` against ``notes`` so the count is scoped to the
       task without an extra subquery.
    3. **Empty-task fast-path** (requirement 13.8). When the task
       has zero comments we return the empty defaults
       (``top_keywords=[]``, ``top_hot_comments=[]``,
       ``sentiment={positive:0.0, neutral:1.0, negative:0.0}``)
       without issuing further queries.
    4. **Fetch ``content`` only** for the keyword + sentiment
       aggregation. Pulling a single column keeps memory low even
       when a task has thousands of comments.
    5. **Fetch ``is_top_hot=1`` comments** ordered ``(like_count
       DESC, create_time DESC)``, capped at
       :data:`TOP_HOT_COMMENTS_LIMIT`.
    6. **Build and return** the :class:`CommentAggregateResponse`.
    """
    try:
        async with store.session() as session:
            # --- 1) Look up the task -------------------------------
            task = await session.get(Task, task_id)
            if task is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=error_detail(
                        code="TASK_NOT_FOUND",
                        message=f"task id={task_id} not found",
                        detail={"task_id": task_id},
                    ),
                )

            # --- 2) Count comments via comments INNER JOIN notes ---
            total_comments_stmt = (
                select(func.count())
                .select_from(Comment)
                .join(Note, Comment.note_id == Note.note_id)
                .where(Note.task_id == task_id)
            )
            total_comments: int = int(
                (await session.execute(total_comments_stmt)).scalar_one()
            )

            # --- 3) Fast-path the empty case (requirement 13.8) ----
            if total_comments == 0:
                return CommentAggregateResponse(
                    total_comments=0,
                    top_keywords=[],
                    sentiment=SentimentDist(
                        positive=0.0, neutral=1.0, negative=0.0
                    ),
                    top_hot_comments=[],
                )

            # --- 4) Pull ``content`` only for the aggregations -----
            # Selecting a single column keeps memory bounded; even a
            # task with several thousand comments fits comfortably.
            content_stmt = (
                select(Comment.content)
                .join(Note, Comment.note_id == Note.note_id)
                .where(Note.task_id == task_id)
            )
            content_result = await session.execute(content_stmt)
            # ``scalars()`` projects to the single selected column,
            # ``all()`` materialises into a list[str | None]. We
            # coerce ``None`` to ``""`` once here so the helpers below
            # can assume str-only input.
            contents: list[str] = [
                (row or "") for row in content_result.scalars().all()
            ]

            # --- 5) Top hot comments (is_top_hot=1, top 20) --------
            hot_stmt = (
                select(Comment)
                .join(Note, Comment.note_id == Note.note_id)
                .where(Note.task_id == task_id)
                .where(Comment.is_top_hot == 1)
                # ``create_time`` is text in ISO 8601 format, so a
                # lexicographic sort is equivalent to a chronological
                # sort. We ORDER BY ``(like_count DESC, create_time
                # DESC)`` per requirement 13.4 and add ``comment_id``
                # as a deterministic tiebreaker for rows that share
                # both fields (e.g. tests with hand-crafted data).
                .order_by(
                    Comment.like_count.desc(),
                    Comment.create_time.desc(),
                    Comment.comment_id.asc(),
                )
                .limit(TOP_HOT_COMMENTS_LIMIT)
            )
            hot_rows = (await session.execute(hot_stmt)).scalars().all()
    except HTTPException:
        # TASK_NOT_FOUND is the only domain-level HTTP error this
        # handler raises explicitly; let it propagate to the unified
        # handler in :mod:`app.main`.
        raise
    except (DBAPIError, SQLAlchemyError):
        logger.exception(
            "GET /api/tasks/{task_id}/comments: database error",
            extra={
                "event": "task_comment_aggregate_db_error",
                "task_id": task_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail(
                code="INTERNAL_ERROR",
                message="database error while aggregating comments",
            ),
        )

    # --- 6) Build the response model -----------------------------
    top_keywords = _compute_top_keywords(contents)
    sentiment = _compute_sentiment_distribution(contents)
    top_hot_comments = [
        HotComment(
            comment_id=row.comment_id,
            note_id=row.note_id,
            user_id=row.user_id,
            nickname=row.nickname,
            content=row.content,
            like_count=int(row.like_count or 0),
            create_time=row.create_time,
            is_top_hot=int(row.is_top_hot or 0),
        )
        for row in hot_rows
    ]

    return CommentAggregateResponse(
        total_comments=total_comments,
        top_keywords=top_keywords,
        sentiment=sentiment,
        top_hot_comments=top_hot_comments,
    )
