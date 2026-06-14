"""Closed effect catalog + appliers (requirements_spec.md Appendix B).

Every mutation the engine can perform is one of these effect types. Unknown
types are rejected at load time (NFR-004) and never applied. Each applier
mutates the GameState in place and is only ever called inside a
GameState.transaction().
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


class EffectError(Exception):
    """Raised when an effect is unknown or its preconditions fail
    (e.g. remove_inventory with insufficient quantity)."""


def apply_effect(effect: dict[str, Any], state: GameState) -> None:
    """Dispatch a single effect descriptor to its applier. Stub.

    `grant_reward` recurses over a bundle of effects; `complete_quest` applies
    the quest's reward bundle; `trigger_end` sets state.ended / state.outcome.
    """
    raise NotImplementedError


# Per-type appliers are registered here (move_location, add_inventory, ...).
APPLIERS: dict[str, Callable[[dict[str, Any], GameState], None]] = {}
