"""Boolean predicate evaluator (requirements_spec.md Appendix A).

Grammar:
    { "and": [ ... ] } | { "or": [ ... ] } | { "not": <pred> }
    { "==" | "!=" | ">" | ">=" | "<" | "<=" | "has": [left, right] }
    { "exists": "<state.path>" }
    bare multi-key object -> implicit AND of equality checks (authoring sugar)

A bare-string left operand in a comparison is interpreted as a state path and
resolved via GameState.resolve_path; any other literal is used as-is. The right
operand is always a literal.
"""

from __future__ import annotations

import operator
from typing import Any, Callable

from .state import GameState

_COMPARATORS: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}
_ORDERING = {">", ">=", "<", "<="}
_OPERATORS = {"and", "or", "not", "has", "exists", *_COMPARATORS}


class PredicateError(Exception):
    """Raised when a predicate is malformed (unknown operator, bad arity, bad type)."""


def evaluate(predicate: dict[str, Any], state: GameState) -> bool:
    """Evaluate a predicate against current state. Pure, side-effect free."""
    if not isinstance(predicate, dict):
        raise PredicateError(f"predicate must be an object, got {type(predicate).__name__}")
    if not predicate:
        raise PredicateError("empty predicate")

    keys = list(predicate.keys())

    # Operator form: exactly one key, and that key is a known operator.
    if len(keys) == 1 and keys[0] in _OPERATORS:
        return _eval_operator(keys[0], predicate[keys[0]], state)

    # Sugar form: a bare object -> implicit AND of equality checks against paths.
    # (Any object that isn't a single-key operator falls here.)
    return all(state.resolve_path(path) == expected for path, expected in predicate.items())


def _eval_operator(op: str, value: Any, state: GameState) -> bool:
    if op == "and":
        _require_list(op, value)
        return all(evaluate(p, state) for p in value)
    if op == "or":
        _require_list(op, value)
        return any(evaluate(p, state) for p in value)
    if op == "not":
        return not evaluate(value, state)
    if op == "exists":
        if not isinstance(value, str):
            raise PredicateError("'exists' operand must be a state-path string")
        resolved = state.resolve_path(value)
        return resolved is not None and resolved is not False
    if op == "has":
        return _eval_has(value, state)
    # comparison
    return _eval_comparison(op, value, state)


def _eval_comparison(op: str, operands: Any, state: GameState) -> bool:
    left, right = _operand_pair(op, operands)
    left_val = state.resolve_path(left) if isinstance(left, str) else left
    right_val = right  # right operand is always a literal
    if op in _ORDERING:
        # Unset / incomparable operands are simply false rather than an error.
        if left_val is None:
            return False
        try:
            return _COMPARATORS[op](left_val, right_val)
        except TypeError:
            return False
    return _COMPARATORS[op](left_val, right_val)


def _eval_has(operands: Any, state: GameState) -> bool:
    container_ref, key = _operand_pair("has", operands)
    container = (
        state.resolve_path(container_ref) if isinstance(container_ref, str) else container_ref
    )
    if isinstance(container, dict):
        return key in container and bool(container[key])
    if isinstance(container, (list, tuple, set)):
        return key in container
    return False


def _operand_pair(op: str, operands: Any) -> tuple[Any, Any]:
    if not isinstance(operands, (list, tuple)) or len(operands) != 2:
        raise PredicateError(f"'{op}' expects [left, right], got {operands!r}")
    return operands[0], operands[1]


def _require_list(op: str, value: Any) -> None:
    if not isinstance(value, list):
        raise PredicateError(f"'{op}' expects a list of predicates, got {type(value).__name__}")
