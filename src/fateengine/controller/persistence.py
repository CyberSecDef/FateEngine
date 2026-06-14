"""Runtime-save persistence.

Saves live at saves/<adventure_id>/<slot>.json, written atomically (temp file +
os.replace) and guarded by a lockfile so a single local session never produces a
torn or concurrently-written save (NFR-005). Saves validate against
schema/save.schema.json on read (NFR-004).
"""

from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import jsonschema

from ..loader.loader import SAVE_SCHEMA

_SLOT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]*$")


class SaveError(Exception):
    """Raised on save/load I/O, an invalid slot name, a held lock, or a save
    that fails schema validation."""

    def __init__(self, message: str, *, diagnostics: list[str] | None = None) -> None:
        self.diagnostics = diagnostics or []
        if self.diagnostics:
            message = message + "\n  - " + "\n  - ".join(self.diagnostics)
        super().__init__(message)


class SaveStore:
    """Atomic, schema-validated runtime-save storage."""

    def __init__(self, saves_dir: Path) -> None:
        self.saves_dir = Path(saves_dir)
        self._schema = json.loads(SAVE_SCHEMA.read_text())

    def path_for(self, adventure_id: str, slot: str) -> Path:
        """saves/<adventure_id>/<slot>.json (slot names are sanitized)."""
        if not _SLOT_RE.match(slot):
            raise SaveError(f"invalid slot name: {slot!r}")
        return self.saves_dir / adventure_id / f"{slot}.json"

    def list_slots(self, adventure_id: str) -> list[str]:
        """Existing save slots for an adventure (interface req, section 5)."""
        d = self.saves_dir / adventure_id
        if not d.is_dir():
            return []
        return sorted(p.stem for p in d.glob("*.json") if p.is_file())

    def write(self, adventure_id: str, slot: str, payload: dict[str, Any]) -> Path:
        """Atomic temp-write + replace under a lockfile (NFR-005)."""
        final = self.path_for(adventure_id, slot)
        final.parent.mkdir(parents=True, exist_ok=True)
        with self._lock(final):
            tmp = final.with_name(final.name + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2))
            os.replace(tmp, final)   # atomic on POSIX
        return final

    def read(self, adventure_id: str, slot: str) -> dict[str, Any]:
        """Load + schema-validate a save (NFR-004)."""
        path = self.path_for(adventure_id, slot)
        if not path.is_file():
            raise SaveError(f"no save slot {slot!r} for adventure {adventure_id!r}")
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise SaveError(f"save {path.name} is not valid JSON: {exc}") from exc
        validator = jsonschema.Draft202012Validator(self._schema)
        errors = [
            f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
            for e in sorted(validator.iter_errors(data), key=lambda e: list(e.path))
        ]
        if errors:
            raise SaveError(f"save {path.name} is invalid", diagnostics=errors)
        return data

    @contextmanager
    def _lock(self, target: Path) -> Iterator[None]:
        """Exclusive lockfile guard. Raises SaveError if a write is in progress."""
        lock = target.with_name(target.name + ".lock")
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise SaveError(
                f"a write is already in progress for {target.name} (lock held)"
            ) from exc
        try:
            yield
        finally:
            os.close(fd)
            try:
                lock.unlink()
            except FileNotFoundError:
                pass
