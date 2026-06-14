"""Authoritative game state container + atomic transactions.

All mutation flows through `GameState`. A turn applies its effects inside a
`transaction()` so partial updates are never observable (NFR-002).
"""

from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import dataclass, field, fields
from typing import Any, Iterator

# State fields that participate in snapshots, diffs, and serialization.
_TRACKED = (
    "location",
    "inventory",
    "status",
    "variables",
    "active_quests",
    "completed_quests",
    "completed_objectives",
    "turn_number",
    "ended",
    "outcome",
    "end_reason",
)

# Bare top-level names a predicate path may reference directly.
_SCALARS = {"location", "turn_number", "ended", "outcome", "end_reason"}
_CONTAINERS = {
    "inventory",
    "status",
    "variables",
    "active_quests",
    "completed_quests",
    "history_log",
}

_MISSING = object()


@dataclass
class GameState:
    """Mutable, authoritative session state. Owned exclusively by the MCP server."""

    location: str = ""
    inventory: dict[str, Any] = field(default_factory=dict)
    status: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    active_quests: list[str] = field(default_factory=list)
    completed_quests: list[str] = field(default_factory=list)
    # quest_id -> [objective_id, ...]
    completed_objectives: dict[str, list[str]] = field(default_factory=dict)
    history_log: list[dict[str, Any]] = field(default_factory=list)
    turn_number: int = 0
    ended: bool = False
    outcome: str | None = None  # "win" | "lose" | None
    end_reason: str | None = None

    # ---- atomicity -------------------------------------------------------
    @contextmanager
    def transaction(self) -> Iterator["GameState"]:
        """Apply a set of effects atomically.

        Deep-snapshots tracked fields on entry; on any exception, restores them
        so no partial mutation is visible to the LLM or presentation layer
        (NFR-002), then re-raises.
        """
        snapshot = {name: copy.deepcopy(getattr(self, name)) for name in _TRACKED}
        try:
            yield self
        except Exception:
            for name, value in snapshot.items():
                setattr(self, name, value)
            raise

    # ---- path resolution (for the predicate evaluator) -------------------
    def resolve_path(self, path: str) -> Any:
        """Resolve a dotted state path. Returns None for any unset/unknown path.

        Examples:
            "location"                     -> current location id
            "inventory.gold"               -> quantity / detail for an item
            "status.has_key"               -> a status value
            "variables.met_oracle"         -> a custom flag
            "inventory"                    -> the whole inventory dict (for `has`)
            "quests.rescue"                -> "completed" | "active" | None
            "quests.rescue.objectives.x"   -> True if that objective is complete
        """
        parts = path.split(".")
        head = parts[0]

        if head == "quests":
            return self._resolve_quest_path(parts)

        if len(parts) == 1:
            if head in _SCALARS or head in _CONTAINERS:
                return getattr(self, head)
            return None

        if head in _CONTAINERS:
            cur: Any = getattr(self, head)
            for seg in parts[1:]:
                if isinstance(cur, dict):
                    cur = cur.get(seg, _MISSING)
                    if cur is _MISSING:
                        return None
                else:
                    return None
            return cur

        return None

    def _resolve_quest_path(self, parts: list[str]) -> Any:
        if len(parts) >= 4 and parts[2] == "objectives":
            qid, oid = parts[1], parts[3]
            return oid in self.completed_objectives.get(qid, [])
        if len(parts) >= 2:
            qid = parts[1]
            if qid in self.completed_quests:
                return "completed"
            if qid in self.active_quests:
                return "active"
            return None
        return None

    # ---- diffing (for history logging) -----------------------------------
    def diff_from(self, before: "GameState") -> dict[str, Any]:
        """Compute the {field: {"from": old, "to": new}} delta vs. a prior snapshot.

        Only changed tracked fields are included. `history_log` is excluded — a
        delta lives *inside* a history entry, so including it would be circular.
        """
        delta: dict[str, Any] = {}
        for f in fields(self):
            if f.name not in _TRACKED:
                continue
            old = getattr(before, f.name)
            new = getattr(self, f.name)
            if old != new:
                delta[f.name] = {"from": copy.deepcopy(old), "to": copy.deepcopy(new)}
        return delta
