"""Session Controller — turn-loop orchestration + runtime-save persistence.

The Controller is the primary MCP client and the only caller of MCP write
tools (hybrid control). It coordinates Loader -> MCP -> LLM each turn and owns
save/load (requirements_spec.md section 6).
"""

from .session import SessionController
from .persistence import SaveStore

__all__ = ["SessionController", "SaveStore"]
