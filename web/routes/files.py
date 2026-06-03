"""
files.py — Serve frame images and study_notes.md for download.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/jobs")


@router.get("/{job_id}/notes")
async def download_notes(job_id: str):
    """Download the raw study_notes.md for an active job."""
    # job_id here is the short UUID — we need the video_id to find output/
    # The notes file is under output/<video_id>/study_notes.md
    # We search output/ for a matching job... but we don't have the store here.
    # Instead we use a different URL pattern: /api/jobs/{job_id}/notes is called
    # from the pages router which knows the video_id and redirects here.
    # For simplicity, job_id in this route IS the video_id (from preview page context).
    notes_path = Path("output") / job_id / "study_notes.md"
    if not notes_path.exists():
        # try final/
        notes_path = Path("final") / job_id / "study_notes.md"
    if not notes_path.exists():
        raise HTTPException(status_code=404, detail="study_notes.md not found")
    return FileResponse(
        path=str(notes_path),
        media_type="text/markdown",
        filename="study_notes.md",
    )


@router.get("/{video_id}/frames/{filename}")
async def serve_frame(video_id: str, filename: str):
    """Serve a frame image from output/<video_id>/frames/<filename>."""
    # Prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    frame_path = Path("output") / video_id / "frames" / filename
    if not frame_path.exists():
        frame_path = Path("final") / video_id / "frames" / filename
    if not frame_path.exists():
        raise HTTPException(status_code=404, detail="Frame not found")
    return FileResponse(path=str(frame_path), media_type="image/jpeg")
