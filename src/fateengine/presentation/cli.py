"""CLI/TUI entry point (console script: `fateengine`).

Renders location prose + a status panel, captures action selection (by number or
free text) and slash-commands (/save /load /restart /quit ...), and drives the
SessionController turn loop. Plays fully offline; an LLM is optional.

The loop's IO is injectable (`read` / `write`) so it can be driven in tests.
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path
from typing import Callable

from ..config import AppConfig
from ..controller.persistence import SaveError, SaveStore
from ..controller.session import SessionController, TurnResult
from ..loader import AdventureLoader, LoadError
from ..mcp.server import FateMCPServer

WIDTH = 78
PROMPT = "\n> "
DEFAULT_SLOT = "quicksave"

HELP = """\
Commands:
  <number>        choose an action by its number
  <text>          or just describe what you want to do
  /save [slot]    save the game (default slot: quicksave)
  /load [slot]    load a saved game
  /saves          list save slots
  /look           re-read the current location
  /status         show the status panel
  /restart        restart the adventure from the beginning
  /help           show this help
  /quit           leave the game"""


# --- styling --------------------------------------------------------------

def _style(text: str, code: str, color: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if color else text


def format_turn(result: TurnResult, title: str, *, color: bool = False) -> str:
    """Render a TurnResult into the terminal screen text."""
    lines: list[str] = []
    rule = "─" * WIDTH
    lines.append(_style(rule, "2", color))
    lines.append(_style(title, "1", color))
    lines.append(_style(rule, "2", color))

    for diag in result.diagnostics:
        lines.append(_style(f"! {diag}", "33", color))
    if result.diagnostics:
        lines.append("")

    lines.append(textwrap.fill(result.prose, width=WIDTH))
    lines.append("")
    lines.append(_style(_status_line(result.status_summary), "36", color))

    if not result.ended:
        lines.append("")
        lines.append(_style("What do you do?", "1", color))
        for i, action in enumerate(result.available_actions, 1):
            lines.append(f"  {i}. {action['name']}")
    return "\n".join(lines)


def _status_line(status: dict) -> str:
    inv = ", ".join(status.get("inventory", [])) or "empty"
    quests = ", ".join(status.get("active_quests", [])) or "none"
    return (
        f"[ {status.get('location', '?')} | turn {status.get('turn', 0)} "
        f"| inventory: {inv} | quests: {quests} ]"
    )


# --- the loop -------------------------------------------------------------

def run_session(
    controller: SessionController,
    title: str,
    *,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
    color: bool = False,
) -> int:
    """Drive the interactive turn loop until the player quits. Returns exit code."""
    result = controller.begin()
    while True:
        write(format_turn(result, title, color=color))
        if result.ended:
            write(_style("\nThe adventure has ended. /restart or /quit.", "1", color))

        try:
            raw = read(PROMPT).strip()
        except (EOFError, KeyboardInterrupt):
            write("\nFarewell.")
            return 0

        if not raw:
            continue

        if raw.startswith("/"):
            done, new_result, message = _command(controller, raw[1:], color=color)
            if message:
                write(message)
            if new_result is not None:
                result = new_result
            if done:
                return 0
            continue

        if result.ended:
            write("The adventure is over — use /restart or /quit.")
            continue

        # Numbered selection -> translate to the chosen action's id.
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(result.available_actions):
                raw = result.available_actions[idx]["id"]
            else:
                write("No option with that number.")
                continue

        result = controller.take_turn(raw)


def _command(controller: SessionController, line: str, *, color: bool):
    """Handle a /command. Returns (should_quit, new_TurnResult_or_None, message)."""
    parts = line.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("quit", "exit", "q"):
        return True, None, "Farewell."
    if cmd in ("help", "h", "?"):
        return False, None, HELP
    if cmd == "save":
        slot = arg or DEFAULT_SLOT
        try:
            controller.save(slot)
            return False, None, _style(f"Saved to slot {slot!r}.", "32", color)
        except SaveError as exc:
            return False, None, _style(f"Save failed: {exc}", "31", color)
    if cmd == "load":
        slot = arg or DEFAULT_SLOT
        try:
            return False, controller.load(slot), _style(f"Loaded slot {slot!r}.", "32", color)
        except SaveError as exc:
            return False, None, _style(f"Load failed: {exc}", "31", color)
    if cmd == "saves":
        slots = controller.saves.list_slots(controller.mcp.adventure.id)
        return False, None, ("Save slots: " + (", ".join(slots) if slots else "(none)"))
    if cmd == "restart":
        return False, controller.restart(), _style("Adventure restarted.", "32", color)
    if cmd == "status":
        return False, None, _status_line(controller._status_summary())
    if cmd == "look":
        desc = controller.mcp.describe_location()
        exits = ", ".join(e.get("to_name", e["to"]) for e in desc["exits"]) or "none"
        return False, None, f"{desc['base_prose']}\nExits: {exits}"
    return False, None, f"Unknown command: /{cmd} (try /help)"


# --- entry point ----------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fateengine", description="Play a FateEngine adventure.")
    sub = parser.add_subparsers(dest="command", required=True)

    play = sub.add_parser("play", help="Start a new adventure.")
    play.add_argument("adventure", help="Path to an adventure JSON file.")
    play.add_argument("--llm", metavar="PROVIDER", default=None,
                      help="Enable LLM narration via the named provider (default: offline).")

    resume = sub.add_parser("resume", help="Resume from a save slot.")
    resume.add_argument("adventure", help="Path to the adventure JSON file.")
    resume.add_argument("slot", help="Save slot name.")
    resume.add_argument("--llm", metavar="PROVIDER", default=None)

    sub.add_parser("list", help="List available adventures.")
    return parser


def _cmd_list(config: AppConfig, write: Callable[[str], None]) -> int:
    loader = AdventureLoader()
    found = loader.list_adventures(config.adventures_dir)
    if not found:
        write(f"No adventures found in {config.adventures_dir}/")
        return 0
    write(f"Adventures in {config.adventures_dir}/:")
    for path in found:
        try:
            adv = loader.load_adventure(path)
            write(f"  {path.name:30}  {adv.metadata['title']}")
        except LoadError:
            write(f"  {path.name:30}  (invalid)")
    return 0


def _maybe_provider(name: str | None, config: AppConfig, write: Callable[[str], None]):
    if not name:
        return None
    from ..llm.provider import get_provider

    config.llm.provider = name
    try:
        return get_provider(config.llm)
    except (NotImplementedError, Exception) as exc:  # noqa: BLE001 - degrade gracefully
        write(f"! LLM provider {name!r} unavailable ({exc}); playing offline.")
        return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = AppConfig()
    color = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

    if args.command == "list":
        return _cmd_list(config, print)

    loader = AdventureLoader()
    try:
        adventure = loader.load_adventure(Path(args.adventure))
    except LoadError as exc:
        print(exc, file=sys.stderr)
        return 1

    engine = FateMCPServer(adventure)
    engine.initialize()
    controller = SessionController(
        engine,
        _maybe_provider(args.llm, config, print),
        SaveStore(config.saves_dir),
        config,
    )

    if args.command == "resume":
        try:
            controller.load(args.slot)
        except SaveError as exc:
            print(exc, file=sys.stderr)
            return 1

    return run_session(controller, adventure.metadata["title"], color=color)


if __name__ == "__main__":
    raise SystemExit(main())
