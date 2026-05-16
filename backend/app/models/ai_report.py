"""ORM model for the ``ai_reports`` table.

Each successful invocation of :func:`AIAnalyzer.analyze` inserts exactly
one row here; existing rows are never modified or deleted (requirement
14.11). The table also carries the ``provider`` enum CHECK and an index
on ``task_id`` for the per-task history list used by both the API
(requirement 16.5) and the report page (requirement 16.4).
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


# Allowed ``ai_reports.provider`` values, kept in sync with the CHECK
# constraint and with :func:`make_analyzer` (task 11.2).
AI_PROVIDERS: tuple[str, ...] = ("openai", "deepseek", "gemini")


class AIReport(Base):
    """A single AI-generated insight report tied to a task."""

    __tablename__ = "ai_reports"
    __table_args__ = (
        # requirement 14.x / design §2
        CheckConstraint(
            "provider IN ('openai', 'deepseek', 'gemini')",
            name="provider_in_enum",
        ),
        Index("idx_ai_reports_task_id", "task_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    prompt_version: Mapped[str] = mapped_column(
        String, nullable=False, default="v1", server_default=text("'v1'")
    )
    report_md: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("(datetime('now'))")
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return (
            f"AIReport(id={self.id!r}, task_id={self.task_id!r}, "
            f"provider={self.provider!r}, model={self.model!r})"
        )
