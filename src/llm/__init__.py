"""
src/llm/__init__.py — Factory for LLMProvider.

Provider and model are resolved in this order (first wins):
  1. Environment variables: LLM_PROVIDER, CLAUDE_MODEL / GEMINI_MODEL
  2. config.yaml defaults

Usage:
    from src.llm import get_llm

    llm = get_llm()
    response = llm.complete("Explain Tridosha theory", max_tokens=500)
    print(response.text)
"""

import os
from functools import lru_cache
from pathlib import Path

import yaml

from .interface import ImageInput, LLMProvider, LLMResponse

__all__ = ["get_llm", "LLMProvider", "LLMResponse", "ImageInput"]

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def get_llm() -> LLMProvider:
    """
    Return a singleton LLMProvider.

    Resolution order (first wins):
      1. LLM_PROVIDER env var
      2. config.yaml llm.default_provider
      3. hardcoded default: "claude"

    Cached — same instance reused across all callers in a process.
    Call get_llm.cache_clear() to force a reload (e.g. in tests).
    """
    config = _load_config()
    llm_cfg = config.get("llm", {})

    provider = (
        os.environ.get("LLM_PROVIDER")
        or llm_cfg.get("default_provider", "claude")
    ).lower()

    if provider == "claude":
        from .claude_provider import ClaudeProvider
        model = (
            os.environ.get("CLAUDE_MODEL")
            or llm_cfg.get("claude", {}).get("default_model", "claude-sonnet-4-6")
        )
        return ClaudeProvider(model=model)

    elif provider == "gemini":
        from .gemini_provider import GeminiProvider
        model = (
            os.environ.get("GEMINI_MODEL")
            or llm_cfg.get("gemini", {}).get("default_model", "gemini-1.5-pro")
        )
        return GeminiProvider(model=model)

    else:
        raise ValueError(
            f"Unknown LLM provider '{provider}'. "
            "Set LLM_PROVIDER in .env to 'claude' or 'gemini'."
        )
