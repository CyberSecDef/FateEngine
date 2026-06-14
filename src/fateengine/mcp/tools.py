"""MCP tool registration (Model Context Protocol surface).

By default the server exposes ONLY the read-only tools (FR-015, hybrid control):
an LLM host can inspect state but not change it. `allow_write=True` additionally
exposes the gameplay-driving write tools for an *agentic* host that should drive
the game itself — an explicit opt-in, since it hands state mutation to the model.

The `mcp` SDK is imported lazily (and the FastMCP factory is injectable) so the
core engine and its tests need no SDK.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .server import FateMCPServer

# Tool names exposed to the LLM by default (FR-015).
READ_TOOLS: tuple[str, ...] = (
    "get_state",
    "describe_location",
    "look_up_npc",
    "recall_history",
)

# Mutating tools — reserved for the Session Controller in the hybrid model, and
# only served over MCP when allow_write=True (agentic host).
WRITE_TOOLS: tuple[str, ...] = (
    "available_actions",
    "apply_action",
    "evaluate_quests",
    "check_end_conditions",
)


def tool_methods(engine: "FateMCPServer", *, allow_write: bool = False) -> dict[str, Callable]:
    """Return {tool_name: bound method} to expose. Pure — no SDK needed."""
    names = list(READ_TOOLS) + (list(WRITE_TOOLS) if allow_write else [])
    return {name: getattr(engine, name) for name in names}


def build_server(
    engine: "FateMCPServer",
    *,
    allow_write: bool = False,
    factory: Callable[[], Any] | None = None,
):
    """Construct a FastMCP server exposing `engine`'s tools.

    `factory` builds the server object (defaults to FastMCP); inject a fake in
    tests. Returns the server instance (not run).
    """
    if factory is None:
        try:
            from mcp.server.fastmcp import FastMCP
        except ImportError as exc:  # pragma: no cover - optional dep
            raise ImportError(
                "The 'mcp' package is required to run the MCP server. "
                "Install it with: pip install mcp"
            ) from exc

        def factory() -> Any:
            return FastMCP("fateengine")

    server = factory()
    for name, method in tool_methods(engine, allow_write=allow_write).items():
        server.add_tool(method, name=name, description=(method.__doc__ or "").strip())
    return server


def serve_stdio(
    engine: "FateMCPServer", *, allow_write: bool = False
) -> None:  # pragma: no cover - needs SDK + host
    """Run the MCP server over stdio (the local transport)."""
    build_server(engine, allow_write=allow_write).run()
