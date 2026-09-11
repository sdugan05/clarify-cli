"""Configuration: TOML config file, environment variables, and precedence.

Precedence for every setting is flag > environment > config profile > default.
"""

from __future__ import annotations

import os
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomli_w

from .errors import ConfigError

DEFAULT_BASE_URL = "https://api.clarify.ai/v1"
DEFAULT_PROFILE = "default"

ENV_API_KEY = "CLARIFY_API_KEY"
ENV_WORKSPACE = "CLARIFY_WORKSPACE"
ENV_BASE_URL = "CLARIFY_BASE_URL"
ENV_PROFILE = "CLARIFY_PROFILE"
ENV_CONFIG = "CLARIFY_CONFIG"

PROFILE_KEYS = ("workspace", "api_key", "base_url")
TOP_LEVEL_KEYS = ("default_profile",)


def config_path() -> Path:
    """Return the config file location, honouring ``CLARIFY_CONFIG`` and XDG."""
    override = os.environ.get(ENV_CONFIG)
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":  # pragma: no cover - platform specific
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "clarify" / "config.toml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load the config file, returning ``{}`` when it does not exist."""
    target = path or config_path()
    if not target.exists():
        return {}
    try:
        with target.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid config file {target}: {exc}") from exc


def save_config(data: Mapping[str, Any], path: Path | None = None) -> Path:
    """Write the config atomically with owner-only permissions."""
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(tomli_w.dumps(dict(data)).encode("utf-8"))
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    return target


def mask_secret(value: str | None) -> str:
    """Show only the ends of a secret, e.g. ``bbb9…0086``."""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]}"


@dataclass(frozen=True)
class Settings:
    """Resolved connection settings plus where each value came from."""

    api_key: str | None
    workspace: str | None
    base_url: str
    profile: str
    sources: Mapping[str, str]

    def source(self, key: str) -> str:
        return self.sources.get(key, "default")


def resolve_settings(
    *,
    api_key: str | None = None,
    workspace: str | None = None,
    base_url: str | None = None,
    profile: str | None = None,
    env: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> Settings:
    """Merge flags, environment, and the config profile into :class:`Settings`."""
    environ = os.environ if env is None else env
    cfg = load_config() if config is None else config

    profile_name = (
        profile or environ.get(ENV_PROFILE) or cfg.get("default_profile") or DEFAULT_PROFILE
    )
    profiles = cfg.get("profiles") or {}
    prof = profiles.get(profile_name) or {}
    if not isinstance(prof, Mapping):
        raise ConfigError(f"Profile '{profile_name}' in the config file must be a table.")

    def pick(
        flag: str | None, env_key: str, cfg_key: str, default: str | None
    ) -> tuple[str | None, str]:
        if flag:
            return flag, "flag"
        env_value = environ.get(env_key)
        if env_value:
            return env_value, "env"
        cfg_value = prof.get(cfg_key)
        if cfg_value:
            return str(cfg_value), f"profile:{profile_name}"
        return default, "default"

    key, key_src = pick(api_key, ENV_API_KEY, "api_key", None)
    ws, ws_src = pick(workspace, ENV_WORKSPACE, "workspace", None)
    url, url_src = pick(base_url, ENV_BASE_URL, "base_url", DEFAULT_BASE_URL)
    assert url is not None
    return Settings(
        api_key=key,
        workspace=ws,
        base_url=url.rstrip("/"),
        profile=profile_name,
        sources={"api_key": key_src, "workspace": ws_src, "base_url": url_src},
    )
