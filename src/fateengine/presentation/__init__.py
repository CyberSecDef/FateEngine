"""Presentation Layer — captures input and renders prose + status.

v1 target is a CLI/TUI (requirements_spec.md section 5). The presentation layer
only invokes SessionController methods; it never touches game state directly.
Alternative front-ends (web, etc.) plug in at this seam.
"""

from .cli import main

__all__ = ["main"]
