"""
app.py — FastAPI application factory.

Start with:
    uv run uvicorn web.app:app --reload --host 0.0.0.0 --port 8000
"""

import os
import sys
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = store
    app.state.executor = executor
    app.state.templates = templates
    app.state.project_root = str(PROJECT_ROOT)
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
