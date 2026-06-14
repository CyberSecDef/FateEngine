"""Provider-agnostic LLM adapter.

A thin interface so the engine can target Anthropic, a local Ollama endpoint, or
any OpenAI-compatible server purely via config (requirements_spec.md sections 7, 8).
Concrete adapters live alongside; `get_provider(config)` selects one.
"""

from __future__ import annotations

from typing import Protocol

from ..config import LLMConfig


class LLMError(Exception):
    """Raised after retries are exhausted; the caller falls back to base_prose (NFR-006)."""


class LLMProvider(Protocol):
    """Minimal text-generation contract. Implementations handle their own auth."""

    def generate(self, system: str, prompt: str, *, max_tokens: int | None = None) -> str:
        """Return narrative text for the given prompt. Raises LLMError on failure."""
        ...


def get_provider(config: LLMConfig) -> LLMProvider:
    """Instantiate the configured provider adapter (anthropic | ollama | openai-compatible). Stub."""
    raise NotImplementedError
