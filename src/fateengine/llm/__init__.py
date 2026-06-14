"""LLM Integration — provider-agnostic narrative generation + intent parsing.

Responsibilities (requirements_spec.md section 6):
  * build prompts from MCP-serialized context + adventure data
  * generate location prose and action-outcome narration (text only)
  * intent-parse free text -> candidate action id (FR-006 fallback path)
  * retry with backoff, then fall back to base_prose (NFR-006)

The LLM never mutates state; it may call only the read-only MCP tools.
"""

from .provider import LLMProvider, LLMError

__all__ = ["LLMProvider", "LLMError"]
