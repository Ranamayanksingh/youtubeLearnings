"""
claude_provider.py — Claude (Anthropic) implementation of LLMProvider.
"""

import os

import anthropic

from .interface import ImageInput, LLMProvider, LLMResponse


class ClaudeProvider(LLMProvider):
    def __init__(self, model: str) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY is not set.")
        self._client = anthropic.Anthropic(api_key=api_key)
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
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image.media_type,
                        "data": image.data,
                    },
                },
                {"type": "text", "text": prompt},
            ]
        else:
            content = prompt

        message = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": content}],
        )
        usage = message.usage
        return LLMResponse(
            text=message.content[0].text,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
