"""
meeting_pipeline.py — Orchestrates the meeting analysis pipeline.

Steps:
  1. file_uploader   — stage local file into output/<job_id>/
  2. audio_extractor — extract audio (skipped if input was already audio)
  3. transcriber     — Whisper transcription
  4. diarizer        — speaker diarization (optional, needs HF_TOKEN)
  5. frame_extractor — extract frames (useful for screen-share recordings)
  6. visual_extractor— OCR + Vision on frames
  7. aligner         — align transcript + frames by timestamp
  8. synthesizer     — per-segment synthesis (meeting domain rules)
  9. md_generator    — full-context meeting brief generation

All steps are idempotent. Progress callbacks allow the web layer to
track step-by-step status.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

MEETING_STEPS = [
    {"index": 1, "name": "Staging file"},
    {"index": 2, "name": "Extracting audio"},
    {"index": 3, "name": "Transcribing"},
    {"index": 4, "name": "Speaker diarization"},
    {"index": 5, "name": "Extracting frames"},
    {"index": 6, "name": "OCR + Vision analysis"},
    {"index": 7, "name": "Aligning content"},
    {"index": 8, "name": "Synthesizing notes"},
    {"index": 9, "name": "Generating meeting brief"},
]


def run_meeting(
    file_path: str,
    job_id: str,
    model_size: str | None = None,
    on_step_start: Callable[[int], None] | None = None,
    on_step_done: Callable[[int], None] | None = None,
    on_log: Callable[[str], None] | None = None,
) -> dict:
    """
    Run the full meeting analysis pipeline for a local file.

    Args:
        file_path: Absolute path to the local meeting recording.
        job_id: Unique job identifier (used as video_id and output dir name).
        model_size: Whisper model size (tiny/base/small/medium/large-v3).
        on_step_start: Called with step index when a step begins.
        on_step_done: Called with step index when a step completes.
        on_log: Called with log message strings.

    Returns:
        Result dict with keys: video_id, title, output_dir, notes_file.
    """
    def log(msg: str) -> None:
        logger.info(msg)
        if on_log:
            on_log(msg)

    def step_start(idx: int) -> None:
        if on_step_start:
            on_step_start(idx)

    def step_done(idx: int) -> None:
        if on_step_done:
            on_step_done(idx)

    from src.ingestion import file_uploader, audio_extractor, frame_extractor
    from src.transcription import transcriber, diarizer
    from src.visual import extractor as visual_extractor
    from src.aligner import aligner
    from src.synthesizer import synthesizer
    from src.generator import md_generator

    # Step 1 — Stage file
    step_start(1)
    log(f"[{job_id}] Staging local file: {file_path}")
    metadata = file_uploader.upload(file_path, job_id)
    video_id = metadata["video_id"]
    out_dir = Path("output") / video_id
    is_audio_only = metadata.get("is_audio_only", False)
    step_done(1)

    # Step 2 — Extract audio (skip if input was already audio)
    step_start(2)
    if is_audio_only:
        log(f"[{video_id}] Input is audio-only — skipping audio extraction.")
    else:
        log(f"[{video_id}] Extracting audio...")
        audio_extractor.extract(video_id, out_dir)
    step_done(2)

    # Step 3 — Transcribe
    step_start(3)
    log(f"[{video_id}] Transcribing audio...")
    transcriber.transcribe(video_id, out_dir, model_size=model_size)
    step_done(3)

    # Step 4 — Speaker diarization (optional)
    step_start(4)
    log(f"[{video_id}] Running speaker diarization...")
    diarizer.diarize(video_id, out_dir)
    step_done(4)

    # Step 5 — Extract frames
    step_start(5)
    log(f"[{video_id}] Extracting frames...")
    if is_audio_only:
        log(f"[{video_id}] Audio-only input — skipping frame extraction.")
        # Create empty frames dir so downstream steps don't break
        (out_dir / "frames").mkdir(exist_ok=True)
    else:
        frame_extractor.extract(video_id, out_dir)
    step_done(5)

    # Step 6 — OCR + Vision
    step_start(6)
    log(f"[{video_id}] Running OCR + Vision analysis...")
    visual_extractor.extract(video_id, out_dir)
    step_done(6)

    # Step 7 — Align
    step_start(7)
    log(f"[{video_id}] Aligning transcript with frames...")
    aligner.align(video_id, out_dir)
    step_done(7)

    # Step 8 — Synthesize
    step_start(8)
    log(f"[{video_id}] Synthesizing meeting notes...")
    synthesizer.synthesize(video_id, out_dir)
    step_done(8)

    # Step 9 — Generate meeting brief
    step_start(9)
    log(f"[{video_id}] Generating meeting brief...")
    notes_file = md_generator.generate(video_id, out_dir)
    step_done(9)

    log(f"[{video_id}] ✓ Meeting brief → {notes_file}")
    return {
        "video_id": video_id,
        "title": metadata["title"],
        "output_dir": str(out_dir),
        "notes_file": str(notes_file),
        "metadata": metadata,
    }
