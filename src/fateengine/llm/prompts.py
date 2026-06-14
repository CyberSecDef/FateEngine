"""Prompt assembly from MCP context + adventure data.

Prompts are built from: serialized MCP state, current location base_prose,
available actions, active quests, and a rolling history summary. LLM output is
narrative text only — these prompts never ask the model to decide state.
"""

from __future__ import annotations

from typing import Any

_NARRATOR_SYSTEM = (
    "You are the narrator of a text adventure. Write vivid, concise second-person "
    "prose (2-4 sentences). Describe only what is given to you — never invent items, "
    "exits, characters, or outcomes, and never decide what the player does next. "
    "Do not list the available actions; just set the scene."
)


def _quest_lines(active_quests: list[dict[str, Any]]) -> str:
    if not active_quests:
        return "(none)"
    return "\n".join(f"- {q['name']}: {q.get('description', '')}" for q in active_quests)


def location_prose_prompt(
    state: dict[str, Any],
    location: dict[str, Any],
    available_actions: list[dict[str, Any]],
    active_quests: list[dict[str, Any]],
    history_summary: str,
) -> tuple[str, str]:
    """Build (system, user) prompt for current-area prose (FR-003)."""
    exits = ", ".join(e.get("to_name", e["to"]) for e in location.get("exits", [])) or "none"
    npcs = ", ".join(n["name"] for n in location.get("npcs", [])) or "none"
    user = (
        f"Location: {location['name']}\n"
        f"Established description (authoritative — do not contradict):\n{location['base_prose']}\n\n"
        f"Visible exits: {exits}\n"
        f"Characters present: {npcs}\n"
        f"Player inventory: {_inventory(state)}\n"
        f"Active quests:\n{_quest_lines(active_quests)}\n\n"
        f"Recent events:\n{history_summary or '(this is the start)'}\n\n"
        "Narrate arriving in / surveying this location now."
    )
    return _NARRATOR_SYSTEM, user


def outcome_prose_prompt(
    state_delta: dict[str, Any],
    action: dict[str, Any],
    history_summary: str,
) -> tuple[str, str]:
    """Build (system, user) prompt for post-action narration (FR-009)."""
    user = (
        f"The player chose: {action['name']} — {action.get('description', '')}\n\n"
        f"Resulting state changes (authoritative):\n{_render_delta(state_delta)}\n\n"
        f"Recent events:\n{history_summary or '(none)'}\n\n"
        "Narrate the outcome of this action. Reflect the state changes exactly; "
        "do not add any change that is not listed."
    )
    return _NARRATOR_SYSTEM, user


def intent_prompt(text: str, available_actions: list[dict[str, Any]]) -> tuple[str, str]:
    """Build (system, user) prompt to map free text to one available action id."""
    system = (
        "You map a player's free-text intent to exactly one available action. "
        "Reply with ONLY the action id, or the word none if nothing fits."
    )
    options = "\n".join(
        f"- {a['id']}: {a['name']} ({', '.join(a.get('synonyms', [])) or 'no synonyms'})"
        for a in available_actions
    )
    user = f"Available actions:\n{options}\n\nPlayer said: {text!r}\n\nAction id:"
    return system, user


def summarize_history(history_log: list[dict[str, Any]], last_n: int = 10) -> str:
    """Roll recent events into a compact prompt summary (last-N by default)."""
    recent = history_log[-last_n:]
    if not recent:
        return ""
    return "\n".join(
        f"- turn {e.get('turn_number', '?')}: {e.get('action_id', '?')}" for e in recent
    )


# --- helpers --------------------------------------------------------------


def _inventory(state: dict[str, Any]) -> str:
    inv = state.get("inventory", {})
    return ", ".join(str(k) for k in inv) if inv else "empty"


def _render_delta(delta: dict[str, Any]) -> str:
    if not delta:
        return "(no observable change)"
    lines = []
    for field, change in delta.items():
        if isinstance(change, dict) and "from" in change and "to" in change:
            lines.append(f"- {field}: {change['from']!r} -> {change['to']!r}")
        else:
            lines.append(f"- {field}: {change!r}")
    return "\n".join(lines)
