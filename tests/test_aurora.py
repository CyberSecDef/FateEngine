"""Tests for the second adventure (The Aurora Heist) — branching, OR/comparison
predicates, predicate-based lose, and an optional reward quest."""

from pathlib import Path

import pytest

from fateengine.loader import AdventureLoader
from fateengine.mcp.server import FateMCPServer

AURORA = Path(__file__).resolve().parents[1] / "adventures" / "aurora_station.json"


@pytest.fixture
def engine() -> FateMCPServer:
    eng = FateMCPServer(AdventureLoader().load_adventure(AURORA))
    eng.initialize()
    return eng


def play(engine, action_ids):
    return [engine.apply_action(a) for a in action_ids]


BRIBE_ROUTE = ["enter_station", "to_security", "bribe_guard", "take_keycard",
               "leave_security", "enter_server", "take_core", "leave_server",
               "return_to_shuttle"]

HACK_ROUTE = ["enter_station", "to_storage", "take_multitool", "leave_storage",
              "hack_terminal", "enter_server", "take_core", "leave_server",
              "return_to_shuttle"]


# ---- validity ------------------------------------------------------------

def test_aurora_loads_and_validates():
    adv = AdventureLoader().load_adventure(AURORA)
    assert adv.id == "aurora-heist"
    assert len(adv.quests) == 2


# ---- two winning routes --------------------------------------------------

def test_win_via_bribe_route(engine):
    final = play(engine, BRIBE_ROUTE)[-1]
    assert final["ended"] and final["outcome"] == "win"
    s = engine.get_state()
    assert "data_core" in s["inventory"]
    assert s["inventory"]["credits"] == 10           # 60 - 50 bribe (comparison + remove)
    assert "extract_core" in s["completed_quests"]
    # Optional side quest completed on this route, and its grant_reward fired.
    assert "pay_dues" in s["completed_quests"]
    assert "access_chip" in s["inventory"]
    assert s["status"].get("guard_friendly") is True


def test_win_via_hack_route_skips_side_quest(engine):
    final = play(engine, HACK_ROUTE)[-1]
    assert final["ended"] and final["outcome"] == "win"
    s = engine.get_state()
    assert "data_core" in s["inventory"]
    assert s["inventory"]["credits"] == 60           # never bribed
    assert engine.state.variables.get("hacked") is True
    # The optional reward quest is NOT completed on the hack route.
    assert "pay_dues" not in s["completed_quests"]
    assert "access_chip" not in s["inventory"]


# ---- predicate-based lose ------------------------------------------------

def test_grabbing_keycard_trips_alarm_and_loses(engine):
    res = play(engine, ["enter_station", "to_security", "grab_keycard"])[-1]
    assert res["ended"] and res["outcome"] == "lose"
    assert engine.state.status.get("alarm") is True


# ---- gating: OR door + comparison ---------------------------------------

def test_server_locked_without_key_or_hack(engine):
    engine.apply_action("enter_station")
    ids = {a["id"] for a in engine.available_actions()}
    assert "enter_server" not in ids                 # neither keycard nor hacked


def test_bribe_requires_enough_credits(engine):
    # Spend down credits below 50 by... there's no spend except bribe, so instead
    # check the comparison gate directly via a depleted state.
    engine.apply_action("enter_station")
    engine.apply_action("to_security")
    engine.state.inventory["credits"] = 40           # below threshold
    ids = {a["id"] for a in engine.available_actions()}
    assert "bribe_guard" not in ids                  # >= 50 fails


def test_breach_objective_auto_completes_on_entry(engine):
    res = play(engine, ["enter_station", "to_storage", "take_multitool",
                        "leave_storage", "hack_terminal", "enter_server"])[-1]
    assert {"type": "objective_complete", "quest": "extract_core", "objective": "breach_server"} in res["events"]
