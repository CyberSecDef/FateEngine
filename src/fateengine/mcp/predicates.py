"""Boolean predicate evaluator (requirements_spec.md Appendix A).

Grammar:
    { "and": [ ... ] } | { "or": [ ... ] } | { "not": <pred> }
    { "==" | "!=" | ">" | ">=" | "<" | "<=" | "has": [left, right] }
    { "exists": "<state.path>" }
    bare multi-key object -> implicit AND of equality checks (authoring sugar)

A bare-string left operand in a comparison is interpreted as a state path and
resolved via GameState.resolve_path; any other literal is used as-is.
"""

from __future__ import annotations

from typing import Any

from .state import GameState


class PredicateError(Exception):
    """Raised when a predicate is malformed (unknown operator, bad arity)."""


def evaluate(predicate: dict[str, Any], state: GameState) -> bool:
    """Evaluate a predicate against current state. Pure, side-effect free. Stub."""
    raise NotImplementedError
