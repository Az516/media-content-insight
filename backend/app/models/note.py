"""ORM model for the ``notes`` table.

Schema highlights (see design §2 and the matching requirements):

* primary key is the small-red-book ``note_id`` string (requirement 9.1);
* ``task_id`` FK cascades on delete so that purging a task drops all of
  its notes (requirement 9.8);
* ``author_user_id`` FK uses ``ON DELETE SET NULL`` -- deleting an author
  deliberately does NOT remove their notes (requirement 9.8);
* ``type`` is restricted to ``{normal, video}`` via a CHECK constraint
  (requirement 9.7 contracts it to the design §2 enum);
* indexes ``idx_notes_task_id`` and ``idx_notes_author_id`` mirror the
  names locked down in design §2 / task 2.1.
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


# Allowed ``notes.type`` values, kept in sync with the CHECK constraint.
NOTE_TYPES: tuple[str, ...] = ("normal", "video")


class Note(Base):
    """A single small-red-book note collected for a given task."""

    __tablename__ = "notes"
    __table_args__ = (
        # requirement 9.7 / design §2
        CheckConstraint(
            "type IN ('normal', 'video')",
            name="type_in_enum",
        ),
        # design §2 indexes -- names must match exactly so that subsequent
        # tasks (e.g. 2.4 query plans, manual SQL audits) can rely on them.
        Index("idx_notes_task_id", "task_id"),
        Index("idx_notes_author_id", "author_user_id"),
    )

    note_id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str | None] = mapped_column(String, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String, nullable=True)
    video_url: Mapped[str | None] = mapped_column(String, nullable=True)
    liked_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    collected_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    comment_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    share_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    author_user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("authors.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    publish_time: Mapped[str | None] = mapped_column(String, nullable=True)
    ip_location: Mapped[str | None] = mapped_column(String, nullable=True)
    # ``tag_list`` is stored as a JSON-encoded array string; the column type
    # stays ``Text`` because SQLite has no native array type.
    tag_list: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("(datetime('now'))")
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return (
            f"Note(note_id={self.note_id!r}, task_id={self.task_id!r}, "
            f"title={self.title!r})"
        )
