"""
pipeline_runner.py — Runs the 8-step pipeline with progress reporting.

Designed to execute inside a ProcessPoolExecutor worker.
Receives only picklable primitives; updates JobStore via a shared reference
passed through multiprocessing-safe means (the store lives in the main process
and is updated via a proxy callback — but since we're using threads + processes
with a shared in-memory store on macOS/fork, we pass the store directly and
rely on the fact that forked processes inherit the parent's memory at fork time).

IMPORTANT: Because ProcessPoolExecutor uses fork on macOS by default, the
child process inherits the parent's JobStore. Writes in the child are NOT
visible to the parent. To solve this we use threading.Thread (not processes)
for the pipeline worker — the pipeline is mostly I/O bound (download, ffmpeg,
Claude API) and the one CPU-heavy step (Whisper) releases the GIL.
The caller (app.py) must submit jobs via ThreadPoolExecutor, not ProcessPoolExecutor.
"""

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def run_job(job_id: str, url: str, model_size: str | None, store, project_root: str) -> None:
    """
    Run all 8 pipeline steps for a single URL.
    Updates `store` (JobStore) with step progress and logs.
    `project_root` is the absolute path to the project root — we chdir there
    so all relative Path("output/...") references resolve correctly.
    """
    os.chdir(project_root)

    # Add project root to sys.path so src.* imports work from this thread
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from src.ingestion import downloader, audio_extractor, frame_extractor
    from src.transcription import transcriber
    from src.visual import extractor as visual_extractor
    from src.aligner import aligner
    from src.synthesizer import synthesizer
    from src.generator import md_generator

    def log(msg: str) -> None:
        store.append_log(job_id, msg)
        logger.info("[%s] %s", job_id, msg)

    try:
        # ── Step 1: Download ──────────────────────────────────────────────────
        store.start_step(job_id, 1)
        log("Resolving video ID and downloading...")
        metadata = downloader.download(url)
        video_id = metadata["video_id"]
        title = metadata.get("title", video_id)
        store.set_video_id(job_id, video_id, title)
        output_dir = Path("output") / video_id
        log(f"Downloaded: {title}")
        store.complete_step(job_id, 1)

        # ── Step 2: Audio extraction ──────────────────────────────────────────
        store.start_step(job_id, 2)
        log("Extracting audio...")
        audio_extractor.extract(video_id, output_dir)
        log("Audio extracted (mono 16kHz)")
        store.complete_step(job_id, 2)

        # ── Step 3: Transcription ─────────────────────────────────────────────
        store.start_step(job_id, 3)
        log(f"Loading Whisper model ({model_size or 'small'}) and transcribing...")
        transcriber.transcribe(video_id, output_dir, model_size=model_size)
        log("Transcription complete")
        store.complete_step(job_id, 3)

        # ── Step 4: Frame extraction ──────────────────────────────────────────
        store.start_step(job_id, 4)
        log("Detecting scene changes and extracting frames...")
        frame_extractor.extract(video_id, output_dir)
        log("Frames extracted")
        store.complete_step(job_id, 4)

        # ── Step 5: OCR + Vision ──────────────────────────────────────────────
        store.start_step(job_id, 5)
        log("Running OCR and Vision analysis on frames...")
        visual_extractor.extract(video_id, output_dir)
        log("Visual content extracted")
        store.complete_step(job_id, 5)

        # ── Step 6: Alignment ─────────────────────────────────────────────────
        store.start_step(job_id, 6)
        log("Aligning transcript with frames...")
        aligner.align(video_id, output_dir)
        log("Content aligned")
        store.complete_step(job_id, 6)

        # ── Step 7: Synthesis ─────────────────────────────────────────────────
        store.start_step(job_id, 7)
        log("Synthesizing per-segment notes (Claude)...")
        synthesizer.synthesize(video_id, output_dir)
        log("Synthesis complete")
        store.complete_step(job_id, 7)

        # ── Step 8: Markdown generation ───────────────────────────────────────
        store.start_step(job_id, 8)
        log("Generating final study notes (Claude)...")
        md_generator.generate(video_id, output_dir)
        log("Study notes generated!")
        store.complete_step(job_id, 8)

        store.complete_job(job_id, metadata=metadata)
        log("Pipeline complete.")

    except Exception as exc:
        error_msg = str(exc)
        logger.exception("[%s] Pipeline failed: %s", job_id, error_msg)
        store.fail_job(job_id, error_msg)
        log(f"ERROR: {error_msg}")
