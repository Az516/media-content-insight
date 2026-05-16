"""ORM model for the ``comments`` table.

Schema highlights:

* one row per comment (both top-level and reply); replies link back to
  their parent via ``parent_comment_id`` (NULL = top-level), matching
  design §2 and requirement 9.5;
* ``is_top_hot`` is a 0/1 integer with a CHECK constraint, gating the
  ``Hot_Comment`` semantics defined in the requirements glossary;
* both FKs cascade on delete -- removing a note also removes its
  comments, and removing a parent comment also removes its replies
  (requirement 9.8);
* indexes ``idx_comments_note_id``, ``idx_comments_parent_id`` and the
  composite ``idx_comments_hot(note_id, is_top_hot)`` mirror the names
  required by task 2.1 / design §2.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Comment(Base):
    """A single comment on a note (level-1 or level-2 reply)."""

    __tablename__ = "comments"
    __table_args__ = (
        # requirement 9.7 / design §2
        CheckConstraint(
            "is_top_hot IN (0, 1)",
            name="is_top_hot_in_enum",
        ),
        Index("idx_comments_note_id", "note_id"),
        Index("idx_comments_parent_id", "parent_comment_id"),
        # Composite index supporting "hot comments per note" lookups
        # (requirement 13.4 / design §2).
        Index("idx_comments_hot", "note_id", "is_top_hot"),
    )

    comment_id: Mapped[str] = mapped_column(String, primary_key=True)
    note_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("notes.note_id", ondelete="CASCADE"),
        nullable=False,
    )
    # NULL for top-level comments. Self-FK with cascade so that deleting a
    # parent comment also deletes its replies.
    parent_comment_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("comments.comment_id", ondelete="CASCADE"),
        nullable=True,
    )
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    nickname: Mapped[str | None] = mapped_column(String, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    like_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    sub_comment_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    create_time: Mapped[str | None] = mapped_column(String, nullable=True)
    is_top_hot: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("(datetime('now'))")
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return (
            f"Comment(comment_id={self.comment_id!r}, "
            f"note_id={self.note_id!r}, "
            f"parent_comment_id={self.parent_comment_id!r}, "
            f"is_top_hot={self.is_top_hot!r})"
        )
