"""
synthesizer.py — Converts aligned content into clean Hinglish study notes using Claude.

Strategy:
  - Merge short/empty windows (< MIN_WINDOW_SECS or no transcript) into adjacent segment
  - Send each merged segment to Claude with minimal prior context
  - Claude extracts the teaching, cleans noise, writes in Hinglish
  - Segments with no useful content are skipped
"""

import json
import logging
import os
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
_TEMPERATURE = 0.3
MIN_WINDOW_SECS = 15       # windows shorter than this are merged with next
MIN_TRANSCRIPT_CHARS = 10  # windows with less speech than this are merged

# Domain detection: ask Claude once what kind of video this is, then use a
# tailored prompt for each segment. Cached per synthesize() call.
_DOMAIN_CACHE: dict[str, str] = {}


def synthesize(video_id: str, output_dir: Path) -> dict:
    """
    Synthesize clean Hinglish study notes from aligned_content.json.

    - Idempotent: returns existing synthesized.json if already done.
    - Merges short/empty windows before calling Claude.
    - Skips windows with no useful content.

    Returns the synthesized dict.
    """
    synthesized_file = output_dir / "synthesized.json"

    if synthesized_file.exists():
        logger.info(f"[{video_id}] Synthesized content already exists, skipping.")
        with open(synthesized_file, encoding="utf-8") as f:
            return json.load(f)

    aligned = _load_json(output_dir / "aligned_content.json", video_id)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. Cannot run synthesizer."
        )

    client = anthropic.Anthropic(api_key=api_key)
    title = aligned.get("title", "Ayurveda Lecture")
    raw_segments = aligned.get("segments", [])

    merged = _merge_short_segments(raw_segments)
    logger.info(
        f"[{video_id}] {len(raw_segments)} aligned segments → "
        f"{len(merged)} after merging short/empty windows"
    )

    # Detect subject domain once for the whole video
    sample_transcript = " ".join(
        t["text"]
        for seg in merged[:3]
        for t in seg["transcript"]
    )[:1500]
    domain = _detect_domain(client, title, sample_transcript)
    logger.info(f"[{video_id}] Detected domain: {domain}")

    topics = []
    prev_heading = None

    for i, seg in enumerate(merged):
        logger.info(
            f"[{video_id}] Synthesizing segment {i + 1}/{len(merged)} "
            f"[{seg['window_start_sec']}s → {seg['window_end_sec']}s]..."
        )
        result = _synthesize_segment(client, title, seg, prev_heading, domain)

        if result is None:
            logger.info(f"[{video_id}]   → skipped (no useful content)")
            continue

        result["window_start_sec"] = seg["window_start_sec"]
        result["window_end_sec"] = seg["window_end_sec"]
        result["frame_file"] = seg["frame"]["file"]
        topics.append(result)
        prev_heading = result["heading"]
        logger.info(f"[{video_id}]   → {result['heading']}")

    synthesized = {
        "video_id": video_id,
        "title": title,
        "domain": domain,
        "total_topics": len(topics),
        "topics": topics,
    }

    with open(synthesized_file, "w", encoding="utf-8") as f:
        json.dump(synthesized, f, ensure_ascii=False, indent=2)

    logger.info(
        f"[{video_id}] Synthesis complete — "
        f"{len(topics)} topics → {synthesized_file}"
    )
    return synthesized


# ---------------------------------------------------------------------------
# Segment merging
# ---------------------------------------------------------------------------

def _merge_short_segments(segments: list[dict]) -> list[dict]:
    """
    Merge windows that are too short or have too little speech into the next segment.

    Merging means:
    - Extend the next segment's window_start to cover the short segment
    - Combine OCR text and transcript lists
    - Keep the next segment's frame as the anchor (it has more content)
    """
    if not segments:
        return []

    result = []
    pending: dict | None = None

    for seg in segments:
        duration = seg["window_end_sec"] - seg["window_start_sec"]
        transcript_text = " ".join(t["text"] for t in seg["transcript"])
        is_short = duration < MIN_WINDOW_SECS
        is_empty = len(transcript_text.strip()) < MIN_TRANSCRIPT_CHARS

        if (is_short or is_empty) and pending is None:
            # Hold this segment — merge it into the next one
            pending = seg
            continue

        if pending is not None:
            # Merge pending into current
            seg = _merge_two(pending, seg)
            pending = None

        result.append(seg)

    # If last segment was pending, append it anyway
    if pending is not None:
        if result:
            result[-1] = _merge_two(result[-1], pending)
        else:
            result.append(pending)

    return result


def _merge_two(earlier: dict, later: dict) -> dict:
    """Merge an earlier segment into a later one, combining content."""
    merged_ocr = "\n".join(
        filter(None, [earlier["frame"]["ocr_text"], later["frame"]["ocr_text"]])
    )
    merged_transcript = earlier["transcript"] + later["transcript"]

    merged = dict(later)  # use later segment's frame as anchor
    merged["window_start_sec"] = earlier["window_start_sec"]
    merged["frame"] = dict(later["frame"])
    merged["frame"]["ocr_text"] = merged_ocr
    merged["transcript"] = merged_transcript
    return merged


# ---------------------------------------------------------------------------
# Domain detection
# ---------------------------------------------------------------------------

def _detect_domain(client: anthropic.Anthropic, title: str, sample_text: str) -> str:
    """
    Ask Claude to identify the subject domain of the video in one short call.
    Returns a short domain label like "ayurveda", "reasoning/aptitude", "mathematics", etc.
    """
    prompt = f"""Video title: {title}

Sample transcript (first few minutes):
{sample_text}

In 3-5 words, what is the subject domain of this video?
Examples: "Ayurveda medical exam prep", "SSC reasoning mock test", "Physics lecture", "History competitive exam", "Mathematics problem solving"
Reply with ONLY the domain label, nothing else."""

    msg = client.messages.create(
        model=_MODEL,
        max_tokens=20,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


# ---------------------------------------------------------------------------
# Claude synthesis per segment
# ---------------------------------------------------------------------------

def _synthesize_segment(
    client: anthropic.Anthropic,
    title: str,
    segment: dict,
    prev_heading: str | None,
    domain: str = "educational lecture",
) -> dict | None:
    """
    Call Claude to synthesize one segment into study notes.

    Returns a dict with heading, content, key_points — or None if skipped.
    """
    ocr_text = segment["frame"].get("ocr_text", "").strip()
    vision_desc = segment["frame"].get("vision_description", "").strip()
    transcript_text = "\n".join(
        f"[{t['start_sec']}s] {t['text']}" for t in segment["transcript"]
    )

    visual_context = ocr_text
    if vision_desc:
        visual_context = f"{ocr_text}\n[Visual description: {vision_desc}]"

    # Domain-specific instructions injected into the prompt
    is_ayurveda = "ayurveda" in domain.lower()
    if is_ayurveda:
        domain_rules = """- PRESERVE all Sanskrit and Ayurvedic technical terms exactly as they appear in the slide text (Devanagari script). E.g. write "प्रमेह पिडिका" not "Prameh Pidika"
- After each Sanskrit term, add the Roman transliteration in parentheses on first use. E.g. "धूमपान (Dhoompaan)"
- For Acharya names, use both scripts: "चरक (Charaka)", "सुश्रुत (Sushruta)", "वाग्भट (Vagbhata)"
- Comparison of Acharyas on any metric → list as bullet points here (the generator will make the table)"""
    else:
        domain_rules = """- Extract EVERY solved problem, question, formula, or concept taught — even if the teacher is just explaining one step
- For mock test / problem-solving videos: each distinct question or concept is a valid topic, do NOT skip them
- Preserve exact numbers, options, answer choices as stated
- If the teacher solves a problem, capture: the problem type, the method used, and the correct answer
- For reasoning/aptitude: name the question type (coding-decoding, syllogism, blood relation, etc.)"""

    prompt = f"""You are creating study notes from a video lecture.

Domain: {domain}
Video: {title}
Previous topic: {prev_heading or "N/A (this is the first topic)"}

SLIDE TEXT (may have OCR noise — ignore garbled symbols):
{visual_context or "(no slide text)"}

TEACHER'S SPEECH (may have transcription noise):
{transcript_text or "(no speech in this window)"}

Write clean study notes in Hinglish (natural Hindi-English mix, as a teacher would explain to students).

Produce your response in exactly this format:
HEADING: <short topic heading, 3-8 words>
CONTENT: <2-5 sentences explaining the concept or problem clearly in Hinglish>
KEY_POINTS:
- <key point 1>
- <key point 2>
- <key point 3 (optional)>
- <key point 4 (optional)>

Rules:
- Write in natural Hinglish — mix Hindi and English as Indian students speak
- Ignore garbled OCR text and transcription noise
- If slide and speech conflict, prefer the speech
- ONLY skip if this window is PURELY intro/outro/blank with zero teaching content (e.g. only "subscribe", "like", "hello everyone", "see you next class" with nothing else)
- If there is ANY teaching, problem-solving, or explanation — extract it, do NOT skip
- Do not invent facts not present in the input
- Keep key points concise — one line each
{domain_rules}"""

    message = client.messages.create(
        model=_MODEL,
        max_tokens=800,
        temperature=_TEMPERATURE,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_response(message.content[0].text)


def _parse_response(text: str) -> dict | None:
    """Parse Claude's HEADING/CONTENT/KEY_POINTS response."""
    heading = ""
    content = ""
    key_points = []
    current_section = None

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("HEADING:"):
            heading = line[len("HEADING:"):].strip()
            current_section = "heading"
        elif line.startswith("CONTENT:"):
            content = line[len("CONTENT:"):].strip()
            current_section = "content"
        elif line.startswith("KEY_POINTS:"):
            current_section = "key_points"
        elif line.startswith("-") and current_section == "key_points":
            key_points.append(line[1:].strip())
        elif current_section == "content" and not line.startswith(("HEADING:", "KEY_POINTS:")):
            # Multi-line content
            content = f"{content} {line}".strip()

    if heading == "[skip]" or not heading:
        return None

    return {
        "heading": heading,
        "content": content,
        "key_points": key_points,
    }


def _load_json(path: Path, video_id: str) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"[{video_id}] File not found: {path}. Run the full pipeline first."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)
