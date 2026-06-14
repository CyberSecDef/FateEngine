"""Tests for the CLI/TUI — drive the loop with scripted input/output."""

from pathlib import Path

import pytest

from fateengine.controller.persistence import SaveStore
from fateengine.controller.session import SessionController
from fateengine.loader import AdventureLoader
from fateengine.mcp.server import FateMCPServer
from fateengine.presentation import cli

EXAMPLE = Path(__file__).resolve().parents[1] / "adventures" / "example.json"

WIN_BY_NAME = [
    "Go to the cottage", "Talk to the hermit", "Accept the rusty key",
    "Return to the clearing", "Go to the crypt archway",
    "Unlock the gate and descend", "Take the amulet",
]


def make_controller(tmp_path) -> SessionController:
    adv = AdventureLoader().load_adventure(EXAMPLE)
    engine = FateMCPServer(adv)
    engine.initialize()
    return SessionController(engine, None, SaveStore(tmp_path))


def driver(lines):
    """A (read, write, output) trio: read pops scripted lines, write collects output."""
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


# ---- parser --------------------------------------------------------------

def test_parser_play_resume_list():
    p = build = cli.build_parser()
    assert build.parse_args(["play", "a.json"]).command == "play"
    assert build.parse_args(["resume", "a.json", "slot1"]).slot == "slot1"
    assert build.parse_args(["list"]).command == "list"
    with pytest.raises(SystemExit):
        p.parse_args([])  # subcommand required


# ---- rendering -----------------------------------------------------------

def test_format_turn_shows_prose_and_numbered_actions(tmp_path):
    ctl = make_controller(tmp_path)
    rendered = cli.format_turn(ctl.begin(), "The Sunken Crypt")
    assert "The Sunken Crypt" in rendered
    assert "1. " in rendered                       # numbered actions
    assert "turn 0" in rendered                     # status line


# ---- interactive play ----------------------------------------------------

def test_offline_win_via_action_names(tmp_path):
    ctl = make_controller(tmp_path)
    read, write, out = driver(WIN_BY_NAME)            # EOF after the win -> graceful exit
    code = cli.run_session(ctl, "The Sunken Crypt", read=read, write=write)
    blob = "\n".join(out)
    assert code == 0
    assert "won" in blob.lower()
    assert ctl.mcp.state.outcome == "win"


def test_numbered_selection(tmp_path):
    ctl = make_controller(tmp_path)
    # Find the number of "Go to the cottage" in the opening menu, then pick it.
    opening = ctl.begin()
    num = next(i for i, a in enumerate(opening.available_actions, 1) if a["id"] == "to_cottage")
    read, write, out = driver([str(num), "/quit"])
    cli.run_session(ctl, "T", read=read, write=write)
    assert ctl.mcp.state.location == "cottage"


def test_bad_number_reports_and_continues(tmp_path):
    ctl = make_controller(tmp_path)
    read, write, out = driver(["999", "/quit"])
    cli.run_session(ctl, "T", read=read, write=write)
    assert any("No option with that number" in line for line in out)
    assert ctl.mcp.state.location == "clearing"


def test_help_command(tmp_path):
    ctl = make_controller(tmp_path)
    read, write, out = driver(["/help", "/quit"])
    cli.run_session(ctl, "T", read=read, write=write)
    assert any("/save" in line for line in out)


def test_save_and_load_commands(tmp_path):
    ctl = make_controller(tmp_path)
    read, write, out = driver(["Go to the cottage", "/save mid", "/quit"])
    cli.run_session(ctl, "T", read=read, write=write)
    assert any("Saved to slot 'mid'" in line for line in out)
    # The save really landed and is loadable in a fresh session.
    ctl2 = make_controller(tmp_path)
    read2, write2, out2 = driver(["/load mid", "/quit"])
    cli.run_session(ctl2, "T", read=read2, write=write2)
    assert ctl2.mcp.state.location == "cottage"


def test_unknown_command(tmp_path):
    ctl = make_controller(tmp_path)
    read, write, out = driver(["/frobnicate", "/quit"])
    cli.run_session(ctl, "T", read=read, write=write)
    assert any("Unknown command" in line for line in out)


def test_eof_quits_gracefully(tmp_path):
    ctl = make_controller(tmp_path)
    read, write, out = driver([])                      # immediate EOF
    assert cli.run_session(ctl, "T", read=read, write=write) == 0


def test_restart_command(tmp_path):
    ctl = make_controller(tmp_path)
    read, write, out = driver(["Go to the cottage", "/restart", "/quit"])
    cli.run_session(ctl, "T", read=read, write=write)
    assert ctl.mcp.state.location == "clearing"
    assert ctl.mcp.state.turn_number == 0


# ---- list command --------------------------------------------------------

def test_cmd_list_includes_example(tmp_path, monkeypatch):
    from fateengine.config import AppConfig

    out: list[str] = []
    config = AppConfig(adventures_dir=EXAMPLE.parent)
    cli._cmd_list(config, lambda t="": out.append(str(t)))
    assert any("The Sunken Crypt" in line for line in out)
