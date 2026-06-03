"""
transcriber.py — Transcribes audio using faster-whisper.

Produces a timestamped transcript with one entry per speech segment.
Preserves Hindi/Hinglish as-is — no forced translation.

Model is configurable via WHISPER_MODEL env var or the `model_size` argument.
Default: "small"
"""

import json
import logging
import os
from pathlib import Path

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "small"


def transcribe(video_id: str, output_dir: Path, model_size: str | None = None) -> dict:
    """
    Transcribe audio.mp3 → transcript.json.

    - Idempotent: returns existing transcript if already done.
    - Auto-detects language from first 30s.
    - Preserves original Hindi/Hinglish text.

    Returns the transcript dict.
    """
    audio_file = output_dir / "audio.mp3"
    transcript_file = output_dir / "transcript.json"

    if not audio_file.exists():
        raise FileNotFoundError(f"[{video_id}] Audio file not found: {audio_file}")

    if transcript_file.exists():
        logger.info(f"[{video_id}] Transcript already exists, skipping.")
        with open(transcript_file, encoding="utf-8") as f:
            return json.load(f)

    model_size = model_size or os.environ.get("WHISPER_MODEL", DEFAULT_MODEL)
    logger.info(f"[{video_id}] Loading Whisper model: {model_size} (downloads on first use)...")

    model = WhisperModel(model_size, device="auto", compute_type="default")

    logger.info(f"[{video_id}] Transcribing audio...")
    segments_iter, info = model.transcribe(
        str(audio_file),
        beam_size=5,
        vad_filter=True,          # skip silent sections
        vad_parameters={"min_silence_duration_ms": 500},
    )

    logger.info(
        f"[{video_id}] Detected language: {info.language!r} "
        f"(confidence: {info.language_probability:.0%})"
    )

    segments = []
    for i, seg in enumerate(segments_iter, start=1):
        segments.append({
            "index": i,
            "start_sec": round(seg.start, 2),
            "end_sec": round(seg.end, 2),
            "text": seg.text.strip(),
        })

    if not segments:
        logger.warning(f"[{video_id}] No speech detected — transcript is empty.")

    transcript = {
        "video_id": video_id,
        "language_detected": info.language,
        "language_confidence": round(info.language_probability, 4),
        "segments": segments,
    }

    with open(transcript_file, "w", encoding="utf-8") as f:
        json.dump(transcript, f, ensure_ascii=False, indent=2)

    logger.info(
        f"[{video_id}] Transcription complete — "
        f"{len(segments)} segments → {transcript_file}"
    )
    return transcript
