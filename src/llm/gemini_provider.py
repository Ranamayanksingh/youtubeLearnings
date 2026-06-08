"""
gemini_provider.py — Google Gemini implementation of LLMProvider.

Requires: pip install google-genai
API key set in env: GEMINI_API_KEY
"""

import os

from .interface import ImageInput, LLMProvider, LLMResponse


class GeminiProvider(LLMProvider):
    def __init__(self, model: str) -> None:
        try:
            from google import genai
        except ImportError:
            raise ImportError(
                "google-genai is not installed. "
                "Run: uv add google-genai"
            )

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY is not set.")

        self._client = genai.Client(api_key=api_key)
        self._model_name = model

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        image: ImageInput | None = None,
    ) -> LLMResponse:
        from google.genai import types

        config = types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        )

        if image:
            import base64
            parts = [
                types.Part.from_bytes(
                    data=base64.b64decode(image.data),
                    mime_type=image.media_type,
                ),
                prompt,
            ]
        else:
            parts = [prompt]

        response = self._client.models.generate_content(
            model=self._model_name,
            contents=parts,
            config=config,
        )

        text = response.text or ""
        input_tokens = 0
        output_tokens = 0
        if response.usage_metadata:
            input_tokens = response.usage_metadata.prompt_token_count or 0
            output_tokens = response.usage_metadata.candidates_token_count or 0

        return LLMResponse(text=text, input_tokens=input_tokens, output_tokens=output_tokens)
