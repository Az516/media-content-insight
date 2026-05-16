"""ORM model for the ``authors`` table.

The author table is keyed by the small-red-book ``user_id`` string. The
``notes.author_user_id`` FK points here with ``ON DELETE SET NULL`` so
that deleting an author row does not cascade-delete their notes.
"""

from __future__ import annotations

from sqlalchemy import Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Author(Base):
    """A small-red-book author (note creator)."""

    __tablename__ = "authors"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    nickname: Mapped[str | None] = mapped_column(String, nullable=True)
    avatar: Mapped[str | None] = mapped_column(String, nullable=True)
    gender: Mapped[str | None] = mapped_column(String, nullable=True)
    ip_location: Mapped[str | None] = mapped_column(String, nullable=True)
    fans_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    follow_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("(datetime('now'))")
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return f"Author(user_id={self.user_id!r}, nickname={self.nickname!r})"
