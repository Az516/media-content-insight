"""SQLAlchemy declarative base.

A single :class:`Base` is shared by every ORM model in
:mod:`app.models`. Keeping it in a dedicated module avoids circular imports
when ``app.core.db`` (which only needs ``Base.metadata``) is imported in
parallel with the model modules themselves.

A :class:`MetaData` naming convention is configured up-front so that
auto-generated constraint and index names are deterministic. Indexes that
must match the names listed in the design document
(``idx_notes_task_id`` etc.) are still defined explicitly via
``Index(...)`` in ``__table_args__``; the convention only governs
non-named constraints (e.g. SQLAlchemy's auto-generated primary-key
constraints).
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


# Deterministic constraint / index names. SQLite's CHECK and FK
# constraint names are mostly opaque, but the convention helps Alembic
# autogenerate diff produce stable output should we ever wire it up.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model in this project."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
