"""
pages.py — HTML page routes (server-rendered via Jinja2).
"""

import json
import re
from pathlib import Path

import markdown as md_lib
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    store = request.app.state.store
    templates = request.app.state.templates
    jobs = store.list_all()
    archived = _list_archived()
    return templates.TemplateResponse(
        request, "dashboard.html",
        {"jobs": jobs, "archived": archived},
    )


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail_page(job_id: str, request: Request):
    store = request.app.state.store
    templates = request.app.state.templates
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return templates.TemplateResponse(
        request, "job_detail.html",
        {"job": job},
    )


@router.get("/jobs/{job_id}/preview", response_class=HTMLResponse)
async def preview_notes(job_id: str, request: Request):
    store = request.app.state.store
    templates = request.app.state.templates
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.video_id:
        raise HTTPException(status_code=400, detail="Pipeline not complete yet")

    notes_path = Path("output") / job.video_id / "study_notes.md"
    if not notes_path.exists():
        raise HTTPException(status_code=404, detail="study_notes.md not ready yet")

    content = notes_path.read_text(encoding="utf-8")
    rendered_html = md_lib.markdown(
        content,
        extensions=["tables", "fenced_code", "nl2br"],
    )

    return templates.TemplateResponse(
        request, "preview.html",
        {
            "job": job,
            "rendered_html": rendered_html,
            "frames_base": f"/api/jobs/{job.video_id}/frames/",
        },
    )


@router.get("/jobs/{job_id}/download")
async def download_notes(job_id: str, request: Request):
    store = request.app.state.store
    job = store.get(job_id)
    if not job or not job.video_id:
        raise HTTPException(status_code=404, detail="Job not found or not complete")
    notes_path = Path("output") / job.video_id / "study_notes.md"
    if not notes_path.exists():
        raise HTTPException(status_code=404, detail="study_notes.md not found")
    safe_title = re.sub(r"[^\w\s-]", "", job.title or job.video_id)[:60].strip()
    return FileResponse(
        path=str(notes_path),
        media_type="text/markdown",
        filename=f"{safe_title}.md",
    )


@router.get("/archived", response_class=HTMLResponse)
async def archived_page(request: Request):
    templates = request.app.state.templates
    archived = _list_archived()
    return templates.TemplateResponse(
        request, "archived_list.html",
        {"archived": archived},
    )


@router.get("/archived/{video_id}/preview", response_class=HTMLResponse)
async def preview_archived(video_id: str, request: Request):
    templates = request.app.state.templates
    notes_path = Path("final") / video_id / "study_notes.md"
    if not notes_path.exists():
        raise HTTPException(status_code=404, detail="Archived notes not found")

    info_file = Path("final") / video_id / "video_info.json"
    info = {}
    if info_file.exists():
        with open(info_file, encoding="utf-8") as f:
            info = json.load(f)

    content = notes_path.read_text(encoding="utf-8")
    rendered_html = md_lib.markdown(
        content,
        extensions=["tables", "fenced_code", "nl2br"],
    )

    return templates.TemplateResponse(
        request, "archived_preview.html",
        {
            "video_id": video_id,
            "title": info.get("title", video_id),
            "url": info.get("url", ""),
            "rendered_html": rendered_html,
        },
    )


@router.get("/archived/{video_id}/download")
async def download_archived(video_id: str):
    notes_path = Path("final") / video_id / "study_notes.md"
    if not notes_path.exists():
        raise HTTPException(status_code=404, detail="Archived notes not found")
    return FileResponse(
        path=str(notes_path),
        media_type="text/markdown",
        filename="study_notes.md",
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _list_archived() -> list[dict]:
    final_dir = Path("final")
    if not final_dir.exists():
        return []
    result = []
    for d in sorted(final_dir.iterdir(), reverse=True):
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
