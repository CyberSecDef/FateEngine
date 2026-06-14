"""Authoritative game state container + atomic transactions.

All mutation flows through `GameState`. A turn applies its effects inside a
`transaction()` so partial updates are never observable (NFR-002).
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class GameState:
    """Mutable, authoritative session state. Owned exclusively by the MCP server."""

    location: str = ""
    inventory: dict[str, Any] = field(default_factory=dict)
    status: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    active_quests: list[str] = field(default_factory=list)
    completed_quests: list[str] = field(default_factory=list)
    history_log: list[dict[str, Any]] = field(default_factory=list)
    turn_number: int = 0
    ended: bool = False
    outcome: str | None = None          # "win" | "lose" | None

    @contextmanager
    def transaction(self) -> Iterator["GameState"]:
        """Apply a set of effects atomically.

        Snapshots state on entry; on any exception, rolls back so no partial
        mutation is visible to the LLM or presentation layer (NFR-002). Stub.
        """
        raise NotImplementedError
        yield self  # pragma: no cover

    def resolve_path(self, path: str) -> Any:
        """Resolve a dotted state path (e.g. 'inventory.torch', 'status.has_key')
        for the predicate evaluator. Stub."""
        raise NotImplementedError

    def diff_from(self, before: "GameState") -> dict[str, Any]:
        """Compute the state delta vs. a prior snapshot, for history logging. Stub."""
        raise NotImplementedError
