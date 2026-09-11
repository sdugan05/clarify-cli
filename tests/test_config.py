from __future__ import annotations

import os
import stat

import pytest

from clarify_cli.config import (
    DEFAULT_BASE_URL,
    config_path,
    load_config,
    mask_secret,
    resolve_settings,
    save_config,
)
from clarify_cli.errors import ConfigError

CFG = {
    "default_profile": "work",
    "profiles": {
        "work": {"workspace": "cfg-ws", "api_key": "cfg-key"},
        "other": {"workspace": "other-ws", "api_key": "other-key", "base_url": "https://x/v1/"},
    },
}


def test_flag_beats_env_beats_profile():
    env = {"CLARIFY_API_KEY": "env-key", "CLARIFY_WORKSPACE": "env-ws"}
    s = resolve_settings(api_key="flag-key", env=env, config=CFG)
    assert s.api_key == "flag-key" and s.source("api_key") == "flag"
    assert s.workspace == "env-ws" and s.source("workspace") == "env"
    assert s.base_url == DEFAULT_BASE_URL and s.source("base_url") == "default"
    assert s.profile == "work"


def test_profile_values_and_default_profile():
    s = resolve_settings(env={}, config=CFG)
    assert s.api_key == "cfg-key" and s.source("api_key") == "profile:work"
    assert s.workspace == "cfg-ws"


def test_explicit_profile_and_base_url_normalised():
    s = resolve_settings(profile="other", env={}, config=CFG)
    assert s.workspace == "other-ws"
    assert s.base_url == "https://x/v1"  # trailing slash stripped


def test_env_profile_selects_profile():
    s = resolve_settings(env={"CLARIFY_PROFILE": "other"}, config=CFG)
    assert s.profile == "other" and s.api_key == "other-key"


def test_missing_values_are_none():
    s = resolve_settings(env={}, config={})
    assert s.api_key is None and s.workspace is None and s.profile == "default"


def test_bad_profile_shape_raises():
    with pytest.raises(ConfigError):
        resolve_settings(env={}, config={"profiles": {"default": "oops"}})


def test_save_and_load_roundtrip_with_owner_only_permissions(tmp_path):
    path = tmp_path / "nested" / "config.toml"
    save_config(CFG, path)
    assert load_config(path) == CFG
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_load_missing_returns_empty(tmp_path):
    assert load_config(tmp_path / "nope.toml") == {}


def test_load_invalid_toml_raises(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text("not = [valid")
    with pytest.raises(ConfigError):
        load_config(path)


def test_config_path_honours_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CLARIFY_CONFIG", str(tmp_path / "c.toml"))
    assert config_path() == tmp_path / "c.toml"
    monkeypatch.delenv("CLARIFY_CONFIG")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert config_path() == tmp_path / "xdg" / "clarify" / "config.toml"


def test_mask_secret():
    assert mask_secret(None) == ""
    assert mask_secret("short") == "*****"
    assert mask_secret("0123456789abcdef0123456789abcdef") == "0123…cdef"
