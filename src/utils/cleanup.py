"""
cleanup.py — Archives final study notes into a clean `final/` folder.

Does NOT delete anything from output/. Just copies the essential files:
  - study_notes.md
  - frames/ (screenshots referenced in the notes)
  - a minimal video_info.json (url, title, duration)

Run via CLI:
    uv run main.py cleanup --all
    uv run main.py cleanup --video-id <id>
"""

import json
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")
FINAL_DIR = Path("final")


def archive(video_id: str) -> Path:
    """
    Copy study_notes.md + referenced frames + video_info.json
    into final/<video_id>/.

    - Idempotent: re-running overwrites with latest study notes.
    - Does NOT touch output/<video_id>/.

    Returns the path to the final/<video_id>/ directory.
    """
    out_dir = OUTPUT_DIR / video_id
    final_video_dir = FINAL_DIR / video_id

    study_notes = out_dir / "study_notes.md"
    metadata_file = out_dir / "metadata.json"

    if not study_notes.exists():
        raise FileNotFoundError(
            f"[{video_id}] study_notes.md not found. Run the full pipeline first."
        )

    final_video_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy study notes
    shutil.copy2(study_notes, final_video_dir / "study_notes.md")
    logger.info(f"[{video_id}] Copied study_notes.md → {final_video_dir}/")

    # 2. Copy only the frames actually referenced in the notes
    referenced_frames = _extract_referenced_frames(study_notes)
    if referenced_frames:
        frames_dest = final_video_dir / "frames"
        frames_dest.mkdir(exist_ok=True)
        for frame_name in referenced_frames:
            src = out_dir / "frames" / frame_name
            if src.exists():
                shutil.copy2(src, frames_dest / frame_name)
        logger.info(f"[{video_id}] Copied {len(referenced_frames)} referenced frame(s)")

    # 3. Write minimal video_info.json
    video_info = _build_video_info(video_id, metadata_file)
    info_path = final_video_dir / "video_info.json"
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(video_info, f, ensure_ascii=False, indent=2)
    logger.info(f"[{video_id}] Written video_info.json")

    logger.info(f"[{video_id}] ✓ Archived to {final_video_dir}/")
    return final_video_dir


def archive_all() -> list[Path]:
    """
    Archive all videos in output/ that have a completed study_notes.md.

    Returns list of archived final/ directories.
    """
    if not OUTPUT_DIR.exists():
        logger.warning("output/ directory not found — nothing to archive.")
        return []

    archived = []
    skipped = []

    for video_dir in sorted(OUTPUT_DIR.iterdir()):
        if not video_dir.is_dir():
            continue
        video_id = video_dir.name
        if not (video_dir / "study_notes.md").exists():
            skipped.append(video_id)
            continue
        try:
            path = archive(video_id)
            archived.append(path)
        except Exception as e:
            logger.error(f"[{video_id}] Archive failed: {e}")

    if skipped:
        logger.info(f"Skipped {len(skipped)} video(s) with no study_notes.md: {skipped}")

    logger.info(f"Archived {len(archived)} video(s) → {FINAL_DIR}/")
    return archived


def _extract_referenced_frames(study_notes_path: Path) -> list[str]:
    """Parse study_notes.md and extract all frame filenames from image links."""
    content = study_notes_path.read_text(encoding="utf-8")
    frames = []
    for line in content.splitlines():
        # Match: ![](frames/0001_t00m00s.jpg)
        if "![" in line and "frames/" in line:
            try:
                frame_path = line.split("frames/")[1].split(")")[0].strip()
                if frame_path:
                    frames.append(frame_path)
            except IndexError:
                continue
    return list(dict.fromkeys(frames))  # deduplicate, preserve order


def _build_video_info(video_id: str, metadata_file: Path) -> dict:
    """Build a minimal video info dict from metadata.json."""
    info = {"video_id": video_id}

    if metadata_file.exists():
        with open(metadata_file, encoding="utf-8") as f:
            meta = json.load(f)
        info["title"] = meta.get("title", "")
        info["url"] = meta.get("url", "")
        info["duration_seconds"] = meta.get("duration_seconds")
        info["language_detected"] = meta.get("language_detected", "")
        info["upload_date"] = meta.get("upload_date", "")
        info["uploader"] = meta.get("uploader", "")
    else:
        logger.warning(f"[{video_id}] metadata.json not found — video_info will be minimal.")

    return info
