from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.api._errors import error_detail
from app.api.deps import get_crawler, get_store
from app.core.logger import logger
from app.models import Author, Comment, Note, Task
from app.services.crawler_service import CrawlerService
from app.services.data_store import DataStore

router = APIRouter(prefix="/api", tags=["tasks"])

KEYWORD_MIN_LEN = 1
KEYWORD_MAX_LEN = 50
MAX_NOTES_MIN = 1
MAX_NOTES_MAX = 20


async def _run_real_crawl(
    crawler: CrawlerService,
    task_id: int,
    keyword: str,
    max_notes: int,
) -> None:
    """Background worker for the real MediaCrawler chain."""
    try:
        await crawler.run_xhs_search(task_id, keyword, max_notes)
    except Exception:
        # run_xhs_search already writes terminal task state;
        # we only keep the traceback for diagnostics.
        logger.exception(
            "background crawl failed",
            extra={
                "event": "task_background_failed",
                "task_id": task_id,
                "keyword": keyword,
            },
        )


@router.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
async def create_task(
    request: dict[str, Any],
    background_tasks: BackgroundTasks,
    store: DataStore = Depends(get_store),
    crawler: CrawlerService = Depends(get_crawler),
):
    keyword = str(request.get("keyword", "")).strip()
    if not (KEYWORD_MIN_LEN <= len(keyword) <= KEYWORD_MAX_LEN):
        raise HTTPException(status_code=422, detail=error_detail("INVALID_KEYWORD", "keyword invalid", {"keyword": request.get("keyword")}))
    try:
        max_notes = int(request.get("max_notes", 20))
    except Exception:
        raise HTTPException(status_code=422, detail=error_detail("OVER_LIMIT", "max_notes invalid", {"max_notes": request.get("max_notes")}))
    if not (MAX_NOTES_MIN <= max_notes <= MAX_NOTES_MAX):
        raise HTTPException(status_code=422, detail=error_detail("OVER_LIMIT", "max_notes invalid", {"max_notes": max_notes}))

    try:
        async with store.session() as session:
            task = Task(keyword=keyword, status="pending", max_notes=max_notes)
            session.add(task)
            await session.flush()
            task_id = int(task.id)
            await session.commit()

    except (DBAPIError, SQLAlchemyError):
        raise HTTPException(status_code=500, detail=error_detail("INTERNAL_ERROR", "database error"))

    background_tasks.add_task(_run_real_crawl, crawler, task_id, keyword, max_notes)
    return JSONResponse(
        status_code=202,
        content={"task_id": task_id, "id": task_id, "status": "pending"},
    )


@router.get("/tasks")
async def list_tasks(
    status: str | None = Query(default=None),
    limit: int = 20,
    offset: int = 0,
    store: DataStore = Depends(get_store),
):
    async with store.session() as session:
        stmt = select(Task)
        if status:
            stmt = stmt.where(Task.status == status)
        total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (await session.execute(stmt.order_by(Task.created_at.desc(), Task.id.desc()).offset(offset).limit(limit))).scalars().all()
        return {
            "items": [
                {
                    "id": t.id,
                    "keyword": t.keyword,
                    "status": t.status,
                    "note_count": t.note_count,
                    "started_at": t.started_at,
                    "finished_at": t.finished_at,
                    "created_at": t.created_at,
                }
                for t in rows
            ],
            "total": int(total),
        }


@router.get("/tasks/{task_id}")
async def get_task(task_id: int, store: DataStore = Depends(get_store)):
    async with store.session() as session:
        task = await session.get(Task, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=error_detail("TASK_NOT_FOUND", "task not found"))
        total_likes = (await session.execute(select(func.coalesce(func.sum(Note.liked_count), 0)).where(Note.task_id == task_id))).scalar_one()
        total_comments = (
            await session.execute(
                select(func.count(Comment.comment_id))
                .select_from(Comment)
                .join(Note, Comment.note_id == Note.note_id)
                .where(Note.task_id == task_id)
            )
        ).scalar_one()
        author_rows = (await session.execute(
            select(Author.user_id, Author.nickname, func.count(Note.note_id).label("note_count"))
            .select_from(Note)
            .join(Author, Note.author_user_id == Author.user_id, isouter=True)
            .where(Note.task_id == task_id)
            .group_by(Author.user_id, Author.nickname)
            .order_by(func.count(Note.note_id).desc(), Author.user_id.asc())
            .limit(5)
        )).all()
        reports = await store.list_ai_reports(task_id)
        return {
            "id": task.id,
            "keyword": task.keyword,
            "status": task.status,
            "note_count": task.note_count,
            "max_notes": task.max_notes,
            "started_at": task.started_at,
            "finished_at": task.finished_at,
            "error_msg": task.error_msg,
            "json_path": task.json_path,
            "created_at": task.created_at,
            "summary": {
                "total_likes": int(total_likes or 0),
                "total_comments": int(total_comments or 0),
                "top_authors": [
                    {"user_id": r[0], "nickname": r[1], "note_count": int(r[2] or 0)}
                    for r in author_rows
                    if r[0] is not None
                ],
            },
            "reports": [r.__dict__ for r in reports],
        }


@router.get("/tasks/{task_id}/export")
async def export_task(task_id: int, store: DataStore = Depends(get_store)):
    async with store.session() as session:
        task = await session.get(Task, task_id)
        if task is None or not task.json_path:
            raise HTTPException(status_code=404, detail=error_detail("EXPORT_NOT_AVAILABLE", "export not available"))
        path = store.json_dir / f"{task_id}.json"
        return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))
