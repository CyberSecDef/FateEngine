"""MCP tool registration (Model Context Protocol surface).

The LLM is given ONLY the read-only tools (FR-015, hybrid control). The mutating
tools stay in-process for the Session Controller and are deliberately NOT
registered on the MCP server handed to the model.

The `mcp` SDK is imported lazily inside `build_server` / `serve_stdio` so the
core engine (`server.py`) and its tests don't require the SDK to be installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import FateMCPServer

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


def build_server(engine: "FateMCPServer"):
    """Construct a FastMCP server exposing only the read-only tools of `engine`.

    Returns the FastMCP instance (not run). Raises ImportError with a helpful
    message if the optional `mcp` SDK is not installed.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - depends on optional dep
        raise ImportError(
            "The 'mcp' package is required to run the MCP server. "
            "Install it with: pip install mcp"
        ) from exc

    mcp = FastMCP("fateengine")
    for name in READ_TOOLS:
        method = getattr(engine, name)
        mcp.add_tool(method, name=name, description=(method.__doc__ or "").strip())
    return mcp


def serve_stdio(engine: "FateMCPServer") -> None:  # pragma: no cover - needs SDK + host
    """Run the MCP server over stdio (the local single-player transport)."""
    build_server(engine).run()
