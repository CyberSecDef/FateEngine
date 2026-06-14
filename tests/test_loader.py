"""Tests for the Adventure Loader (schema + referential-integrity validation)."""

import copy
import json
from pathlib import Path

import pytest

from fateengine.loader import AdventureLoader, LoadError

EXAMPLE = Path(__file__).resolve().parents[1] / "adventures" / "example.json"


@pytest.fixture
def loader() -> AdventureLoader:
    return AdventureLoader()


@pytest.fixture
def example_data() -> dict:
    return json.loads(EXAMPLE.read_text())


# ---- the shipped example must be valid -----------------------------------

def test_example_adventure_loads(loader):
    adv = loader.load_adventure(EXAMPLE)
    assert adv.id == "sunken-crypt"
    assert adv.version == "1.0.0"
    assert len(adv.map["locations"]) == 4
    assert adv.initial_state["location"] == "clearing"


def test_list_adventures_finds_example(loader):
    found = loader.list_adventures(EXAMPLE.parent)
    assert EXAMPLE in found


# ---- structural (schema) failures ----------------------------------------

def test_missing_required_section_raises(loader, tmp_path, example_data):
    del example_data["quests"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(example_data))
    with pytest.raises(LoadError) as exc:
        loader.load_adventure(bad)
    assert any("quests" in d for d in exc.value.diagnostics)


def test_unknown_effect_type_rejected_by_schema(loader, tmp_path, example_data):
    example_data["actions"][0]["effects"] = [{"type": "teleport", "parameters": {}}]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(example_data))
    with pytest.raises(LoadError):
        loader.load_adventure(bad)


def test_not_json_raises(loader, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json ")
    with pytest.raises(LoadError) as exc:
        loader.load_adventure(bad)
    assert "not valid JSON" in str(exc.value)


# ---- semantic (referential-integrity) failures ---------------------------

def test_connection_to_unknown_location(loader, tmp_path, example_data):
    data = copy.deepcopy(example_data)
    data["map"]["connections"][0]["to"] = "nowhere"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data))
    with pytest.raises(LoadError) as exc:
        loader.load_adventure(bad)
    assert any("unknown location 'nowhere'" in d for d in exc.value.diagnostics)


def test_effect_targets_unknown_quest(loader, tmp_path, example_data):
    data = copy.deepcopy(example_data)
    data["actions"][4]["effects"][1]["parameters"]["quest"] = "ghost_quest"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data))
    with pytest.raises(LoadError) as exc:
        loader.load_adventure(bad)
    assert any("ghost_quest" in d for d in exc.value.diagnostics)


def test_starting_location_must_exist(loader, tmp_path, example_data):
    data = copy.deepcopy(example_data)
    data["metadata"]["starting_location"] = "void"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data))
    with pytest.raises(LoadError) as exc:
        loader.load_adventure(bad)
    assert any("starting_location" in d for d in exc.value.diagnostics)


def test_duplicate_location_id(loader, tmp_path, example_data):
    data = copy.deepcopy(example_data)
    data["map"]["locations"].append(dict(data["map"]["locations"][0]))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data))
    with pytest.raises(LoadError) as exc:
        loader.load_adventure(bad)
    assert any("duplicate location id" in d for d in exc.value.diagnostics)


# ---- the example is actually winnable via the tested effect engine -------

def test_example_is_completable(loader):
    """Drive the example through a winning path using the real effect engine,
    then confirm the win predicate holds — a smoke test that the adventure's
    actions, effects, and win condition agree end-to-end."""
    from fateengine.mcp.effects import apply_effect
    from fateengine.mcp.predicates import evaluate
    from fateengine.mcp.state import GameState

    adv = loader.load_adventure(EXAMPLE)
    actions = {a["id"]: a for a in adv.actions}
    rewards = {q["id"]: q["reward"]["effects"] for q in adv.quests if q.get("reward")}

    state = GameState(**{k: v for k, v in adv.initial_state.items()})
    winning_path = ["to_cottage", "talk_hermit", "take_key", "leave_cottage",
                    "to_crypt", "enter_vault", "take_amulet"]

    for action_id in winning_path:
        action = actions[action_id]
        assert evaluate(action["available_when"], state), f"{action_id} not available"
        with state.transaction():
            for e in action["effects"]:
                apply_effect(e, state, reward_resolver=rewards.get)

    assert evaluate(adv.win_conditions[0], state) is True
    assert state.status.get("hero") is True
    assert "amulet" in state.inventory
