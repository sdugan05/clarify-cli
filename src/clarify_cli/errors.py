"""Error types and process exit codes.

All errors derive from :class:`click.ClickException` so Click/Typer print them
and exit with ``exit_code`` both when run as a program and under ``CliRunner``.
"""

from __future__ import annotations

from typing import Any

from rich.markup import escape

try:  # typer >= 0.20 vendors click under typer._click
    from typer._click.exceptions import ClickException
except ImportError:  # pragma: no cover - older typer versions use the click package
    from click import ClickException

EXIT_OK = 0
EXIT_GENERAL = 1
EXIT_USAGE = 2
EXIT_AUTH = 3
EXIT_NOT_FOUND = 4
EXIT_RATE_LIMITED = 5


class ClarifyError(ClickException):
    """Base class for every error the CLI reports."""

    exit_code = EXIT_GENERAL

    def __init__(self, message: str, *, exit_code: int | None = None, hint: str | None = None):
        super().__init__(message)
        if exit_code is not None:
            self.exit_code = exit_code
        self.hint = hint

    def format_message(self) -> str:
        text = self.message
        if self.hint:
            text += f"\nHint: {self.hint}"
        return text

    def show(self, file: Any = None) -> None:
        from .console import err_console

        err_console.print(f"[bold red]Error:[/] {escape(self.format_message())}")


class ConfigError(ClarifyError):
    """Missing or invalid configuration (API key, workspace, config file)."""

    exit_code = EXIT_AUTH


class UsageError(ClarifyError):
    """The command was invoked incorrectly (bad flag values, invalid JSON, ...)."""

    exit_code = EXIT_USAGE


class APIError(ClarifyError):
    """A non-2xx response from the Clarify API, carrying its JSON:API ``errors``."""

    def __init__(
        self,
        status: int,
        errors: list[dict[str, Any]],
        *,
        method: str,
        url: str,
        raw: str = "",
    ):
        self.status = status
        self.errors = errors
        self.method = method.upper()
        self.url = url
        self.raw = raw
        super().__init__(
            self._summary(),
            exit_code=exit_code_for_status(status),
            hint=self._hint(),
        )

    def _summary(self) -> str:
        lines: list[str] = []
        for err in self.errors:
            title = err.get("title")
            detail = err.get("detail")
            pointer = (err.get("source") or {}).get("pointer") if isinstance(err, dict) else None
            text = detail or title or "Unknown error"
            if title and detail and title not in detail:
                text = f"{title}: {detail}"
            if pointer and pointer not in text:
                text += f" (at {pointer})"
            lines.append(str(text))
        if not lines:
            snippet = self.raw.strip()
            lines.append(snippet[:500] if snippet else "Request failed")
        return f"HTTP {self.status} from {self.method} {self.url}\n  " + "\n  ".join(lines)

    def _hint(self) -> str | None:
        details = " ".join(str(e.get("detail") or "") for e in self.errors)
        if self.status == 401:
            return (
                "Clarify expects `Authorization: api-key <key>`. Check CLARIFY_API_KEY "
                "or run `clarify auth login`."
            )
        if self.status == 403:
            return (
                "The key lacks permission. Access-delegation endpoints require a "
                "user-backed (Personal) API key."
            )
        if self.status == 404 and "workspace" in details.lower():
            return "Check the workspace slug (--workspace or CLARIFY_WORKSPACE)."
        if self.status == 409:
            return "Another request is modifying the schema; retry in a moment."
        if self.status == 429:
            return "Rate limited (3000 requests/min per workspace per endpoint). Retry later."
        return None


def exit_code_for_status(status: int) -> int:
    """Map an HTTP status to the CLI's exit code."""
    if status in (401, 403):
        return EXIT_AUTH
    if status == 404:
        return EXIT_NOT_FOUND
    if status == 429:
        return EXIT_RATE_LIMITED
    return EXIT_GENERAL
