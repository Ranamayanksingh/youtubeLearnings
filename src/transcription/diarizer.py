"""
diarizer.py — Optional speaker diarization for meeting recordings.

Uses pyannote.audio to label who spoke when, then merges speaker labels
into the existing transcript.json segments.

Requires:
  - HF_TOKEN environment variable
  - Accepted model licenses at:
      hf.co/pyannote/speaker-diarization-3.1
      hf.co/pyannote/segmentation-3.0

If HF_TOKEN is missing or diarization fails, this step is skipped gracefully
and the transcript remains without speaker labels.

Output: output/<video_id>/diarized_transcript.json
  {
    "video_id": "...",
    "speakers_detected": 2,
    "segments": [
      {"index": 1, "start_sec": 0.5, "end_sec": 4.2, "text": "...", "speaker": "SPEAKER_00"},
      ...
    ]
  }
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def diarize(video_id: str, output_dir: Path) -> dict:
    """
    Run speaker diarization on audio.mp3 and merge labels into transcript segments.

    - Idempotent: returns existing diarized_transcript.json if already done.
    - Skips gracefully if HF_TOKEN is not set or pyannote is unavailable.

    Returns the diarized transcript dict (or plain transcript dict if skipped).
    """
    diarized_file = output_dir / "diarized_transcript.json"

    if diarized_file.exists():
        logger.info(f"[{video_id}] Diarized transcript already exists, skipping.")
        with open(diarized_file, encoding="utf-8") as f:
            return json.load(f)

    transcript_file = output_dir / "transcript.json"
    if not transcript_file.exists():
        raise FileNotFoundError(
            f"[{video_id}] transcript.json not found — run transcriber first."
        )

    with open(transcript_file, encoding="utf-8") as f:
        transcript = json.load(f)

    hf_token = os.environ.get("HF_TOKEN", "").strip()
    if not hf_token:
        logger.warning(
            f"[{video_id}] HF_TOKEN not set — skipping speaker diarization. "
            "Set HF_TOKEN in .env to enable speaker labels."
        )
        return transcript

    audio_file = output_dir / "audio.mp3"
    if not audio_file.exists():
        logger.warning(f"[{video_id}] audio.mp3 not found — skipping diarization.")
        return transcript

    try:
        from pyannote.audio import Pipeline
        import torch
    except ImportError:
        logger.warning(
            f"[{video_id}] pyannote.audio not installed — skipping diarization."
        )
        return transcript

    logger.info(f"[{video_id}] Running speaker diarization...")

    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )

        # Use MPS on Apple Silicon if available, else CPU
        if torch.backends.mps.is_available():
            pipeline.to(torch.device("mps"))
        elif torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))

        diarization = pipeline(str(audio_file))

    except Exception as exc:
        logger.warning(
            f"[{video_id}] Diarization failed ({exc}) — continuing without speaker labels."
        )
        return transcript

    # Build a list of (start, end, speaker) turns from pyannote output
    turns = [
        (turn.start, turn.end, speaker)
        for turn, _, speaker in diarization.itertracks(yield_label=True)
    ]

    speakers_seen: set[str] = set()
    segments = transcript.get("segments", [])

    for seg in segments:
        seg_mid = (seg["start_sec"] + seg["end_sec"]) / 2
        speaker = _find_speaker(seg_mid, turns)
        seg["speaker"] = speaker
        speakers_seen.add(speaker)

    result = {
        "video_id": video_id,
        "speakers_detected": len(speakers_seen),
        "speaker_ids": sorted(speakers_seen),
        "segments": segments,
    }

    with open(diarized_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info(
        f"[{video_id}] Diarization complete — "
        f"{len(speakers_seen)} speaker(s): {sorted(speakers_seen)}"
    )
    return result


def _find_speaker(timestamp: float, turns: list[tuple]) -> str:
    """Return the speaker label for the turn containing this timestamp."""
    for start, end, speaker in turns:
        if start <= timestamp <= end:
            return speaker
    # If no exact match, find the closest turn
    if not turns:
        return "SPEAKER_00"
    closest = min(turns, key=lambda t: min(abs(t[0] - timestamp), abs(t[1] - timestamp)))
    return closest[2]
