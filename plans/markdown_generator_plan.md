# Markdown Generator — Plan

## Responsibility

Take all synthesized topics from `synthesized.json` and produce a single
exam-ready `.md` cheat sheet. The output should be scannable in 5 minutes
before an exam — zero filler, maximum information density.

---

## Two Key Problems to Solve

### 1. Topic Fragmentation
Same topic (e.g. "Nidra Bhed comparison") appears across 3–4 segments because
the teacher covered it across multiple slides. The MD generator must merge
these into a single logical section.

### 2. Format for Exam Content
Ayurveda MCQ exams test precise numbers and comparisons — "Charaka ke according
Dhoompaan ke kitne kaal hain?" The best format for this is a comparison table,
not bullet points.

---

## Approach: Full-Context Re-synthesis

Unlike the segment-by-segment synthesizer, the MD generator sends **all topics
at once** to Claude and asks it to restructure the entire video's content into
a cheat sheet. This is affordable because `synthesized.json` is already compact
(~3–4k tokens for a 16-min video).

### Two-Pass Prompt Strategy

**Pass 1 — Structure Pass:**
Ask Claude to group the topics into logical sections and identify where
comparison tables would be better than bullet lists.

**Pass 2 — Write Pass:**
Ask Claude to write the final `.md` using the structure from Pass 1, with
strict formatting rules.

> For shorter videos (< 30 min), both passes can be merged into one call.
> We'll start with a single-pass approach and split if quality is insufficient.

---

## Markdown Output Format

```markdown
# <Video Title>
> Source: <YouTube URL> | Duration: <mm:ss>

---

## <Topic 1 Heading>
<1–2 line summary in Hinglish>

| Acharya | Point 1 | Point 2 | Point 3 |
|---------|---------|---------|---------|
| Charaka | ... | ... | ... |
| Sushruta | ... | ... | ... |
| Vagbhata | ... | ... | ... |

**Key exam points:**
- <precise fact 1>
- <precise fact 2>

---

## <Topic 2 Heading>
...

---
> Screenshots: output/<video_id>/frames/
```

### Format Rules for the Prompt
1. Use **comparison tables** whenever 2+ Acharyas are being compared on same metric
2. **Bold** all numbers, measurements, and named classifications
3. One-line Hinglish summary per topic — no paragraphs
4. Key exam points = only things an MCQ would directly test
5. Merge segments with same or closely related headings into one section
6. Skip any section that has no factual content after cleaning
7. Include a `![frame](frames/xxxx.jpg)` reference for the most relevant screenshot per topic

---

## Inputs & Outputs

| | Detail |
|---|---|
| **Input** | `output/<video_id>/synthesized.json` + `output/<video_id>/metadata.json` |
| **Output** | `output/<video_id>/study_notes.md` |

---

## Module Structure

```
src/
└── generator/
    ├── __init__.py
    └── md_generator.py    # Claude call + markdown file writer
```

---

## Integration into Pipeline

`pipeline.py` calls `md_generator.generate(video_id, out_dir)` as the last step.

Final pipeline order:
```
download → audio_extract → transcribe → frame_extract → visual_extract
    → align → synthesize → generate_md → done
```

---

## No New Dependencies

`anthropic` already installed. Pure Python + file I/O.

---

## Expected Output for Test Video

For the Dhoompaan lecture, we expect:
- ~4–5 merged sections (Angul Praman, Dhoompaan Types, Dhoompaan Kaal, Nidra Bhed, Comparison)
- 2–3 comparison tables (one for each Acharya comparison topic)
- All numbers bolded (24, 32, 36 angul etc.)
- Zero teacher talk, zero filler
