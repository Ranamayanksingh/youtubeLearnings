"""
interface.py — Abstract LLM interface.

All LLM providers must implement LLMProvider.
Callers use only this interface — never provider SDKs directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ImageInput:
    """An image to include in a multimodal message."""
    data: str          # base64-encoded bytes
    media_type: str    # e.g. "image/jpeg", "image/png"


@dataclass
class LLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(ABC):
    """
    Abstract base for all LLM providers (Claude, Gemini, …).

    All methods are synchronous — the pipeline is thread-based, not async.
    """

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        image: ImageInput | None = None,
    ) -> LLMResponse:
        """
        Send a single-turn prompt and return the response.

        Args:
            prompt:      The user message.
            max_tokens:  Maximum tokens in the response.
            temperature: Sampling temperature (0 = deterministic).
            image:       Optional image for multimodal calls.

        Returns:
            LLMResponse with .text and optional token counts.
        """
        ...
