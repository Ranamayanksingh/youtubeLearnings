"""
vision.py — Claude Vision wrapper for describing lecture frames.

Called only when OCR yields insufficient text (sparse or unreadable output).
Uses claude-sonnet-4-6 with a context-aware prompt for Ayurveda lecture content.
"""

import base64
import logging
import os
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"

_PROMPT = """You are analyzing a frame from an Ayurveda educational video (Hindi/English lecture).

Examine the image and provide:
1. All visible text — transcribe it exactly as shown (Hindi or English)
2. A brief description of what is shown (slide, whiteboard, diagram, table, etc.)
3. Content type — classify as one of: slide | whiteboard | diagram | table | mixed | unclear

Format your response as:
TEXT: <all visible text, or "none" if no text>
DESCRIPTION: <one or two sentences describing the frame>
TYPE: <content type>"""


def describe_frame(image_path: str) -> dict:
    """
    Send a frame to Claude Vision and return a structured description.

    Returns dict with keys: text, description, content_type.
    Requires ANTHROPIC_API_KEY environment variable.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. Claude Vision fallback cannot be used."
        )

    image_data = _encode_image(image_path)
    ext = Path(image_path).suffix.lower().lstrip(".")
    media_type = f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}"

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=_MODEL,
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": _PROMPT},
                ],
            }
        ],
    )

    return _parse_response(message.content[0].text)


def _encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def _parse_response(response_text: str) -> dict:
    """Parse the structured TEXT/DESCRIPTION/TYPE response from Claude."""
    result = {"text": "", "description": "", "content_type": "unclear"}

    for line in response_text.splitlines():
        if line.startswith("TEXT:"):
            val = line[len("TEXT:"):].strip()
            result["text"] = "" if val.lower() == "none" else val
        elif line.startswith("DESCRIPTION:"):
            result["description"] = line[len("DESCRIPTION:"):].strip()
        elif line.startswith("TYPE:"):
            result["content_type"] = line[len("TYPE:"):].strip().lower()

    return result
