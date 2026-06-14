"""Runtime + LLM configuration (requirements_spec.md section 7).

Provider-agnostic: the LLM is addressed by endpoint + model + params so a
single default can be swapped without touching the integration layer.

Plain dataclasses (no third-party dependency) keep the loader / mcp / controller
chain lightweight; provider adapters bring their own SDKs as needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LLMConfig:
    """External LLM configuration. `temperature` is advisory — some providers/models
    (e.g. Claude Opus 4.8) ignore it."""

    provider: str = "anthropic"  # adapter key in fateengine.llm.provider
    endpoint: str | None = None  # override base URL; None = provider default
    api_key_env: str = "ANTHROPIC_API_KEY"
    model: str = "claude-opus-4-8"
    max_tokens: int = 1024
    timeout_seconds: float = 30.0
    temperature: float | None = None  # advisory; may be ignored by the provider
    max_retries: int = 3  # exponential backoff before base_prose fallback (NFR-006)


@dataclass
class AppConfig:
    """Top-level engine configuration."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    adventures_dir: Path = Path("adventures")
    saves_dir: Path = Path("saves")
    log_level: str = "INFO"  # configurable verbosity (NFR-007)
    diagnostic_mode: bool = False  # expose raw state / prompts / effect traces (section 7)

    @classmethod
    def load(cls, path: Path | None = None) -> "AppConfig":
        """Load config from a JSON file (and/or environment). Stub."""
        raise NotImplementedError
