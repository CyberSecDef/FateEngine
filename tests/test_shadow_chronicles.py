"""Tests for the Shadow Chronicles adaptation — a larger 17-room map with
cross-wing dependencies, a weapon-gated 'combat' step, and a trigger_end win."""

from pathlib import Path

import pytest

from fateengine.loader import AdventureLoader
from fateengine.mcp.server import FateMCPServer

ADV = Path(__file__).resolve().parents[1] / "adventures" / "shadow_chronicles.json"


@pytest.fixture
def engine() -> FateMCPServer:
    eng = FateMCPServer(AdventureLoader().load_adventure(ADV))
    eng.initialize()
    return eng


def play(engine, ids):
    return [engine.apply_action(a) for a in ids]


# The full critical path: keycard + knife, power cell from engineering -> power the
# scanner -> lab badge -> beat the specimen -> anchor key, read the code, activate.
WIN = [
    "go_dark_hallway", "go_security_office", "take_keycard", "take_knife", "go_dark_hallway",
    "go_central_hub", "go_engineering_entrance", "go_utility_corridor", "go_generator_room",
    "take_power_cell", "go_utility_corridor", "go_engineering_entrance", "go_central_hub",
    "go_science_entrance", "insert_power_cell", "go_science_lab", "take_lab_badge",
    "read_terminal", "go_specimen_containment", "attack_specimen", "take_anchor_key",
    "go_science_lab", "go_science_entrance", "go_central_hub", "go_command_corridor",
    "go_observation_deck", "read_console", "go_command_corridor", "go_anchor_antechamber",
    "go_anchor_chamber", "activate_anchor",
]


def test_loads_and_validates():
    adv = AdventureLoader().load_adventure(ADV)
    assert adv.id == "shadow-chronicles"
    assert len(adv.map["locations"]) == 17


def test_full_critical_path_wins(engine):
    final = play(engine, WIN)[-1]
    assert final["ended"] and final["outcome"] == "win"
    s = engine.get_state()
    assert s["status"].get("anchor_activated") is True
    assert "project_anchor" in s["completed_quests"]
    assert "echoes" in s["completed_quests"]          # read_terminal -> optional quest
    assert s["status"].get("attuned") is True          # echoes grant_reward


def test_gating_blocks_premature_progress(engine):
    # The COMMAND door needs the keycard; the lab needs a powered scanner.
    play(engine, ["go_dark_hallway", "go_central_hub"])
    ids = {a["id"] for a in engine.available_actions()}
    assert "go_command_corridor" not in ids            # no keycard yet
    assert "go_science_lab" not in ids                 # (not even adjacent / unpowered)


def test_specimen_blocks_the_anchor_key(engine):
    # Reach containment but the key isn't takeable until the specimen is down.
    path = ["go_dark_hallway", "go_security_office", "take_keycard", "go_dark_hallway",
            "go_central_hub", "go_engineering_entrance", "go_utility_corridor",
            "go_generator_room", "take_power_cell", "go_utility_corridor",
            "go_engineering_entrance", "go_central_hub", "go_science_entrance",
            "insert_power_cell", "go_science_lab", "take_lab_badge", "go_specimen_containment"]
    play(engine, path)
    ids = {a["id"] for a in engine.available_actions()}
    assert "take_anchor_key" not in ids                # specimen not defeated
    assert "attack_specimen" not in ids                # no knife (left it behind)
    assert "fight_barehanded" in ids                   # ...but you can do something foolish


def test_barehanded_rush_is_lethal(engine):
    # No knife -> rushing the specimen is a lose.
    path = ["go_dark_hallway", "go_security_office", "take_keycard", "go_dark_hallway",
            "go_central_hub", "go_engineering_entrance", "go_utility_corridor",
            "go_generator_room", "take_power_cell", "go_utility_corridor",
            "go_engineering_entrance", "go_central_hub", "go_science_entrance",
            "insert_power_cell", "go_science_lab", "take_lab_badge",
            "go_specimen_containment", "fight_barehanded"]
    res = play(engine, path)[-1]
    assert res["ended"] and res["outcome"] == "lose"


def test_cannot_enter_chamber_without_key(engine):
    # Even with the code, no anchor key means the chamber stays sealed.
    assert engine.describe_location("anchor_antechamber")  # location exists
    # From the antechamber with no key, the chamber move is unavailable.
    engine.state.location = "anchor_antechamber"
    ids = {a["id"] for a in engine.available_actions()}
    assert "go_anchor_chamber" not in ids
