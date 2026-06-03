# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A CLI pipeline that takes YouTube lecture videos (Hindi/English/Hinglish) and produces exam-ready Markdown cheat sheets. Built for Ayurveda competitive exam (AIAPGET) preparation.

## Commands

```bash
# Single video
uv run main.py ingest --url "https://www.youtube.com/watch?v=<id>"

# Batch processing (one URL per line, # for comments)
uv run main.py ingest --batch data/urls.txt

# Use a larger Whisper model for better Hindi transcription
uv run main.py ingest --url <url> --model medium
```

## Dependencies

```bash
uv sync                        # install all deps
brew install ffmpeg            # required for audio extraction
brew install tesseract tesseract-lang  # required for OCR (includes Hindi pack)
```

First run downloads the Whisper model (~500MB for `small`) from HuggingFace.

## Environment

Copy `.env.example` to `.env` and set:
```
ANTHROPIC_API_KEY=sk-ant-...
WHISPER_MODEL=small   # optional override
```

## Architecture

All pipeline steps are **idempotent** — re-running skips already-completed steps. Each step reads/writes from `output/<video_id>/`.

### Pipeline Order

```
main.py ingest
    └── pipeline.run()
        ├── 1. downloader       → output/<id>/video.mp4 + metadata.json
        ├── 2. audio_extractor  → output/<id>/audio.mp3  (mono 16kHz)
        ├── 3. transcriber      → output/<id>/transcript.json
        ├── 4. frame_extractor  → output/<id>/frames/*.jpg  (scene-change detection)
        ├── 5. visual extractor → output/<id>/visual_content.json  (OCR + Vision fallback)
        ├── 6. aligner          → output/<id>/aligned_content.json
        ├── 7. synthesizer      → output/<id>/synthesized.json
        └── 8. md_generator     → output/<id>/study_notes.md  ← final output
```

### Module Map

```
src/
├── ingestion/
│   ├── downloader.py       # yt-dlp wrapper
│   ├── audio_extractor.py  # ffmpeg — video → audio.mp3
│   ├── frame_extractor.py  # PySceneDetect — scene-change frames
│   └── pipeline.py         # orchestrates all 8 steps
├── transcription/
│   └── transcriber.py      # faster-whisper — audio → timestamped segments
├── visual/
│   ├── ocr.py              # Tesseract (Hindi + English)
│   ├── vision.py           # Claude Vision fallback for sparse OCR
│   └── extractor.py        # OCR-first, Vision fallback per frame
├── aligner/
│   └── aligner.py          # merges transcript + frames by timestamp
├── synthesizer/
│   └── synthesizer.py      # Claude — per-segment Hinglish notes
└── generator/
    └── md_generator.py     # Claude — full-context exam cheat sheet
```

### Key Design Decisions

- **Frame anchor strategy**: each video frame defines a time window; transcript segments whose `start_sec` falls in that window are grouped under that frame
- **Short segment merging**: windows < 15s or with < 10 chars of speech are merged into the adjacent segment before synthesis
- **OCR-first, Vision fallback**: Tesseract runs on every frame; Claude Vision only called when OCR yields < 20 chars
- **Two LLM stages**: synthesizer (per-segment, resumable) → md_generator (full-context, final restructuring)
- **Output language**: Hinglish throughout — preserve Hindi terms, explain in natural Hindi-English mix
- **Comparison tables**: md_generator prompt enforces Markdown tables for any Acharya-vs-Acharya comparison

### Data Flow per Video

```
output/<video_id>/
├── video.mp4                # raw download
├── audio.mp3                # mono 16kHz
├── transcript.json          # {segments: [{index, start_sec, end_sec, text}]}
├── frames/                  # 0001_t00m32s.jpg  (filename encodes timestamp)
├── visual_content.json      # {frames: [{ocr_text, vision_description, content_type}]}
├── aligned_content.json     # {segments: [{frame, transcript[], window_start_sec, window_end_sec}]}
├── synthesized.json         # {topics: [{heading, content, key_points, frame_file}]}
└── study_notes.md           # ← exam cheat sheet with comparison tables + screenshots
```

## Planned Extensions

- **Telegram bot**: expose pipeline as a bot — send URL, receive `.md` file
- **Web UI**: upload URL, download `.md`
- **Claude Vision for all frames**: if OCR quality is consistently poor, switch `extractor.py` to always use Vision
