"""Turn-loop orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import AppConfig
from ..llm import intent, prompts
from ..llm.provider import LLMError, LLMProvider
from ..mcp.server import ActionError, FateMCPServer
from .persistence import SaveStore


@dataclass
class TurnResult:
    """What the presentation layer renders after a turn."""

    prose: str
    available_actions: list[dict[str, Any]]
    status_summary: dict[str, Any]
    ended: bool = False
    outcome: str | None = None
    diagnostics: list[str] = field(default_factory=list)


class SessionController:
    """Coordinates Loader/MCP/LLM and drives the turn loop.

    The Controller is the only caller of the MCP write tools (hybrid control).
    The LLM (if any) is used solely for prose and free-text intent fallback; when
    `llm` is None, narration falls back to authored base_prose and free-text
    resolution is local-only — i.e. the game is fully playable offline (NFR-008).
    """

    def __init__(
        self,
        mcp: FateMCPServer,
        llm: LLMProvider | None,
        saves: SaveStore,
        config: AppConfig | None = None,
    ) -> None:
        self.mcp = mcp
        self.llm = llm
        self.saves = saves
        self.config = config or AppConfig()
        self._actions = {a["id"]: a for a in mcp.adventure.actions}
        self._quests = {q["id"]: q for q in mcp.adventure.quests}

    # ---- turn loop -------------------------------------------------------
    def begin(self) -> TurnResult:
        """Render the opening location (FR-003)."""
        return self._render(self._narrate_location())

    def take_turn(self, user_input: str) -> TurnResult:
        """Resolve input -> validate -> apply -> evaluate -> narrate."""
        if self.mcp.state.ended:
            return self._render("The adventure is over.", diagnostics=["Session has ended."])

        available = self.mcp.available_actions()
        resolution = intent.resolve(user_input, available, self.llm)
        if resolution.action_id is None:
            return self._render(
                self.mcp.describe_location()["base_prose"],
                diagnostics=[f"Couldn't match {user_input!r} to an available action."],
            )

        try:
            result = self.mcp.apply_action(resolution.action_id, resolution.params)
        except ActionError as exc:
            return self._render(
                self.mcp.describe_location()["base_prose"],
                diagnostics=[str(exc)],
            )

        prose = self._narrate_outcome(result, resolution.action_id)
        if result["ended"]:
            prose = self._append_ending(prose, result["outcome"])
        return self._render(prose, ended=result["ended"], outcome=result["outcome"])

    # ---- persistence (invoked by the presentation layer) -----------------
    def save(self, slot: str) -> None:
        """Serialize via the MCP and persist atomically (FR-011)."""
        self.saves.write(self.mcp.adventure.id, slot, self.mcp.serialize())

    def load(self, slot: str) -> TurnResult:
        """Restore a save into the MCP and resume (FR-012)."""
        data = self.saves.read(self.mcp.adventure.id, slot)
        self.mcp.deserialize(data)
        return self._render(self._narrate_location())

    def restart(self) -> TurnResult:
        """Reset the MCP to the adventure's initial_state."""
        self.mcp.initialize()
        return self.begin()

    # ---- narration -------------------------------------------------------
    def _narrate_location(self) -> str:
        desc = self.mcp.describe_location()
        base = desc["base_prose"]
        if self.llm is None:
            return base
        try:
            system, user = prompts.location_prose_prompt(
                self.mcp.get_state(),
                desc,
                self.mcp.available_actions(),
                self._active_quest_views(),
                prompts.summarize_history(self.mcp.state.history_log),
            )
            return self.llm.generate(system, user, max_tokens=self.config.llm.max_tokens)
        except LLMError:
            return base  # NFR-006 fallback

    def _narrate_outcome(self, result: dict[str, Any], action_id: str) -> str:
        action = self._actions[action_id]
        if self.llm is None:
            return self._offline_outcome(action, result)
        try:
            system, user = prompts.outcome_prose_prompt(
                result["delta"],
                action,
                prompts.summarize_history(self.mcp.state.history_log),
            )
            return self.llm.generate(system, user, max_tokens=self.config.llm.max_tokens)
        except LLMError:
            return self._offline_outcome(action, result)

    def _offline_outcome(self, action: dict[str, Any], result: dict[str, Any]) -> str:
        parts = [action.get("description") or action["name"]]
        for ev in result.get("events", []):
            if ev["type"] == "objective_complete":
                parts.append(f"(Objective complete: {self._objective_name(ev['quest'], ev['objective'])})")
            elif ev["type"] == "quest_complete":
                parts.append(f"(Quest complete: {self._quests[ev['quest']]['name']})")
        return " ".join(parts)

    def _append_ending(self, prose: str, outcome: str | None) -> str:
        banner = {"win": "You have won.", "lose": "You have lost."}.get(outcome or "", "The end.")
        reason = self.mcp.state.end_reason
        if reason:
            banner = f"{banner} {reason}"
        return f"{prose}\n\n{banner}"

    # ---- view helpers ----------------------------------------------------
    def _render(self, prose: str, *, ended: bool = False, outcome: str | None = None,
                diagnostics: list[str] | None = None) -> TurnResult:
        s = self.mcp.state
        return TurnResult(
            prose=prose,
            available_actions=self.mcp.available_actions(),
            status_summary=self._status_summary(),
            ended=ended or s.ended,
            outcome=outcome or s.outcome,
            diagnostics=diagnostics or [],
        )

    def _status_summary(self) -> dict[str, Any]:
        s = self.mcp.get_state()
        return {
            "location": s["location_name"],
            "inventory": list(s["inventory"].keys()),
            "active_quests": [self._quests[q]["name"] for q in s["active_quests"] if q in self._quests],
            "status": s["status"],
            "turn": s["turn_number"],
        }

    def _active_quest_views(self) -> list[dict[str, Any]]:
        return [self._quests[q] for q in self.mcp.state.active_quests if q in self._quests]

    def _objective_name(self, quest_id: str, objective_id: str) -> str:
        for obj in self._quests.get(quest_id, {}).get("objectives", []):
            if obj["id"] == objective_id:
                return obj["description"]
        return objective_id
