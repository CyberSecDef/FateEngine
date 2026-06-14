"""Tests for logging, diagnostics, autosave, and the map summary."""

import logging
from pathlib import Path

import pytest

from fateengine.config import AppConfig
from fateengine.controller.persistence import SaveStore
from fateengine.controller.session import SessionController
from fateengine.loader import AdventureLoader
from fateengine.mcp.server import FateMCPServer
from fateengine.observability import configure_logging, new_session_id
from fateengine.presentation import cli

EXAMPLE = Path(__file__).resolve().parents[1] / "adventures" / "example.json"


@pytest.fixture(autouse=True)
def _reset_logger():
    yield
    logger = logging.getLogger("fateengine")
    for h in list(logger.handlers):
        if not isinstance(h, logging.NullHandler):
            logger.removeHandler(h)
            h.close()


def make_controller(tmp_path, llm=None, session_id="testsess") -> SessionController:
    eng = FateMCPServer(AdventureLoader().load_adventure(EXAMPLE))
    eng.initialize()
    return SessionController(eng, llm, SaveStore(tmp_path), session_id=session_id)


def driver(lines):
    it = iter(lines)
    out: list[str] = []

    def read(prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    def write(text=""):
        out.append(str(text))

    return read, write, out


# ---- session id ----------------------------------------------------------


def test_new_session_id_unique():
    assert new_session_id() != new_session_id()
    assert len(new_session_id()) == 8


# ---- logging (NFR-007) ---------------------------------------------------


def test_transition_is_logged_with_session_and_delta(tmp_path):
    cfg = AppConfig()
    cfg.log_level = "DEBUG"
    configure_logging(cfg, "abc123", log_dir=tmp_path)
    ctl = make_controller(tmp_path, session_id="abc123")
    ctl.take_turn("Go to the cottage")

    log_text = (tmp_path / "fateengine-abc123.log").read_text()
    assert "abc123" in log_text  # session id present
    assert "to_cottage" in log_text  # the action
    assert "delta=" in log_text  # before/after delta (DEBUG)


def test_diagnostic_mode_streams_to_stderr(tmp_path, capsys):
    cfg = AppConfig()
    cfg.diagnostic_mode = True
    configure_logging(cfg, "diag1", log_dir=tmp_path)
    ctl = make_controller(tmp_path, session_id="diag1")
    ctl.take_turn("Go to the cottage")
    assert "to_cottage" in capsys.readouterr().err


# ---- diagnostic snapshot -------------------------------------------------


def test_debug_snapshot_contains_state(tmp_path):
    ctl = make_controller(tmp_path)
    ctl.take_turn("Go to the cottage")
    snap = ctl.debug_snapshot()
    assert "session: testsess" in snap
    assert "cottage" in snap
    assert "recent history" in snap


# ---- autosave on shutdown ------------------------------------------------


def test_autosave_on_quit_is_resumable(tmp_path):
    ctl = make_controller(tmp_path)
    read, write, out = driver(["Go to the cottage", "/quit"])
    cli.run_session(ctl, "T", read=read, write=write)
    assert any("autosaved" in line for line in out)
    assert "autosave" in ctl.saves.list_slots(ctl.mcp.adventure.id)

    # A fresh session can resume from the autosave.
    ctl2 = make_controller(tmp_path)
    ctl2.load("autosave")
    assert ctl2.mcp.state.location == "cottage"


def test_no_autosave_after_game_ends(tmp_path):
    ctl = make_controller(tmp_path)
    win = [
        "to_cottage",
        "talk_hermit",
        "take_key",
        "leave_cottage",
        "to_crypt",
        "enter_vault",
        "take_amulet",
    ]
    read, write, out = driver(win)  # EOF after the win
    cli.run_session(ctl, "T", read=read, write=write)
    assert "autosave" not in ctl.saves.list_slots(ctl.mcp.adventure.id)


# ---- map summary (interface §5) ------------------------------------------


def test_map_summary_lists_locations_and_marks_current(tmp_path):
    ctl = make_controller(tmp_path)
    text = cli._map_summary(ctl)
    assert "Forest Clearing" in text
    assert "Drowned Vault" in text
    assert "you are here" in text
    assert "[locked]" in text  # the gated vault connection
