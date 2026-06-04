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


def run_meeting_job(
    job_id: str,
    file_path: str,
    model_size: str | None,
    store,
    project_root: str,
) -> None:
    """
    Run the meeting analysis pipeline for a local uploaded file.
    Uses the same 8-step slot structure as run_job for UI compatibility.

    Step mapping:
      1 → Stage file
      2 → Extract audio
      3 → Transcribe
      4 → Speaker diarization
      5 → Extract frames
      6 → OCR + Vision
      7 → Align + Synthesize
      8 → Generate meeting brief
    """
    os.chdir(project_root)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from src.ingestion import file_uploader, audio_extractor, frame_extractor
    from src.transcription import transcriber, diarizer
    from src.visual import extractor as visual_extractor
    from src.aligner import aligner
    from src.synthesizer import synthesizer
    from src.generator import md_generator

    def log(msg: str) -> None:
        store.append_log(job_id, msg)
        logger.info("[%s] %s", job_id, msg)

    try:
        # Step 1 — Stage file
        store.start_step(job_id, 1)
        log(f"Staging local file: {file_path}")
        metadata = file_uploader.upload(file_path, job_id)
        video_id = metadata["video_id"]
        title = metadata.get("title", video_id)
        is_audio_only = metadata.get("is_audio_only", False)
        store.set_video_id(job_id, video_id, title)
        output_dir = Path("output") / video_id
        log(f"Staged: {title}")
        store.complete_step(job_id, 1)

        # Step 2 — Extract audio (skip if audio-only input)
        store.start_step(job_id, 2)
        if is_audio_only:
            log("Audio-only input — skipping audio extraction.")
        else:
            log("Extracting audio from video...")
            audio_extractor.extract(video_id, output_dir)
            log("Audio extracted")
        store.complete_step(job_id, 2)

        # Step 3 — Transcribe
        store.start_step(job_id, 3)
        log(f"Transcribing with Whisper ({model_size or 'small'})...")
        transcriber.transcribe(video_id, output_dir, model_size=model_size)
        log("Transcription complete")
        store.complete_step(job_id, 3)

        # Step 4 — Speaker diarization (optional)
        store.start_step(job_id, 4)
        log("Running speaker diarization...")
        result = diarizer.diarize(video_id, output_dir)
        n = result.get("speakers_detected", 0)
        log(f"Diarization complete — {n} speaker(s) detected" if n else "Diarization skipped")
        store.complete_step(job_id, 4)

        # Step 5 — Extract frames
        store.start_step(job_id, 5)
        if is_audio_only:
            log("Audio-only input — skipping frame extraction.")
            (output_dir / "frames").mkdir(exist_ok=True)
        else:
            log("Extracting frames from video...")
            frame_extractor.extract(video_id, output_dir)
            log("Frames extracted")
        store.complete_step(job_id, 5)

        # Step 6 — OCR + Vision
        store.start_step(job_id, 6)
        log("Running OCR + Vision analysis...")
        visual_extractor.extract(video_id, output_dir)
        log("Visual analysis complete")
        store.complete_step(job_id, 6)

        # Step 7 — Align + Synthesize
        store.start_step(job_id, 7)
        log("Aligning and synthesizing meeting notes...")
        aligner.align(video_id, output_dir)
        synthesizer.synthesize(video_id, output_dir)
        log("Synthesis complete")
        store.complete_step(job_id, 7)

        # Step 8 — Generate meeting brief
        store.start_step(job_id, 8)
        log("Generating meeting brief (Claude)...")
        md_generator.generate(video_id, output_dir)
        log("Meeting brief generated!")
        store.complete_step(job_id, 8)

        store.complete_job(job_id, metadata=metadata)
        log("Meeting analysis complete.")

    except Exception as exc:
        error_msg = str(exc)
        logger.exception("[%s] Meeting pipeline failed: %s", job_id, error_msg)
        store.fail_job(job_id, error_msg)
        log(f"ERROR: {error_msg}")
