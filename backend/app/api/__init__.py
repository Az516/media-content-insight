"""HTTP routing layer for media-content-insight.

Each module in this package owns exactly one thematic group of routes
(``tasks``, ``notes``, ``comments``, ``ai_reports``). The aggregate set
of routes mounted by :func:`app.main.create_app` is locked down by
requirement 19.1 -- adding a new module here without updating
:doc:`design.md` and :doc:`requirements.md` would silently widen the
public route surface beyond the 9-endpoint contract.
"""

from app.api.comments import router as comments_router
from app.api.notes import router as notes_router
from app.api.tasks import router as tasks_router

__all__ = ["comments_router", "notes_router", "tasks_router"]
