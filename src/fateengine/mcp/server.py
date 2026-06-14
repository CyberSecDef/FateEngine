"""MCP server wiring — exposes game state as a Model Context Protocol server.

Read tools are LLM-visible; write tools are reserved for the Session Controller
(hybrid control, requirements_spec.md section 8). Transport is stdio for the
local single-player case.

Intended SDK: the official `mcp` Python package (FastMCP). Wiring is sketched
here; tool bodies delegate to state / effects / predicates.
"""

from __future__ import annotations

from typing import Any

from ..loader.loader import Adventure
from .state import GameState


class FateMCPServer:
    """Owns the authoritative GameState and the MCP tool surface."""

    def __init__(self, adventure: Adventure, state: GameState | None = None) -> None:
        self.adventure = adventure
        self.state = state or GameState()
        # self._mcp = FastMCP("fateengine")  # registered in _register_tools()

    # ---- lifecycle -------------------------------------------------------
    def initialize(self) -> None:
        """Seed state from adventure.initial_state (or a loaded save) and
        register tools (FR-002). Stub."""
        raise NotImplementedError

    def serve_stdio(self) -> None:
        """Run the MCP server over stdio. Stub."""
        raise NotImplementedError

    # ---- read tools (LLM-visible) ---------------------------------------
    def get_state(self) -> dict[str, Any]:
        """Serialized snapshot for prompt construction (FR-003, FR-015). Stub."""
        raise NotImplementedError

    def describe_location(self, location_id: str | None = None) -> dict[str, Any]:
        """Location name, base_prose, exits, present NPCs. Stub."""
        raise NotImplementedError

    def look_up_npc(self, npc_id: str) -> dict[str, Any]:
        """NPC public data (name, location, dialogue_seed, exposed state). Stub."""
        raise NotImplementedError

    def recall_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Recent history events for the prompt's rolling summary. Stub."""
        raise NotImplementedError

    # ---- write tools (Controller-only) ----------------------------------
    def available_actions(self) -> list[dict[str, Any]]:
        """Actions whose `available_when` predicate currently holds (FR-004). Stub."""
        raise NotImplementedError

    def apply_action(self, action_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Validate `available_when`, then apply all effects atomically; return the
        state delta (FR-007, FR-008, NFR-002). Stub."""
        raise NotImplementedError

    def evaluate_quests(self) -> list[dict[str, Any]]:
        """Check objective/quest predicates; complete + reward as met (FR-010). Stub."""
        raise NotImplementedError

    def check_end_conditions(self) -> str | None:
        """Evaluate win/lose predicates; return 'win'/'lose'/None (FR-013). Stub."""
        raise NotImplementedError

    def serialize(self) -> dict[str, Any]:
        """Deterministic runtime-save dict (FR-011, save.schema.json). Stub."""
        raise NotImplementedError

    def deserialize(self, save: dict[str, Any]) -> None:
        """Restore state from a validated save (FR-012). Stub."""
        raise NotImplementedError
