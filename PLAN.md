# YouTube Learning Material Extractor — Project Plan

## What We're Building

A pipeline that takes a YouTube video (Hindi or English) of a teacher explaining a topic, and produces a clean, structured `.md` study document from it.

The core challenge: a teacher's explanation exists across two parallel streams:
- **Visual** — slides, diagrams, text on screen, written equations
- **Audio** — verbal explanation, transitions, emphasis, Q&A

We capture both, align them temporally, and synthesize them into coherent study material.

---

## Components & Responsibilities

### 1. Video Ingestion & Preprocessing
Accepts a YouTube URL, downloads the video, extracts audio and frame sequences.
- Download video (yt-dlp)
- Extract audio track for transcription
- Sample video frames at intelligent intervals (detect slide changes, not every frame)

### 2. Audio Transcription & Translation
Converts speech to text; normalizes to English if Hindi.
- Transcribe audio with timestamps — Whisper handles Hindi, English, and Hinglish
- Translate Hindi segments to English (or keep bilingual based on preference)
- Output: timestamped transcript segments

### 3. Visual Content Extractor
Understands what's on screen at any given moment.
- Detect "slide change" events to avoid duplicate frame processing
- OCR text from slides and whiteboards
- Use a vision model (Claude) to describe diagrams, charts, or non-text visuals
- Output: timestamped visual snapshots with extracted content

### 4. Content Aligner / Synchronizer
Merges transcript + visual content by timestamp.
- Match "what teacher said" with "what was shown"
- Group into logical segments (e.g., one topic explained while one slide was visible)
- Output: unified timeline of `{timestamp, visual_content, speech_content}`

### 5. Content Synthesizer (LLM Layer)
Transforms raw aligned data into clean study material.
- Remove filler words, repetitions, off-topic tangents
- Expand shorthand from slides using the verbal explanation
- Restructure into: topic → subtopics → explanation → examples/questions
- Output: structured draft content

### 6. Markdown Generator
Formats synthesized content into a clean `.md` file.
- Hierarchical headings based on topic structure
- Include key diagrams/screenshots where relevant
- Optionally embed images of important slides
- Output: final `.md` study document

---

## Data Flow

```
YouTube URL
    │
    ▼
[Ingestion] ──► raw video + audio
    │
    ├──► [Transcription] ──► timestamped text (Hindi/English → English)
    │
    └──► [Visual Extractor] ──► timestamped slide content + OCR
              │
              ▼
         [Aligner] ──► unified timeline
              │
              ▼
        [Synthesizer] ──► clean, structured content (LLM)
              │
              ▼
      [MD Generator] ──► study_material.md
```

---

## Technology Decisions

| Component | Choice | Reason |
|---|---|---|
| Video download | yt-dlp | Reliable, actively maintained |
| Transcription | Whisper (local) | Free, handles Hindi/Hinglish well |
| Frame sampling | PySceneDetect | Scene-aware, avoids duplicate frames |
| OCR | Tesseract | Lightweight, works for clean slides |
| Vision / diagram understanding | Claude Vision | Handles messy slides + diagrams |
| Content synthesis | Claude | Structured output, good at cleanup |
| Orchestration | Plain Python pipeline | Simple to start, easy to extend |

---

## Decisions

| Question | Decision |
|---|---|
| Output language | **Hinglish** — natural mix of Hindi and English as a teacher would explain |
| Images in output | **Screenshots embedded** in the `.md` alongside text content |
| Scale | **Batch processing primary** (playlist or list of URLs), single video also supported |
| Interface | **CLI tool** for now — architecture kept clean so web or Telegram bot can be layered on top later |

---

## Future Interface Extensions (Out of Scope Now)

- **Web UI** — upload URL, download resulting `.md`
- **Telegram Bot** — send a YouTube link, receive the `.md` file back in chat
