"""
job_store.py — In-memory job registry.

Jobs reset on server restart (by design — no persistence needed for now).
Thread-safe: all mutations go through a single RLock.
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

# ── Step definitions ──────────────────────────────────────────────────────────

PIPELINE_STEPS = [
    {"index": 1, "name": "Downloading video",     "weight": 10},
    {"index": 2, "name": "Extracting audio",      "weight":  5},
    {"index": 3, "name": "Transcribing",           "weight": 25},
    {"index": 4, "name": "Extracting frames",     "weight": 10},
    {"index": 5, "name": "OCR + Vision analysis", "weight": 20},
    {"index": 6, "name": "Aligning content",      "weight":  5},
    {"index": 7, "name": "Synthesizing notes",    "weight": 15},
    {"index": 8, "name": "Generating study notes","weight": 10},
]

_CUMULATIVE_WEIGHTS: list[float] = []
_total = sum(s["weight"] for s in PIPELINE_STEPS)
_running = 0
for s in PIPELINE_STEPS:
    _running += s["weight"]
    _CUMULATIVE_WEIGHTS.append(_running / _total * 100)

MAX_LOG_LINES = 200


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class StepStatus:
    index: int
    name: str
    status: Literal["pending", "running", "completed", "skipped", "failed"] = "pending"
    started_at: datetime | None = None
    duration_s: float | None = None


@dataclass
class Job:
    job_id: str
    url: str
    model_size: str | None
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    video_id: str | None = None
    title: str | None = None
    current_step: int = 0          # 0 = not started, 1-8 = active step
    steps: list[StepStatus] = field(default_factory=list)
    log_lines: list[str] = field(default_factory=list)
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    metadata: dict = field(default_factory=dict)

    def progress_pct(self) -> float:
        """Return 0-100 based on completed steps' cumulative weight."""
        if self.status == "completed":
            return 100.0
        completed = [s for s in self.steps if s.status == "completed"]
        if not completed:
            return 0.0
        last_done = max(s.index for s in completed)
        return _CUMULATIVE_WEIGHTS[last_done - 1]

    def current_step_name(self) -> str:
        if self.status == "completed":
            return "Done"
        if self.status == "failed":
            return "Failed"
        if self.current_step == 0:
            return "Queued"
        for s in self.steps:
            if s.index == self.current_step:
                return s.name
        return "Running"

    def elapsed_s(self) -> float:
        end = self.completed_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()


# ── Store ─────────────────────────────────────────────────────────────────────

class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()

    # ── creation ──────────────────────────────────────────────────────────────

    def create(self, url: str, model_size: str | None = None) -> Job:
        job_id = str(uuid.uuid4())[:8]
        steps = [StepStatus(index=s["index"], name=s["name"]) for s in PIPELINE_STEPS]
        job = Job(job_id=job_id, url=url, model_size=model_size, steps=steps)
        with self._lock:
            self._jobs[job_id] = job
        return job

    # ── reads ─────────────────────────────────────────────────────────────────

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_all(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.started_at, reverse=True)

    def find_by_video_id(self, video_id: str) -> Job | None:
        with self._lock:
            for job in self._jobs.values():
                if job.video_id == video_id:
                    return job
        return None

    # ── mutations ─────────────────────────────────────────────────────────────

    def set_video_id(self, job_id: str, video_id: str, title: str | None = None) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.video_id = video_id
                if title:
                    job.title = title

    def start_step(self, job_id: str, step_index: int) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.status = "running"
            job.current_step = step_index
            for s in job.steps:
                if s.index == step_index:
                    s.status = "running"
                    s.started_at = datetime.utcnow()

    def complete_step(self, job_id: str, step_index: int) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            for s in job.steps:
                if s.index == step_index and s.started_at:
                    s.status = "completed"
                    s.duration_s = (datetime.utcnow() - s.started_at).total_seconds()

    def complete_job(self, job_id: str, metadata: dict | None = None) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = "completed"
                job.current_step = 8
                job.completed_at = datetime.utcnow()
                if metadata:
                    job.metadata = metadata

    def fail_job(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = "failed"
                job.error = error
                job.completed_at = datetime.utcnow()
                # mark current step as failed
                for s in job.steps:
                    if s.status == "running":
                        s.status = "failed"

    def append_log(self, job_id: str, line: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                ts = datetime.utcnow().strftime("%H:%M:%S")
                job.log_lines.append(f"{ts}  {line}")
                if len(job.log_lines) > MAX_LOG_LINES:
                    job.log_lines = job.log_lines[-MAX_LOG_LINES:]

    def remove(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def restore_completed_job(
        self,
        video_id: str,
        url: str,
        title: str,
        model_size: str | None = None,
    ) -> None:
        """Re-hydrate a completed job from disk so it shows on the dashboard after restart.

        Uses video_id as the job_id so repeated restarts are idempotent.
        """
        with self._lock:
            if video_id in self._jobs:
                return  # already present (e.g. just ran in this session)
            steps = []
            for s in PIPELINE_STEPS:
                step = StepStatus(index=s["index"], name=s["name"], status="completed")
                steps.append(step)
            job = Job(
                job_id=video_id,
                url=url,
                model_size=model_size,
                status="completed",
                video_id=video_id,
                title=title,
                current_step=8,
                steps=steps,
                completed_at=datetime.utcnow(),
            )
            self._jobs[video_id] = job
