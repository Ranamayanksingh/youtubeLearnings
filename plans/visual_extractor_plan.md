# Visual Content Extractor — Plan

## Responsibility

For each key frame saved by the frame extractor, understand what is visually present:
- Extract text from slides/whiteboards via OCR
- Describe diagrams, tables, or non-text visuals via Claude Vision
- Produce a structured per-frame understanding that downstream components can use

The goal is not just raw OCR — we want *meaning* from each frame, so the synthesis
layer can combine it with what the teacher was saying at that timestamp.

---

## Inputs & Outputs

| | Detail |
|---|---|
| **Input** | `output/<video_id>/frames/*.jpg` + `output/<video_id>/metadata.json` (for timestamps) |
| **Output** | `output/<video_id>/visual_content.json` |

### visual_content.json shape

```json
{
  "video_id": "abc123",
  "frames": [
    {
      "index": 1,
      "timestamp_sec": 32,
      "file": "frames/0001_t00m32s.jpg",
      "ocr_text": "Dhoompaan - Definition\nCauses: ...",
      "vision_description": "Slide showing a heading 'Dhoompaan' with a bullet list of 4 causes written in Hindi",
      "content_type": "slide"   // slide | whiteboard | diagram | mixed | unclear
    },
    ...
  ]
}
```

---

## Two-Layer Extraction Strategy

### Layer 1 — OCR (Tesseract)
- Fast, free, runs locally
- Good for clean slide text, printed content
- Handles Hindi (Devanagari) with `hin` language pack + English with `eng`
- Output: raw text dump per frame

### Layer 2 — Claude Vision
- Handles what OCR misses: diagrams, tables, handwritten text, messy layouts
- Also classifies content type (slide / whiteboard / diagram / mixed)
- Produces a human-readable description of the frame
- Called only when OCR text is sparse (< 20 chars) OR frame has non-text content
- This keeps API costs low — avoid calling Vision on every frame if OCR is sufficient

### Decision Logic

```
for each frame:
    ocr_text = tesseract(frame)
    if len(ocr_text.strip()) >= 20:
        use ocr_text as primary content
        still call Vision for content_type classification + description
    else:
        call Vision for full description (OCR clearly insufficient)
```

> **Note:** We can refine this threshold later once we see real output quality.

---

## Module Structure

```
src/
└── visual/
    ├── __init__.py
    ├── ocr.py           # Tesseract wrapper — extract text from a frame
    ├── vision.py        # Claude Vision wrapper — describe a frame
    └── extractor.py     # Orchestrates ocr + vision per frame, writes visual_content.json
```

---

## Technology Decisions

| Component | Choice | Reason |
|---|---|---|
| OCR | `pytesseract` + Tesseract | Free, local, supports Hindi (Devanagari) |
| Vision | Claude (`claude-sonnet-4-6`) | Best quality for mixed Hindi/English slide content |
| Claude SDK | `anthropic` Python SDK | Direct API access |

System dependency: `tesseract` must be installed (`brew install tesseract tesseract-lang`)

---

## Dependencies to Add

```
pytesseract       # Python wrapper for Tesseract
anthropic         # Claude API SDK
Pillow            # Image handling for pytesseract
```

---

## Claude Vision Prompt Design

The prompt will be context-aware — we tell Claude this is an Ayurveda lecture frame:

```
You are analyzing a frame from an Ayurveda educational video.
Describe what is shown in this image:
- If it's a slide: extract all visible text and summarize the topic
- If it's a diagram/table: describe the structure and content
- If it's a whiteboard: transcribe what is written
- Classify the frame as one of: slide | whiteboard | diagram | mixed | unclear
Keep your response concise and structured.
```

---

## Idempotency & Cost Control

- Skip entire extraction if `visual_content.json` already exists
- Claude Vision called per frame — log estimated cost at end (input tokens × frames)
- Frames with very low information (black screen, camera pan) skipped based on OCR + brightness check

---

## Integration into Pipeline

`pipeline.py` calls `extractor.extract(video_id, out_dir)` as Step 5, after frame extraction.

Updated pipeline order:
```
download → audio_extract → transcribe → frame_extract → visual_extract → metadata update
```

---

## Open Questions

1. **Always call Claude Vision**, or only as fallback when OCR is sparse? Always calling gives richer descriptions but costs more API tokens.
2. **Hindi OCR quality** — Tesseract Hindi support can be poor for stylized fonts. If OCR is consistently bad, should we skip Tesseract entirely and rely only on Claude Vision?
