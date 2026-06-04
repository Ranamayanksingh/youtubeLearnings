"""
file_uploader.py — Stages a local meeting file into output/<job_id>/.

Replaces the downloader step for meeting recordings.
Supports: .mp4, .webm (video), .mp3, .m4a, .wav (audio-only).

Returns a metadata dict compatible with downloader.download() output.
"""

import json
import logging
import shutil
from pathlib import Path

import cv2

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov"}


def upload(file_path: str, job_id: str) -> dict:
    """
    Stage a local meeting file into output/<job_id>/.

    - For video files (.mp4, .webm): copies to output/<job_id>/video.mp4
    - For audio files (.mp3, .m4a, .wav): copies to output/<job_id>/audio.mp3
      (audio extraction step will be skipped automatically)
    - Writes metadata.json
    - Idempotent: skips copy if destination already exists

    Returns metadata dict with keys: video_id, title, url, duration_seconds.
    """
    src = Path(file_path)
    if not src.exists():
        raise FileNotFoundError(f"Meeting file not found: {file_path}")

    suffix = src.suffix.lower()
    if suffix not in AUDIO_EXTENSIONS and suffix not in VIDEO_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format: {suffix}. "
            f"Supported: {sorted(AUDIO_EXTENSIONS | VIDEO_EXTENSIONS)}"
        )

    out_dir = Path("output") / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    is_audio_only = suffix in AUDIO_EXTENSIONS
    title = src.stem  # filename without extension

    if is_audio_only:
        dest = out_dir / "audio.mp3"
        if not dest.exists():
            logger.info(f"[{job_id}] Copying audio file → {dest}")
            shutil.copy2(str(src), str(dest))
        else:
            logger.info(f"[{job_id}] Audio already staged, skipping copy.")
        duration_sec = _get_audio_duration(str(dest))
    else:
        dest = out_dir / "video.mp4"
        if not dest.exists():
            logger.info(f"[{job_id}] Copying video file → {dest}")
            shutil.copy2(str(src), str(dest))
        else:
            logger.info(f"[{job_id}] Video already staged, skipping copy.")
        duration_sec = _get_video_duration(str(dest))

    metadata = {
        "video_id": job_id,
        "title": title,
        "url": f"local://{src.name}",
        "duration_seconds": int(duration_sec),
        "source": "local_upload",
        "original_filename": src.name,
        "is_audio_only": is_audio_only,
    }

    metadata_file = out_dir / "metadata.json"
    if not metadata_file.exists():
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    logger.info(
        f"[{job_id}] Staged '{src.name}' "
        f"({'audio-only' if is_audio_only else 'video'}, "
        f"{int(duration_sec)}s) → {out_dir}"
    )
    return metadata


def _get_video_duration(video_path: str) -> float:
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    return frame_count / fps if fps > 0 else 0.0


def _get_audio_duration(audio_path: str) -> float:
    """Use ffprobe via cv2 fallback — cv2 can open audio files too."""
    try:
        cap = cv2.VideoCapture(audio_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.release()
        if fps > 0:
            return frame_count / fps
    except Exception:
        pass
    return 0.0
