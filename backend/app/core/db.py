"""Async SQLAlchemy engine and session plumbing.

This module owns the global async engine plus the matching
:class:`async_sessionmaker`. It exposes three things callers actually
need:

* :func:`get_engine` -- the lazily-constructed :class:`AsyncEngine`;
* :data:`AsyncSessionLocal` (via :func:`get_session_maker`) -- an
  ``async_sessionmaker[AsyncSession]`` for opening sessions;
* :func:`init_db` -- creates ``data/insight.db`` (and any missing
  parent directories) and runs ``Base.metadata.create_all``;
* :func:`dispose_engine` -- closes the engine, useful in tests and
  during graceful shutdown.

Design notes / why this shape
-----------------------------

* SQLite enforces foreign keys only when ``PRAGMA foreign_keys=ON`` is
  issued *per connection*. We therefore attach a ``connect`` event hook
  to the underlying ``Engine.sync_engine`` that issues the PRAGMA
  immediately after the DBAPI connection is established. This is the
  recommended SQLAlchemy pattern for SQLite + FK enforcement.
* The default DB path is ``<repo_root>/data/insight.db``. We do NOT make
  it configurable through the public Settings surface yet because task
  2.1's requirement 20.2 explicitly fixes the location to ``data/``.
* The engine and session-maker are created lazily so importing this
  module never touches the filesystem. Tests (and any future
  alternative storage backends) can rebind them through
  :func:`configure_engine` before :func:`init_db` runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logger import logger

# Importing the models package registers every ORM class on
# ``Base.metadata``, which :func:`init_db` then materialises into DDL.
from app.models import Base


# ---------------------------------------------------------------------------
# Default DB location
# ---------------------------------------------------------------------------

#: Default path of the on-disk SQLite database, locked to ``data/insight.db``
#: by requirement 20.2.
DEFAULT_DB_PATH: Path = settings.repo_root / "data" / "insight.db"


def _build_sqlite_url(db_path: Path) -> str:
    """Return an ``aiosqlite`` URL that points at ``db_path``.

    SQLAlchemy's SQLite URLs use POSIX-style separators on every
    platform, so we explicitly call :meth:`Path.as_posix` on the
    absolute path to avoid Windows ``\\`` showing up inside the URL.
    """
    return f"sqlite+aiosqlite:///{db_path.absolute().as_posix()}"


# ---------------------------------------------------------------------------
# Engine / session-maker singletons
# ---------------------------------------------------------------------------

_engine: Optional[AsyncEngine] = None
_session_maker: Optional[async_sessionmaker[AsyncSession]] = None
_db_path: Path = DEFAULT_DB_PATH


def configure_engine(db_path: Path | str | None = None) -> AsyncEngine:
    """(Re)configure the global engine to point at ``db_path``.

    Tests rely on this to swap the on-disk DB for a per-test temp file
    or an in-memory database. Calling it disposes any previously
    configured engine to avoid lingering connections.
    """
    global _engine, _session_maker, _db_path

    if db_path is None:
        target = DEFAULT_DB_PATH
    else:
        target = Path(db_path)
    _db_path = target

    if _engine is not None:
        # Best-effort sync close; ``dispose_engine`` is the proper async
        # alternative but ``configure_engine`` is itself synchronous.
        try:
            _engine.sync_engine.dispose()
        except Exception:  # pragma: no cover - defensive only
            logger.exception("failed to dispose previous engine")

    _engine = create_async_engine(
        _build_sqlite_url(target),
        # SQLite + aiosqlite plays poorly with connection pooling under
        # async workloads; ``future=True`` keeps us on the 2.x style.
        future=True,
        # Echoing SQL is noisy by default; flip via SQLALCHEMY_ECHO env
        # var or a future Settings flag if needed.
        echo=False,
    )

    # Enable FK enforcement on every new connection. Without this PRAGMA
    # SQLite silently ignores ``ON DELETE CASCADE`` / ``SET NULL``.
    @event.listens_for(_engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(  # pragma: no cover - tiny hook
        dbapi_connection, connection_record
    ) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    _session_maker = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    return _engine


def get_engine() -> AsyncEngine:
    """Return the singleton :class:`AsyncEngine`, building it on first call."""
    if _engine is None:
        configure_engine(DEFAULT_DB_PATH)
    assert _engine is not None  # for the type-checker
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Return the singleton :class:`async_sessionmaker`."""
    if _session_maker is None:
        configure_engine(DEFAULT_DB_PATH)
    assert _session_maker is not None  # for the type-checker
    return _session_maker


def get_db_path() -> Path:
    """Return the absolute path of the SQLite file currently in use."""
    return _db_path


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create the SQLite file and all tables / indexes.

    Idempotent -- safe to call repeatedly. ``CREATE TABLE IF NOT EXISTS``
    semantics are produced by SQLAlchemy's ``checkfirst=True`` (the
    default for :meth:`MetaData.create_all`).
    """
    engine = get_engine()
    db_path = get_db_path()

    # Ensure the parent directory (e.g. ``<repo>/data/``) exists before
    # SQLite opens the file. Missing directories raise ``OperationalError``.
    db_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "init_db",
        extra={
            "event": "init_db",
            "db_path": str(db_path),
        },
    )

    async with engine.begin() as conn:
        # Verify the FK PRAGMA is on this connection too -- handy for
        # diagnostics and a cheap sanity check.
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    """Dispose the global engine.

    Called from the FastAPI lifespan shutdown branch and from tests
    that need to release the underlying SQLite file before deleting it.
    """
    global _engine, _session_maker

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_maker = None
