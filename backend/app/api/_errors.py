"""Shared helpers for building the project-wide error envelope.

The unified exception handler in :mod:`app.main` recognises the
``{code, message, detail}`` shape on ``HTTPException.detail`` and
renders it verbatim into the response body. Centralising the
construction in one helper keeps the envelope identical across every
route handler so the contract is trivial to audit.

The helper is intentionally tiny -- no Pydantic, no imports beyond
``typing`` -- because every API module imports it and we want the
overhead to stay near zero.
"""

from __future__ import annotations

from typing import Any


def error_detail(
    code: str, message: str, detail: Any = None
) -> dict[str, Any]:
    """Build the structured ``HTTPException.detail`` payload.

    Parameters
    ----------
    code:
        Stable string error code (e.g. ``"INVALID_QUERY_PARAM"``,
        ``"TASK_NOT_FOUND"``). The frontend uses this value for
        branching, so the strings are part of the API contract.
    message:
        Human-readable description of the failure. Safe to surface in
        the UI as a fallback when the frontend has no localised string
        for the ``code``.
    detail:
        Optional additional context (typically a small dict) the
        client may use to render a richer error. Pass ``None`` -- not
        an empty dict -- when there is nothing extra to send.

    Returns
    -------
    dict
        A new dictionary with exactly the three keys ``code``,
        ``message`` and ``detail``.
    """
    return {"code": code, "message": message, "detail": detail}
