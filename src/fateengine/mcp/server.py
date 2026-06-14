"""MCP server — the authoritative game-state engine.

`FateMCPServer` owns the GameState and is the only thing that mutates it. It
builds on the tested core (state / predicates / effects): predicates gate
actions and resolve quests; effects are applied atomically inside a
GameState.transaction() so a turn is all-or-nothing (NFR-002).

The class itself has no dependency on the MCP SDK — it is a plain, fully
unit-testable engine. `tools.py` wraps it as a real Model Context Protocol
server (FastMCP, stdio) and exposes the read-only subset to the LLM
(requirements_spec.md sections 6, 8).
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from ..loader.loader import Adventure
from .effects import apply_effect
from .predicates import evaluate
from .state import GameState


class ActionError(Exception):
    """Raised when an action is unknown or not currently available (FR-007)."""


class FateMCPServer:
    """Owns the authoritative GameState and the engine's tool surface."""

    def __init__(self, adventure: Adventure, state: GameState | None = None) -> None:
        self.adventure = adventure
        self.state = state or GameState()
        self._actions = {a["id"]: a for a in adventure.actions}
        self._quests = {q["id"]: q for q in adventure.quests}
        self._locations = {loc["id"]: loc for loc in adventure.map["locations"]}
        self._connections = adventure.map["connections"]

    # ---- lifecycle -------------------------------------------------------
    def initialize(self) -> None:
        """Seed state from the adventure's initial_state (FR-002)."""
        init = self.adventure.initial_state
        self.state = GameState(
            location=init["location"],
            inventory=copy.deepcopy(init.get("inventory", {})),
            status=copy.deepcopy(init.get("status", {})),
            variables=copy.deepcopy(init.get("variables", {})),
            active_quests=list(init.get("active_quests", [])),
        )

    def _reward_for(self, quest_id: str) -> list[dict[str, Any]] | None:
        quest = self._quests.get(quest_id)
        reward = quest.get("reward") if quest else None
        return reward["effects"] if reward else None

    # ---- read tools (LLM-visible) ---------------------------------------
    def get_state(self) -> dict[str, Any]:
        """Serialized snapshot for prompt construction (FR-003, FR-015)."""
        s = self.state
        return {
            "location": s.location,
            "location_name": self._locations.get(s.location, {}).get("name", s.location),
            "inventory": copy.deepcopy(s.inventory),
            "status": copy.deepcopy(s.status),
            "variables": copy.deepcopy(s.variables),
            "active_quests": list(s.active_quests),
            "completed_quests": list(s.completed_quests),
            "completed_objectives": copy.deepcopy(s.completed_objectives),
            "turn_number": s.turn_number,
            "ended": s.ended,
            "outcome": s.outcome,
        }

    def describe_location(self, location_id: str | None = None) -> dict[str, Any]:
        """Location name, base_prose, currently-open exits, and present NPCs."""
        loc_id = location_id or self.state.location
        loc = self._locations.get(loc_id)
        if loc is None:
            raise ActionError(f"unknown location: {loc_id!r}")
        exits = []
        for conn in self._connections:
            if conn["from"] != loc_id:
                continue
            cond = conn.get("condition")
            if cond is not None and not evaluate(cond, self.state):
                continue
            exits.append(
                {
                    "to": conn["to"],
                    "to_name": self._locations.get(conn["to"], {}).get("name", conn["to"]),
                    "description": conn.get("description", ""),
                }
            )
        npcs = [
            {"id": n["id"], "name": n["name"]}
            for n in self.adventure.npcs
            if n["current_location"] == loc_id
        ]
        return {
            "id": loc_id,
            "name": loc.get("name", loc_id),
            "base_prose": loc.get("base_prose", ""),
            "tags": loc.get("tags", []),
            "exits": exits,
            "npcs": npcs,
        }

    def look_up_npc(self, npc_id: str) -> dict[str, Any]:
        """NPC public data (name, location, dialogue_seed, exposed state)."""
        for n in self.adventure.npcs:
            if n["id"] == npc_id:
                return {
                    "id": n["id"],
                    "name": n["name"],
                    "current_location": n["current_location"],
                    "dialogue_seed": n.get("dialogue_seed", ""),
                    "state": copy.deepcopy(n.get("state", {})),
                }
        raise ActionError(f"unknown npc: {npc_id!r}")

    def recall_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Most recent history events for the prompt's rolling summary."""
        return copy.deepcopy(self.state.history_log[-limit:])

    # ---- write tools (Controller-only) ----------------------------------
    def available_actions(self) -> list[dict[str, Any]]:
        """Actions whose `available_when` predicate currently holds (FR-004)."""
        out = []
        for action in self.adventure.actions:
            if evaluate(action["available_when"], self.state):
                out.append(
                    {
                        "id": action["id"],
                        "name": action["name"],
                        "description": action["description"],
                        "synonyms": action.get("synonyms", []),
                    }
                )
        return out

    def apply_action(self, action_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Validate + apply an action atomically, then resolve quests + end state.

        Returns {delta, events, ended, outcome}. Raises ActionError if the action
        is unknown or unavailable (FR-007, FR-008, NFR-002).
        """
        if self.state.ended:
            raise ActionError("the session has already ended")
        action = self._actions.get(action_id)
        if action is None:
            raise ActionError(f"unknown action: {action_id!r}")
        if not evaluate(action["available_when"], self.state):
            raise ActionError(f"action not available now: {action_id!r}")

        before = copy.deepcopy(self.state)
        events: list[dict[str, Any]] = []
        with self.state.transaction():
            for effect in action["effects"]:
                apply_effect(effect, self.state, reward_resolver=self._reward_for)
            events = self._run_quest_evaluation()
            self.state.turn_number += 1

        outcome = self._resolve_end_conditions()
        delta = self.state.diff_from(before)
        self.state.history_log.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "turn_number": self.state.turn_number,
                "action_id": action_id,
                "state_delta": delta,
            }
        )
        return {"delta": delta, "events": events, "ended": self.state.ended, "outcome": outcome}

    def evaluate_quests(self) -> list[dict[str, Any]]:
        """Standalone quest evaluation (FR-010). Atomic. Returns completion events."""
        with self.state.transaction():
            return self._run_quest_evaluation()

    def check_end_conditions(self) -> str | None:
        """Evaluate win/lose predicates; return 'win' | 'lose' | None (FR-013)."""
        return self._resolve_end_conditions()

    # ---- internals -------------------------------------------------------
    def _run_quest_evaluation(self) -> list[dict[str, Any]]:
        """Complete objectives/quests whose criteria now hold. Mutates state;
        assumes the caller holds a transaction."""
        events: list[dict[str, Any]] = []
        for quest in self.adventure.quests:
            qid = quest["id"]
            if qid not in self.state.active_quests:
                continue
            all_done = True
            for obj in quest["objectives"]:
                oid = obj["id"]
                done = oid in self.state.completed_objectives.get(qid, [])
                if not done and evaluate(obj["completion_criteria"], self.state):
                    apply_effect(
                        {
                            "type": "complete_objective",
                            "parameters": {"quest": qid, "objective": oid},
                        },
                        self.state,
                    )
                    events.append({"type": "objective_complete", "quest": qid, "objective": oid})
                    done = True
                all_done = all_done and done
            if all_done and quest["objectives"]:
                apply_effect(
                    {"type": "complete_quest", "parameters": {"quest": qid}},
                    self.state,
                    reward_resolver=self._reward_for,
                )
                events.append({"type": "quest_complete", "quest": qid})
        return events

    def _resolve_end_conditions(self) -> str | None:
        """Apply win/lose predicates (lose takes precedence). trigger_end may have
        already ended the session."""
        s = self.state
        if s.ended:
            return s.outcome
        for pred in self.adventure.lose_conditions:
            if evaluate(pred, s):
                s.ended, s.outcome = True, "lose"
                return "lose"
        for pred in self.adventure.win_conditions:
            if evaluate(pred, s):
                s.ended, s.outcome = True, "win"
                return "win"
        return None

    # ---- persistence -----------------------------------------------------
    def serialize(self) -> dict[str, Any]:
        """Deterministic runtime-save dict (FR-011, save.schema.json)."""
        s = self.state
        return {
            "adventure_id": self.adventure.id,
            "adventure_version": self.adventure.version,
            "location": s.location,
            "inventory": copy.deepcopy(s.inventory),
            "status": copy.deepcopy(s.status),
            "variables": copy.deepcopy(s.variables),
            "active_quests": list(s.active_quests),
            "completed_quests": list(s.completed_quests),
            "completed_objectives": copy.deepcopy(s.completed_objectives),
            "ended": s.ended,
            "outcome": s.outcome,
            "end_reason": s.end_reason,
            "turn_number": s.turn_number,
            "history_log": copy.deepcopy(s.history_log),
        }

    def deserialize(self, save: dict[str, Any]) -> None:
        """Restore state from a (validated) save dict (FR-012).

        Raises ActionError if the save is for a different adventure.
        """
        if save.get("adventure_id") != self.adventure.id:
            raise ActionError(
                f"save is for adventure {save.get('adventure_id')!r}, not {self.adventure.id!r}"
            )
        self.state = GameState(
            location=save["location"],
            inventory=copy.deepcopy(save.get("inventory", {})),
            status=copy.deepcopy(save.get("status", {})),
            variables=copy.deepcopy(save.get("variables", {})),
            active_quests=list(save.get("active_quests", [])),
            completed_quests=list(save.get("completed_quests", [])),
            completed_objectives=copy.deepcopy(save.get("completed_objectives", {})),
            history_log=copy.deepcopy(save.get("history_log", [])),
            turn_number=save.get("turn_number", 0),
            ended=save.get("ended", False),
            outcome=save.get("outcome"),
            end_reason=save.get("end_reason"),
        )

    def serve_stdio(self, *, allow_write: bool = False) -> None:
        """Run as a Model Context Protocol server over stdio.

        Exposes the read-only tool subset to an LLM host by default; set
        allow_write=True to also expose the gameplay-driving write tools for an
        agentic host that should drive the game itself.
        """
        from . import tools

        tools.serve_stdio(self, allow_write=allow_write)
