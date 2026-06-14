"""MCP Server — the single source of truth for all game state.

This package exposes game state as a real Model Context Protocol server
(requirements_spec.md section 6). It is the ONLY component permitted to mutate
state.

Tool surface:
    Read tools (LLM-visible):    get_state, describe_location, look_up_npc, recall_history
    Write tools (Controller-only): apply_action, apply_effect, evaluate_quests,
                                   check_end_conditions, serialize, deserialize

Submodules:
    state       — GameState container + atomic transaction support
    predicates  — boolean predicate evaluator (Appendix A)
    effects     — closed effect catalog + appliers (Appendix B)
    tools       — MCP tool registration / server wiring
"""

from .state import GameState
from .server import FateMCPServer

__all__ = ["GameState", "FateMCPServer"]
