from __future__ import annotations

import json

from clarify_cli.config import load_config


def test_config_path(invoke, isolated_env):
    result = invoke("config", "path")
    assert result.exit_code == 0
    assert result.stdout.strip() == str(isolated_env / "config.toml")


def test_config_set_get_list_unset(invoke, isolated_env):
    assert invoke("config", "set", "workspace", "ws1").exit_code == 0
    assert invoke("config", "set", "api_key", "abcdefghijkl").exit_code == 0
    assert invoke("config", "set", "workspace", "ws2", "-p", "second").exit_code == 0
    assert invoke("config", "set", "default_profile", "second").exit_code == 0
    cfg = load_config(isolated_env / "config.toml")
    assert cfg == {
        "default_profile": "second",
        "profiles": {
            "default": {"workspace": "ws1", "api_key": "abcdefghijkl"},
            "second": {"workspace": "ws2"},
        },
    }

    assert invoke("config", "get", "workspace", "-p", "default").stdout.strip() == "ws1"
    assert (
        invoke("config", "get", "workspace").stdout.strip() == "ws2"
    )  # default profile now 'second'
    assert invoke("config", "get", "api_key", "-p", "default").stdout.strip() == "abcd…ijkl"
    assert (
        invoke("config", "get", "api_key", "-p", "default", "--reveal").stdout.strip()
        == "abcdefghijkl"
    )
    assert invoke("config", "get", "base_url").exit_code == 1

    listing = json.loads(invoke("config", "list").stdout)
    rows = {r["profile"]: r for r in listing["data"]}
    assert rows["second"]["default"] is True and rows["default"]["api_key"] == "abcd…ijkl"

    assert invoke("config", "unset", "api_key", "-p", "default").exit_code == 0
    assert invoke("config", "unset", "default_profile").exit_code == 0
    cfg = load_config(isolated_env / "config.toml")
    assert "api_key" not in cfg["profiles"]["default"] and "default_profile" not in cfg


def test_config_rejects_unknown_key(invoke):
    assert invoke("config", "set", "colour", "blue").exit_code == 2
    assert invoke("config", "get", "colour").exit_code == 2
