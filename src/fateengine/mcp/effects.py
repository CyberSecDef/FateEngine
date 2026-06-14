"""Closed effect catalog + appliers (requirements_spec.md Appendix B).

Every mutation the engine can perform is one of these effect types. Unknown
types are rejected (NFR-004) and never applied. Appliers mutate the GameState in
place and are only ever called inside a GameState.transaction(), so a failure
mid-bundle rolls the whole turn back (NFR-002).
"""

from __future__ import annotations

from typing import Any, Callable

from .state import GameState

# The authoritative set of effect types. Mirrors schema/adventure.schema.json.
EFFECT_TYPES: frozenset[str] = frozenset(
    {
        "move_location",
        "add_inventory",
        "remove_inventory",
        "set_status",
        "clear_status",
        "set_variable",
        "start_quest",
        "complete_objective",
        "complete_quest",
        "grant_reward",
        "trigger_end",
    }
)

# Resolves a quest id -> its reward effect list (or None). Supplied by the
# server, which holds the adventure definition; kept out of this module so
# effects stay pure over GameState and unit-testable with a dict-backed stub.
RewardResolver = Callable[[str], "list[dict[str, Any]] | None"]


class EffectError(Exception):
    """Raised when an effect is unknown or its preconditions fail
    (e.g. remove_inventory with insufficient quantity)."""


def apply_effect(
    effect: dict[str, Any],
    state: GameState,
    *,
    reward_resolver: RewardResolver | None = None,
) -> None:
    """Validate and apply a single effect descriptor.

    `grant_reward` recurses over a bundle; `complete_quest` applies the quest's
    reward (via `reward_resolver`) after marking completion; `trigger_end` sets
    the session outcome.
    """
    if not isinstance(effect, dict):
        raise EffectError(f"effect must be an object, got {type(effect).__name__}")
    etype = effect.get("type")
    if etype not in EFFECT_TYPES:
        raise EffectError(f"unknown effect type: {etype!r}")
    params = effect.get("parameters", {}) or {}

    if etype == "grant_reward":
        for child in params.get("effects", []):
            apply_effect(child, state, reward_resolver=reward_resolver)
        return

    if etype == "complete_quest":
        _complete_quest(state, _require(params, "quest", etype))
        rewards = reward_resolver(params["quest"]) if reward_resolver else None
        for child in rewards or []:
            apply_effect(child, state, reward_resolver=reward_resolver)
        return

    _SIMPLE[etype](params, state)


# --- simple appliers (no recursion) --------------------------------------

def _move_location(p: dict[str, Any], s: GameState) -> None:
    s.location = _require(p, "to", "move_location")


def _add_inventory(p: dict[str, Any], s: GameState) -> None:
    item = _require(p, "item", "add_inventory")
    if "detail" in p:
        s.inventory[item] = p["detail"]
        return
    qty = p.get("qty", 1)
    cur = s.inventory.get(item, 0)
    if isinstance(cur, dict):
        raise EffectError(f"cannot add a numeric quantity to detail item {item!r}")
    s.inventory[item] = cur + qty


def _remove_inventory(p: dict[str, Any], s: GameState) -> None:
    item = _require(p, "item", "remove_inventory")
    qty = p.get("qty", 1)
    cur = s.inventory.get(item)
    if cur is None:
        raise EffectError(f"cannot remove absent item {item!r}")
    if isinstance(cur, dict):
        # Detail items are singletons; a single remove clears them.
        del s.inventory[item]
        return
    if cur < qty:
        raise EffectError(f"insufficient {item!r}: have {cur}, removing {qty}")
    remaining = cur - qty
    if remaining == 0:
        del s.inventory[item]
    else:
        s.inventory[item] = remaining


def _set_status(p: dict[str, Any], s: GameState) -> None:
    s.status[_require(p, "key", "set_status")] = _require(p, "value", "set_status")


def _clear_status(p: dict[str, Any], s: GameState) -> None:
    s.status.pop(_require(p, "key", "clear_status"), None)


def _set_variable(p: dict[str, Any], s: GameState) -> None:
    s.variables[_require(p, "key", "set_variable")] = _require(p, "value", "set_variable")


def _start_quest(p: dict[str, Any], s: GameState) -> None:
    quest = _require(p, "quest", "start_quest")
    if quest not in s.active_quests and quest not in s.completed_quests:
        s.active_quests.append(quest)


def _complete_objective(p: dict[str, Any], s: GameState) -> None:
    quest = _require(p, "quest", "complete_objective")
    objective = _require(p, "objective", "complete_objective")
    done = s.completed_objectives.setdefault(quest, [])
    if objective not in done:
        done.append(objective)


def _trigger_end(p: dict[str, Any], s: GameState) -> None:
    outcome = _require(p, "outcome", "trigger_end")
    if outcome not in ("win", "lose"):
        raise EffectError(f"trigger_end outcome must be 'win' or 'lose', got {outcome!r}")
    s.ended = True
    s.outcome = outcome
    s.end_reason = p.get("reason")


def _complete_quest(s: GameState, quest: str) -> None:
    if quest in s.active_quests:
        s.active_quests.remove(quest)
    if quest not in s.completed_quests:
        s.completed_quests.append(quest)


_SIMPLE: dict[str, Callable[[dict[str, Any], GameState], None]] = {
    "move_location": _move_location,
    "add_inventory": _add_inventory,
    "remove_inventory": _remove_inventory,
    "set_status": _set_status,
    "clear_status": _clear_status,
    "set_variable": _set_variable,
    "start_quest": _start_quest,
    "complete_objective": _complete_objective,
    "trigger_end": _trigger_end,
}


def _require(params: dict[str, Any], key: str, etype: str) -> Any:
    if key not in params:
        raise EffectError(f"{etype} requires parameter {key!r}")
    return params[key]
