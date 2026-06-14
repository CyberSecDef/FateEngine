"""FateEngine — choose-your-own-adventure engine.

Authoritative game state lives behind a Model Context Protocol (MCP) server
(`fateengine.mcp`); an LLM (`fateengine.llm`) supplies narrative prose only.
See requirements_spec.md for the full specification.

Components (strict separation of concerns, requirements_spec.md section 6):
    loader        — Adventure Loader: I/O, parse, schema validation
    mcp           — MCP Server: single source of truth for all game state
    llm           — LLM Integration: prompts, provider adapter, intent parsing
    controller    — Session Controller: turn loop + runtime-save persistence
    presentation  — Presentation Layer: CLI/TUI

Invariant: no component except `mcp` mutates game state.
"""

import logging

__version__ = "0.0.1"

# Library logging is silent until a host calls observability.configure_logging.
logging.getLogger("fateengine").addHandler(logging.NullHandler())
