"""
app.py — FastAPI application factory.

Start with:
    uv run uvicorn web.app:app --reload --host 0.0.0.0 --port 8000
"""

import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

# ── Project root setup (must happen before any src.* imports) ─────────────────
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from web.job_store import JobStore  # noqa: E402 — after path setup

# ── Shared singletons (attached to app.state) ─────────────────────────────────
store = JobStore()
executor = ThreadPoolExecutor(max_workers=2)

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "web" / "templates"))


def _restore_completed_jobs(store: "JobStore") -> None:  # noqa: F821
    """Scan output/ on startup and restore any completed jobs into the store."""
    output_dir = PROJECT_ROOT / "output"
    if not output_dir.exists():
        return
    restored = 0
    for video_dir in sorted(output_dir.iterdir()):
        if not video_dir.is_dir():
            continue
        # Completion marker: study_notes.md must exist
        if not (video_dir / "study_notes.md").exists():
            continue
        video_id = video_dir.name
        # Read title and URL from metadata.json
        metadata_file = video_dir / "metadata.json"
        url = f"https://www.youtube.com/watch?v={video_id}"
        title = video_id
        if metadata_file.exists():
            try:
                with open(metadata_file, encoding="utf-8") as f:
                    meta = json.load(f)
                title = meta.get("title", video_id)
                url = meta.get("url", url)
            except Exception:
                pass
        store.restore_completed_job(video_id=video_id, url=url, title=title)
        restored += 1
    if restored:
        logger.info(f"[startup] Restored {restored} completed job(s) from output/")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = store
    app.state.executor = executor
    app.state.templates = templates
    app.state.project_root = str(PROJECT_ROOT)
    _restore_completed_jobs(store)
    yield
    executor.shutdown(wait=False)


app = FastAPI(title="Ayurveda Study Notes Generator", lifespan=lifespan)

# ── Static files ──────────────────────────────────────────────────────────────
static_dir = PROJECT_ROOT / "web" / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# ── Routes ────────────────────────────────────────────────────────────────────
from web.routes import pages, jobs_api, files  # noqa: E402

app.include_router(jobs_api.router)
app.include_router(files.router)
app.include_router(pages.router)
