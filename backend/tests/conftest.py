"""Shared pytest fixtures for the backend test suite.

Every test runs against a *fresh* on-disk SQLite database in a
temporary directory so that:

* tests cannot accidentally touch the real ``data/insight.db``;
* concurrent test runs do not race on a shared file;
* the schema is materialised by ``Base.metadata.create_all`` rather
  than relying on a migration tool we have not set up yet.

The fixtures also expose a ready-made :class:`DataStore` so individual
tests do not have to plumb the session-maker through themselves.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio

# Force the application config to load with a known JSON archive root
# *before* importing any app modules, since ``Settings`` resolves the
# path at import time. Tests redirect the archive into a temp dir
# below via monkey-patching :data:`DataStore.json_dir`.
os.environ.setdefault("HOST", "127.0.0.1")

from app.core import db as db_module  # noqa: E402
from app.models import Base  # noqa: E402
from app.services.data_store import DataStore  # noqa: E402


@pytest.fixture
def event_loop():
    """Provide a fresh asyncio event loop per test.

    pytest-asyncio defaults to ``function`` scope which already creates
    a per-test loop, but we override the policy here so a test that
    leaves a background task running cannot leak into the next test.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def store(tmp_path: Path) -> AsyncIterator[DataStore]:
    """Return a :class:`DataStore` bound to a per-test SQLite file.

    The fixture:

    1. Reconfigures the global engine onto ``<tmp_path>/test.db``;
    2. Runs ``Base.metadata.create_all`` to materialise the schema;
    3. Yields a DataStore using the global session-maker, with its
       ``json_dir`` redirected into ``<tmp_path>/json`` so archive
       writes never escape the temp tree;
    4. Disposes the engine on teardown so SQLite releases the file
       handle and pytest can clean up on Windows.
    """
    db_path = tmp_path / "test.db"
    db_module.configure_engine(db_path)
    engine = db_module.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    json_dir = tmp_path / "json"
    json_dir.mkdir(parents=True, exist_ok=True)

    store = DataStore(db_module.get_session_maker())
    store.json_dir = json_dir

    try:
        yield store
    finally:
        await db_module.dispose_engine()
