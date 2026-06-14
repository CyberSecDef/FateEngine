"""Tests for GameState path resolution, transactions, and diffing."""

from fateengine.mcp.state import GameState


def test_resolve_scalar_and_containers():
    s = GameState(location="hall", inventory={"gold": 9})
    assert s.resolve_path("location") == "hall"
    assert s.resolve_path("inventory") == {"gold": 9}
    assert s.resolve_path("inventory.gold") == 9
    assert s.resolve_path("inventory.missing") is None
    assert s.resolve_path("nonsense.path") is None


def test_transaction_commits_on_success():
    s = GameState(location="a")
    with s.transaction():
        s.location = "b"
        s.inventory["gold"] = 3
    assert s.location == "b"
    assert s.inventory == {"gold": 3}


def test_transaction_rolls_back_nested_mutation():
    s = GameState(location="a", inventory={"gold": 1})
    try:
        with s.transaction():
            s.location = "b"
            s.inventory["gold"] = 99
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert s.location == "a"
    assert s.inventory == {"gold": 1}  # deep snapshot restored the nested dict


def test_diff_from_reports_changed_fields_only():
    before = GameState(location="a", turn_number=1, status={"x": 1})
    after = GameState(location="b", turn_number=1, status={"x": 1, "y": 2})
    delta = after.diff_from(before)
    assert "location" in delta and delta["location"] == {"from": "a", "to": "b"}
    assert "status" in delta
    assert "turn_number" not in delta  # unchanged
    assert "history_log" not in delta  # never diffed
