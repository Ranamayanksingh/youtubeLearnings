"""
extractor.py — Orchestrates OCR + Claude Vision fallback for all frames of a video.

Strategy:
  1. Run Tesseract OCR on every frame (free, local)
  2. If OCR text is sufficient (>= 20 chars), use it — skip Claude Vision
  3. If OCR is sparse, call Claude Vision for a richer description
  4. Write all results to visual_content.json
"""

import json
import logging
from pathlib import Path

from src.visual import ocr, vision

logger = logging.getLogger(__name__)


def extract(video_id: str, output_dir: Path) -> dict:
    """
    Extract visual content from all frames of a video.

    - Idempotent: returns existing visual_content.json if already done.
    - Uses OCR first; falls back to Claude Vision for sparse frames.

    Returns the visual_content dict.
    """
    visual_file = output_dir / "visual_content.json"
    frames_dir = output_dir / "frames"

    if visual_file.exists():
        logger.info(f"[{video_id}] Visual content already extracted, skipping.")
        with open(visual_file, encoding="utf-8") as f:
            return json.load(f)

    frame_files = sorted(frames_dir.glob("*.jpg"))
    if not frame_files:
        raise FileNotFoundError(f"[{video_id}] No frames found in {frames_dir}")

    # Load frame index from metadata for timestamp info
    frame_index = _load_frame_index(output_dir, video_id)

    logger.info(f"[{video_id}] Extracting visual content from {len(frame_files)} frame(s)...")

    results = []
    ocr_count = 0
    vision_count = 0

    for frame_file in frame_files:
        frame_meta = frame_index.get(frame_file.name, {})
        frame_result = _process_frame(
            video_id=video_id,
            frame_path=frame_file,
            frame_meta=frame_meta,
        )
        results.append(frame_result)

        if frame_result["source"] == "ocr":
            ocr_count += 1
        else:
            vision_count += 1

    visual_content = {
        "video_id": video_id,
        "frames": results,
        "stats": {
            "total_frames": len(results),
            "ocr_frames": ocr_count,
            "vision_frames": vision_count,
        },
    }

    with open(visual_file, "w", encoding="utf-8") as f:
        json.dump(visual_content, f, ensure_ascii=False, indent=2)

    logger.info(
        f"[{video_id}] Visual extraction complete — "
        f"{ocr_count} OCR, {vision_count} Vision fallback → {visual_file}"
    )
    return visual_content


def _process_frame(video_id: str, frame_path: Path, frame_meta: dict) -> dict:
    """Run OCR on a frame; fall back to Claude Vision if OCR is insufficient."""
    base_result = {
        "index": frame_meta.get("index"),
        "timestamp_sec": frame_meta.get("timestamp_sec"),
        "file": f"frames/{frame_path.name}",
        "ocr_text": "",
        "vision_description": "",
        "content_type": "unclear",
        "source": "ocr",
    }

    # Layer 1: OCR
    try:
        ocr_text = ocr.extract_text(str(frame_path))
        base_result["ocr_text"] = ocr_text
    except Exception as e:
        logger.warning(f"[{video_id}] OCR failed for {frame_path.name}: {e}")
        ocr_text = ""

    if ocr.is_sufficient(ocr_text):
        logger.debug(f"[{video_id}] {frame_path.name} — OCR sufficient ({len(ocr_text.strip())} chars)")
        base_result["content_type"] = "slide"  # reasonable default when OCR works
        return base_result

    # Layer 2: Claude Vision fallback
    logger.info(
        f"[{video_id}] {frame_path.name} — OCR sparse ({len(ocr_text.strip())} chars), "
        f"falling back to Claude Vision..."
    )
    try:
        vision_result = vision.describe_frame(str(frame_path))
        base_result["ocr_text"] = vision_result["text"] or ocr_text
        base_result["vision_description"] = vision_result["description"]
        base_result["content_type"] = vision_result["content_type"]
        base_result["source"] = "vision"
    except EnvironmentError as e:
        # API key not set — log and continue with whatever OCR gave us
        logger.warning(f"[{video_id}] {e} Keeping sparse OCR result.")
    except Exception as e:
        logger.warning(f"[{video_id}] Claude Vision failed for {frame_path.name}: {e}")

    return base_result


def _load_frame_index(output_dir: Path, video_id: str) -> dict:
    """
    Build frame index keyed by filename, parsing timestamps directly from filenames.
    Filename format: 0001_t00m32s.jpg → timestamp = 32s
    This avoids depending on metadata.json which is written after this step.
    """
    frames_dir = output_dir / "frames"
    index = {}
    for i, f in enumerate(sorted(frames_dir.glob("*.jpg")), start=1):
        try:
            stem = f.stem  # e.g. "0001_t00m32s"
            time_part = stem.split("_t")[1]  # "00m32s"
            minutes = int(time_part.split("m")[0])
            seconds = int(time_part.split("m")[1].rstrip("s"))
            ts = minutes * 60 + seconds
        except (IndexError, ValueError):
            ts = 0
        index[f.name] = {"index": i, "timestamp_sec": ts, "file": f"frames/{f.name}"}
    return index
