# Transcription Component — Plan

## Responsibility

Take the extracted `audio.mp3` for a video and produce a timestamped transcript.
Since the content is Hindi/Hinglish, we preserve it as-is (no forced translation) —
the LLM synthesis layer later will clean and structure it in Hinglish.

---

## Inputs & Outputs

| | Detail |
|---|---|
| **Input** | `output/<video_id>/audio.mp3` |
| **Output** | `output/<video_id>/transcript.json` |

### transcript.json shape

```json
{
  "video_id": "abc123",
  "language_detected": "hi",
  "segments": [
    {
      "index": 1,
      "start_sec": 0.0,
      "end_sec": 4.8,
      "text": "Aaj hum Govind Parikh ke baare mein padhenge"
    },
    ...
  ]
}
```

Each segment corresponds to one natural speech chunk Whisper identifies.

---

## Module Structure

```
src/
└── transcription/
    ├── __init__.py
    └── transcriber.py      # Whisper wrapper — transcribe audio → transcript.json
```

---

## Component Details

### transcriber.py

- Uses `faster-whisper` (drop-in Whisper replacement, significantly faster, lower RAM)
- Model: `medium` by default — good balance of accuracy for Hindi/Hinglish
  - Configurable via env var `WHISPER_MODEL` (tiny / base / small / medium / large-v3)
- Runs on CPU (works everywhere); uses GPU automatically if available
- Idempotent: skips if `transcript.json` already exists
- Detects language from first 30s of audio — stored in output as `language_detected`
- Segments include `start_sec`, `end_sec`, `text`

---

## Technology Choice

| Option | Reason for / against |
|---|---|
| `openai-whisper` | Original, but slow on CPU |
| `faster-whisper` | 4x faster, lower memory, same accuracy — preferred |
| AssemblyAI / Deepgram | Paid API, requires internet — avoid for now |

**Choice: `faster-whisper`**

---

## Dependencies to Add

```
faster-whisper
```

System: no extra install needed — faster-whisper bundles CTranslate2.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| `audio.mp3` missing | Raise `FileNotFoundError` with clear message |
| Whisper model download fails | Let exception propagate — user needs internet on first run |
| Already transcribed | Skip, load and return existing `transcript.json` |
| Empty transcript (silent video) | Write empty segments list, log warning |

---

## Integration into Pipeline

`pipeline.py` will call `transcriber.transcribe(video_id, out_dir)` as Step 3,
after audio extraction and before frame extraction (both are independent, but
transcript is needed earlier by the synthesis layer).

Updated pipeline order:
```
download → audio_extract → transcribe → frame_extract → metadata update
```

---

## Open Questions

1. **Model size** — `medium` is recommended but ~1.5GB download on first run. Use `small` as default to keep it lightweight, with a `--model` CLI flag to override?
2. **Word-level timestamps** — Whisper can give per-word timing (useful for aligning with frames). Worth enabling, or segment-level is enough?
