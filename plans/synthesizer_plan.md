# Content Synthesizer — Plan

## Responsibility

Take the aligned content (frames + transcript per window) and produce clean,
structured Hinglish study notes. This is the LLM layer — Claude reads what was
on screen and what the teacher said, and rewrites it as a student would want to
study it.

---

## The Core Challenge

Raw aligned content is noisy:
- OCR has garbled characters, broken Devanagari, mixed symbols
- Transcript (Whisper small) has hallucinations, repetitions, filler words
- Same concept may be spread across multiple segments as the teacher builds on it

Claude's job: ignore the noise, extract the actual teaching, write it clearly in Hinglish.

---

## Inputs & Outputs

| | Detail |
|---|---|
| **Input** | `output/<video_id>/aligned_content.json` |
| **Output** | `output/<video_id>/synthesized.json` |

### synthesized.json shape

```json
{
  "video_id": "abc123",
  "title": "Govind Parikh Page 1 ...",
  "topics": [
    {
      "segment_index": 3,
      "window_start_sec": 238,
      "window_end_sec": 422,
      "frame_file": "frames/0003_t03m58s.jpg",
      "heading": "Dhoompaan ka Angul Praman",
      "content": "Dhoompaan ke liye alag alag Acharyas ne alag praman bataye hain:\n- Charaka: 24, 32, 36 angul\n- Sushruta: 24, 32 (36 ki jagah 9 bataya)\n- Ashtanga Hridayam: ...",
      "key_points": [
        "Charaka ne 3 praman bataye: 24, 32, 36 angul",
        "Sushruta ne 36 ki jagah 9 angul bataya"
      ]
    },
    ...
  ]
}
```

---

## Processing Strategy

### Option A — Segment by Segment (chosen)
Send each aligned segment (one frame window) to Claude independently.

**Pros:**
- Predictable token usage per call
- Easy to resume if interrupted (idempotent per segment)
- Parallelisable later

**Cons:**
- Claude lacks cross-segment context (teacher may reference previous slide)

**Mitigation:** Pass previous segment's heading as context so Claude knows what came before.

### Option B — Full video in one call
Send entire `aligned_content.json` in one prompt.

**Pros:** Claude has full context, can detect topic flow

**Cons:** Long videos exceed context window; expensive; all-or-nothing

**Decision: Option A** — segment by segment with minimal prior context.

---

## Prompt Design

Each call sends:
- Video title (for domain context)
- The frame's OCR text
- The transcript segments spoken during that window
- The previous segment's heading (for continuity)

Instruction: extract the actual teaching, clean noise, write in Hinglish,
produce a heading + flowing content + 2–4 key bullet points.

```
You are creating study notes from an Ayurveda lecture video.

Video: {title}
Previous topic: {prev_heading or "N/A"}

SLIDE TEXT (may have OCR noise):
{ocr_text}

TEACHER'S SPEECH (may have transcription noise):
{transcript_text}

Write clean study notes in Hinglish (natural Hindi-English mix as a teacher would explain).
Produce:
HEADING: <short topic heading>
CONTENT: <2–5 sentences explaining the concept clearly>
KEY_POINTS:
- <point 1>
- <point 2>
...

Rules:
- Ignore garbled text, symbols, and noise
- If slide and speech conflict, prefer the speech
- If a window has no useful content, respond with HEADING: [skip]
- Do not invent content not present in the input
```

---

## Skipping Empty Segments

Segments where both OCR and transcript are empty/noisy get marked as `skipped: true`
and are excluded from the final output. Claude signals this with `HEADING: [skip]`.

---

## Module Structure

```
src/
└── synthesizer/
    ├── __init__.py
    └── synthesizer.py    # Claude API calls per segment, writes synthesized.json
```

---

## Dependencies

`anthropic` is already installed.

---

## Cost Estimate

For the test video (23 segments):
- ~300 tokens input + ~200 tokens output per segment
- 23 × 500 = ~11,500 tokens total ≈ fractions of a cent

---

## Integration into Pipeline

`pipeline.py` calls `synthesizer.synthesize(video_id, out_dir)` as the final step.

Updated pipeline order:
```
download → audio_extract → transcribe → frame_extract → visual_extract → align → synthesize → metadata update
```

---

## Open Questions

1. **Segment grouping** — some frame windows are very short (5–10s, e.g. segment 5 with 0 transcript). Should we merge short/empty windows with adjacent ones before sending to Claude, for better context?
2. **Temperature** — use `temperature=0` for deterministic factual output, or allow slight creativity for better Hinglish flow?
