from __future__ import annotations

import json

import httpx

from clarify_cli.config import load_config
from helpers import page, query_pairs


def test_login_verifies_and_saves(invoke, api, isolated_env, monkeypatch):
    monkeypatch.delenv("CLARIFY_API_KEY")
    monkeypatch.delenv("CLARIFY_WORKSPACE")
    route = api.get("/workspaces/myws/users").mock(
        return_value=httpx.Response(200, json=page([], total=4))
    )
    result = invoke("auth", "login", "--workspace", "myws", "--api-key", "secret-key-123456")
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert request.headers["Authorization"] == "api-key secret-key-123456"
    assert query_pairs(request) == [("page[limit]", "1")]
    cfg = load_config(isolated_env / "config.toml")
    assert cfg == {
        "default_profile": "default",
        "profiles": {"default": {"workspace": "myws", "api_key": "secret-key-123456"}},
    }
    assert "Saved profile 'default'" in result.stderr


def test_login_prompts_when_missing(invoke, api, isolated_env, monkeypatch):
    monkeypatch.delenv("CLARIFY_API_KEY")
    monkeypatch.delenv("CLARIFY_WORKSPACE")
    api.get("/workspaces/p/users").mock(return_value=httpx.Response(200, json=page([])))
    result = invoke("auth", "login", "--no-verify", input="p\nk-1234567890\n")
    assert result.exit_code == 0, result.output
    cfg = load_config(isolated_env / "config.toml")
    assert cfg["profiles"]["default"] == {"workspace": "p", "api_key": "k-1234567890"}


def test_login_failure_does_not_save(invoke, api, isolated_env, monkeypatch):
    monkeypatch.delenv("CLARIFY_API_KEY")
    api.get("/workspaces/acme/users").mock(
        return_value=httpx.Response(
            401, json={"errors": [{"status": "401", "detail": "Unauthorized"}]}
        )
    )
    result = invoke("auth", "login", "--workspace", "acme", "--api-key", "bad-key-000000")
    assert result.exit_code == 3
    assert "Verification failed" in result.stderr
    assert not (isolated_env / "config.toml").exists()


def test_login_named_profile_and_custom_base_url(invoke, api, isolated_env):
    with __import__("respx").mock(base_url="https://staging.example/v2") as staging:
        staging.get("/workspaces/acme/users").mock(return_value=httpx.Response(200, json=page([])))
        result = invoke(
            "--base-url",
            "https://staging.example/v2",
            "auth",
            "login",
            "-p",
            "stg",
            "--api-key",
            "stg-key-123456",
        )
    assert result.exit_code == 0, result.output
    cfg = load_config(isolated_env / "config.toml")
    assert cfg["profiles"]["stg"] == {
        "workspace": "acme",
        "api_key": "stg-key-123456",
        "base_url": "https://staging.example/v2",
    }
    assert cfg["default_profile"] == "stg"


def test_status_reports_sources_and_masks_key(invoke, api):
    api.get("/workspaces/acme/users").mock(return_value=httpx.Response(200, json=page([], total=7)))
    result = invoke("auth", "status")
    assert result.exit_code == 0, result.output
    info = json.loads(result.stdout)
    assert info["workspace"] == "acme" and info["workspace_source"] == "env"
    assert info["api_key"] == "********" and info["api_key_source"] == "env"
    assert info["authenticated"] is True and info["users"] == 7
    assert "test-key" not in result.stdout


def test_status_unauthenticated_exit_3(invoke, api):
    api.get("/workspaces/acme/users").mock(
        return_value=httpx.Response(
            401, json={"errors": [{"status": "401", "detail": "Unauthorized"}]}
        )
    )
    result = invoke("auth", "status")
    assert result.exit_code == 3
    assert json.loads(result.stdout)["authenticated"] is False


def test_status_no_verify_without_credentials(invoke, monkeypatch):
    monkeypatch.delenv("CLARIFY_API_KEY")
    result = invoke("auth", "status", "--no-verify")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["api_key_source"] == "missing"


def test_logout_removes_key(invoke, isolated_env):
    from clarify_cli.config import save_config

    save_config(
        {"profiles": {"default": {"workspace": "w", "api_key": "k"}}}, isolated_env / "config.toml"
    )
    result = invoke("auth", "logout")
    assert result.exit_code == 0, result.output
    assert load_config(isolated_env / "config.toml") == {
        "profiles": {"default": {"workspace": "w"}}
    }
    assert invoke("auth", "logout").exit_code == 0
