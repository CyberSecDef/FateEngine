"""CLI/TUI entry point (console script: `fateengine`).

Renders location prose and a status summary panel, captures action selection or
free text, and exposes save / load / restart / exit commands (section 5).
Wires together: AdventureLoader -> FateMCPServer -> LLMProvider -> SessionController.
"""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fateengine", description="Play a FateEngine adventure.")
    sub = parser.add_subparsers(dest="command", required=True)

    play = sub.add_parser("play", help="Start a new adventure.")
    play.add_argument("adventure", help="Path to an adventure JSON file.")

    resume = sub.add_parser("resume", help="Resume from a save slot.")
    resume.add_argument("adventure", help="Path to the adventure JSON file.")
    resume.add_argument("slot", help="Save slot name.")

    sub.add_parser("list", help="List available adventures.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Console entry point. Stub — dispatches to the SessionController turn loop."""
    args = build_parser().parse_args(argv)
    raise NotImplementedError(f"command {args.command!r} not yet implemented")


if __name__ == "__main__":
    raise SystemExit(main())
