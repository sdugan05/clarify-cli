"""Root Typer application: global options and command-group registration."""

from __future__ import annotations

import importlib
from typing import Annotated

import typer

from . import __version__
from .commands import GROUPS
from .config import resolve_settings
from .output import OutputFormat
from .params import parse_csv_list
from .state import AppState

app = typer.Typer(
    name="clarify",
    help=(
        "Command-line interface for the Clarify CRM API.\n\n"
        "Authenticate with `clarify auth login` or set CLARIFY_API_KEY and CLARIFY_WORKSPACE. "
        "Output is JSON when piped and a table on a terminal; override with -o."
    ),
    no_args_is_help=True,
    rich_markup_mode="markdown",
    context_settings={"help_option_names": ["-h", "--help"]},
    pretty_exceptions_enable=False,
)


def _version_callback(value: bool) -> None:
    if value:
        print(f"clarify-cli {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    workspace: Annotated[
        str | None,
        typer.Option("--workspace", "-w", help="Workspace slug [env: CLARIFY_WORKSPACE]."),
    ] = None,
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", help="API key [env: CLARIFY_API_KEY]. Prefer env or config."),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Config profile name [env: CLARIFY_PROFILE]."),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help="API base URL [env: CLARIFY_BASE_URL]."),
    ] = None,
    output: Annotated[
        OutputFormat | None,
        typer.Option("--output", "-o", help="Output format: json, table, ndjson, csv."),
    ] = None,
    fields: Annotated[
        str | None,
        typer.Option("--fields", help="Comma-separated columns for table/csv output."),
    ] = None,
    silent: Annotated[
        bool,
        typer.Option("--silent", help="Suppress in-app and Slack notifications for mutations."),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompts.")] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Log each request to stderr.")
    ] = False,
    debug: Annotated[
        bool, typer.Option("--debug", help="Log request and response bodies to stderr.")
    ] = False,
    timeout: Annotated[
        float, typer.Option("--timeout", min=0.1, help="HTTP timeout in seconds.")
    ] = 30.0,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    settings = resolve_settings(
        api_key=api_key, workspace=workspace, base_url=base_url, profile=profile
    )
    ctx.obj = AppState(
        settings=settings,
        output=output.value if output else None,
        fields=parse_csv_list(fields) or None,
        silent=silent,
        yes=yes,
        verbose=verbose,
        debug=debug,
        timeout=timeout,
    )


def _register_groups() -> None:
    for cli_name, module_name, help_text in GROUPS:
        module = importlib.import_module(f"clarify_cli.commands.{module_name}")
        if hasattr(module, "app"):
            app.add_typer(module.app, name=cli_name, help=help_text)
        else:
            app.command(cli_name, help=help_text)(module.command)


_register_groups()
