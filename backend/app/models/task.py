"""ORM model for the ``tasks`` table.

The schema mirrors design §2 (the DDL block) and the requirements that
constrain it:

* requirement 3.6: ``status`` is restricted to
  ``{pending, running, success, failed}`` via a CHECK constraint;
* requirement 1.5 / 2.1: ``max_notes`` defaults to 20 and
  ``note_count`` defaults to 0 so that newly-inserted ``pending`` rows
  start in a well-defined shape;
* requirement 9.8: deleting a ``tasks`` row cascades to ``notes`` and
  ``ai_reports`` (the FK with ``ON DELETE CASCADE`` lives on the child
  tables, see ``Note`` and ``AIReport``).
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# Allowed ``tasks.status`` values, kept in sync with the CHECK constraint.
TASK_STATUSES: tuple[str, ...] = ("pending", "running", "success", "failed")


class Task(Base):
    """A single end-to-end keyword crawl task."""

    __tablename__ = "tasks"
    __table_args__ = (
        # requirement 3.6
        CheckConstraint(
            "status IN ('pending', 'running', 'success', 'failed')",
            name="status_in_enum",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default=text("'pending'")
    )
    note_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    max_notes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=20, server_default=text("20")
    )
    started_at: Mapped[str | None] = mapped_column(String, nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    json_path: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("(datetime('now'))")
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return (
            f"Task(id={self.id!r}, keyword={self.keyword!r}, "
            f"status={self.status!r}, note_count={self.note_count!r})"
        )
