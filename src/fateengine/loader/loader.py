"""Adventure + save file loading and schema validation.

Two layers of checking (FR-001, FR-014, NFR-004):
  1. JSON Schema validation against schema/*.schema.json (structural).
  2. Referential-integrity validation (semantic) — cross-references the schema
     cannot express: do ids referenced by connections, effects, npcs, and
     initial_state actually exist?

Either layer's failures are collected and raised together as a LoadError with
structured diagnostics; an invalid file never initializes a session.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schema"
ADVENTURE_SCHEMA = SCHEMA_DIR / "adventure.schema.json"
SAVE_SCHEMA = SCHEMA_DIR / "save.schema.json"


class LoadError(Exception):
    """Raised when a file cannot be read, parsed, or fails validation.

    Carries structured diagnostics (FR-014) so the presentation layer can show
    *where* an adventure is malformed rather than a bare stack trace.
    """

    def __init__(self, message: str, *, diagnostics: list[str] | None = None) -> None:
        self.diagnostics = diagnostics or []
        if self.diagnostics:
            message = message + "\n  - " + "\n  - ".join(self.diagnostics)
        super().__init__(message)


@dataclass(frozen=True)
class Adventure:
    """A validated, in-memory adventure definition (read-only)."""

    metadata: dict[str, Any]
    map: dict[str, Any]
    quests: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    npcs: list[dict[str, Any]]
    initial_state: dict[str, Any]
    win_conditions: list[dict[str, Any]]
    lose_conditions: list[dict[str, Any]]
    raw: dict[str, Any]

    @property
    def id(self) -> str:
        return self.metadata["id"]

    @property
    def version(self) -> str:
        return self.metadata["version"]


class AdventureLoader:
    """Loads and validates adventure and runtime-save JSON files."""

    def list_adventures(self, directory: Path) -> list[Path]:
        """Return candidate adventure files (*.json) for selection (section 5)."""
        if not directory.is_dir():
            return []
        return sorted(p for p in directory.glob("*.json") if p.is_file())

    def load_adventure(self, path: Path) -> Adventure:
        """Parse + schema-validate + integrity-check an adventure. Raises LoadError."""
        data = _read_json(path)
        diagnostics = _schema_errors(data, _schema(ADVENTURE_SCHEMA))
        # Only run semantic checks if the structure is sound enough to walk.
        if not diagnostics:
            diagnostics = _integrity_errors(data)
        if diagnostics:
            raise LoadError(f"Adventure {path.name} is invalid", diagnostics=diagnostics)
        return Adventure(
            metadata=data["metadata"],
            map=data["map"],
            quests=data["quests"],
            actions=data["actions"],
            npcs=data["npcs"],
            initial_state=data["initial_state"],
            win_conditions=data.get("win_conditions", []),
            lose_conditions=data.get("lose_conditions", []),
            raw=data,
        )

    def load_save(self, path: Path) -> dict[str, Any]:
        """Parse + schema-validate a runtime save file. Raises LoadError."""
        data = _read_json(path)
        diagnostics = _schema_errors(data, _schema(SAVE_SCHEMA))
        if diagnostics:
            raise LoadError(f"Save {path.name} is invalid", diagnostics=diagnostics)
        return data


# --- internals ------------------------------------------------------------


@lru_cache(maxsize=None)
def _schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _read_json(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text()
    except OSError as exc:
        raise LoadError(f"Cannot read {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LoadError(f"{path.name} is not valid JSON: {exc}") from exc


def _schema_errors(instance: Any, schema: dict[str, Any]) -> list[str]:
    validator = jsonschema.Draft202012Validator(schema)
    out = []
    for err in sorted(validator.iter_errors(instance), key=lambda e: list(e.path)):
        where = "/".join(str(p) for p in err.path) or "<root>"
        out.append(f"{where}: {err.message}")
    return out


def _walk_effects(effects: list[dict[str, Any]]):
    """Yield every effect, descending into grant_reward bundles."""
    for eff in effects:
        yield eff
        if eff.get("type") == "grant_reward":
            yield from _walk_effects(eff.get("parameters", {}).get("effects", []))


def _integrity_errors(data: dict[str, Any]) -> list[str]:
    """Cross-reference id usage the JSON Schema cannot check."""
    errors: list[str] = []

    loc_ids = {loc["id"] for loc in data["map"]["locations"]}
    quest_ids = {q["id"] for q in data["quests"]}
    objective_ids = {(q["id"], obj["id"]) for q in data["quests"] for obj in q["objectives"]}

    def dup_check(items: list[dict[str, Any]], label: str) -> None:
        seen: set[str] = set()
        for it in items:
            if it["id"] in seen:
                errors.append(f"duplicate {label} id: {it['id']!r}")
            seen.add(it["id"])

    dup_check(data["map"]["locations"], "location")
    dup_check(data["quests"], "quest")
    dup_check(data["actions"], "action")
    dup_check(data["npcs"], "npc")

    # Location references.
    start = data["metadata"]["starting_location"]
    if start not in loc_ids:
        errors.append(f"metadata.starting_location references unknown location {start!r}")
    init_loc = data["initial_state"]["location"]
    if init_loc not in loc_ids:
        errors.append(f"initial_state.location references unknown location {init_loc!r}")
    for i, conn in enumerate(data["map"]["connections"]):
        for end in ("from", "to"):
            if conn[end] not in loc_ids:
                errors.append(f"connections[{i}].{end} references unknown location {conn[end]!r}")
    for npc in data["npcs"]:
        if npc["current_location"] not in loc_ids:
            errors.append(
                f"npc {npc['id']!r} current_location references unknown location "
                f"{npc['current_location']!r}"
            )

    # Quest references.
    for q in data["initial_state"].get("active_quests", []):
        if q not in quest_ids:
            errors.append(f"initial_state.active_quests references unknown quest {q!r}")

    # Effect target references (actions + quest rewards).
    reward_effects = [
        eff for q in data["quests"] if q.get("reward") for eff in q["reward"]["effects"]
    ]
    action_effects = [eff for a in data["actions"] for eff in a["effects"]]
    for eff in _walk_effects(action_effects + reward_effects):
        _check_effect_targets(eff, loc_ids, quest_ids, objective_ids, errors)

    return errors


def _check_effect_targets(eff, loc_ids, quest_ids, objective_ids, errors) -> None:
    t = eff.get("type")
    p = eff.get("parameters", {})
    if t == "move_location" and p.get("to") not in loc_ids:
        errors.append(f"move_location effect targets unknown location {p.get('to')!r}")
    elif t in ("start_quest", "complete_quest") and p.get("quest") not in quest_ids:
        errors.append(f"{t} effect targets unknown quest {p.get('quest')!r}")
    elif t == "complete_objective" and (p.get("quest"), p.get("objective")) not in objective_ids:
        errors.append(
            f"complete_objective targets unknown objective "
            f"{p.get('quest')!r}/{p.get('objective')!r}"
        )
