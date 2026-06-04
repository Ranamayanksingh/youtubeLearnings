"""
jobs_api.py — REST API routes for job management.
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class SubmitRequest(BaseModel):
    url: str
    model_size: str | None = None


# ── Submit a new job ──────────────────────────────────────────────────────────

@router.post("/jobs")
async def submit_job(body: SubmitRequest, request: Request):
    store = request.app.state.store
    executor = request.app.state.executor
    project_root = request.app.state.project_root

    # Deduplication: check if a job for this URL is already active/completed
    for job in store.list_all():
        if job.url.strip() == body.url.strip() and job.status in ("queued", "running", "completed"):
            return {"job_id": job.job_id, "status": job.status, "deduplicated": True}

    job = store.create(url=body.url, model_size=body.model_size)

    from web.pipeline_runner import run_job
    executor.submit(run_job, job.job_id, body.url, body.model_size, store, project_root)

    return {"job_id": job.job_id, "status": job.status}


# ── List all jobs (JSON) ──────────────────────────────────────────────────────

@router.get("/jobs")
async def list_jobs(request: Request):
    store = request.app.state.store
    jobs = store.list_all()
    return [_job_summary(j) for j in jobs]


# ── Job detail (JSON) ─────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request):
    store = request.app.state.store
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_detail(job)


# ── HTMX status fragment ──────────────────────────────────────────────────────

@router.get("/dashboard/jobs", response_class=HTMLResponse)
async def dashboard_jobs_fragment(request: Request):
    """HTML fragment for the jobs sections on the dashboard — polled every 4s."""
    store = request.app.state.store
    templates = request.app.state.templates
    jobs = store.list_all()
    return templates.TemplateResponse(
        request, "partials/dashboard_jobs.html",
        {"jobs": jobs},
    )


@router.get("/jobs/{job_id}/status", response_class=HTMLResponse)
async def job_status_fragment(job_id: str, request: Request):
    store = request.app.state.store
    templates = request.app.state.templates
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return templates.TemplateResponse(
        request, "partials/progress_panel.html",
        {"job": job},
    )


# ── Archive (cleanup) ─────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/archive")
async def archive_job(job_id: str, request: Request):
    store = request.app.state.store
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.video_id:
        raise HTTPException(status_code=400, detail="Video ID not yet known — job still running?")

    from src.utils import cleanup
    try:
        archived_path = cleanup.archive(job.video_id)
        store.remove(job_id)
        return {"status": "archived", "archived_path": str(archived_path)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Archived list (JSON) ──────────────────────────────────────────────────────

@router.get("/archived")
async def list_archived(request: Request):
    final_dir = Path("final")
    if not final_dir.exists():
        return []
    result = []
    for d in sorted(final_dir.iterdir()):
        if not d.is_dir():
            continue
        info_file = d / "video_info.json"
        info = {}
        if info_file.exists():
            with open(info_file, encoding="utf-8") as f:
                info = json.load(f)
        result.append({
            "video_id": d.name,
            "title": info.get("title", d.name),
            "url": info.get("url", ""),
        })
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _job_summary(job) -> dict:
    return {
        "job_id": job.job_id,
        "url": job.url,
        "title": job.title or job.url,
        "status": job.status,
        "current_step": job.current_step,
        "current_step_name": job.current_step_name(),
        "progress_pct": round(job.progress_pct(), 1),
        "elapsed_s": round(job.elapsed_s(), 0),
        "video_id": job.video_id,
    }


def _job_detail(job) -> dict:
    return {
        **_job_summary(job),
        "steps": [
            {
                "index": s.index,
                "name": s.name,
                "status": s.status,
                "duration_s": round(s.duration_s, 1) if s.duration_s else None,
            }
            for s in job.steps
        ],
        "log_lines": job.log_lines[-50:],
        "error": job.error,
        "metadata": job.metadata,
    }
