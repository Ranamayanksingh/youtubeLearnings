"""
frame_extractor.py — Extracts key frames from a video on scene/slide changes.

Uses PySceneDetect (content-aware) to find transitions.
Falls back to fixed-interval sampling if too few scenes are detected.

Output: output/<video_id>/frames/<index>_t<mm>m<ss>s.jpg
"""

import logging
from pathlib import Path

import cv2
from scenedetect import SceneManager, open_video
from scenedetect.detectors import ContentDetector

logger = logging.getLogger(__name__)

# Tuning constants
CONTENT_THRESHOLD = 18.0       # lowered from 27 — catches slide transitions, not just dramatic cuts
MIN_SCENE_LENGTH_SECS = 2      # ignore scenes shorter than this (avoid flicker noise)
FALLBACK_INTERVAL_SECS = 60    # fixed interval if scene detection yields too few frames
MIN_SCENES_THRESHOLD = 3       # if fewer scenes than this, trigger fallback
MAX_GAP_SECS = 90              # never go more than this many seconds without a frame (gap fill)


def extract(video_id: str, output_dir: Path) -> list[dict]:
    """
    Detect scene changes and save one representative frame per scene.

    - Idempotent: skips if frames/ directory already has images.
    - Falls back to fixed-interval sampling if scene detection yields < MIN_SCENES_THRESHOLD scenes.

    Returns a list of frame metadata dicts:
      [{"index": 1, "timestamp_sec": 32, "file": "frames/0001_t00m32s.jpg"}, ...]
    """
    video_file = output_dir / "video.mp4"
    frames_dir = output_dir / "frames"

    if not video_file.exists():
        raise FileNotFoundError(f"Video file not found: {video_file}")

    # Idempotent check
    existing = sorted(frames_dir.glob("*.jpg")) if frames_dir.exists() else []
    if existing:
        logger.info(f"[{video_id}] Frames already extracted ({len(existing)} found), skipping.")
        return _frames_from_existing(existing, output_dir)

    frames_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"[{video_id}] Detecting scene changes...")
    duration = _get_duration(str(video_file))
    timestamps = _detect_scene_timestamps(str(video_file))

    if len(timestamps) < MIN_SCENES_THRESHOLD:
        logger.info(
            f"[{video_id}] Only {len(timestamps)} scene(s) detected — "
            f"falling back to fixed {FALLBACK_INTERVAL_SECS}s interval sampling."
        )
        timestamps = list(range(0, int(duration), FALLBACK_INTERVAL_SECS))
    else:
        # Gap-fill: if two consecutive scene timestamps are more than MAX_GAP_SECS apart,
        # insert evenly-spaced frames in between so no window is too long.
        timestamps = _fill_gaps(timestamps, int(duration))
        logger.info(
            f"[{video_id}] {len(timestamps)} frame(s) after gap-fill "
            f"(max gap: {MAX_GAP_SECS}s)"
        )

    logger.info(f"[{video_id}] Saving {len(timestamps)} frame(s)...")
    frames = _save_frames(str(video_file), timestamps, frames_dir, video_id)

    logger.info(f"[{video_id}] Frame extraction complete → {frames_dir}")
    return frames


def _detect_scene_timestamps(video_path: str) -> list[int]:
    """Return start-of-scene timestamps in seconds using content-aware detection."""
    min_len_frames = MIN_SCENE_LENGTH_SECS * 30  # assume ~30fps; SceneDetect handles actual fps

    video = open_video(video_path)
    scene_manager = SceneManager()
    scene_manager.add_detector(
        ContentDetector(threshold=CONTENT_THRESHOLD, min_scene_len=min_len_frames)
    )
    scene_manager.detect_scenes(video, show_progress=False)
    scenes = scene_manager.get_scene_list()

    # Use start timecode of each scene
    return [int(scene[0].get_seconds()) for scene in scenes]


def _save_frames(
    video_path: str,
    timestamps: list[int],
    frames_dir: Path,
    video_id: str,
) -> list[dict]:
    """Seek to each timestamp and save a JPEG frame."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"[{video_id}] Cannot open video: {video_path}")

    frames = []
    try:
        for idx, ts in enumerate(timestamps, start=1):
            cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000)
            ret, frame = cap.read()
            if not ret:
                logger.warning(f"[{video_id}] Could not read frame at {ts}s, skipping.")
                continue

            filename = _frame_filename(idx, ts)
            filepath = frames_dir / filename
            cv2.imwrite(str(filepath), frame)

            frames.append({
                "index": idx,
                "timestamp_sec": ts,
                "file": f"frames/{filename}",
            })
    finally:
        cap.release()

    return frames


def _frame_filename(index: int, timestamp_sec: int) -> str:
    minutes = timestamp_sec // 60
    seconds = timestamp_sec % 60
    return f"{index:04d}_t{minutes:02d}m{seconds:02d}s.jpg"


def _get_duration(video_path: str) -> float:
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    return frame_count / fps if fps > 0 else 0.0


def _fill_gaps(timestamps: list[int], duration: int) -> list[int]:
    """
    Ensure no two consecutive timestamps are more than MAX_GAP_SECS apart.
    Inserts evenly-spaced fill frames inside any gap that exceeds the limit.
    Also appends a frame near the end of the video if needed.
    """
    # Ensure we have a sentinel at the end so the last gap is checked too
    extended = sorted(set(timestamps))
    if duration > 0 and (not extended or duration - extended[-1] > MAX_GAP_SECS):
        extended.append(min(duration - 2, duration))  # near-end frame

    result = []
    for i, ts in enumerate(extended):
        result.append(ts)
        if i + 1 < len(extended):
            gap = extended[i + 1] - ts
            if gap > MAX_GAP_SECS:
                # how many fill frames do we need?
                n_fill = gap // MAX_GAP_SECS
                step = gap / (n_fill + 1)
                for j in range(1, n_fill + 1):
                    result.append(int(ts + step * j))

    return sorted(set(result))


def _frames_from_existing(existing_files: list[Path], output_dir: Path) -> list[dict]:
    """Reconstruct frame metadata from already-saved frame filenames."""
    frames = []
    for idx, f in enumerate(existing_files, start=1):
        # Parse timestamp from filename: 0001_t00m32s.jpg
        try:
            stem = f.stem  # e.g. "0001_t00m32s"
            time_part = stem.split("_t")[1]  # "00m32s"
            minutes = int(time_part.split("m")[0])
            seconds = int(time_part.split("m")[1].rstrip("s"))
            ts = minutes * 60 + seconds
        except (IndexError, ValueError):
            ts = 0

        frames.append({
            "index": idx,
            "timestamp_sec": ts,
            "file": f"frames/{f.name}",
        })
    return frames
