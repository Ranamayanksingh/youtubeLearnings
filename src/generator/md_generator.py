"""
md_generator.py — Generates an exam-ready Markdown cheat sheet from synthesized topics.

Sends all synthesized topics in one Claude call for full-context restructuring:
- Merges fragmented/duplicate topics into logical sections
- Uses comparison tables for Acharya comparisons
- Bolds all exam-testable facts (numbers, classifications)
- Strips all filler — only facts remain
"""

import json
import logging
import os
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
_TEMPERATURE = 0.2  # lower than synthesizer — we want consistent, precise output


_PROMPT_TEMPLATE = """You are creating an exam-ready cheat sheet from a video lecture.

Domain: {domain}
Video: {title}
URL: {url}

Below are the extracted study topics from this lecture (already cleaned from raw video):

{topics_block}

---

Your task: Rewrite this as a precise, scannable Markdown cheat sheet.

STRICT RULES:
1. **Merge** topics with the same or closely related headings into one section
2. **Comparison tables**: Whenever 2+ items/concepts/people are compared on the same metric — ALWAYS use a Markdown table, never bullet points
3. **Bold** every number, answer, correct option, formula, and named classification that an MCQ could directly test
4. Each section: one Hinglish summary line (max 15 words) + content below it
5. Key exam traps (common confusions, exceptions, "trick" points) — highlight with ⚠️
6. NO unnecessary paragraphs, NO conversational filler, NO repetition
7. Include screenshot reference `![](frames/<filename>)` once per section using the most relevant frame
8. Only skip a topic if it has zero exam-testable content (pure filler). For mock-test/problem-solving videos: EVERY solved question is testable — do NOT skip any
9. {domain_specific_rule}

QUESTION TYPE FORMATTING — apply per section based on the [type:...] tag in the input:

**[type:knowledge]** — Use Q→A bullet format:
- `- **Q:** <the question an examiner would ask> → **A:** <the precise answer>`
- `- ⚠️ **Q:** <trap question> → **A:** <correct answer>`
- Use a Markdown table only when comparing 2+ items on the same metric

**[type:math]** — Use tutor's solution approach format:
- Start with: `**Given:** <the values/data stated in the problem>`
- Then numbered steps showing the calculation exactly as the tutor explained it:
  `1. <step description> → <working>`
  `2. <next step> → <working>`
  `3. ...`
- End with: `**Answer: <correct option/value>**`
- Add `- ⚠️ **Trap:** <common mistake>` if applicable
- Use a table ONLY if it genuinely helps (e.g. comparing two methods) — do NOT force a table for straight calculations

OUTPUT FORMAT:
```
# <Video Title>
> {url} | {duration}

---

## <Section Heading>
> <one-line Hinglish summary>

<table or Q→A bullet points>

**Exam points:**
- **Q:** <question> → **A:** <answer>
- ⚠️ **Q:** <trap question> → **A:** <correct answer>

![](frames/<most_relevant_frame_filename>)

---
```

Write only the Markdown. No preamble, no explanation."""


_MEETING_PROMPT_TEMPLATE = """You are producing a structured meeting brief for a Data Engineering and Data Science team from a client meeting recording.

Meeting: {title}
Duration: {duration}
Source: {url}

Below are the extracted notes from this meeting (already segmented):

{topics_block}

---

Your task: Produce a professional meeting brief in Markdown. Write in clear English only — no Hindi, no Hinglish.

STRICT RULES:
1. **Meeting Summary** — one concise paragraph covering: who attended (use speaker labels if present), what data topics were discussed, key decisions made
2. **Data Concepts & Architecture** — for EVERY data concept, table, field, hierarchy, join type, schema, system, or pipeline mentioned: create a dedicated subsection explaining it clearly for a data engineer new to this client's data
3. **Preserve exact names** — all table names, field names, system names, hierarchy levels, codes (e.g. SHIP_TO, GMC_CODE, SOLD2) must appear exactly as stated
4. **Action Items** — Markdown table: Owner | Action | Context
5. **Follow-up Questions** — specific questions to ask the client in the next meeting, especially for ⚠️ unclear items
6. **Knowledge Gaps** — data concepts or systems the team should read up on to better understand this client's data model
7. Do NOT merge different data concepts — each gets its own subsection under Data Concepts

OUTPUT FORMAT:
```
# Meeting Brief: {title}
> {url} | {duration}

---

## Meeting Summary
<one paragraph — attendees, data topics discussed, decisions made>

---

## Data Concepts & Architecture

### <Concept / Table / Hierarchy / System Name>
> Referenced at ~<timestamp>

**What the client explained:** <direct paraphrase of what was said>

**What this means:** <plain English explanation for a data engineer — define terms, explain relationships>

**Relevance to the project:** <how this affects the DE/DS pipeline or data model being built>

---

## Data Relationships & Hierarchies
<Use tables or diagrams to capture any hierarchy or relationship structures discussed>

| Level | Field / Code | Description |
|-------|-------------|-------------|
| ... | ... | ... |

---

## Action Items

| Owner | Action | Context |
|-------|--------|---------|
| ... | ... | ... |

---

## Follow-up Questions
- ⚠️ **Unclear:** <what was unclear> → **Ask:** <specific question to clarify>
- **Dig deeper:** <topic> → **Ask:** <question>

---

## Knowledge Gaps
Topics the DE/DS team should read up on before the next meeting:
- **<Term/system>** — <one-line why it matters>
```

Write only the Markdown. No preamble, no explanation. English only."""


def generate(video_id: str, output_dir: Path) -> Path:
    """
    Generate exam-ready study_notes.md from synthesized.json.

    - Idempotent: skips if study_notes.md already exists.

    Returns the path to the generated .md file.
    """
    output_file = output_dir / "study_notes.md"

    if output_file.exists():
        logger.info(f"[{video_id}] study_notes.md already exists, skipping.")
        return output_file

    synthesized = _load_json(output_dir / "synthesized.json", video_id)
    metadata = _load_json(output_dir / "metadata.json", video_id)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set.")

    topics = synthesized.get("topics", [])
    if not topics:
        raise ValueError(f"[{video_id}] No topics in synthesized.json.")

    title = metadata.get("title", "Lecture")
    url = metadata.get("url", "")
    duration_sec = metadata.get("duration_seconds", 0)
    duration = _format_duration(duration_sec)
    domain = synthesized.get("domain", "educational lecture")

    is_ayurveda = "ayurveda" in domain.lower()
    is_meeting = "meeting" in domain.lower() or "client meeting" in domain.lower()

    if is_meeting:
        selected_template = _MEETING_PROMPT_TEMPLATE
        log_label = "meeting brief"
    elif is_ayurveda:
        selected_template = _PROMPT_TEMPLATE
        domain_specific_rule = (
            "**Sanskrit terms**: Always use Devanagari script for Sanskrit/Ayurvedic terms — "
            "format: \"धूमपान (Dhoompaan)\", \"प्रमेह पिडिका (Prameh Pidika)\". "
            "Acharya names: \"चरक (Charaka)\", \"सुश्रुत (Sushruta)\", \"वाग्भट (Vagbhata)\". "
            "Acharya comparisons → ALWAYS use a table"
        )
        log_label = "exam cheat sheet"
    else:
        selected_template = _PROMPT_TEMPLATE
        domain_specific_rule = (
            "For each solved problem/question: state the question type, the approach/trick used, "
            "and the correct answer. Number each question if the video covers multiple questions. "
            "Do NOT merge different problems together — each question gets its own section"
        )
        log_label = "exam cheat sheet"

    client = anthropic.Anthropic(api_key=api_key)

    logger.info(f"[{video_id}] Generating {log_label} ({len(topics)} topics)...")

    # Split into batches of BATCH_SIZE topics so we never hit the output token limit.
    # Each batch produces standalone ## sections; we stitch them together.
    BATCH_SIZE = 10
    batches = [topics[i:i + BATCH_SIZE] for i in range(0, len(topics), BATCH_SIZE)]
    all_sections: list[str] = []

    for batch_idx, batch in enumerate(batches):
        logger.info(
            f"[{video_id}] Batch {batch_idx + 1}/{len(batches)} "
            f"({len(batch)} topics)..."
        )
        topics_block = _build_topics_block(batch)
        if is_meeting:
            prompt = selected_template.format(
                title=title,
                url=url,
                duration=duration,
                topics_block=topics_block,
            )
        else:
            prompt = selected_template.format(
                title=title,
                url=url,
                duration=duration,
                domain=domain,
                domain_specific_rule=domain_specific_rule,
                topics_block=topics_block,
            )
        message = client.messages.create(
            model=_MODEL,
            max_tokens=8096,
            temperature=_TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )
        chunk = message.content[0].text.strip()

        # Strip markdown code fences if Claude wrapped output in ```markdown ... ```
        if chunk.startswith("```"):
            lines = chunk.splitlines()
            chunk = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()

        # First batch includes the full header; subsequent batches strip it
        # (the header is everything before the first `---\n\n##` section)
        if batch_idx == 0:
            all_sections.append(chunk)
        else:
            # Drop any title/header lines Claude may have repeated
            lines = chunk.splitlines()
            # Find the first `## ` heading and keep from there
            for i, line in enumerate(lines):
                if line.startswith("## "):
                    all_sections.append("\n".join(lines[i:]))
                    break
            else:
                all_sections.append(chunk)

    md_content = "\n\n---\n\n".join(all_sections)

    # Ensure file ends cleanly
    if not md_content.endswith("\n"):
        md_content += "\n"

    output_file.write_text(md_content, encoding="utf-8")

    logger.info(f"[{video_id}] Cheat sheet generated → {output_file}")
    return output_file


def _build_topics_block(topics: list[dict]) -> str:
    """Serialize synthesized topics into a compact text block for the prompt."""
    lines = []
    for t in topics:
        qt = t.get("question_type", "knowledge")
        lines.append(f"### {t['heading']} [type:{qt}]")
        lines.append(f"[{t['window_start_sec']}s–{t['window_end_sec']}s | frame: {t['frame_file']}]")
        lines.append(t["content"])
        for kp in t.get("key_points", []):
            lines.append(f"- {kp}")
        lines.append("")
    return "\n".join(lines)


def _format_duration(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


def _load_json(path: Path, video_id: str) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"[{video_id}] File not found: {path}. Run the full pipeline first."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)
