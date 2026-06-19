"""HTTP routes for the AI report module (tasks 11.3 + 11.5).

This router owns exactly two of the nine HTTP endpoints locked down
by requirement 19.1:

* ``POST /api/tasks/{task_id}/ai-report`` -- kick off an LLM analysis
  for a previously-collected task. Synchronous validation first
  (task must exist, must be in ``success``, provider whitelisted,
  model length sane); on success delegates to
  :func:`make_analyzer` + :meth:`AIAnalyzer.analyze` which is the only
  code path allowed to write into ``ai_reports``.
* ``GET /api/ai-reports/{report_id}`` -- fetch a previously generated
  report by its autoincrement id. Pure read.

The router intentionally does **not** expose ``GET /api/ai-reports``
or any "list reports for a task" endpoint -- task 5.4's
``GET /api/tasks/{task_id}`` returns the history list in its
``reports`` field, which keeps the public surface at exactly 9 routes
(requirement 19.1).

Why we return 202 + ``"pending"`` on success
--------------------------------------------

The design pseudocode locks the response shape to
``202 {"report_id": <int>, "status": "pending"}``. ``analyze`` is
awaited inline here so the row is already persisted by the time the
202 is sent; the ``"pending"`` literal exists so the wire shape is
ready to support background generation in a follow-up milestone
without breaking clients that already read the field.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse

from app.api._errors import error_detail
from app.api.deps import get_store
from app.core.logger import logger
from app.models import Task
from app.schemas.task import AIReportCreateRequest, AIReportResponse
from app.services.ai_analyzer import LLMError
from app.services.ai_providers import make_analyzer, supported_providers
from app.services.data_store import DataStore

router = APIRouter(prefix="/api", tags=["ai-reports"])

MODEL_MIN_LEN = 1
MODEL_MAX_LEN = 100


@router.post(
    "/tasks/{task_id}/ai-report",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate an AI insight report for a completed task",
)
async def create_ai_report(
    task_id: int,
    request: AIReportCreateRequest,
    store: DataStore = Depends(get_store),
) -> JSONResponse:
    """Run the AI pipeline for a task and persist exactly one report row.

    Validation order (per design §5.4):

    1. ``task_id`` exists -- 404 ``TASK_NOT_FOUND`` otherwise;
    2. ``task.status == "success"`` -- 409 ``TASK_NOT_READY`` otherwise.
       This MUST run before any LLM call so we never burn quota on a
       still-running task (requirement 14.2 / 14.12);
    3. ``provider`` (case-insensitive) belongs to the whitelist
       ``{openai, deepseek, gemini}`` -- 422 ``INVALID_PROVIDER``
       otherwise;
    4. ``model`` length lies within ``[1, 100]`` -- 422 ``INVALID_MODEL``
       otherwise.

    Any :class:`LLMError` raised by the provider is mapped to
    ``HTTP 502 AI_FAILED`` with **no** row inserted into
    ``ai_reports`` (requirement 14.10 / 14.12). Successful analyses
    return ``202 {"report_id": <int>, "status": "pending"}``.
    """

    async with store.session() as session:
        task = await session.get(Task, task_id)
        if task is None:
            raise HTTPException(
                status_code=404,
                detail=error_detail(
                    "TASK_NOT_FOUND",
                    "task not found",
                    {"task_id": task_id},
                ),
            )
        task_status = task.status

    if task_status != "success":
        raise HTTPException(
            status_code=409,
            detail=error_detail(
                "TASK_NOT_READY",
                "task is not ready for AI analysis",
                {"task_id": task_id, "status": task_status},
            ),
        )

    provider_norm = (request.provider or "").strip().lower()
    if provider_norm not in supported_providers():
        raise HTTPException(
            status_code=422,
            detail=error_detail(
                "INVALID_PROVIDER",
                "provider must be one of openai/deepseek/gemini",
                {"provider": request.provider},
            ),
        )

    model = (request.model or "").strip()
    if not (MODEL_MIN_LEN <= len(model) <= MODEL_MAX_LEN):
        raise HTTPException(
            status_code=422,
            detail=error_detail(
                "INVALID_MODEL",
                f"model length must be within [{MODEL_MIN_LEN}, {MODEL_MAX_LEN}]",
                {"model": request.model},
            ),
        )

    analyzer = make_analyzer(provider_norm, model, store)

    try:
        _, report_id = await analyzer.analyze(task_id)
    except LLMError as exc:
        logger.warning(
            "ai_report_failed",
            extra={
                "event": "ai_report_failed",
                "task_id": task_id,
                "provider": provider_norm,
                "model": model,
                "error": str(exc),
            },
        )
        raise HTTPException(
            status_code=502,
            detail=error_detail(
                "AI_FAILED",
                "LLM call failed; see server logs for details",
                {"task_id": task_id, "provider": provider_norm},
            ),
        ) from exc

    logger.info(
        "ai_report_created",
        extra={
            "event": "ai_report_created",
            "task_id": task_id,
            "report_id": report_id,
            "provider": provider_norm,
            "model": model,
        },
    )
    return JSONResponse(
        status_code=202,
        content={"report_id": report_id, "status": "pending"},
    )


@router.get(
    "/ai-reports/{report_id}",
    response_model=AIReportResponse,
    summary="Fetch a single AI report by id",
)
async def get_ai_report(
    report_id: int,
    store: DataStore = Depends(get_store),
) -> dict[str, object]:
    """Return the full report row for ``report_id``.

    Pure read, no side effects, no LLM interaction. ``404
    REPORT_NOT_FOUND`` is returned (with the standard
    ``{code, message, detail}`` envelope) when the id is unknown so
    clients can distinguish a missing report from a transient error.
    """
    report = await store.get_ai_report(report_id)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail=error_detail(
                "REPORT_NOT_FOUND",
                "ai report not found",
                {"report_id": report_id},
            ),
        )
    return {
        "id": int(report.id),
        "task_id": int(report.task_id),
        "provider": report.provider,
        "model": report.model,
        "prompt_version": report.prompt_version,
        "report_md": report.report_md,
        "created_at": report.created_at,
    }


__all__ = ["router"]
