"""Sanity tests for the JSON Schemas — these should pass before any engine code lands."""

import json
from pathlib import Path

import pytest

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schema"


@pytest.mark.parametrize("name", ["adventure.schema.json", "save.schema.json"])
def test_schema_is_valid_jsonschema(name: str) -> None:
    """Each schema file parses and is itself a valid JSON Schema (draft 2020-12)."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((SCHEMA_DIR / name).read_text())
    # Raises jsonschema.SchemaError if the schema itself is malformed.
    jsonschema.Draft202012Validator.check_schema(schema)
