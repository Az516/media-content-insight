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

import json
import re

from fastapi import APIRouter, Depends, status
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse

from app.api._errors import error_detail
from app.api.deps import get_store
from app.core.logger import logger
from app.models import Task
from app.schemas.task import (
    AIReportChatRequest,
    AIReportChatResponse,
    AIReportCreateRequest,
    AIReportResponse,
    ContentDirectionsRequest,
    ContentDraftRequest,
    ContentOutlineRequest,
    ContentPlanRequest,
)
from app.services.ai_analyzer import LLMError
from app.services.ai_providers import make_analyzer, provider_config_error, supported_providers
from app.services.data_store import AIReportInput, DataStore
from app.core.config import settings

router = APIRouter(prefix="/api", tags=["ai-reports"])

MODEL_MIN_LEN = 1
MODEL_MAX_LEN = 100
CHAT_MESSAGE_MAX_LEN = 4000
CHAT_HISTORY_MAX_ITEMS = 12
CONTENT_JSON_MAX_CHARS = 80_000

DEEPSEEK_ROUTED_MODELS: dict[str, str] = {
    "deepseek-chat": "deepseek-chat",
    "gpt-5.5": "deepseek-chat",
    "gemini-3": "deepseek-chat",
    "claude-opus-4.8": "deepseek-chat",
}


def _normalise_model(value: str | None) -> str:
    return (value or "").strip()


def _resolve_report_model(provider: str | None, model: str) -> tuple[str, str, str]:
    """Return provider, actual model, and display model for one request.

    The product UI can show aspirational model names while this local
    build routes them through the configured DeepSeek key. Unknown
    model ids keep the old provider-specific behavior for API
    compatibility.
    """

    display_model = _normalise_model(model)
    alias_key = display_model.lower()
    if alias_key in DEEPSEEK_ROUTED_MODELS:
        return "deepseek", DEEPSEEK_ROUTED_MODELS[alias_key], display_model
    provider_norm = (provider or "").strip().lower()
    return provider_norm, display_model, display_model


def _build_report_chat_prompt(
    report_md: str,
    user_message: str,
    history: list[object],
) -> str:
    history_lines: list[str] = []
    for item in history[-CHAT_HISTORY_MAX_ITEMS:]:
        role = getattr(item, "role", "")
        content = (getattr(item, "content", "") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        speaker = "用户" if role == "user" else "AI"
        history_lines.append(f"{speaker}: {content[:1000]}")
    history_text = "\n".join(history_lines) or "暂无"
    return (
        "你是一名资深内容运营分析师，正在辅助用户审阅和修改一份内容洞察报告。\n"
        "请基于报告正文、历史对话和用户最新要求回答。可以提出改写建议、补充分析、"
        "输出可直接替换进报告的段落，但不要声称已经修改数据库中的原报告。\n\n"
        f"【报告正文】\n{report_md[:12000]}\n\n"
        f"【历史对话】\n{history_text}\n\n"
        f"【用户最新要求】\n{user_message}\n\n"
        "请用中文回答，结构清晰，优先给出可执行的修改建议。"
    )


def _truncate_text(value: object, limit: int) -> str:
    text = "" if value is None else str(value).strip()
    return text[:limit]


def _build_material_digest(keyword: str, notes: list[object], comments: list[object]) -> str:
    top_notes = sorted(
        notes,
        key=lambda n: (getattr(n, "liked_count", 0) or 0) + (getattr(n, "comment_count", 0) or 0) * 2,
        reverse=True,
    )[:20]
    top_comments = sorted(
        comments,
        key=lambda c: getattr(c, "like_count", 0) or 0,
        reverse=True,
    )[:50]
    note_lines = [
        (
            f"{idx}. 标题:{_truncate_text(getattr(note, 'title', None) or '-', 80)} | "
            f"赞:{getattr(note, 'liked_count', 0) or 0} | "
            f"评:{getattr(note, 'comment_count', 0) or 0} | "
            f"正文:{_truncate_text(getattr(note, 'desc', None), 180)}"
        )
        for idx, note in enumerate(top_notes, start=1)
    ]
    comment_lines = [
        (
            f"{idx}. 赞:{getattr(comment, 'like_count', 0) or 0} | "
            f"评论:{_truncate_text(getattr(comment, 'content', None), 160)}"
        )
        for idx, comment in enumerate(top_comments, start=1)
    ]
    return (
        f"关键词:{keyword}\n\n"
        "【高互动笔记】\n"
        + "\n".join(note_lines)
        + "\n\n【高赞评论】\n"
        + "\n".join(comment_lines)
    )[:CONTENT_JSON_MAX_CHARS]


def _json_schema_instruction(shape: str) -> str:
    return (
        "只返回严格 JSON，不要 Markdown，不要代码块，不要解释。\n"
        "所有字段必须是中文内容；分数用 0-100 的数字；数组数量严格遵守要求。\n"
        f"JSON 结构如下:\n{shape}\n"
    )


def _parse_llm_json(text: str) -> dict:
    raw = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, flags=re.S)
    if fenced:
        raw = fenced.group(1).strip()
    if not raw.startswith("{"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(f"content workflow returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMError("content workflow returned a non-object JSON payload")
    return parsed


def _mock_content_payload(stage: str) -> dict:
    if stage == "opportunities":
        return {
            "items": [
                {
                    "id": "mock-topic-1",
                    "title": "AI 工具组合拳：普通人如何一天省 3 小时",
                    "score": 92,
                    "summary": "评论区反复出现求教程和求工具组合，适合做低门槛实操内容。",
                    "metrics": [
                        {"label": "热度", "value": "高"},
                        {"label": "评论需求", "value": "强"},
                        {"label": "竞争", "value": "中"},
                        {"label": "转化", "value": "高"},
                    ],
                    "evidence": "高赞笔记集中在 DeepSeek、Kimi、PPT、周报等效率场景。",
                    "audience": "职场新人、自媒体新手、学生党",
                    "risk": "避免夸大一键替代工作，强调流程和边界。",
                }
            ]
        }
    if stage == "directions":
        return {
            "items": [
                {
                    "id": "mock-direction-1",
                    "type": "实用教程型",
                    "title": "从选题到交付的 AI 效率流程",
                    "hook": "我把一天工作拆成 4 个 AI 步骤，终于不用熬夜补材料了。",
                    "promise": "给用户一套可照着做的工具链。",
                    "audience": "想快速上手 AI 的职场人",
                    "evidence": "评论区多次出现求步骤和求工具名。",
                }
            ]
        }
    if stage == "outline":
        return {
            "titles": [{"text": "我用 3 个 AI 工具，把一天工作压缩成 4 小时", "reason": "有结果、有工具、有反差"}],
            "outline": [{"title": "开头钩子", "points": ["用真实工作场景切入", "承诺给出可复制流程"]}],
            "cover_copy": ["3 个 AI 工具", "一天省 3 小时"],
            "comment_guide": ["你最想让 AI 替你做哪一步？"],
            "tags": ["AI工具", "效率提升"],
            "evidence": "基于热门笔记和高赞评论生成。",
        }
    return {
        "title": "我用 3 个 AI 工具，把一天工作压缩成 4 小时",
        "cover": "3 个 AI 工具 / 一套工作流 / 普通人也能抄",
        "body": "这是一份基于真实数据生成的模拟草稿。配置真实 AI 后会生成完整正文。",
        "tags": ["AI工具", "效率提升"],
        "checks": ["已降低夸大表达", "建议补充真实案例"],
    }


async def _assert_task_ready(task_id: int, store: DataStore) -> None:
    async with store.session() as session:
        task = await session.get(Task, task_id)
        if task is None:
            raise HTTPException(
                status_code=404,
                detail=error_detail("TASK_NOT_FOUND", "task not found", {"task_id": task_id}),
            )
        if task.status != "success":
            raise HTTPException(
                status_code=409,
                detail=error_detail(
                    "TASK_NOT_READY",
                    "task is not ready for AI content planning",
                    {"task_id": task_id, "status": task.status},
                ),
            )


async def _run_content_json(
    task_id: int,
    request: ContentPlanRequest,
    store: DataStore,
    stage: str,
    prompt: str,
) -> dict:
    await _assert_task_ready(task_id, store)
    provider_norm, actual_model, display_model = _resolve_report_model(
        request.provider,
        _normalise_model(request.model),
    )
    if provider_norm not in supported_providers():
        raise HTTPException(
            status_code=422,
            detail=error_detail(
                "INVALID_PROVIDER",
                "provider must be one of openai/deepseek/gemini",
                {"provider": request.provider},
            ),
        )
    config_error = provider_config_error(provider_norm)
    if config_error:
        raise HTTPException(
            status_code=503,
            detail=error_detail(
                "AI_PROVIDER_NOT_CONFIGURED",
                config_error,
                {"provider": provider_norm},
            ),
        )
    if settings.MOCK_AI_REPORT:
        return _mock_content_payload(stage)
    analyzer = make_analyzer(provider_norm, actual_model, store, display_model=display_model)
    try:
        return _parse_llm_json(await analyzer._call_llm(prompt))
    except LLMError as exc:
        logger.warning(
            "content_workflow_failed",
            extra={
                "event": "content_workflow_failed",
                "task_id": task_id,
                "stage": stage,
                "model": display_model,
                "error": str(exc),
            },
        )
        raise HTTPException(
            status_code=502,
            detail=error_detail(
                "AI_FAILED",
                "LLM content workflow failed; see server logs for details",
                {"task_id": task_id, "stage": stage},
            ),
        ) from exc


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

    requested_model = _normalise_model(request.model)
    provider_norm, actual_model, display_model = _resolve_report_model(
        request.provider,
        requested_model,
    )
    if provider_norm not in supported_providers():
        raise HTTPException(
            status_code=422,
            detail=error_detail(
                "INVALID_PROVIDER",
                "provider must be one of openai/deepseek/gemini",
                {"provider": request.provider},
            ),
        )

    if not (MODEL_MIN_LEN <= len(display_model) <= MODEL_MAX_LEN):
        raise HTTPException(
            status_code=422,
            detail=error_detail(
                "INVALID_MODEL",
                f"model length must be within [{MODEL_MIN_LEN}, {MODEL_MAX_LEN}]",
                {"model": request.model},
            ),
        )

    config_error = provider_config_error(provider_norm)
    if config_error:
        raise HTTPException(
            status_code=503,
            detail=error_detail(
                "AI_PROVIDER_NOT_CONFIGURED",
                config_error,
                {"provider": provider_norm},
            ),
        )

    if settings.MOCK_AI_REPORT:
        keyword, notes, comments = await store.load_for_ai(task_id)
        report_id = await store.save_ai_report(
            AIReportInput(
                task_id=task_id,
                provider=provider_norm,
                model=display_model,
                prompt_version="mock-v1",
                report_md=(
                    f"# AI 内容洞察报告\n\n"
                    f"> 本报告由本地 MOCK_AI_REPORT 生成,用于无 API Key 时验证页面。\n\n"
                    f"## 关键词\n\n{keyword}\n\n"
                    f"## 数据概览\n\n- 笔记: {len(notes)} 条\n- 评论: {len(comments)} 条\n\n"
                    "## 建议\n\n- 配置真实 provider API Key 后可生成完整洞察报告。\n"
                ),
            )
        )
        return JSONResponse(
            status_code=202,
            content={"report_id": report_id, "status": "pending"},
        )

    analyzer = make_analyzer(
        provider_norm,
        actual_model,
        store,
        display_model=display_model,
    )

    try:
        _, report_id = await analyzer.analyze(task_id)
    except LLMError as exc:
        logger.warning(
            "ai_report_failed",
            extra={
                "event": "ai_report_failed",
                "task_id": task_id,
                "provider": provider_norm,
                "model": display_model,
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
            "model": display_model,
        },
    )
    return JSONResponse(
        status_code=202,
        content={"report_id": report_id, "status": "pending"},
    )


@router.post(
    "/tasks/{task_id}/content-topics",
    summary="Generate AI topic recommendations from crawled data",
)
async def generate_content_topics(
    task_id: int,
    request: ContentPlanRequest,
    store: DataStore = Depends(get_store),
) -> dict:
    keyword, notes, comments = await store.load_for_ai(task_id)
    materials = _build_material_digest(keyword, notes, comments)
    prompt = (
        "你是小红书内容策划专家。请根据真实采集数据，生成 5 个适合继续创作的选题推荐。\n"
        "选题必须彼此不同，且必须引用数据里的需求、热度或评论证据。不要泛泛而谈。\n"
        + _json_schema_instruction(
            '{"items":[{"id":"topic-1","title":"选题标题","score":88,'
            '"summary":"为什么值得做","metrics":[{"label":"热度","value":"高"}],'
            '"evidence":"来自笔记/评论的数据依据","audience":"适合人群","risk":"风险提醒"}]}'
        )
        + f"\n【采集数据】\n{materials}"
    )
    return await _run_content_json(task_id, request, store, "opportunities", prompt)


@router.post(
    "/tasks/{task_id}/content-directions",
    summary="Generate creative angles for a selected topic",
)
async def generate_content_directions(
    task_id: int,
    request: ContentDirectionsRequest,
    store: DataStore = Depends(get_store),
) -> dict:
    keyword, notes, comments = await store.load_for_ai(task_id)
    materials = _build_material_digest(keyword, notes, comments)
    prompt = (
        "你是小红书内容策划专家。用户已经选择了一个选题，请基于该选题和原始数据，生成 3-5 个不同创作角度。\n"
        "每个角度必须服务同一个选题，但打法不同，例如教程型、避坑型、测评型、故事型、清单型。\n"
        + _json_schema_instruction(
            '{"items":[{"id":"direction-1","type":"实用教程型","title":"角度标题",'
            '"hook":"开头钩子","promise":"内容承诺","audience":"适合人群","evidence":"数据证据"}]}'
        )
        + f"\n【用户选择的选题】\n{json.dumps(request.opportunity, ensure_ascii=False)}\n\n"
        + f"【采集数据】\n{materials}"
    )
    return await _run_content_json(task_id, request, store, "directions", prompt)


@router.post(
    "/tasks/{task_id}/content-outline",
    summary="Generate an outline for a selected topic and angle",
)
async def generate_content_outline(
    task_id: int,
    request: ContentOutlineRequest,
    store: DataStore = Depends(get_store),
) -> dict:
    keyword, notes, comments = await store.load_for_ai(task_id)
    materials = _build_material_digest(keyword, notes, comments)
    prompt = (
        "你是小红书内容主编。用户已经选择了选题和创作角度，请生成可执行的大纲。\n"
        "需要包含 5 个标题候选、正文结构、封面文案、评论区引导、标签建议和数据依据。\n"
        + _json_schema_instruction(
            '{"titles":[{"text":"标题","reason":"推荐原因"}],'
            '"outline":[{"title":"开头钩子","points":["要点1","要点2"]}],'
            '"cover_copy":["封面短句"],"comment_guide":["评论引导"],'
            '"tags":["标签"],"evidence":"为什么这个大纲符合数据"}'
        )
        + f"\n【用户选择的选题】\n{json.dumps(request.opportunity, ensure_ascii=False)}\n\n"
        + f"【用户选择的创作角度】\n{json.dumps(request.direction, ensure_ascii=False)}\n\n"
        + f"【采集数据】\n{materials}"
    )
    return await _run_content_json(task_id, request, store, "outline", prompt)


@router.post(
    "/tasks/{task_id}/content-draft",
    summary="Generate a Xiaohongshu draft from a selected outline",
)
async def generate_content_draft(
    task_id: int,
    request: ContentDraftRequest,
    store: DataStore = Depends(get_store),
) -> dict:
    keyword, notes, comments = await store.load_for_ai(task_id)
    materials = _build_material_digest(keyword, notes, comments)
    prompt = (
        "你是小红书文案编辑。请根据用户选择的选题、创作角度和大纲，生成完整文案草稿。\n"
        "文案要像真实创作者写的，不要报告腔。避免夸大效果，保留风险边界。\n"
        + _json_schema_instruction(
            '{"title":"最终标题","cover":"封面文案","body":"完整正文，使用换行组织段落",'
            '"tags":["标签"],"checks":["发布前检查或优化建议"]}'
        )
        + f"\n【选题】\n{json.dumps(request.opportunity, ensure_ascii=False)}\n\n"
        + f"【创作角度】\n{json.dumps(request.direction, ensure_ascii=False)}\n\n"
        + f"【大纲】\n{json.dumps(request.outline, ensure_ascii=False)}\n\n"
        + f"【用户选中的标题】\n{request.selected_title or ''}\n\n"
        + f"【采集数据】\n{materials}"
    )
    return await _run_content_json(task_id, request, store, "draft", prompt)


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


@router.post(
    "/ai-reports/{report_id}/chat",
    response_model=AIReportChatResponse,
    summary="Chat with an existing AI report",
)
async def chat_with_ai_report(
    report_id: int,
    request: AIReportChatRequest,
    store: DataStore = Depends(get_store),
) -> dict[str, str]:
    """Ask follow-up questions against one generated report.

    The chat response is intentionally ephemeral: it helps the user
    refine, challenge or rewrite parts of the report without mutating
    the persisted report row.
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

    user_message = (request.message or "").strip()
    if not user_message or len(user_message) > CHAT_MESSAGE_MAX_LEN:
        raise HTTPException(
            status_code=422,
            detail=error_detail(
                "INVALID_MESSAGE",
                f"message length must be within [1, {CHAT_MESSAGE_MAX_LEN}]",
                {"message_length": len(user_message)},
            ),
        )

    display_model = _normalise_model(request.model) or "gpt-5.5"
    _, actual_model, display_model = _resolve_report_model("deepseek", display_model)
    config_error = provider_config_error("deepseek")
    if config_error:
        raise HTTPException(
            status_code=503,
            detail=error_detail(
                "AI_PROVIDER_NOT_CONFIGURED",
                config_error,
                {"provider": "deepseek"},
            ),
        )

    prompt = _build_report_chat_prompt(
        report_md=report.report_md,
        user_message=user_message,
        history=list(request.history),
    )
    if settings.MOCK_AI_REPORT:
        return {
            "provider": "deepseek",
            "model": display_model,
            "message": (
                "这是本地模拟回复：我会基于你的要求调整报告表达。"
                f"\n\n你的要求是：{user_message}\n\n"
                "建议先标出需要改写的章节，再把新增观点整理成 3-5 条可执行结论。"
            ),
        }

    analyzer = make_analyzer(
        "deepseek",
        actual_model,
        store,
        display_model=display_model,
    )
    try:
        answer = await analyzer._call_llm(prompt)
    except LLMError as exc:
        logger.warning(
            "ai_report_chat_failed",
            extra={
                "event": "ai_report_chat_failed",
                "report_id": report_id,
                "provider": "deepseek",
                "model": display_model,
                "error": str(exc),
            },
        )
        raise HTTPException(
            status_code=502,
            detail=error_detail(
                "AI_FAILED",
                "LLM call failed; see server logs for details",
                {"report_id": report_id, "provider": "deepseek"},
            ),
        ) from exc

    return {
        "provider": "deepseek",
        "model": display_model,
        "message": answer,
    }


__all__ = ["router"]
