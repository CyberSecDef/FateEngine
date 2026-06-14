"""Tests for the effect catalog + appliers (requirements_spec.md Appendix B)."""

import pytest

from fateengine.mcp.effects import EFFECT_TYPES, EffectError, apply_effect
from fateengine.mcp.state import GameState


def eff(type_, **params):
    return {"type": type_, "parameters": params}


# ---- inventory -----------------------------------------------------------

def test_add_inventory_new_and_increment():
    s = GameState()
    apply_effect(eff("add_inventory", item="gold", qty=10), s)
    apply_effect(eff("add_inventory", item="gold", qty=5), s)
    assert s.inventory["gold"] == 15


def test_add_inventory_defaults_qty_one():
    s = GameState()
    apply_effect(eff("add_inventory", item="torch"), s)
    assert s.inventory["torch"] == 1


def test_add_inventory_detail_item():
    s = GameState()
    apply_effect(eff("add_inventory", item="sword", detail={"durability": 50}), s)
    assert s.inventory["sword"] == {"durability": 50}


def test_remove_inventory_decrement_and_delete():
    s = GameState(inventory={"gold": 10})
    apply_effect(eff("remove_inventory", item="gold", qty=4), s)
    assert s.inventory["gold"] == 6
    apply_effect(eff("remove_inventory", item="gold", qty=6), s)
    assert "gold" not in s.inventory


def test_remove_inventory_insufficient_raises():
    s = GameState(inventory={"gold": 3})
    with pytest.raises(EffectError):
        apply_effect(eff("remove_inventory", item="gold", qty=5), s)


def test_remove_absent_item_raises():
    with pytest.raises(EffectError):
        apply_effect(eff("remove_inventory", item="ghost"), GameState())


# ---- status / variables / location --------------------------------------

def test_move_location():
    s = GameState(location="a")
    apply_effect(eff("move_location", to="b"), s)
    assert s.location == "b"


def test_set_and_clear_status():
    s = GameState()
    apply_effect(eff("set_status", key="wounded", value=True), s)
    assert s.status["wounded"] is True
    apply_effect(eff("clear_status", key="wounded"), s)
    assert "wounded" not in s.status


def test_set_variable():
    s = GameState()
    apply_effect(eff("set_variable", key="met_oracle", value=True), s)
    assert s.variables["met_oracle"] is True


# ---- quests --------------------------------------------------------------

def test_start_quest_idempotent():
    s = GameState()
    apply_effect(eff("start_quest", quest="rescue"), s)
    apply_effect(eff("start_quest", quest="rescue"), s)
    assert s.active_quests == ["rescue"]


def test_complete_objective():
    s = GameState(active_quests=["rescue"])
    apply_effect(eff("complete_objective", quest="rescue", objective="find_cell"), s)
    apply_effect(eff("complete_objective", quest="rescue", objective="find_cell"), s)
    assert s.completed_objectives == {"rescue": ["find_cell"]}


def test_complete_quest_moves_active_to_completed():
    s = GameState(active_quests=["rescue"])
    apply_effect(eff("complete_quest", quest="rescue"), s)
    assert s.active_quests == []
    assert s.completed_quests == ["rescue"]


def test_complete_quest_applies_reward_via_resolver():
    s = GameState(active_quests=["rescue"])
    rewards = {"rescue": [eff("add_inventory", item="gold", qty=100), eff("set_status", key="hero", value=True)]}
    apply_effect(eff("complete_quest", quest="rescue"), s, reward_resolver=rewards.get)
    assert s.inventory["gold"] == 100
    assert s.status["hero"] is True
    assert s.completed_quests == ["rescue"]


# ---- grant_reward (recursive bundle) ------------------------------------

def test_grant_reward_applies_bundle():
    s = GameState()
    bundle = eff("grant_reward", effects=[
        eff("add_inventory", item="map", qty=1),
        eff("set_variable", key="blessed", value=True),
    ])
    apply_effect(bundle, s)
    assert s.inventory["map"] == 1
    assert s.variables["blessed"] is True


# ---- trigger_end ---------------------------------------------------------

def test_trigger_end_win():
    s = GameState()
    apply_effect(eff("trigger_end", outcome="win", reason="dragon slain"), s)
    assert s.ended is True and s.outcome == "win" and s.end_reason == "dragon slain"


def test_trigger_end_bad_outcome_raises():
    with pytest.raises(EffectError):
        apply_effect(eff("trigger_end", outcome="draw"), GameState())


# ---- validation ----------------------------------------------------------

def test_unknown_effect_type_raises():
    with pytest.raises(EffectError):
        apply_effect(eff("teleport", to="moon"), GameState())


def test_missing_required_param_raises():
    with pytest.raises(EffectError):
        apply_effect(eff("move_location"), GameState())


def test_catalog_matches_schema_enum():
    # Guardrail: the code catalog and the JSON Schema enum must not drift.
    import json
    from pathlib import Path

    schema = json.loads((Path(__file__).resolve().parents[1] / "schema" / "adventure.schema.json").read_text())
    enum = set(schema["$defs"]["effect"]["properties"]["type"]["enum"])
    assert enum == set(EFFECT_TYPES)


# ---- atomicity (NFR-002) -------------------------------------------------

def test_transaction_rolls_back_on_failure():
    s = GameState(inventory={"gold": 5})
    bundle = [
        eff("add_inventory", item="gold", qty=10),     # ok
        eff("remove_inventory", item="potion", qty=1),  # fails: absent
    ]
    with pytest.raises(EffectError):
        with s.transaction():
            for e in bundle:
                apply_effect(e, s)
    # Neither effect should be visible after rollback.
    assert s.inventory == {"gold": 5}
