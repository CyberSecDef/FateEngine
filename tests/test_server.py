"""Tests for FateMCPServer — the authoritative engine, driven via the example."""

import json
from pathlib import Path

import jsonschema
import pytest

from fateengine.loader import AdventureLoader
from fateengine.mcp.server import ActionError, FateMCPServer

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "adventures" / "example.json"
SAVE_SCHEMA = json.loads((ROOT / "schema" / "save.schema.json").read_text())


@pytest.fixture
def engine() -> FateMCPServer:
    adv = AdventureLoader().load_adventure(EXAMPLE)
    eng = FateMCPServer(adv)
    eng.initialize()
    return eng


WIN_PATH = ["to_cottage", "talk_hermit", "take_key", "leave_cottage",
            "to_crypt", "enter_vault", "take_amulet"]


def play(engine: FateMCPServer, action_ids):
    results = []
    for aid in action_ids:
        results.append(engine.apply_action(aid))
    return results


# ---- initialization + read tools -----------------------------------------

def test_initialize_seeds_from_initial_state(engine):
    s = engine.get_state()
    assert s["location"] == "clearing"
    assert s["location_name"] == "Forest Clearing"
    assert s["inventory"] == {}
    assert s["turn_number"] == 0


def test_describe_location_filters_conditional_exits(engine):
    desc = engine.describe_location("crypt_entrance")
    exits = {e["to"] for e in desc["exits"]}
    # The gated vault exit requires the rusty key, which we don't have yet.
    assert "crypt_vault" not in exits
    assert "clearing" in exits


def test_describe_location_lists_npcs(engine):
    desc = engine.describe_location("cottage")
    assert any(n["id"] == "hermit" for n in desc["npcs"])


def test_look_up_npc(engine):
    npc = engine.look_up_npc("hermit")
    assert npc["name"] == "The Old Hermit"
    with pytest.raises(ActionError):
        engine.look_up_npc("ghost")


# ---- available actions + gating ------------------------------------------

def test_available_actions_gated_by_location(engine):
    ids = {a["id"] for a in engine.available_actions()}
    assert "to_cottage" in ids
    assert "take_amulet" not in ids   # wrong location


def test_apply_unavailable_action_raises(engine):
    with pytest.raises(ActionError):
        engine.apply_action("take_amulet")   # not in crypt_vault


def test_apply_unknown_action_raises(engine):
    with pytest.raises(ActionError):
        engine.apply_action("fly")


def test_take_key_gated_until_hermit_met(engine):
    engine.apply_action("to_cottage")
    with pytest.raises(ActionError):
        engine.apply_action("take_key")       # haven't talked to hermit
    engine.apply_action("talk_hermit")
    engine.apply_action("take_key")           # now allowed
    assert "rusty_key" in engine.get_state()["inventory"]


# ---- full winning playthrough --------------------------------------------

def test_winning_playthrough(engine):
    results = play(engine, WIN_PATH)
    final = results[-1]
    assert final["ended"] is True
    assert final["outcome"] == "win"
    s = engine.get_state()
    assert s["status"].get("hero") is True
    assert "amulet" in s["inventory"]
    assert "recover_amulet" in s["completed_quests"]


def test_engine_auto_completes_quest_from_criteria(engine):
    # Strip the explicit completion effects so the quest must be resolved purely
    # by the engine's criteria-based evaluator (completion_criteria predicates).
    engine._actions["enter_vault"]["effects"] = [
        {"type": "move_location", "parameters": {"to": "crypt_vault"}},
    ]
    engine._actions["take_amulet"]["effects"] = [
        {"type": "add_inventory", "parameters": {"item": "amulet", "qty": 1}},
    ]
    play(engine, WIN_PATH[:-1])               # up to entering the vault
    assert "recover_amulet" in engine.get_state()["active_quests"]

    res = engine.apply_action("take_amulet")
    assert {"type": "objective_complete", "quest": "recover_amulet", "objective": "claim_amulet"} in res["events"]
    assert {"type": "quest_complete", "quest": "recover_amulet"} in res["events"]
    # Reward applied via the auto-completed quest.
    assert engine.get_state()["status"].get("hero") is True


def test_history_and_turn_counter_advance(engine):
    play(engine, WIN_PATH[:3])
    s = engine.get_state()
    assert s["turn_number"] == 3
    assert len(engine.recall_history()) == 3
    assert engine.recall_history(1)[0]["action_id"] == "take_key"


def test_no_actions_after_end(engine):
    play(engine, WIN_PATH)
    with pytest.raises(ActionError):
        engine.apply_action("look")


# ---- lose path -----------------------------------------------------------

def test_lose_via_trigger_end(engine):
    engine.apply_action("to_crypt")
    res = engine.apply_action("step_into_pit")
    assert res["ended"] is True and res["outcome"] == "lose"
    assert engine.state.end_reason


# ---- atomicity -----------------------------------------------------------

def test_failed_action_leaves_state_untouched(engine):
    # Force a mid-bundle failure by monkeypatching an action to a bad effect.
    engine._actions["look"]["effects"] = [
        {"type": "set_status", "parameters": {"key": "tested", "value": True}},
        {"type": "remove_inventory", "parameters": {"item": "absent"}},  # raises
    ]
    before = engine.get_state()
    with pytest.raises(Exception):
        engine.apply_action("look")
    assert engine.get_state() == before        # rolled back, incl. turn_number


# ---- persistence round-trip ----------------------------------------------

def test_serialize_matches_schema(engine):
    play(engine, WIN_PATH[:4])
    save = engine.serialize()
    jsonschema.Draft202012Validator(SAVE_SCHEMA).validate(save)


def test_save_resume_round_trip(engine):
    play(engine, WIN_PATH[:5])                 # mid-adventure
    save = engine.serialize()

    fresh = FateMCPServer(AdventureLoader().load_adventure(EXAMPLE))
    fresh.initialize()
    fresh.deserialize(save)
    assert fresh.get_state() == engine.get_state()

    # Resumed session can finish and win.
    fresh.apply_action("enter_vault")
    res = fresh.apply_action("take_amulet")
    assert res["outcome"] == "win"


def test_deserialize_rejects_foreign_save(engine):
    save = engine.serialize()
    save["adventure_id"] = "some-other-adventure"
    with pytest.raises(ActionError):
        engine.deserialize(save)
