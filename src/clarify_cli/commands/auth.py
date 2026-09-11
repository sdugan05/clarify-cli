"""``clarify auth``: store credentials in a config profile and verify them."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from ..client import ClarifyClient
from ..config import (
    DEFAULT_BASE_URL,
    config_path,
    load_config,
    mask_secret,
    save_config,
)
from ..errors import APIError, ConfigError
from ..output import emit, emit_message
from ..state import get_state

app = typer.Typer(no_args_is_help=True)

VERIFY_PATH = "/users"
VERIFY_PARAMS = [("page[limit]", "1")]


def _verify(base_url: str, api_key: str, workspace: str, timeout: float) -> dict[str, Any]:
    with ClarifyClient(
        base_url=base_url, api_key=api_key, workspace=workspace, timeout=timeout
    ) as c:
        body = c.get(VERIFY_PATH, params=VERIFY_PARAMS)
    meta = body.get("meta") if isinstance(body, dict) else None
    return {"users": meta.get("total_records") if isinstance(meta, dict) else None}


@app.command()
def login(
    ctx: typer.Context,
    workspace: Annotated[
        str | None, typer.Option("--workspace", "-w", help="Workspace slug to store.")
    ] = None,
    api_key: Annotated[
        str | None, typer.Option("--api-key", help="API key to store (prompted if omitted).")
    ] = None,
    profile: Annotated[
        str | None, typer.Option("--profile", "-p", help="Profile to write (default: active).")
    ] = None,
    no_verify: Annotated[
        bool, typer.Option("--no-verify", help="Skip the test request before saving.")
    ] = False,
    make_default: Annotated[
        bool, typer.Option("--default/--no-default", help="Make this profile the default.")
    ] = True,
) -> None:
    """Save an API key and workspace slug to the config file.

    Create a key under Settings → API Keys in Clarify. The slug is the segment
    after `app.clarify.ai/` in your workspace URL.
    """
    state = get_state(ctx)
    settings = state.settings
    name = profile or settings.profile
    slug = workspace or settings.workspace or typer.prompt("Workspace slug")
    key = api_key or settings.api_key or typer.prompt("API key", hide_input=True)
    if not slug or not key:
        raise ConfigError("Both a workspace slug and an API key are required.")

    if not no_verify:
        try:
            _verify(settings.base_url, key, slug, state.timeout)
        except APIError as exc:
            raise ConfigError(
                f"Verification failed: {exc.message}",
                hint=exc.hint or "Use --no-verify to save anyway.",
            ) from exc

    cfg = load_config()
    profiles = cfg.setdefault("profiles", {})
    prof = profiles.setdefault(name, {})
    prof["workspace"] = slug
    prof["api_key"] = key
    if settings.base_url != DEFAULT_BASE_URL:
        prof["base_url"] = settings.base_url
    else:
        prof.pop("base_url", None)
    if make_default or "default_profile" not in cfg:
        cfg["default_profile"] = name
    path = save_config(cfg)
    emit_message(f"Saved profile '{name}' for workspace '{slug}' to {path}")


@app.command()
def status(
    ctx: typer.Context,
    no_verify: Annotated[
        bool, typer.Option("--no-verify", help="Only show the resolved settings.")
    ] = False,
) -> None:
    """Show which workspace and key are active, where they came from, and whether they work."""
    state = get_state(ctx)
    s = state.settings
    info: dict[str, Any] = {
        "profile": s.profile,
        "workspace": s.workspace,
        "workspace_source": s.source("workspace"),
        "api_key": mask_secret(s.api_key),
        "api_key_source": s.source("api_key") if s.api_key else "missing",
        "base_url": s.base_url,
        "config_path": str(config_path()),
    }
    if not no_verify:
        if not s.api_key or not s.workspace:
            info["authenticated"] = False
            info["error"] = "API key or workspace missing."
        else:
            try:
                info.update(_verify(s.base_url, s.api_key, s.workspace, state.timeout))
                info["authenticated"] = True
            except APIError as exc:
                info["authenticated"] = False
                info["error"] = exc.message.splitlines()[0]
    emit(state, info)
    if info.get("authenticated") is False:
        raise typer.Exit(code=3)


@app.command()
def logout(
    ctx: typer.Context,
    profile: Annotated[
        str | None, typer.Option("--profile", "-p", help="Profile to clear (default: active).")
    ] = None,
) -> None:
    """Remove the stored API key from a profile (the workspace slug is kept)."""
    state = get_state(ctx)
    name = profile or state.settings.profile
    cfg = load_config()
    prof = (cfg.get("profiles") or {}).get(name)
    if not prof or "api_key" not in prof:
        emit_message(f"No API key stored for profile '{name}'.")
        return
    prof.pop("api_key", None)
    save_config(cfg)
    emit_message(f"Removed the API key from profile '{name}'.")
