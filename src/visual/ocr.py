"""
ocr.py — Tesseract OCR wrapper for extracting text from lecture frames.

Attempts Hindi + English extraction together.
Returns raw text; caller decides if quality is sufficient.
"""

import logging

import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

# Combined Hindi + English — handles Devanagari and Roman script in the same frame
_LANG = "hin+eng"

# Tesseract page segmentation mode 6: assume a single uniform block of text.
# Mode 3 (auto) also works but is slower; 6 is better for slides.
_CONFIG = "--psm 6"


def extract_text(image_path: str) -> str:
    """
    Run OCR on a single image file.

    Returns extracted text (may be empty or noisy for non-text frames).
    Raises RuntimeError if Tesseract is not installed.
    """
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang=_LANG, config=_CONFIG)
        return text.strip()
    except pytesseract.pytesseract.TesseractNotFoundError:
        raise RuntimeError(
            "Tesseract is not installed. Run: brew install tesseract tesseract-lang"
        )


def is_sufficient(text: str, min_chars: int = 20) -> bool:
    """Return True if OCR output has enough content to be considered useful."""
    cleaned = text.strip()
    # Strip whitespace-only lines before measuring
    meaningful = " ".join(cleaned.split())
    return len(meaningful) >= min_chars
