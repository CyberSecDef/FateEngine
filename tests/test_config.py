"""Tests for layered configuration (defaults -> file -> env) and key resolution."""

import json

from fateengine.config import AppConfig, LLMConfig
from fateengine.llm.provider import OpenAIProvider, get_provider


def test_defaults():
    cfg = AppConfig.load(path="/nonexistent/none.json")  # no file, no env
    assert cfg.llm.provider == "anthropic"
    assert cfg.llm.model == "claude-opus-4-8"
    assert cfg.llm.endpoint is None


def test_loads_from_file(tmp_path):
    p = tmp_path / "fe.json"
    p.write_text(
        json.dumps(
            {
                "llm": {
                    "provider": "ollama",
                    "endpoint": "http://localhost:11434/v1",
                    "model": "gemma4-rev",
                },
                "saves_dir": "/tmp/fe-saves",
            }
        )
    )
    cfg = AppConfig.load(path=p)
    assert cfg.llm.provider == "ollama"
    assert cfg.llm.endpoint == "http://localhost:11434/v1"
    assert cfg.llm.model == "gemma4-rev"
    assert str(cfg.saves_dir) == "/tmp/fe-saves"


def test_env_overrides_file(tmp_path, monkeypatch):
    p = tmp_path / "fe.json"
    p.write_text(json.dumps({"llm": {"model": "from-file", "max_tokens": 100}}))
    monkeypatch.setenv("FATEENGINE_LLM_MODEL", "from-env")
    monkeypatch.setenv("FATEENGINE_LLM_ENDPOINT", "http://strix:11434/v1")
    monkeypatch.setenv("FATEENGINE_LLM_MAX_TOKENS", "2048")
    cfg = AppConfig.load(path=p)
    assert cfg.llm.model == "from-env"  # env wins over file
    assert cfg.llm.endpoint == "http://strix:11434/v1"
    assert cfg.llm.max_tokens == 2048  # coerced to int


def test_env_only(monkeypatch):
    monkeypatch.setenv("FATEENGINE_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("FATEENGINE_LLM_TEMPERATURE", "0.5")
    monkeypatch.setenv("FATEENGINE_DIAGNOSTIC", "true")
    cfg = AppConfig.load(path="/nonexistent/none.json")
    assert cfg.llm.provider == "openai-compatible"
    assert cfg.llm.temperature == 0.5
    assert cfg.diagnostic_mode is True


# ---- key/endpoint resolution in get_provider -----------------------------


def test_local_gemma_needs_no_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = LLMConfig(
        provider="openai-compatible", endpoint="http://localhost:11434/v1", model="gemma4-rev"
    )
    p = get_provider(cfg)
    assert isinstance(p, OpenAIProvider)
    assert p._base_url == "http://localhost:11434/v1"
    assert p.model == "gemma4-rev"


def test_direct_api_key_wins(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = LLMConfig(provider="openai", api_key="sk-direct", model="gpt-4o-mini")
    p = get_provider(cfg)
    assert p._api_key == "sk-direct"
