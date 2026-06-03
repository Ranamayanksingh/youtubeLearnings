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
4. Each section: one Hinglish summary line (max 15 words) + table/bullets below it
5. Key exam traps (common confusions, exceptions, "trick" points) — highlight with ⚠️
6. NO paragraphs, NO conversational language, NO repetition
7. Include screenshot reference `![](frames/<filename>)` once per section using the most relevant frame
8. Only skip a topic if it has zero exam-testable content (pure filler). For mock-test/problem-solving videos: EVERY solved question is testable — do NOT skip any
9. {domain_specific_rule}
10. **Q&A format for fact points**: Every bullet point MUST follow:
    `- **Q:** <the question an examiner would ask> → **A:** <the precise answer>`
    Example: `- **Q:** Statement mein conclusion valid kab hota hai? → **A:** Jab directly statement se derive ho, bahar ki assumption na le`
    Example: `- ⚠️ **Q:** Common trap kya hai? → **A:** Jo sach lagta ho lekin statement se directly support nahi hota — woh follow nahi karta`

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
    if is_ayurveda:
        domain_specific_rule = (
            "**Sanskrit terms**: Always use Devanagari script for Sanskrit/Ayurvedic terms — "
            "format: \"धूमपान (Dhoompaan)\", \"प्रमेह पिडिका (Prameh Pidika)\". "
            "Acharya names: \"चरक (Charaka)\", \"सुश्रुत (Sushruta)\", \"वाग्भट (Vagbhata)\". "
            "Acharya comparisons → ALWAYS use a table"
        )
    else:
        domain_specific_rule = (
            "For each solved problem/question: state the question type, the approach/trick used, "
            "and the correct answer. Number each question if the video covers multiple questions. "
            "Do NOT merge different problems together — each question gets its own section"
        )

    topics_block = _build_topics_block(topics)

    prompt = _PROMPT_TEMPLATE.format(
        title=title,
        url=url,
        duration=duration,
        domain=domain,
        domain_specific_rule=domain_specific_rule,
        topics_block=topics_block,
    )

    logger.info(f"[{video_id}] Generating exam cheat sheet ({len(topics)} topics)...")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        temperature=_TEMPERATURE,
        messages=[{"role": "user", "content": prompt}],
    )

    md_content = message.content[0].text.strip()

    # Strip markdown code fences if Claude wrapped output in ```markdown ... ```
    if md_content.startswith("```"):
        lines = md_content.splitlines()
        md_content = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()

    output_file.write_text(md_content, encoding="utf-8")

    logger.info(f"[{video_id}] Cheat sheet generated → {output_file}")
    return output_file


def _build_topics_block(topics: list[dict]) -> str:
    """Serialize synthesized topics into a compact text block for the prompt."""
    lines = []
    for t in topics:
        lines.append(f"### {t['heading']}")
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
