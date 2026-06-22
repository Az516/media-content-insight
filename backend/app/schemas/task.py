"""Wire schemas for task-related endpoints.

The request / response shapes for ``POST /api/tasks`` (task 5.1) and
``GET /api/tasks`` (task 5.3) are defined here. Subsequent tasks (5.4,
5.5) will extend this module with the schemas backing the remaining
task endpoints.

Why we keep the field constraints permissive
--------------------------------------------

Pydantic ships generic 422 ``VALIDATION_ERROR`` responses when a
``Field(..., ge=1, le=20)`` style constraint fails. The project-wide
error contract requires ``POST /api/tasks`` to surface
``INVALID_KEYWORD`` / ``OVER_LIMIT`` (requirements 1.4 / 1.5) and
``GET /api/tasks`` to surface ``INVALID_QUERY_PARAM``
(requirement 4.6) as the literal error codes, so we deliberately
leave range checks off the schema and re-implement them inside the
route handlers. The schemas therefore only enforce the *types* of the
fields, which is enough to keep the wire shape well-formed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TaskCreateRequest(BaseModel):
    """Request body for ``POST /api/tasks``.

    ``max_notes`` defaults to 20 to match requirement 1.2 ("若请求未
    提供该字段则默认为 20").
    """

    # Reject unknown keys so a typo such as ``"keywords"`` (note the
    # plural) surfaces as a 422 validation error rather than being
    # silently swallowed and treated as a missing ``keyword``.
    model_config = ConfigDict(extra="forbid")

    keyword: str = Field(
        ...,
        description=(
            "Search keyword to send to MediaCrawler. After "
            "``str.strip()`` the length must lie within [1, 50]; "
            "otherwise the request is rejected with the "
            "``INVALID_KEYWORD`` error code."
        ),
    )
    platform: str = Field(
        default="xhs",
        description=(
            "MediaCrawler platform key. Supported values are xhs, dy, ks, "
            "bili, wb, tieba and zhihu. Defaults to xhs for compatibility."
        ),
    )
    max_notes: int = Field(
        default=20,
        description=(
            "Upper bound on notes to ingest from this crawl. Must be "
            "an integer in [1, 20]; otherwise the request is rejected "
            "with the ``OVER_LIMIT`` error code."
        ),
    )


class TaskCreateResponse(BaseModel):
    """Response body for a successful ``POST /api/tasks`` (HTTP 202)."""

    task_id: int = Field(
        ...,
        description="Autoincrement primary key of the freshly-created task.",
    )
    platform: str = Field(
        default="xhs",
        description="MediaCrawler platform key used by the task.",
    )
    status: str = Field(
        ...,
        description=(
            "Task status at the time of creation; always ``\"pending\"`` "
            "for this endpoint. The crawler runs in the background and "
            "transitions the row through ``running`` to a terminal state."
        ),
    )


class TaskListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[dict] = Field(default_factory=list)
    total: int = Field(default=0)


class TaskDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    keyword: str
    platform: str = "xhs"
    status: str
    note_count: int
    max_notes: int
    started_at: str | None = None
    finished_at: str | None = None
    error_msg: str | None = None
    json_path: str | None = None
    created_at: str
    summary: dict
    reports: list[dict] = Field(default_factory=list)


class AIReportCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = "openai"
    model: str = "mock"


class AIReportChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str
    content: str


class AIReportChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str
    model: str = "gpt-5.5"
    history: list[AIReportChatMessage] = Field(default_factory=list)


class AIReportChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    model: str
    message: str


class ContentPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = "deepseek"
    model: str = "gpt-5.5"


class ContentDirectionsRequest(ContentPlanRequest):
    opportunity: dict


class ContentOutlineRequest(ContentPlanRequest):
    opportunity: dict
    direction: dict


class ContentDraftRequest(ContentPlanRequest):
    opportunity: dict
    direction: dict
    outline: dict
    selected_title: str | None = None


class AIReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    task_id: int
    provider: str
    model: str
    prompt_version: str
    report_md: str
    created_at: str
