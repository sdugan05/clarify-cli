"""Allow ``python -m clarify_cli``."""

from __future__ import annotations

from .main import app

if __name__ == "__main__":  # pragma: no cover
    app()
