"""FastAPI dependency providers.

This module centralises the construction of service-layer objects so
route handlers in :mod:`app.api` can stay focused on HTTP concerns. It
deliberately keeps the dependency tree shallow:

* :func:`get_store` builds a fresh :class:`DataStore` per request,
  bound to the global :class:`async_sessionmaker` that
  :mod:`app.core.db` exposes. ``DataStore`` is itself stateless (it
  only holds a reference to the session factory), so per-request
  construction is cheap and avoids subtle issues with sharing
  sessions across requests.
* :func:`get_crawler` chains on top of ``get_store`` so the
  :class:`CrawlerService` instance and the surrounding background-task
  runner observe the *same* :class:`DataStore` (and therefore the
  same connection pool / engine) throughout the lifetime of a single
  request. This guarantees the foreground and background work see a
  consistent view of the database.
"""

from __future__ import annotations

from fastapi import Depends

from app.core.db import get_session_maker
from app.services.crawler_service import CrawlerService
from app.services.data_store import DataStore


def get_store() -> DataStore:
    """Return a fresh :class:`DataStore` bound to the global session-maker.

    ``DataStore`` is intentionally lightweight (it only stores a
    reference to the ``async_sessionmaker``) so building one per
    request keeps the code path simple and avoids accidentally sharing
    request-scoped state between concurrent callers.
    """
    return DataStore(get_session_maker())


def get_crawler(
    store: DataStore = Depends(get_store),
) -> CrawlerService:
    """Return a :class:`CrawlerService` reusing the request-scoped store.

    Sharing the same :class:`DataStore` instance with the route handler
    matters for two reasons:

    1. The background task scheduled via ``BackgroundTasks`` reads /
       writes the same ORM tables touched by the synchronous code path
       in the same request, so they must agree on which engine /
       session-maker to use.
    2. Tests can override ``get_store`` exactly once and have the
       override automatically propagate to the crawler dependency,
       avoiding the duplicate wiring that would otherwise be needed.
    """
    return CrawlerService(store)
