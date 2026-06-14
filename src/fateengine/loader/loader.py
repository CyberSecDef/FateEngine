"""Adventure + save file loading and schema validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schema"
ADVENTURE_SCHEMA = SCHEMA_DIR / "adventure.schema.json"
SAVE_SCHEMA = SCHEMA_DIR / "save.schema.json"


class LoadError(Exception):
    """Raised when a file cannot be read, parsed, or fails schema validation.

    Carries structured diagnostics (FR-014) so the presentation layer can show
    *where* an adventure is malformed rather than a bare stack trace.
    """

    def __init__(self, message: str, *, diagnostics: list[str] | None = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or []


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


class AdventureLoader:
    """Loads and validates adventure and runtime-save JSON files."""

    def list_adventures(self, directory: Path) -> list[Path]:
        """Return candidate adventure files for selection (interface req, section 5). Stub."""
        raise NotImplementedError

    def load_adventure(self, path: Path) -> Adventure:
        """Parse + schema-validate an adventure file. Raises LoadError on failure. Stub."""
        raise NotImplementedError

    def load_save(self, path: Path) -> dict[str, Any]:
        """Parse + schema-validate a runtime save file. Raises LoadError on failure. Stub."""
        raise NotImplementedError
