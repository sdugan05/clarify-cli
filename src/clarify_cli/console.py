"""Shared rich consoles. Results go to stdout; diagnostics go to stderr."""

from __future__ import annotations

from rich.console import Console

console = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)
