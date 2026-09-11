from __future__ import annotations

from clarify_cli import __version__
from clarify_cli.main import IMPORT_ERRORS


def test_every_command_group_imports():
    assert IMPORT_ERRORS == {}


def test_version(invoke):
    result = invoke("--version")
    assert result.exit_code == 0
    assert result.stdout.strip() == f"clarify-cli {__version__}"


def test_help_lists_groups(invoke):
    result = invoke("--help")
    assert result.exit_code == 0
    for group in ("auth", "config", "api", "records", "lists", "schemas", "users", "settings"):
        assert group in result.stdout


def test_missing_api_key_is_exit_3(invoke, monkeypatch):
    monkeypatch.delenv("CLARIFY_API_KEY")
    result = invoke("users", "list")
    assert result.exit_code == 3
    assert "No API key configured" in result.stderr
    assert "clarify auth login" in result.stderr


def test_missing_workspace_is_exit_3(invoke, monkeypatch):
    monkeypatch.delenv("CLARIFY_WORKSPACE")
    result = invoke("users", "list")
    assert result.exit_code == 3
    assert "No workspace configured" in result.stderr


def test_invalid_output_format_is_usage_error(invoke):
    result = invoke("-o", "xml", "users", "list")
    assert result.exit_code == 2


def test_api_errors_render_as_plain_lines(invoke, api):
    import httpx

    api.get("/workspaces/acme/users/nope").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "User not found"}]}
        )
    )
    result = invoke("users", "get", "nope")
    assert result.exit_code == 4
    assert result.stderr.startswith("Error: HTTP 404 from GET ")
    assert "User not found" in result.stderr
    assert "╭" not in result.stderr  # no rich panel around our errors
