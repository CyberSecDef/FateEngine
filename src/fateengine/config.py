"""Runtime + LLM configuration (requirements_spec.md section 7).

Provider-agnostic: the LLM is addressed by endpoint + model + params so a
single default can be swapped without touching the integration layer.

Configuration layers, lowest precedence first:
  1. dataclass defaults
  2. a JSON config file (./fateengine.config.json or ~/.config/fateengine/config.json,
     or an explicit path) — keep this OUT of version control for secrets/endpoints
  3. FATEENGINE_* environment variables (override the file)

Plain dataclasses (no third-party dependency) keep the loader / mcp / controller
chain lightweight; provider adapters bring their own SDKs as needed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

DEFAULT_CONFIG_PATHS = (
    Path("fateengine.config.json"),
    Path.home() / ".config" / "fateengine" / "config.json",
)
ENV_PREFIX = "FATEENGINE_"


@dataclass
class LLMConfig:
    """External LLM configuration. `temperature` is advisory — some providers/models
    (e.g. Claude Opus 4.8) ignore it."""

    provider: str = "anthropic"  # adapter key in fateengine.llm.provider
    endpoint: str | None = None  # override base URL; None = provider default
    api_key: str | None = None  # direct key (overrides api_key_env); usually from env
    api_key_env: str | None = None  # env var to read the key from; None = provider default
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
        """Build config from defaults, then a JSON file, then FATEENGINE_* env vars.

        File search order when `path` is None: ./fateengine.config.json, then
        ~/.config/fateengine/config.json. The file should not be committed.
        """
        cfg = cls()
        for candidate in [path] if path else DEFAULT_CONFIG_PATHS:
            if candidate and Path(candidate).is_file():
                cfg._apply_dict(json.loads(Path(candidate).read_text()))
                break
        cfg._apply_env(os.environ)
        return cfg

    # ---- internals -------------------------------------------------------
    def _apply_dict(self, data: Mapping[str, Any]) -> None:
        llm = data.get("llm", {})
        for key, value in llm.items():
            if hasattr(self.llm, key):
                setattr(self.llm, key, value)
        for key in ("adventures_dir", "saves_dir", "log_level", "diagnostic_mode"):
            if key in data:
                value = data[key]
                setattr(self, key, Path(value) if key.endswith("_dir") else value)

    def _apply_env(self, env: Mapping[str, str]) -> None:
        # llm.* fields, with type coercion.
        str_keys = ("provider", "endpoint", "api_key", "api_key_env", "model")
        for name in str_keys:
            val = env.get(f"{ENV_PREFIX}LLM_{name.upper()}")
            if val is not None:
                setattr(self.llm, name, val)
        if (v := env.get(f"{ENV_PREFIX}LLM_MAX_TOKENS")) is not None:
            self.llm.max_tokens = int(v)
        if (v := env.get(f"{ENV_PREFIX}LLM_MAX_RETRIES")) is not None:
            self.llm.max_retries = int(v)
        if (v := env.get(f"{ENV_PREFIX}LLM_TIMEOUT")) is not None:
            self.llm.timeout_seconds = float(v)
        if (v := env.get(f"{ENV_PREFIX}LLM_TEMPERATURE")) is not None:
            self.llm.temperature = float(v)
        # app-level
        if (v := env.get(f"{ENV_PREFIX}ADVENTURES_DIR")) is not None:
            self.adventures_dir = Path(v)
        if (v := env.get(f"{ENV_PREFIX}SAVES_DIR")) is not None:
            self.saves_dir = Path(v)
        if (v := env.get(f"{ENV_PREFIX}LOG_LEVEL")) is not None:
            self.log_level = v
        if (v := env.get(f"{ENV_PREFIX}DIAGNOSTIC")) is not None:
            self.diagnostic_mode = v.lower() in ("1", "true", "yes", "on")
