"""Wire schemas for the ``/api/.../notes`` endpoint family.

Implements the response shapes for both note-related endpoints:

* ``GET /api/tasks/{task_id}/notes`` (task 6.1) -- the paginated
  task-scoped list, modelled by :class:`NoteListResponse` /
  :class:`NoteListItem` / :class:`AuthorBrief`.
* ``GET /api/notes/{note_id}`` (task 6.2) -- the per-note detail
  payload, modelled by :class:`NoteDetailResponse` /
  :class:`NoteDetail` / :class:`AuthorDetail` / :class:`CommentNode`.

The handlers in :mod:`app.api.notes` build these models from ORM
rows after running their own queries; the schemas only declare the
*response* body shape so we never accidentally hand validation
duties to Pydantic for a response code that requires a
project-specific error envelope.

Why we keep the field constraints permissive
--------------------------------------------

Mirror the rationale from :mod:`app.schemas.task`: Pydantic ships
generic 422 ``VALIDATION_ERROR`` responses when a ``Field(..., ge=...,
le=...)`` constraint fails, but requirement 11.4 mandates the literal
``INVALID_QUERY_PARAM`` code for out-of-range ``limit`` / ``offset``.
Accordingly the *query parameters* of the endpoint are validated by
hand inside the route handler; the schemas in this module only model
the *response* body so we only need to declare types.

``CommentNode`` self-reference
------------------------------

``CommentNode.sub_comments`` is typed ``list["CommentNode"]`` so a
top-level node can carry a flat list of replies (the design only
exposes two levels). The forward reference is resolved by the
``CommentNode.model_rebuild()`` call at module import time so
:class:`NoteDetailResponse` validation works the first time it is
exercised.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AuthorBrief(BaseModel):
    """Compact author projection embedded in each note list item.

    Both fields are nullable because :class:`Note.author_user_id` is a
    nullable FK with ``ON DELETE SET NULL`` -- a note may legitimately
    sit in the database without a linked author row, in which case
    both fields surface as ``None`` rather than triggering a 500.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str | None = Field(
        default=None,
        description=(
            "Small-red-book author id. ``None`` when the note has no "
            "linked author row (the FK is nullable)."
        ),
    )
    nickname: str | None = Field(
        default=None,
        description=(
            "Author display name. ``None`` when the linked author row "
            "carries no nickname or no author is linked."
        ),
    )


class NoteListItem(BaseModel):
    """One row of the paginated ``/api/tasks/{task_id}/notes`` response.

    Field selection follows requirement 11.1 verbatim. Counter fields
    are non-nullable integers because the underlying ORM columns
    declare ``NOT NULL DEFAULT 0`` (see :mod:`app.models.note`).
    """

    model_config = ConfigDict(extra="forbid")

    note_id: str = Field(..., description="Primary key of the note.")
    title: str | None = Field(
        default=None,
        description="Note title. ``None`` when the crawler returned no title.",
    )
    type: str | None = Field(
        default=None,
        description="Note type, ``'normal'`` or ``'video'`` when present.",
    )
    cover_url: str | None = Field(
        default=None,
        description="Cover image URL. ``None`` when no cover is available.",
    )
    liked_count: int = Field(
        ...,
        description="Number of likes on the note (defaults to 0 in DB).",
    )
    collected_count: int = Field(
        ...,
        description="Number of saves/collects on the note.",
    )
    comment_count: int = Field(
        ...,
        description="Number of comments on the note.",
    )
    author: AuthorBrief = Field(
        ...,
        description=(
            "Compact author projection. Both inner fields are nullable; "
            "the object itself is always present so clients can render "
            "a placeholder uniformly."
        ),
    )


class NoteListResponse(BaseModel):
    """Wire shape of ``GET /api/tasks/{task_id}/notes``.

    ``total`` reflects the total number of notes attached to the
    target task (NOT the size of the current page) so the frontend
    can drive pagination without issuing a second request
    (requirement 11.1).
    """

    model_config = ConfigDict(extra="forbid")

    items: list[NoteListItem] = Field(
        default_factory=list,
        description=(
            "Page of notes ordered by ``publish_time DESC`` with "
            "``note_id ASC`` as the deterministic tiebreaker."
        ),
    )
    total: int = Field(
        ...,
        description=(
            "Total number of notes attached to the task (across all "
            "pages). Always ``>= len(items)``."
        ),
    )


# ---------------------------------------------------------------------------
# Note detail (task 6.2) -- ``GET /api/notes/{note_id}``
# ---------------------------------------------------------------------------


class NoteDetail(BaseModel):
    """The ``note`` block of ``GET /api/notes/{note_id}``.

    Field selection mirrors design §3.5 verbatim. Nullable columns on
    :class:`app.models.note.Note` surface as ``Optional`` here so that
    a partially-populated row -- e.g. one whose crawler payload omitted
    ``desc`` or ``video_url`` -- still validates against this schema.

    ``tag_list`` is intentionally typed ``str | None`` rather than
    ``list[str] | None``: the design notes that the column stores a
    "JSON 数组字符串" (a JSON-encoded array as a string), and the
    backend deliberately *passes the value through unchanged* so the
    frontend can decide whether and how to parse it. Decoding it here
    would risk returning a 500 the first time a row carried malformed
    JSON.
    """

    model_config = ConfigDict(extra="forbid")

    note_id: str = Field(..., description="Primary key of the note.")
    title: str | None = Field(
        default=None,
        description="Note title (``None`` when the crawler returned no title).",
    )
    desc: str | None = Field(
        default=None,
        description="Note body / description text.",
    )
    type: str | None = Field(
        default=None,
        description="Note type, ``'normal'`` or ``'video'`` when present.",
    )
    cover_url: str | None = Field(
        default=None,
        description="Cover image URL. ``None`` when no cover is available.",
    )
    video_url: str | None = Field(
        default=None,
        description=(
            "Video URL when ``type == 'video'``; ``None`` for image notes "
            "or when the crawler did not surface a URL."
        ),
    )
    source_url: str | None = Field(
        default=None,
        description=(
            "Original platform page URL for opening the source post in "
            "the user's browser. This is intentionally separate from "
            "``video_url`` because platform pages are not playable media files."
        ),
    )
    liked_count: int = Field(
        ...,
        description="Number of likes on the note (defaults to 0 in DB).",
    )
    collected_count: int = Field(
        ...,
        description="Number of saves/collects on the note.",
    )
    comment_count: int = Field(
        ...,
        description="Number of comments on the note.",
    )
    share_count: int = Field(
        ...,
        description="Number of shares on the note.",
    )
    publish_time: str | None = Field(
        default=None,
        description=(
            "ISO 8601 timestamp of when the note was published. ``None`` "
            "when the crawler payload carried no publish time."
        ),
    )
    ip_location: str | None = Field(
        default=None,
        description="IP-derived geographic location, when surfaced by the platform.",
    )
    tag_list: str | None = Field(
        default=None,
        description=(
            "JSON-encoded array of tag strings. Returned as-is so the "
            "frontend can decide whether to parse it; ``None`` when the "
            "crawler payload carried no tags."
        ),
    )


class AuthorDetail(BaseModel):
    """The ``author`` block of ``GET /api/notes/{note_id}``.

    Mirrors the columns on :class:`app.models.author.Author`. Every
    non-PK column is nullable so a partially-populated author row -- a
    common case for accounts whose profile the crawler never fetched
    in full -- still validates. The PK ``user_id`` is required because
    the ``author`` block itself is omitted from the response when the
    note has no linked author row (see :class:`NoteDetailResponse`).
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., description="Small-red-book author id.")
    nickname: str | None = Field(default=None)
    avatar: str | None = Field(default=None)
    gender: str | None = Field(default=None)
    ip_location: str | None = Field(default=None)
    fans_count: int = Field(
        default=0,
        description="Number of fans the author has (defaults to 0 in DB).",
    )
    follow_count: int = Field(
        default=0,
        description="Number of accounts the author follows.",
    )


class CommentNode(BaseModel):
    """One node in the comment tree returned by ``GET /api/notes/{note_id}``.

    The same shape is reused for both top-level comments and their
    replies. Top-level comments may carry a populated
    ``sub_comments`` list whose entries are themselves
    :class:`CommentNode` instances; replies always carry an empty
    ``sub_comments`` list because the design exposes only two levels
    (requirement 12.2).

    Per requirement 12.3 every node retains the eight bookkeeping
    fields ``comment_id``, ``user_id``, ``nickname``, ``content``,
    ``like_count``, ``sub_comment_count``, ``create_time`` and
    ``is_top_hot`` regardless of nesting level.
    """

    model_config = ConfigDict(extra="forbid")

    comment_id: str = Field(..., description="Primary key of the comment.")
    user_id: str | None = Field(default=None)
    nickname: str | None = Field(default=None)
    content: str | None = Field(default=None)
    like_count: int = Field(
        ...,
        description="Number of likes on the comment (defaults to 0 in DB).",
    )
    sub_comment_count: int = Field(
        ...,
        description="Number of replies recorded on the comment.",
    )
    create_time: str | None = Field(
        default=None,
        description="ISO 8601 timestamp of when the comment was authored.",
    )
    is_top_hot: int = Field(
        ...,
        description=(
            "``1`` for hot replies surfaced by the crawler, ``0`` "
            "otherwise. Top-level comments always carry ``0``."
        ),
    )
    sub_comments: list["CommentNode"] = Field(
        default_factory=list,
        description=(
            "Replies nested under this comment, ordered by "
            "``(create_time ASC, comment_id ASC)`` (requirement 12.2). "
            "Always empty for nodes that are themselves replies."
        ),
    )


class NoteDetailResponse(BaseModel):
    """Wire shape of ``GET /api/notes/{note_id}``.

    Top-level comments populate ``comments`` ordered by
    ``(like_count DESC, create_time DESC, comment_id ASC)`` per
    requirement 12.2; each top-level node then nests its replies
    under ``sub_comments`` ordered by
    ``(create_time ASC, comment_id ASC)``.
    """

    model_config = ConfigDict(extra="forbid")

    note: NoteDetail = Field(..., description="The note itself.")
    author: AuthorDetail | None = Field(
        default=None,
        description=(
            "Author profile, or ``None`` when the note has no linked "
            "author row (FK is nullable / set-null on author delete)."
        ),
    )
    comments: list[CommentNode] = Field(
        default_factory=list,
        description=(
            "Top-level comments ordered by ``(like_count DESC, "
            "create_time DESC, comment_id ASC)``. Empty list when the "
            "note has no comments."
        ),
    )


# Resolve the forward reference declared on ``CommentNode.sub_comments``
# so :class:`NoteDetailResponse` can be validated without further setup.
# ``model_rebuild`` is idempotent and safe to call at import time.
CommentNode.model_rebuild()
