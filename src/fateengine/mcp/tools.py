"""MCP tool registration.

Binds FateMCPServer methods to MCP tools and tags each as read-only
(LLM-visible) or write (Controller-only). Keeping the split here makes the
hybrid-control boundary explicit and auditable.
"""

from __future__ import annotations

# Tool names exposed to the LLM. The LLM is given ONLY these (FR-015).
READ_TOOLS: tuple[str, ...] = (
    "get_state",
    "describe_location",
    "look_up_npc",
    "recall_history",
)

# Mutating tools — reserved for the Session Controller. Never handed to the LLM.
WRITE_TOOLS: tuple[str, ...] = (
    "available_actions",
    "apply_action",
    "evaluate_quests",
    "check_end_conditions",
    "serialize",
    "deserialize",
)


def register(server: "object") -> None:  # noqa: ARG001 — FateMCPServer
    """Register read + write tools on the FastMCP instance. Stub."""
    raise NotImplementedError
