"""
audio_extractor.py — Extracts audio from a downloaded video using ffmpeg.

Output: output/<video_id>/audio.mp3  (mono, 16kHz — optimal for Whisper)
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def extract(video_id: str, output_dir: Path) -> Path:
    """
    Extract audio from video.mp4 → audio.mp3.

    - Mono channel, 16kHz sample rate (Whisper-optimised).
    - Idempotent: skips extraction if audio.mp3 already exists.

    Returns the path to the audio file.
    """
    video_file = output_dir / "video.mp4"
    audio_file = output_dir / "audio.mp3"

    if not video_file.exists():
        raise FileNotFoundError(f"Video file not found: {video_file}")

    if audio_file.exists():
        logger.info(f"[{video_id}] Audio already extracted, skipping.")
        return audio_file

    logger.info(f"[{video_id}] Extracting audio...")

    cmd = [
        "ffmpeg",
        "-i", str(video_file),
        "-vn",              # no video
        "-ac", "1",         # mono
        "-ar", "16000",     # 16kHz sample rate
        "-q:a", "4",        # variable bitrate quality (good enough for speech)
        "-y",               # overwrite without asking
        str(audio_file),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"[{video_id}] ffmpeg failed:\n{result.stderr}"
        )

    logger.info(f"[{video_id}] Audio extracted → {audio_file}")
    return audio_file
