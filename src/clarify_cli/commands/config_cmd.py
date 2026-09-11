"""``clarify config``: inspect and edit the config file."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from ..config import (
    PROFILE_KEYS,
    TOP_LEVEL_KEYS,
    config_path,
    load_config,
    mask_secret,
    save_config,
)
from ..errors import UsageError
from ..output import emit, emit_message
from ..state import get_state

app = typer.Typer(no_args_is_help=True)

ProfileOpt = Annotated[
    str | None, typer.Option("--profile", "-p", help="Profile to act on (default: active).")
]


def _validate_key(key: str) -> None:
    if key not in PROFILE_KEYS and key not in TOP_LEVEL_KEYS:
        allowed = ", ".join((*PROFILE_KEYS, *TOP_LEVEL_KEYS))
        raise UsageError(f"Unknown config key {key!r}. Allowed: {allowed}.")


@app.command()
def path() -> None:
    """Print the config file location."""
    print(config_path())


@app.command("list")
def list_config(ctx: typer.Context) -> None:
    """Show every profile (API keys are masked)."""
    state = get_state(ctx)
    cfg = load_config()
    default = cfg.get("default_profile")
    rows: list[dict[str, Any]] = []
    for name, prof in (cfg.get("profiles") or {}).items():
        rows.append(
            {
                "profile": name,
                "default": name == default,
                "workspace": prof.get("workspace"),
                "api_key": mask_secret(prof.get("api_key")),
                "base_url": prof.get("base_url"),
            }
        )
    emit(state, {"data": rows, "meta": {"config_path": str(config_path())}})


@app.command()
def get(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="workspace, api_key, base_url, or default_profile.")],
    profile: ProfileOpt = None,
    reveal: Annotated[bool, typer.Option("--reveal", help="Print the API key unmasked.")] = False,
) -> None:
    """Print one config value."""
    state = get_state(ctx)
    _validate_key(key)
    cfg = load_config()
    if key in TOP_LEVEL_KEYS:
        value = cfg.get(key)
    else:
        name = profile or state.settings.profile
        value = (cfg.get("profiles") or {}).get(name, {}).get(key)
    if value is None:
        raise typer.Exit(code=1)
    if key == "api_key" and not reveal:
        value = mask_secret(str(value))
    print(value)


@app.command("set")
def set_value(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="workspace, api_key, base_url, or default_profile.")],
    value: Annotated[str, typer.Argument(help="Value to store.")],
    profile: ProfileOpt = None,
) -> None:
    """Store one config value in the active profile (or the top level)."""
    state = get_state(ctx)
    _validate_key(key)
    cfg = load_config()
    if key in TOP_LEVEL_KEYS:
        cfg[key] = value
        target = "config"
    else:
        name = profile or state.settings.profile
        cfg.setdefault("profiles", {}).setdefault(name, {})[key] = value
        target = f"profile '{name}'"
    save_config(cfg)
    shown = mask_secret(value) if key == "api_key" else value
    emit_message(f"Set {key} = {shown} in {target}.")


@app.command()
def unset(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="workspace, api_key, base_url, or default_profile.")],
    profile: ProfileOpt = None,
) -> None:
    """Remove one config value."""
    state = get_state(ctx)
    _validate_key(key)
    cfg = load_config()
    if key in TOP_LEVEL_KEYS:
        cfg.pop(key, None)
    else:
        name = profile or state.settings.profile
        (cfg.get("profiles") or {}).get(name, {}).pop(key, None)
    save_config(cfg)
    emit_message(f"Unset {key}.")
