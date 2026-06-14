"""Prompt assembly from MCP context + adventure data.

Prompts are built from: serialized MCP state, current location base_prose,
available actions, active quests, and a rolling history summary (last-N events
plus an optional running summary). Output is narrative text only.
"""

from __future__ import annotations

from typing import Any


def location_prose_prompt(
    state: dict[str, Any],
    location: dict[str, Any],
    available_actions: list[dict[str, Any]],
    active_quests: list[dict[str, Any]],
    history_summary: str,
) -> tuple[str, str]:
    """Build (system, user) prompt for current-area prose (FR-003). Stub."""
    raise NotImplementedError


def outcome_prose_prompt(
    state_delta: dict[str, Any],
    action: dict[str, Any],
    history_summary: str,
) -> tuple[str, str]:
    """Build (system, user) prompt for post-action narration (FR-009). Stub."""
    raise NotImplementedError


def summarize_history(history_log: list[dict[str, Any]], last_n: int = 10) -> str:
    """Roll recent events (+ optional running summary) into prompt context. Stub."""
    raise NotImplementedError
