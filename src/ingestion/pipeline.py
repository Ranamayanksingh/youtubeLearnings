"""
pipeline.py — Orchestrates the full ingestion pipeline for one or more YouTube URLs.

Order: download → audio_extract → transcribe → frame_extract → visual_extract → align → synthesize → generate_md
"""

import json
import logging
from pathlib import Path

from src.aligner import aligner
from src.generator import md_generator
from src.ingestion import audio_extractor, downloader, frame_extractor
from src.synthesizer import synthesizer
from src.transcription import transcriber
from src.visual import extractor as visual_extractor

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")


def run(url: str, model_size: str | None = None) -> dict:
    """
    Run the full ingestion pipeline for a single YouTube URL.

    Returns the final metadata dict (with frames and transcript path populated).
    """
    logger.info(f"=== Starting ingestion: {url} ===")

    # Step 1: Download
    metadata = downloader.download(url)
    video_id = metadata["video_id"]
    out_dir = OUTPUT_DIR / video_id

    # Step 2: Extract audio
    audio_extractor.extract(video_id, out_dir)

    # Step 3: Transcribe
    transcript = transcriber.transcribe(video_id, out_dir, model_size=model_size)
    metadata["language_detected"] = transcript["language_detected"]
    metadata["transcript_segments"] = len(transcript["segments"])

    # Step 4: Extract frames
    frames = frame_extractor.extract(video_id, out_dir)

    # Step 5: Extract visual content (OCR + Vision fallback)
    visual = visual_extractor.extract(video_id, out_dir)

    # Step 6: Align transcript with visual frames
    aligned = aligner.align(video_id, out_dir)

    # Step 7: Synthesize into Hinglish study notes
    synthesized = synthesizer.synthesize(video_id, out_dir)

    # Step 8: Generate exam-ready Markdown cheat sheet
    md_file = md_generator.generate(video_id, out_dir)

    # Step 9: Update metadata
    metadata["frames"] = frames
    metadata["visual_stats"] = visual["stats"]
    metadata["aligned_segments"] = aligned["total_aligned_segments"]
    metadata["synthesized_topics"] = synthesized["total_topics"]
    metadata["study_notes"] = str(md_file)
    _write_metadata(out_dir, metadata)

    logger.info(f"=== Pipeline complete: [{video_id}] {metadata['title']} ===")
    logger.info(f"    Audio      → {out_dir}/audio.mp3")
    logger.info(f"    Transcript → {len(transcript['segments'])} segments")
    logger.info(f"    Frames     → {len(frames)} saved")
    logger.info(f"    Visual     → {visual['stats']['ocr_frames']} OCR, {visual['stats']['vision_frames']} Vision")
    logger.info(f"    Aligned    → {aligned['total_aligned_segments']} segments")
    logger.info(f"    Synthesized→ {synthesized['total_topics']} topics")
    logger.info(f"    ✓ Study notes → {md_file}")

    return metadata


def run_batch(urls: list[str], model_size: str | None = None) -> tuple[list[dict], list[str]]:
    """
    Run the ingestion pipeline for multiple URLs sequentially.

    Returns (succeeded_metadata_list, failed_urls).
    """
    succeeded = []
    failed = []

    for i, url in enumerate(urls, start=1):
        logger.info(f"[{i}/{len(urls)}] Processing: {url}")
        try:
            metadata = run(url, model_size=model_size)
            succeeded.append(metadata)
        except Exception as e:
            logger.error(f"Failed [{url}]: {e}")
            failed.append(url)

    return succeeded, failed


def _write_metadata(out_dir: Path, metadata: dict) -> None:
    path = out_dir / "metadata.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
