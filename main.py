"""
main.py — CLI entry point for the YouTube Learning Material Extractor.
"""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # loads .env from project root if present

from src.ingestion import pipeline
from src.utils import cleanup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def cmd_ingest(args: argparse.Namespace) -> None:
    urls: list[str] = []

    if args.url:
        urls.append(args.url.strip())

    if args.batch:
        batch_file = Path(args.batch)
        if not batch_file.exists():
            logger.error(f"Batch file not found: {batch_file}")
            sys.exit(1)
        lines = batch_file.read_text(encoding="utf-8").splitlines()
        urls.extend(line.strip() for line in lines if line.strip() and not line.startswith("#"))

    if not urls:
        logger.error("Provide --url or --batch with at least one URL.")
        sys.exit(1)

    logger.info(f"Processing {len(urls)} video(s)...")

    succeeded, failed = pipeline.run_batch(urls, model_size=args.model)

    logger.info(f"{len(succeeded)} succeeded, {len(failed)} failed.")
    if failed:
        logger.warning("Failed URLs:")
        for u in failed:
            logger.warning(f"  {u}")
        sys.exit(1)


def cmd_cleanup(args: argparse.Namespace) -> None:
    if args.all:
        archived = cleanup.archive_all()
        logger.info(f"Done — {len(archived)} video(s) archived to final/")
    elif args.video_id:
        path = cleanup.archive(args.video_id)
        logger.info(f"Done — archived to {path}/")
    else:
        logger.error("Provide --all or --video-id <id>.")
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="YouTube Learning Material Extractor",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- ingest ---
    ingest = subparsers.add_parser("ingest", help="Download and extract video content")
    group = ingest.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="Single YouTube URL")
    group.add_argument("--batch", metavar="FILE", help="Text file with one YouTube URL per line")
    ingest.add_argument(
        "--model",
        default=None,
        metavar="SIZE",
        help="Whisper model size: tiny, base, small (default), medium, large-v3",
    )

    # --- cleanup ---
    clean = subparsers.add_parser(
        "cleanup",
        help="Archive study notes + frames into final/ (does not delete output/)",
    )
    clean_group = clean.add_mutually_exclusive_group(required=True)
    clean_group.add_argument("--all", action="store_true", help="Archive all completed videos")
    clean_group.add_argument("--video-id", metavar="ID", help="Archive a single video by ID")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "cleanup":
        cmd_cleanup(args)


if __name__ == "__main__":
    main()
