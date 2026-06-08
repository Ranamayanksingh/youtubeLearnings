"""
groq_provider.py — Groq implementation of LLMProvider.

Requires: pip install groq
API key set in env: GROQ_API_KEY

Text models  : llama-3.3-70b-versatile, llama-3.1-8b-instant, mixtral-8x7b-32768, gemma2-9b-it
Vision models: meta-llama/llama-4-scout-17b-16e-instruct (set GROQ_MODEL to use vision)
"""

import os

from .interface import ImageInput, LLMProvider, LLMResponse


class GroqProvider(LLMProvider):
    def __init__(self, model: str) -> None:
        try:
            from groq import Groq
        except ImportError:
            raise ImportError(
                "groq is not installed. "
                "Run: uv add groq"
            )

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError("GROQ_API_KEY is not set.")

        self._client = Groq(api_key=api_key)
        self._model = model

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        image: ImageInput | None = None,
    ) -> LLMResponse:
        if image:
            content = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image.media_type};base64,{image.data}"
                    },
                },
                {"type": "text", "text": prompt},
            ]
        else:
            content = prompt

        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": content}],
        )

        text = response.choices[0].message.content or ""
        usage = response.usage
        return LLMResponse(
            text=text,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )
