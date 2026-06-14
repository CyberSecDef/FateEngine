"""Tests for SaveStore — atomic, schema-validated runtime saves."""

import json

import pytest

from fateengine.controller.persistence import SaveError, SaveStore


def minimal_save(**over):
    base = {
        "adventure_id": "sunken-crypt",
        "adventure_version": "1.0.0",
        "location": "clearing",
        "inventory": {},
        "status": {},
        "active_quests": [],
        "history_log": [],
        "turn_number": 0,
    }
    base.update(over)
    return base


@pytest.fixture
def store(tmp_path) -> SaveStore:
    return SaveStore(tmp_path)


def test_write_then_read_round_trip(store):
    payload = minimal_save(turn_number=5, status={"hero": True})
    path = store.write("sunken-crypt", "slot1", payload)
    assert path.is_file()
    assert store.read("sunken-crypt", "slot1") == payload


def test_write_is_pretty_json(store):
    store.write("sunken-crypt", "slot1", minimal_save())
    raw = store.path_for("sunken-crypt", "slot1").read_text()
    assert "\n" in raw  # indent=2


def test_list_slots(store):
    store.write("sunken-crypt", "alpha", minimal_save())
    store.write("sunken-crypt", "beta", minimal_save())
    assert store.list_slots("sunken-crypt") == ["alpha", "beta"]
    assert store.list_slots("other") == []


def test_invalid_slot_name_rejected(store):
    with pytest.raises(SaveError):
        store.path_for("sunken-crypt", "../escape")


def test_read_missing_slot_raises(store):
    with pytest.raises(SaveError):
        store.read("sunken-crypt", "nope")


def test_read_rejects_schema_invalid_save(store, tmp_path):
    path = store.path_for("sunken-crypt", "bad")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"adventure_id": "sunken-crypt"}))  # missing required fields
    with pytest.raises(SaveError) as exc:
        store.read("sunken-crypt", "bad")
    assert exc.value.diagnostics


def test_lock_blocks_concurrent_write(store):
    final = store.path_for("sunken-crypt", "slot1")
    final.parent.mkdir(parents=True, exist_ok=True)
    lock = final.with_name(final.name + ".lock")
    lock.write_text("")  # simulate an in-progress write holding the lock
    with pytest.raises(SaveError):
        store.write("sunken-crypt", "slot1", minimal_save())


def test_no_temp_file_left_behind(store):
    store.write("sunken-crypt", "slot1", minimal_save())
    leftovers = list((store.saves_dir / "sunken-crypt").glob("*.tmp"))
    assert leftovers == []
