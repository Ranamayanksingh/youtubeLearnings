"""
gemini_provider.py — Google Gemini implementation of LLMProvider.

Requires: pip install google-generativeai
API key set in env: GEMINI_API_KEY
"""

import os

from .interface import ImageInput, LLMProvider, LLMResponse


class GeminiProvider(LLMProvider):
    def __init__(self, model: str) -> None:
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "google-generativeai is not installed. "
                "Run: uv add google-generativeai"
            )

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY is not set.")

        genai.configure(api_key=api_key)
        self._genai = genai
        self._model_name = model

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        image: ImageInput | None = None,
    ) -> LLMResponse:
        import base64

        generation_config = self._genai.types.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        model = self._genai.GenerativeModel(
            model_name=self._model_name,
            generation_config=generation_config,
        )

        if image:
            import PIL.Image
            import io
            raw = base64.b64decode(image.data)
            pil_image = PIL.Image.open(io.BytesIO(raw))
            parts = [pil_image, prompt]
        else:
            parts = [prompt]

        response = model.generate_content(parts)
        text = response.text

        # Gemini token counts (available in usage_metadata when present)
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

        return LLMResponse(text=text, input_tokens=input_tokens, output_tokens=output_tokens)
