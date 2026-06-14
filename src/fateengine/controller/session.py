"""Turn-loop orchestration."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from ..config import AppConfig
from ..llm import intent, prompts
from ..llm.provider import LLMError, LLMProvider
from ..mcp.server import ActionError, FateMCPServer
from ..observability import new_session_id
from .persistence import SaveStore

_log = logging.getLogger("fateengine.session")


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
        session_id: str | None = None,
    ) -> None:
        self.mcp = mcp
        self.llm = llm
        self.saves = saves
        self.config = config or AppConfig()
        self.session_id = session_id or new_session_id()
        self._actions = {a["id"]: a for a in mcp.adventure.actions}
        self._quests = {q["id"]: q for q in mcp.adventure.quests}
        # Last constructed prompt / LLM response, surfaced by diagnostic mode.
        self.last_prompt: str | None = None
        self.last_response: str | None = None

    def _emit(self, level: int, msg: str, *args: Any) -> None:
        _log.log(level, msg, *args, extra={"session": self.session_id})

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
            self._emit(logging.INFO, "unresolved input: %r", user_input)
            return self._render(
                self.mcp.describe_location()["base_prose"],
                diagnostics=[f"Couldn't match {user_input!r} to an available action."],
            )

        try:
            result = self.mcp.apply_action(resolution.action_id, resolution.params)
        except ActionError as exc:
            self._emit(logging.WARNING, "rejected action %s: %s", resolution.action_id, exc)
            return self._render(
                self.mcp.describe_location()["base_prose"],
                diagnostics=[str(exc)],
            )

        # NFR-007: log the transition with before/after state delta.
        self._emit(
            logging.INFO,
            "turn %d: action=%s (via %s) outcome=%s",
            self.mcp.state.turn_number,
            resolution.action_id,
            resolution.source,
            result["outcome"],
        )
        self._emit(logging.DEBUG, "delta=%s events=%s", result["delta"], result["events"])

        prose = self._narrate_outcome(result, resolution.action_id)
        if result["ended"]:
            prose = self._append_ending(prose, result["outcome"])
        return self._render(prose, ended=result["ended"], outcome=result["outcome"])

    # ---- persistence (invoked by the presentation layer) -----------------
    def save(self, slot: str) -> None:
        """Serialize via the MCP and persist atomically (FR-011)."""
        self.saves.write(self.mcp.adventure.id, slot, self.mcp.serialize())
        self._emit(logging.INFO, "saved to slot %r (turn %d)", slot, self.mcp.state.turn_number)

    def load(self, slot: str) -> TurnResult:
        """Restore a save into the MCP and resume (FR-012)."""
        data = self.saves.read(self.mcp.adventure.id, slot)
        self.mcp.deserialize(data)
        self._emit(logging.INFO, "loaded slot %r (turn %d)", slot, self.mcp.state.turn_number)
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
            return self._generate(system, user, "location")
        except LLMError:
            self._emit(logging.WARNING, "LLM failed; falling back to base_prose")
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
            return self._generate(system, user, "outcome")
        except LLMError:
            self._emit(logging.WARNING, "LLM failed; using offline narration")
            return self._offline_outcome(action, result)

    def _generate(self, system: str, user: str, kind: str) -> str:
        """Call the LLM, recording the prompt + response (NFR-007, diagnostic mode)."""
        assert self.llm is not None
        self.last_prompt = f"[{kind}]\nSYSTEM:\n{system}\n\nUSER:\n{user}"
        self._emit(logging.DEBUG, "llm prompt %s", self.last_prompt)
        response = self.llm.generate(system, user, max_tokens=self.config.llm.max_tokens)
        self.last_response = response
        self._emit(logging.DEBUG, "llm response [%s]: %s", kind, response)
        return response

    def debug_snapshot(self) -> str:
        """Human-readable dump of raw MCP state, last prompt/response, and recent
        history — backs the CLI /debug command and diagnostic mode (section 7)."""
        lines = [
            f"session: {self.session_id}",
            "state:",
            json.dumps(self.mcp.get_state(), indent=2, default=str),
            "recent history:",
            json.dumps(self.mcp.recall_history(5), indent=2, default=str),
        ]
        if self.last_prompt:
            lines += ["last prompt:", self.last_prompt]
        if self.last_response:
            lines += ["last response:", self.last_response]
        return "\n".join(lines)

    def _offline_outcome(self, action: dict[str, Any], result: dict[str, Any]) -> str:
        parts = [action.get("description") or action["name"]]
        for ev in result.get("events", []):
            if ev["type"] == "objective_complete":
                parts.append(
                    f"(Objective complete: {self._objective_name(ev['quest'], ev['objective'])})"
                )
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
    def _render(
        self,
        prose: str,
        *,
        ended: bool = False,
        outcome: str | None = None,
        diagnostics: list[str] | None = None,
    ) -> TurnResult:
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
            "active_quests": [
                self._quests[q]["name"] for q in s["active_quests"] if q in self._quests
            ],
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
