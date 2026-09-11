"""Per-invocation state shared by every command via ``ctx.obj``."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

import typer

from .client import ClarifyClient
from .config import Settings
from .errors import ConfigError, UsageError


@dataclass
class AppState:
    settings: Settings
    output: str | None = None
    fields: list[str] | None = None
    silent: bool = False
    yes: bool = False
    verbose: bool = False
    debug: bool = False
    timeout: float = 30.0
    _client: ClarifyClient | None = field(default=None, repr=False)

    def client(self) -> ClarifyClient:
        """Return the shared API client, validating credentials on first use."""
        if self._client is None:
            settings = self.settings
            if not settings.api_key:
                raise ConfigError(
                    "No API key configured.",
                    hint="Set CLARIFY_API_KEY, pass --api-key, or run `clarify auth login`.",
                )
            if not settings.workspace:
                raise ConfigError(
                    "No workspace configured.",
                    hint="Set CLARIFY_WORKSPACE, pass --workspace, or run `clarify auth login`.",
                )
            self._client = ClarifyClient(
                base_url=settings.base_url,
                api_key=settings.api_key,
                workspace=settings.workspace,
                timeout=self.timeout,
                verbose=self.verbose,
                debug=self.debug,
            )
        return self._client

    def confirm(self, message: str) -> None:
        """Ask before a destructive action unless ``--yes`` was given.

        Without a TTY the command refuses instead of hanging on a prompt.
        """
        if self.yes:
            return
        if not sys.stdin.isatty():
            raise UsageError(
                f"Refusing to continue without confirmation: {message}",
                hint="Pass --yes to skip the prompt in scripts.",
            )
        if not typer.confirm(message, default=False):
            raise UsageError("Aborted.")


def get_state(ctx: typer.Context) -> AppState:
    state = ctx.find_object(AppState)
    if state is None:  # pragma: no cover - only if a command bypasses the root callback
        raise RuntimeError("AppState missing; commands must run under the root app.")
    return state
