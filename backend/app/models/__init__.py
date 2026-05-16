"""SQLAlchemy ORM models for xhs-content-insight.

Importing this package side-effect registers every model class on
``Base.metadata`` so that :func:`Base.metadata.create_all` (called from
:mod:`app.core.db`) sees the full schema regardless of which models the
caller imported directly.
"""

from app.models.ai_report import AI_PROVIDERS, AIReport
from app.models.author import Author
from app.models.base import Base
from app.models.comment import Comment
from app.models.note import NOTE_TYPES, Note
from app.models.task import TASK_STATUSES, Task

__all__ = [
    "AI_PROVIDERS",
    "AIReport",
    "Author",
    "Base",
    "Comment",
    "NOTE_TYPES",
    "Note",
    "TASK_STATUSES",
    "Task",
]
