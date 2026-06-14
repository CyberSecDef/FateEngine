"""Runtime-save persistence.

Saves live at saves/<adventure_id>/<slot>.json, written atomically (temp file +
os.replace) and guarded by a lockfile so a single local session never produces a
torn or concurrently-written save (NFR-005). Saves validate against
schema/save.schema.json on read (NFR-004).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class SaveStore:
    """Atomic, schema-validated runtime-save storage."""

    def __init__(self, saves_dir: Path) -> None:
        self.saves_dir = saves_dir

    def path_for(self, adventure_id: str, slot: str) -> Path:
        """saves/<adventure_id>/<slot>.json. Stub."""
        raise NotImplementedError

    def list_slots(self, adventure_id: str) -> list[str]:
        """Existing save slots for an adventure (interface req, section 5). Stub."""
        raise NotImplementedError

    def write(self, adventure_id: str, slot: str, payload: dict[str, Any]) -> Path:
        """Atomic temp-write + replace under a lockfile (NFR-005). Stub."""
        raise NotImplementedError

    def read(self, adventure_id: str, slot: str) -> dict[str, Any]:
        """Load + schema-validate a save (NFR-004). Stub."""
        raise NotImplementedError
