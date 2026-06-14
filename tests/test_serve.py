"""Tests for the MCP serve path (tool selection + registration + CLI dispatch)."""

from pathlib import Path

import pytest

from fateengine.loader import AdventureLoader
from fateengine.mcp import tools
from fateengine.mcp.server import FateMCPServer
from fateengine.presentation import cli

EXAMPLE = Path(__file__).resolve().parents[1] / "adventures" / "example.json"


@pytest.fixture
def engine() -> FateMCPServer:
    eng = FateMCPServer(AdventureLoader().load_adventure(EXAMPLE))
    eng.initialize()
    return eng


class FakeFastMCP:
    """Records add_tool calls so we can assert the exposed surface without the SDK."""

    def __init__(self):
        self.tools: dict[str, object] = {}
        self.ran = False

    def add_tool(self, fn, name=None, description=None, **_):
        self.tools[name] = fn

    def run(self, *a, **k):
        self.ran = True


# ---- tool selection ------------------------------------------------------

def test_read_only_by_default(engine):
    names = set(tools.tool_methods(engine))
    assert names == set(tools.READ_TOOLS)
    assert "apply_action" not in names


def test_allow_write_adds_mutating_tools(engine):
    names = set(tools.tool_methods(engine, allow_write=True))
    assert names == set(tools.READ_TOOLS) | set(tools.WRITE_TOOLS)
    assert "apply_action" in names


# ---- registration via injected factory -----------------------------------

def test_build_server_registers_read_tools(engine):
    fake = FakeFastMCP()
    tools.build_server(engine, factory=lambda: fake)
    assert set(fake.tools) == set(tools.READ_TOOLS)


def test_build_server_registers_write_tools_when_allowed(engine):
    fake = FakeFastMCP()
    tools.build_server(engine, allow_write=True, factory=lambda: fake)
    assert "apply_action" in fake.tools


def test_registered_read_tool_is_callable_and_bound(engine):
    fake = FakeFastMCP()
    tools.build_server(engine, factory=lambda: fake)
    # The registered get_state is the engine's bound method and works.
    assert fake.tools["get_state"]()["location"] == "clearing"


def test_registered_write_tool_drives_the_engine(engine):
    fake = FakeFastMCP()
    tools.build_server(engine, allow_write=True, factory=lambda: fake)
    fake.tools["apply_action"]("to_cottage")
    assert engine.state.location == "cottage"


# ---- CLI dispatch --------------------------------------------------------

def test_parser_has_serve():
    args = cli.build_parser().parse_args(["serve", "a.json", "--write"])
    assert args.command == "serve" and args.write is True


def test_cli_serve_invokes_serve_stdio(monkeypatch, capsys):
    captured = {}

    def fake_serve(self, *, allow_write=False):
        captured["allow_write"] = allow_write

    monkeypatch.setattr(FateMCPServer, "serve_stdio", fake_serve)
    code = cli.main(["serve", str(EXAMPLE), "--write"])
    assert code == 0
    assert captured == {"allow_write": True}
    assert "MCP server" in capsys.readouterr().err   # status goes to stderr


def test_cli_serve_resume_bad_slot_errors(monkeypatch):
    monkeypatch.setattr(FateMCPServer, "serve_stdio", lambda self, **k: None)
    code = cli.main(["serve", str(EXAMPLE), "--slot", "nonexistent"])
    assert code == 1
