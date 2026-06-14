"""Tests for the LLM provider adapters (fake clients — no SDK / network)."""

import pytest

from fateengine.config import LLMConfig
from fateengine.llm.provider import (
    AnthropicProvider,
    LLMError,
    OpenAIProvider,
    _retry,
    get_provider,
)


# --- fake SDK clients -----------------------------------------------------

class _Block:
    def __init__(self, text):
        self.text = text


class _AnthResp:
    def __init__(self, text):
        self.content = [_Block(text)]


class _Messages:
    def __init__(self, text):
        self.text, self.kwargs = text, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return _AnthResp(self.text)


class FakeAnthropic:
    def __init__(self, text="narrated by claude"):
        self.messages = _Messages(text)


class _Msg:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _OAResp:
    def __init__(self, content):
        self.choices = [_Msg(content)]


class _Completions:
    def __init__(self, text):
        self.text, self.kwargs = text, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return _OAResp(self.text)


class FakeOpenAI:
    def __init__(self, text="narrated by gpt"):
        self.chat = type("C", (), {"completions": _Completions(text)})()


# --- Anthropic ------------------------------------------------------------

def test_anthropic_generate_returns_text_and_shapes_request():
    fake = FakeAnthropic("once upon a time")
    p = AnthropicProvider(model="claude-opus-4-8", client=fake, max_tokens=512)
    out = p.generate("SYSTEM", "PROMPT")
    assert out == "once upon a time"
    kw = fake.messages.kwargs
    assert kw["model"] == "claude-opus-4-8"
    assert kw["system"] == "SYSTEM"
    assert kw["messages"] == [{"role": "user", "content": "PROMPT"}]
    assert kw["max_tokens"] == 512
    assert "temperature" not in kw          # Opus rejects sampling params


# --- OpenAI ---------------------------------------------------------------

def test_openai_generate_returns_text_and_shapes_request():
    fake = FakeOpenAI("a dark and stormy night")
    p = OpenAIProvider(model="gpt-4o-mini", client=fake, temperature=0.7)
    out = p.generate("SYS", "USER")
    assert out == "a dark and stormy night"
    kw = fake.chat.completions.kwargs
    assert kw["model"] == "gpt-4o-mini"
    assert kw["messages"][0] == {"role": "system", "content": "SYS"}
    assert kw["messages"][1] == {"role": "user", "content": "USER"}
    assert kw["temperature"] == 0.7


def test_openai_omits_temperature_when_unset():
    fake = FakeOpenAI()
    OpenAIProvider(client=fake).generate("s", "u")
    assert "temperature" not in fake.chat.completions.kwargs


# --- retry ----------------------------------------------------------------

def test_retry_succeeds_after_transient_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("connection reset")   # no status -> retryable
        return "ok"

    assert _retry(flaky, max_retries=5, sleep=lambda _: None) == "ok"
    assert calls["n"] == 3


def test_retry_gives_up_and_raises_llmerror():
    def always_fail():
        raise RuntimeError("nope")

    with pytest.raises(LLMError):
        _retry(always_fail, max_retries=2, sleep=lambda _: None)


def test_retry_does_not_retry_non_retryable_status():
    calls = {"n": 0}

    def bad_request():
        calls["n"] += 1
        raise type("E", (Exception,), {"status_code": 400})("bad request")

    with pytest.raises(LLMError):
        _retry(bad_request, max_retries=5, sleep=lambda _: None)
    assert calls["n"] == 1                    # 400 is not retried


# --- factory --------------------------------------------------------------

def test_get_provider_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    p = get_provider(LLMConfig(provider="anthropic", model="claude-opus-4-8"))
    assert isinstance(p, AnthropicProvider)
    assert p.model == "claude-opus-4-8"


def test_get_provider_anthropic_missing_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMError):
        get_provider(LLMConfig(provider="anthropic"))


def test_get_provider_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    p = get_provider(LLMConfig(provider="openai", model="gpt-4o-mini"))
    assert isinstance(p, OpenAIProvider)


def test_get_provider_ollama_needs_no_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = get_provider(LLMConfig(provider="ollama", model="gemma2"))
    assert isinstance(p, OpenAIProvider)
    assert p._base_url == "http://localhost:11434/v1"


def test_get_provider_unknown():
    with pytest.raises(LLMError):
        get_provider(LLMConfig(provider="nope"))
