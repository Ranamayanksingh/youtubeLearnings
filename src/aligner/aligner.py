"""
aligner.py — Merges transcript segments and visual frames into a unified timeline.

Strategy: frame-as-anchor
  - Each frame defines a time window: [frame.timestamp, next_frame.timestamp)
  - Transcript segments whose start_sec falls in that window are grouped under that frame
  - Transcript before the first frame is attached to the first frame's window
  - Last frame's window extends to end of video
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def align(video_id: str, output_dir: Path) -> dict:
    """
    Align transcript segments with visual frames by timestamp.

    - Idempotent: returns existing aligned_content.json if already done.

    Returns the aligned_content dict.
    """
    aligned_file = output_dir / "aligned_content.json"

    if aligned_file.exists():
        logger.info(f"[{video_id}] Aligned content already exists, skipping.")
        with open(aligned_file, encoding="utf-8") as f:
            return json.load(f)

    transcript = _load_json(output_dir / "transcript.json", video_id, "transcript")
    visual = _load_json(output_dir / "visual_content.json", video_id, "visual_content")
    metadata = _load_json(output_dir / "metadata.json", video_id, "metadata")

    frames = visual.get("frames", [])
    if not frames:
        raise ValueError(f"[{video_id}] No frames in visual_content.json — cannot align.")

    segments = transcript.get("segments", [])
    duration = metadata.get("duration_seconds", 0)

    aligned_segments = _build_aligned_segments(frames, segments, duration)

    aligned_content = {
        "video_id": video_id,
        "title": metadata.get("title", ""),
        "duration_seconds": duration,
        "language_detected": transcript.get("language_detected", ""),
        "total_aligned_segments": len(aligned_segments),
        "segments": aligned_segments,
    }

    with open(aligned_file, "w", encoding="utf-8") as f:
        json.dump(aligned_content, f, ensure_ascii=False, indent=2)

    logger.info(
        f"[{video_id}] Alignment complete — "
        f"{len(aligned_segments)} segments → {aligned_file}"
    )
    return aligned_content


def _build_aligned_segments(
    frames: list[dict],
    transcript_segments: list[dict],
    duration: float,
) -> list[dict]:
    """
    Group transcript segments into frame-anchored windows.

    Each window covers [frame_start, next_frame_start).
    The last window covers [last_frame_start, duration].
    Any transcript before the first frame is prepended to the first window.
    """
    # Build time windows per frame
    windows = []
    for i, frame in enumerate(frames):
        window_start = frame["timestamp_sec"]
        window_end = frames[i + 1]["timestamp_sec"] if i + 1 < len(frames) else duration
        windows.append((window_start, window_end, frame))

    # Extend first window to capture transcript before first frame
    if windows:
        first_start, first_end, first_frame = windows[0]
        windows[0] = (0, first_end, first_frame)

    # Assign each transcript segment to the window its start_sec falls in
    window_transcripts: list[list[dict]] = [[] for _ in windows]

    for seg in transcript_segments:
        seg_start = seg["start_sec"]
        assigned = False
        for idx, (w_start, w_end, _) in enumerate(windows):
            if w_start <= seg_start < w_end:
                window_transcripts[idx].append(seg)
                assigned = True
                break
        if not assigned:
            # Segment starts after last window end — attach to last window
            window_transcripts[-1].append(seg)

    # Build output
    aligned = []
    for idx, ((w_start, w_end, frame), t_segs) in enumerate(
        zip(windows, window_transcripts), start=1
    ):
        aligned.append({
            "segment_index": idx,
            "window_start_sec": w_start,
            "window_end_sec": w_end,
            "frame": frame,
            "transcript": t_segs,
        })

    return aligned


def _load_json(path: Path, video_id: str, label: str) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"[{video_id}] {label} file not found: {path}. "
            f"Run the full pipeline first."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)
