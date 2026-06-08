"""
src/llm/__init__.py — Factory for LLMProvider.

Usage:
    from src.llm import get_llm

    llm = get_llm()
    response = llm.complete("Explain Tridosha theory", max_tokens=500)
    print(response.text)
"""

from pathlib import Path
from functools import lru_cache

import yaml

from .interface import LLMProvider, LLMResponse, ImageInput

__all__ = ["get_llm", "LLMProvider", "LLMResponse", "ImageInput"]

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"config.yaml not found at {_CONFIG_PATH}. "
            "Copy config.yaml from the project root and set your provider."
        )
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def get_llm() -> LLMProvider:
    """
    Return a singleton LLMProvider based on config.yaml.

    Cached — the same instance is reused across all callers in a process.
    To force a reload (e.g. in tests), call get_llm.cache_clear() first.
    """
    config = _load_config()
    llm_cfg = config.get("llm", {})
    provider = llm_cfg.get("provider", "claude").lower()

    if provider == "claude":
        from .claude_provider import ClaudeProvider
        model = llm_cfg.get("claude", {}).get("model", "claude-sonnet-4-6")
        return ClaudeProvider(model=model)

    elif provider == "gemini":
        from .gemini_provider import GeminiProvider
        model = llm_cfg.get("gemini", {}).get("model", "gemini-1.5-pro")
        return GeminiProvider(model=model)

    else:
        raise ValueError(
            f"Unknown LLM provider '{provider}' in config.yaml. "
            "Valid values: 'claude', 'gemini'."
        )
