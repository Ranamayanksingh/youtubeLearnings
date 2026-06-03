# Ingestion Component — Implementation Plan

## Responsibility

Accept one or more YouTube URLs, download the video, extract the audio track, and sample key frames (on slide/scene changes). Output structured artifacts that downstream components consume.

---

## Inputs & Outputs

| | Detail |
|---|---|
| **Input** | Single YouTube URL **or** a `.txt` file with one URL per line (batch mode) |
| **Output dir** | `output/<video_id>/` per video |

### Output Artifacts per Video

```
output/
└── <video_id>/
    ├── audio.mp3              # extracted audio for Whisper
    ├── frames/
    │   ├── 0001_t00m32s.jpg   # filename encodes timestamp
    │   ├── 0002_t01m14s.jpg
    │   └── ...
    └── metadata.json          # title, duration, url, language hint, frame index
```

`metadata.json` shape:
```json
{
  "video_id": "abc123",
  "title": "Ayurveda Basics - Lecture 1",
  "url": "https://youtube.com/watch?v=abc123",
  "duration_seconds": 3420,
  "language_hint": "hi",
  "frames": [
    { "index": 1, "timestamp_sec": 32, "file": "frames/0001_t00m32s.jpg" },
    ...
  ]
}
```

---

## Module Structure

```
ingestion/
├── __init__.py
├── downloader.py       # yt-dlp wrapper — video + audio download
├── frame_extractor.py  # PySceneDetect — scene-change frame sampling
├── audio_extractor.py  # ffmpeg — strips audio from video to mp3
└── pipeline.py         # orchestrates the above; single entry point
```

CLI entry point (top-level):
```
main.py ingest --url <url>
main.py ingest --batch <urls.txt>
```

---

## Component Details

### downloader.py
- Wraps `yt-dlp` to download the best available quality video
- Fetches video metadata (title, duration, detected language)
- Saves raw video to a temp location under `output/<video_id>/`
- Skips download if `output/<video_id>/` already exists (idempotent re-runs)

### audio_extractor.py
- Uses `ffmpeg` (via `subprocess` or `ffmpeg-python`) to extract audio
- Output: `audio.mp3` at 16kHz mono (optimal for Whisper)
- Runs after download completes

### frame_extractor.py
- Uses `PySceneDetect` with content-aware detection to find scene/slide changes
- Saves one representative frame per detected scene
- Frame filename encodes timestamp: `0001_t00m32s.jpg`
- Configurable threshold to tune sensitivity (default tuned for lecture slides)

### pipeline.py
- Accepts single URL or list of URLs
- Calls downloader → audio_extractor → frame_extractor in sequence
- Writes `metadata.json` at end
- Handles errors per-video (one failure doesn't abort batch)
- Logs progress to stdout

---

## Dependencies

```
yt-dlp
ffmpeg-python
scenedetect[opencv]   # PySceneDetect with OpenCV backend
```

System dependency: `ffmpeg` must be installed (`brew install ffmpeg`)

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Invalid / private URL | Log error, skip video, continue batch |
| Video already downloaded | Skip download, re-use existing artifacts |
| No scene changes detected | Fall back to fixed-interval sampling (every 60s) |
| ffmpeg not found | Fail fast with clear install instruction |

---

## What This Component Does NOT Do

- No transcription (that's Component 2)
- No OCR or visual understanding (that's Component 3)
- No cleanup of the raw video file after extraction (kept for debugging; can add a `--clean` flag later)

---

## Open Questions

1. Should we keep the raw downloaded video file after extraction, or delete it to save disk space?
2. For batch mode, run videos sequentially or in parallel?
