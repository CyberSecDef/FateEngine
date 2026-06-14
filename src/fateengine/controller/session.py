"""Turn-loop orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import AppConfig
from ..llm.provider import LLMProvider
from ..mcp.server import FateMCPServer
from .persistence import SaveStore


@dataclass
class TurnResult:
    """What the presentation layer renders after a turn."""

    prose: str
    available_actions: list[dict[str, Any]]
    status_summary: dict[str, Any]
    ended: bool
    outcome: str | None
    diagnostics: list[str]


class SessionController:
    """Coordinates Loader/MCP/LLM and drives the turn loop.

    Turn (requirements_spec.md sections 1-2):
      1. read state + available_actions from the MCP (read tools)
      2. render location prose via LLM (fallback: base_prose)
      3. take input; resolve free text local-first, LLM fallback
      4. MCP validates + applies effects atomically (write tools)
      5. MCP evaluate_quests + check_end_conditions; LLM narrates outcome
    """

    def __init__(
        self,
        mcp: FateMCPServer,
        llm: LLMProvider,
        saves: SaveStore,
        config: AppConfig,
    ) -> None:
        self.mcp = mcp
        self.llm = llm
        self.saves = saves
        self.config = config

    def begin(self) -> TurnResult:
        """Render the opening location (FR-003). Stub."""
        raise NotImplementedError

    def take_turn(self, user_input: str) -> TurnResult:
        """Resolve input -> validate -> apply -> evaluate -> narrate. Stub."""
        raise NotImplementedError

    def save(self, slot: str) -> None:
        """Serialize via the MCP and persist atomically (FR-011). Stub."""
        raise NotImplementedError

    def load(self, slot: str) -> TurnResult:
        """Restore a save into the MCP and resume (FR-012). Stub."""
        raise NotImplementedError

    def restart(self) -> TurnResult:
        """Reset the MCP to the adventure's initial_state. Stub."""
        raise NotImplementedError
