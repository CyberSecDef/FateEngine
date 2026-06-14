"""Adventure Loader — file I/O, JSON parsing, schema validation.

Responsibilities (requirements_spec.md FR-001, FR-014, NFR-004):
  * read adventure / save JSON from disk
  * validate against schema/adventure.schema.json and schema/save.schema.json
  * surface structured diagnostics; never initialize a session from invalid data
"""

from .loader import AdventureLoader, LoadError

__all__ = ["AdventureLoader", "LoadError"]
