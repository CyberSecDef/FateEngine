"""Tests for the predicate evaluator (requirements_spec.md Appendix A)."""

import pytest

from fateengine.mcp.predicates import PredicateError, evaluate
from fateengine.mcp.state import GameState


@pytest.fixture
def state() -> GameState:
    return GameState(
        location="tavern",
        inventory={"gold": 75, "torch": 1, "sword": {"durability": 40}},
        status={"has_key": True, "wounded": False},
        variables={"met_oracle": True, "count": 0},
        active_quests=["rescue"],
        completed_quests=["intro"],
        completed_objectives={"rescue": ["find_cell"]},
    )


# ---- leaf comparisons ----------------------------------------------------


def test_eq_on_path(state):
    assert evaluate({"==": ["location", "tavern"]}, state) is True
    assert evaluate({"==": ["location", "dungeon"]}, state) is False


def test_neq(state):
    assert evaluate({"!=": ["location", "dungeon"]}, state) is True


def test_eq_status_bool(state):
    assert evaluate({"==": ["status.has_key", True]}, state) is True
    assert evaluate({"==": ["status.wounded", False]}, state) is True


def test_ordering(state):
    assert evaluate({">": ["inventory.gold", 50]}, state) is True
    assert evaluate({">=": ["inventory.gold", 75]}, state) is True
    assert evaluate({"<": ["inventory.gold", 75]}, state) is False
    assert evaluate({"<=": ["inventory.gold", 75]}, state) is True


def test_ordering_on_unset_path_is_false(state):
    # Missing path resolves to None; ordering against None is false, not an error.
    assert evaluate({">": ["inventory.silver", 0]}, state) is False


def test_nested_detail_path(state):
    assert evaluate({">": ["inventory.sword.durability", 30]}, state) is True


# ---- has / exists --------------------------------------------------------


def test_has_inventory(state):
    assert evaluate({"has": ["inventory", "torch"]}, state) is True
    assert evaluate({"has": ["inventory", "shield"]}, state) is False


def test_has_zero_quantity_is_false():
    s = GameState(inventory={"arrow": 0})
    assert evaluate({"has": ["inventory", "arrow"]}, s) is False


def test_has_list_membership(state):
    assert evaluate({"has": ["active_quests", "rescue"]}, state) is True
    assert evaluate({"has": ["active_quests", "intro"]}, state) is False


def test_exists(state):
    assert evaluate({"exists": "variables.met_oracle"}, state) is True
    assert evaluate({"exists": "variables.unset"}, state) is False


def test_exists_treats_zero_as_set(state):
    # A variable explicitly set to 0 is "set" even though it is falsy.
    assert evaluate({"exists": "variables.count"}, state) is True


# ---- quest paths ---------------------------------------------------------


def test_quest_status_paths(state):
    assert evaluate({"==": ["quests.rescue", "active"]}, state) is True
    assert evaluate({"==": ["quests.intro", "completed"]}, state) is True
    assert evaluate({"==": ["quests.unknown", None]}, state) is True


def test_objective_completion_path(state):
    assert evaluate({"==": ["quests.rescue.objectives.find_cell", True]}, state) is True
    assert evaluate({"==": ["quests.rescue.objectives.escape", False]}, state) is True


# ---- boolean composition -------------------------------------------------


def test_and(state):
    assert (
        evaluate({"and": [{"==": ["location", "tavern"]}, {"has": ["inventory", "torch"]}]}, state)
        is True
    )
    assert (
        evaluate({"and": [{"==": ["location", "tavern"]}, {"has": ["inventory", "shield"]}]}, state)
        is False
    )


def test_or(state):
    assert (
        evaluate({"or": [{"==": ["location", "dungeon"]}, {"has": ["inventory", "torch"]}]}, state)
        is True
    )


def test_not(state):
    assert evaluate({"not": {"==": ["location", "dungeon"]}}, state) is True


def test_nested_composition(state):
    pred = {
        "and": [
            {"==": ["status.has_key", True]},
            {"or": [{">": ["inventory.gold", 100]}, {"has": ["inventory", "torch"]}]},
            {"not": {"==": ["quests.intro", "active"]}},
        ]
    }
    assert evaluate(pred, state) is True


# ---- implicit-AND sugar --------------------------------------------------


def test_sugar_single_key(state):
    assert evaluate({"location": "tavern"}, state) is True
    assert evaluate({"location": "dungeon"}, state) is False


def test_sugar_multi_key_implicit_and(state):
    assert evaluate({"location": "tavern", "status.has_key": True}, state) is True
    assert evaluate({"location": "tavern", "status.has_key": False}, state) is False


# ---- error handling ------------------------------------------------------


def test_bad_arity_raises(state):
    with pytest.raises(PredicateError):
        evaluate({"==": ["location"]}, state)


def test_and_requires_list(state):
    with pytest.raises(PredicateError):
        evaluate({"and": {"==": ["location", "tavern"]}}, state)


def test_empty_predicate_raises(state):
    with pytest.raises(PredicateError):
        evaluate({}, state)
