"""Logging + session identity (requirements_spec.md NFR-007, section 7).

Configures the `fateengine` logger so MCP transitions and LLM prompts/responses
are recorded with a session id, timestamp, and (at DEBUG) before/after state
deltas. Verbosity is configurable; diagnostic mode raises it to DEBUG and mirrors
to stderr.

Logs go to a file under ./logs/ — never stdout — so the MCP stdio protocol and a
clean TUI are never corrupted.
"""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path

from .config import AppConfig

LOGGER_NAME = "fateengine"


def new_session_id() -> str:
    """Short, unique id used to correlate a play/serve session's log records."""
    return uuid.uuid4().hex[:8]


class _SessionDefaultFilter(logging.Filter):
    """Guarantee every record has a `session` attribute so the formatter is safe."""

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "session"):
            record.session = self.session_id
        return True


def configure_logging(config: AppConfig, session_id: str, *, log_dir: Path | None = None) -> None:
    """Set up the `fateengine` logger from config.

    Level is config.log_level, or DEBUG when config.diagnostic_mode. Always writes
    to logs/fateengine-<session>.log; diagnostic mode also streams to stderr.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.propagate = False

    level = logging.DEBUG if config.diagnostic_mode else _level_of(config.log_level)
    logger.setLevel(level)

    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(session)s] %(name)s: %(message)s")
    session_filter = _SessionDefaultFilter(session_id)

    directory = log_dir or Path("logs")
    directory.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(directory / f"fateengine-{session_id}.log")
    file_handler.setFormatter(fmt)
    file_handler.addFilter(session_filter)
    logger.addHandler(file_handler)

    if config.diagnostic_mode:
        stream = logging.StreamHandler(sys.stderr)
        stream.setLevel(logging.DEBUG)
        stream.setFormatter(fmt)
        stream.addFilter(session_filter)
        logger.addHandler(stream)


def _level_of(name: str) -> int:
    return getattr(logging, str(name).upper(), logging.INFO)
