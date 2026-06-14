"""Provider-agnostic LLM adapters.

A thin `generate(system, prompt) -> str` contract with two concrete adapters:

  * AnthropicProvider — official `anthropic` SDK (Claude, e.g. claude-opus-4-8).
  * OpenAIProvider    — official `openai` SDK; also drives any OpenAI-compatible
                        endpoint (Ollama, vLLM, etc.) via `base_url`.

Each adapter uses ONLY its own SDK; they are never mixed. SDKs are imported
lazily so the engine and tests don't require them, and the underlying client can
be injected for testing. Transient failures retry with exponential backoff and
then raise LLMError, at which point the controller falls back to base_prose
(NFR-006).
"""

from __future__ import annotations

import os
import random
import time
from typing import Any, Callable, Protocol

from ..config import LLMConfig


class LLMError(Exception):
    """Raised after retries are exhausted (or on a non-retryable error); the caller
    falls back to base_prose (NFR-006)."""


class LLMProvider(Protocol):
    """Minimal text-generation contract. Implementations handle their own auth."""

    def generate(self, system: str, prompt: str, *, max_tokens: int | None = None) -> str:
        """Return narrative text for the given prompt. Raises LLMError on failure."""
        ...


# --- retry helper ---------------------------------------------------------


def _status_of(exc: Exception) -> int | None:
    for attr in ("status_code", "status"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    return None


def _is_retryable(exc: Exception) -> bool:
    status = _status_of(exc)
    if status is None:
        return True  # connection / timeout style — worth a retry
    return status == 429 or 500 <= status < 600


def _retry(
    call: Callable[[], str],
    *,
    max_retries: int,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Call `call()`, retrying transient failures with exponential backoff + jitter."""
    last: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - normalized to LLMError below
            last = exc
            if attempt >= max_retries or not _is_retryable(exc):
                break
            delay = min(max_delay, base_delay * (2**attempt)) + random.uniform(0, 0.5)
            sleep(delay)
    raise LLMError(f"LLM request failed: {last}") from last


# --- Anthropic ------------------------------------------------------------


class AnthropicProvider:
    """Claude via the official `anthropic` SDK."""

    def __init__(
        self,
        model: str = "claude-opus-4-8",
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 1024,
        timeout: float = 30.0,
        max_retries: int = 3,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout
        self._client = client

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                from anthropic import Anthropic
            except ImportError as exc:  # pragma: no cover - optional dep
                raise LLMError(
                    "the 'anthropic' package is required; pip install anthropic"
                ) from exc
            self._client = Anthropic(
                api_key=self._api_key, base_url=self._base_url, timeout=self._timeout
            )
        return self._client

    def generate(self, system: str, prompt: str, *, max_tokens: int | None = None) -> str:
        client = self._ensure_client()

        def call() -> str:
            # No `temperature`: Opus 4.x rejects sampling params. Narration prompts
            # already constrain output, so we leave thinking off (default).
            resp = client.messages.create(
                model=self.model,
                max_tokens=max_tokens or self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(getattr(block, "text", "") for block in resp.content).strip()

        return _retry(call, max_retries=self.max_retries)


# --- OpenAI / OpenAI-compatible ------------------------------------------


class OpenAIProvider:
    """OpenAI (and OpenAI-compatible servers via base_url) using the `openai` SDK."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 1024,
        timeout: float = 30.0,
        temperature: float | None = None,
        max_retries: int = 3,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout
        self._client = client

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - optional dep
                raise LLMError("the 'openai' package is required; pip install openai") from exc
            self._client = OpenAI(
                api_key=self._api_key or "no-key", base_url=self._base_url, timeout=self._timeout
            )
        return self._client

    def generate(self, system: str, prompt: str, *, max_tokens: int | None = None) -> str:
        client = self._ensure_client()

        def call() -> str:
            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens or self.max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            }
            if self.temperature is not None:
                kwargs["temperature"] = self.temperature
            resp = client.chat.completions.create(**kwargs)
            return (resp.choices[0].message.content or "").strip()

        return _retry(call, max_retries=self.max_retries)


# --- factory --------------------------------------------------------------

_OPENAI_LIKE = {"openai", "openai-compatible", "ollama", "local"}


def _resolve_key(config: LLMConfig, default_env: str, *, required: bool) -> str | None:
    """Direct config.api_key wins; otherwise read the named env var."""
    if config.api_key:
        return config.api_key
    env_name = config.api_key_env or default_env
    val = os.environ.get(env_name)
    if not val and required:
        raise LLMError(f"missing API key: set ${env_name} or llm.api_key")
    return val


def get_provider(config: LLMConfig) -> LLMProvider:
    """Instantiate the configured provider adapter.

    provider:
      "anthropic"                         -> AnthropicProvider (Claude)
      "openai"                            -> OpenAIProvider (api.openai.com)
      "ollama" | "local"                  -> OpenAIProvider at a local base_url
      "openai-compatible"                 -> OpenAIProvider at config.endpoint
    """
    provider = config.provider.lower()

    if provider == "anthropic":
        return AnthropicProvider(
            model=config.model,
            api_key=_resolve_key(config, "ANTHROPIC_API_KEY", required=True),
            base_url=config.endpoint,
            max_tokens=config.max_tokens,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )

    if provider in _OPENAI_LIKE:
        local = provider in ("ollama", "local")
        base_url = config.endpoint or ("http://localhost:11434/v1" if local else None)
        # Local servers (and any endpoint override) don't require a key.
        return OpenAIProvider(
            model=config.model,
            api_key=_resolve_key(config, "OPENAI_API_KEY", required=not local and base_url is None),
            base_url=base_url,
            max_tokens=config.max_tokens,
            timeout=config.timeout_seconds,
            temperature=config.temperature,
            max_retries=config.max_retries,
        )

    raise LLMError(f"unknown LLM provider: {config.provider!r}")
