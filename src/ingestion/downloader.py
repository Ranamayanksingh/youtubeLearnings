"""
downloader.py — yt-dlp wrapper for downloading YouTube videos and extracting metadata.
"""

import json
import logging
from pathlib import Path

import yt_dlp

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")


def _video_output_dir(video_id: str) -> Path:
    return OUTPUT_DIR / video_id


def _metadata_path(video_id: str) -> Path:
    return _video_output_dir(video_id) / "metadata.json"


def _video_path(video_id: str) -> Path:
    return _video_output_dir(video_id) / "video.mp4"


def extract_video_id(url: str) -> str:
    """Extract the YouTube video ID from a URL without downloading anything."""
    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info["id"]


def download(url: str) -> dict:
    """
    Download a YouTube video and return its metadata dict.

    - Skips download if video.mp4 already exists (idempotent).
    - Creates output/<video_id>/ directory automatically.
    - Writes metadata.json alongside the video.

    Returns the metadata dict.
    """
    # First extract video_id to check if already downloaded
    logger.info(f"Resolving video ID for: {url}")
    video_id = extract_video_id(url)
    out_dir = _video_output_dir(video_id)
    video_file = _video_path(video_id)

    if video_file.exists():
        logger.info(f"[{video_id}] Already downloaded, loading existing metadata.")
        with open(_metadata_path(video_id)) as f:
            return json.load(f)

    out_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": str(video_file),
        "quiet": False,
        "no_warnings": False,
        "noprogress": False,
    }

    logger.info(f"[{video_id}] Downloading video...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    metadata = _build_metadata(info)
    _write_metadata(video_id, metadata)

    logger.info(f"[{video_id}] Download complete: {out_dir}")
    return metadata


def _build_metadata(info: dict) -> dict:
    """Build a clean metadata dict from yt-dlp info."""
    return {
        "video_id": info.get("id"),
        "title": info.get("title"),
        "url": info.get("webpage_url") or info.get("original_url"),
        "duration_seconds": info.get("duration"),
        "language_hint": info.get("language"),
        "uploader": info.get("uploader"),
        "upload_date": info.get("upload_date"),
        "frames": [],  # populated later by frame_extractor
    }


def _write_metadata(video_id: str, metadata: dict) -> None:
    path = _metadata_path(video_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    logger.info(f"[{video_id}] Metadata written to {path}")
