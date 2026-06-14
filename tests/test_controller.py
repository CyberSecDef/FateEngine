"""Tests for SessionController — the turn loop (offline and with a fake LLM)."""

from pathlib import Path

import pytest

from fateengine.controller.persistence import SaveStore
from fateengine.controller.session import SessionController
from fateengine.llm.provider import LLMError
from fateengine.loader import AdventureLoader
from fateengine.mcp.server import FateMCPServer

EXAMPLE = Path(__file__).resolve().parents[1] / "adventures" / "example.json"


def make_controller(tmp_path, llm=None) -> SessionController:
    adv = AdventureLoader().load_adventure(EXAMPLE)
    engine = FateMCPServer(adv)
    engine.initialize()
    return SessionController(engine, llm, SaveStore(tmp_path))


class FakeLLM:
    """Deterministic provider for the LLM-path tests."""

    def __init__(self, *, prose="<<narrated>>", pick=None, fail=False):
        self.prose, self.pick, self.fail = prose, pick, fail
        self.calls = 0

    def generate(self, system, prompt, *, max_tokens=None):
        self.calls += 1
        if self.fail:
            raise LLMError("boom")
        if "Action id:" in prompt:          # intent-resolution prompt
            return self.pick or "none"
        return self.prose


WIN_PATH = ["to_cottage", "talk_hermit", "take_key", "leave_cottage",
            "to_crypt", "enter_vault", "take_amulet"]


# ---- offline turn loop ---------------------------------------------------

def test_begin_renders_base_prose_offline(tmp_path):
    ctl = make_controller(tmp_path)
    res = ctl.begin()
    assert "clearing" in res.prose.lower()
    assert res.status_summary["location"] == "Forest Clearing"
    assert any(a["id"] == "to_cottage" for a in res.available_actions)


def test_take_turn_by_exact_name(tmp_path):
    ctl = make_controller(tmp_path)
    res = ctl.take_turn("Go to the cottage")
    assert ctl.mcp.state.location == "cottage"
    assert res.diagnostics == []


def test_take_turn_by_synonym(tmp_path):
    ctl = make_controller(tmp_path)
    ctl.take_turn("cottage")               # synonym of to_cottage
    assert ctl.mcp.state.location == "cottage"


def test_take_turn_fuzzy(tmp_path):
    ctl = make_controller(tmp_path)
    ctl.take_turn("go to teh cotage")      # typos -> fuzzy match
    assert ctl.mcp.state.location == "cottage"


def test_unmatched_input_reports_diagnostic(tmp_path):
    ctl = make_controller(tmp_path)
    res = ctl.take_turn("xyzzy plugh nonsense")
    assert res.diagnostics
    assert ctl.mcp.state.location == "clearing"   # nothing changed


def test_unavailable_action_reports_diagnostic(tmp_path):
    ctl = make_controller(tmp_path)
    res = ctl.take_turn("take the amulet")        # not in the vault
    assert res.diagnostics
    assert ctl.mcp.state.location == "clearing"


def test_full_offline_playthrough(tmp_path):
    ctl = make_controller(tmp_path)
    ctl.begin()
    last = None
    for cmd in WIN_PATH:
        last = ctl.take_turn(cmd)
    assert last.ended is True
    assert last.outcome == "win"
    assert "won" in last.prose.lower()


def test_lose_path(tmp_path):
    ctl = make_controller(tmp_path)
    ctl.take_turn("go to the crypt archway")
    res = ctl.take_turn("peer into the pit")
    assert res.ended and res.outcome == "lose"


# ---- save / load via the controller --------------------------------------

def test_save_and_load_round_trip(tmp_path):
    ctl = make_controller(tmp_path)
    for cmd in WIN_PATH[:4]:
        ctl.take_turn(cmd)
    ctl.save("mid")

    ctl2 = make_controller(tmp_path)
    res = ctl2.load("mid")
    assert ctl2.mcp.get_state() == ctl.mcp.get_state()
    assert res.status_summary["turn"] == 4


def test_restart_resets_state(tmp_path):
    ctl = make_controller(tmp_path)
    for cmd in WIN_PATH[:3]:
        ctl.take_turn(cmd)
    res = ctl.restart()
    assert ctl.mcp.state.location == "clearing"
    assert res.status_summary["turn"] == 0


# ---- LLM path ------------------------------------------------------------

def test_llm_prose_used_when_provider_present(tmp_path):
    llm = FakeLLM(prose="<<narrated>>")
    ctl = make_controller(tmp_path, llm=llm)
    res = ctl.begin()
    assert res.prose == "<<narrated>>"
    assert llm.calls == 1


def test_llm_failure_falls_back_to_base_prose(tmp_path):
    llm = FakeLLM(fail=True)
    ctl = make_controller(tmp_path, llm=llm)
    res = ctl.begin()
    assert "clearing" in res.prose.lower()   # base_prose fallback (NFR-006)


def test_llm_intent_fallback_resolves_action(tmp_path):
    # Input that local matching won't confidently resolve; the LLM picks the id.
    llm = FakeLLM(pick="to_crypt")
    ctl = make_controller(tmp_path, llm=llm)
    res = ctl.take_turn("I want to investigate that ominous stone thing to the east")
    assert ctl.mcp.state.location == "crypt_entrance"
    assert res.diagnostics == []
