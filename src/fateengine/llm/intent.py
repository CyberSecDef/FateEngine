"""Free-text -> action resolution (requirements_spec.md FR-006).

Two-stage, local-match-first:
  1. local_match: deterministic name / synonym / fuzzy match against the
     currently-available actions. Fully offline, no LLM.
  2. llm_intent: fallback only when local match is not confident — the LLM maps
     free text to a candidate action id (+params). The MCP still authoritatively
     validates `available_when` before anything is applied; the LLM cannot
     mutate state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .provider import LLMProvider


@dataclass
class Resolution:
    """Outcome of resolving free text to an action."""

    action_id: str | None
    params: dict[str, Any]
    confidence: float
    source: str          # "local" | "llm" | "none"


def local_match(text: str, available_actions: list[dict[str, Any]]) -> Resolution:
    """Deterministic match by name/synonym/fuzzy. Stub."""
    raise NotImplementedError


def llm_intent(
    text: str,
    available_actions: list[dict[str, Any]],
    provider: LLMProvider,
) -> Resolution:
    """LLM fallback intent parse -> candidate action id. Stub."""
    raise NotImplementedError


def resolve(
    text: str,
    available_actions: list[dict[str, Any]],
    provider: LLMProvider | None,
    *,
    threshold: float = 0.6,
) -> Resolution:
    """Local match first; fall back to llm_intent below threshold. Stub."""
    raise NotImplementedError
