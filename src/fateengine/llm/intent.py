"""Free-text -> action resolution (requirements_spec.md FR-006).

Two-stage, local-match-first:
  1. local_match: deterministic name / synonym / fuzzy match against the
     currently-available actions. Fully offline, no LLM.
  2. llm_intent: fallback only when local match is not confident — the LLM maps
     free text to a candidate action id. The MCP still authoritatively validates
     `available_when` before anything is applied; the LLM cannot mutate state.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any

from . import prompts
from .provider import LLMError, LLMProvider


@dataclass
class Resolution:
    """Outcome of resolving free text to an action."""

    action_id: str | None
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    source: str = "none"          # "local" | "llm" | "none"


def local_match(text: str, available_actions: list[dict[str, Any]]) -> Resolution:
    """Deterministic match by exact id/name/synonym, then substring, then fuzzy."""
    t = text.strip().lower()
    if not t:
        return Resolution(None)

    # 1. exact id / name / synonym -> certain.
    for a in available_actions:
        for key in (a["id"], a["name"], *a.get("synonyms", [])):
            if t == key.strip().lower():
                return Resolution(a["id"], confidence=1.0, source="local")

    # 2. substring containment -> strong.
    best: tuple[float, str] | None = None
    for a in available_actions:
        for key in (a["name"], *a.get("synonyms", [])):
            kl = key.lower()
            if t in kl or kl in t:
                if best is None or 0.85 > best[0]:
                    best = (0.85, a["id"])

    # 3. fuzzy ratio over names / synonyms / ids.
    for a in available_actions:
        for key in (a["name"], a["id"], *a.get("synonyms", [])):
            ratio = difflib.SequenceMatcher(None, t, key.lower()).ratio()
            if best is None or ratio > best[0]:
                best = (ratio, a["id"])

    if best is not None:
        return Resolution(best[1], confidence=best[0], source="local")
    return Resolution(None)


def llm_intent(
    text: str,
    available_actions: list[dict[str, Any]],
    provider: LLMProvider,
) -> Resolution:
    """LLM fallback: ask the model to pick a candidate action id from free text."""
    system, user = prompts.intent_prompt(text, available_actions)
    raw = provider.generate(system, user, max_tokens=64)
    lowered = raw.lower()
    # Prefer the action id that appears earliest in the response.
    hits = [(lowered.find(a["id"].lower()), a["id"]) for a in available_actions]
    hits = [(pos, aid) for pos, aid in hits if pos != -1]
    if hits:
        hits.sort()
        return Resolution(hits[0][1], confidence=0.9, source="llm")
    return Resolution(None)


def resolve(
    text: str,
    available_actions: list[dict[str, Any]],
    provider: LLMProvider | None,
    *,
    threshold: float = 0.6,
) -> Resolution:
    """Local match first; fall back to llm_intent below the confidence threshold."""
    local = local_match(text, available_actions)
    if local.action_id is not None and local.confidence >= threshold:
        return local
    if provider is not None:
        try:
            llm = llm_intent(text, available_actions, provider)
            if llm.action_id is not None:
                return llm
        except LLMError:
            pass
    # Nothing confident enough to act on. Surface the weak guess as a non-actionable
    # suggestion (action_id stays None) so callers can offer "did you mean ...?".
    return Resolution(None, confidence=local.confidence, source="none",
                      params={"suggestion": local.action_id} if local.action_id else {})
