from __future__ import annotations

import csv
import io
import json

import httpx
import pytest

from clarify_cli.commands import settings
from clarify_cli.errors import UsageError
from helpers import json_body, query_pairs

WS = "/workspaces/acme"

ALL_SETTINGS = {
    "orgDescription": "Acme Corp builds industrial hardware and software.",
    "dealDetectionEnabled": True,
    "fiscalYearOffset": 3,
    "companyEmailDomains": ["acme.com", "acme.io"],
    "ingestionRules": {"action": "block", "items": []},
    "closedWonDealStage": None,
}


def test_operations_manifest_covers_every_settings_operation():
    assert settings.OPERATIONS == {
        "readAllWorkspaceSettings": "list",
        "readWorkspaceSettings": "get",
        "writeWorkspaceSetting": "set",
        "deleteWorkspaceSetting": "reset",
    }


def test_setting_keys_match_spec_enum():
    assert len(settings.SETTING_KEYS) == 43
    assert len(set(settings.SETTING_KEYS)) == len(settings.SETTING_KEYS)
    assert "orgDescription" in settings.SETTING_KEYS
    assert "fiscalYearOffset" in settings.SETTING_KEYS


# -- helpers ---------------------------------------------------------------


def test_normalize_key_accepts_canonical_and_case_insensitive():
    assert settings.normalize_key("orgDescription") == "orgDescription"
    assert settings.normalize_key("orgdescription") == "orgDescription"
    assert settings.normalize_key("DEALDETECTIONENABLED") == "dealDetectionEnabled"


def test_normalize_key_rejects_unknown_with_suggestions():
    with pytest.raises(UsageError) as info:
        settings.normalize_key("orgDescriptin")
    assert "Unknown setting key 'orgDescriptin'" in info.value.message
    assert "Did you mean orgDescription" in info.value.hint
    assert "Allowed keys:" in info.value.hint
    assert "fiscalYearOffset" in info.value.hint


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("true", True),
        ("false", False),
        ("42", 42),
        ("null", None),
        ("plain text", "plain text"),
        ('"42"', "42"),
        ('["a","b"]', ["a", "b"]),
        ('{"action": "allow"}', {"action": "allow"}),
    ],
)
def test_parse_value_coerces_scalars(text, expected):
    assert settings.parse_value(text) == expected


def test_parse_value_reads_file(tmp_path):
    path = tmp_path / "value.json"
    path.write_text('{"action": "block", "items": []}', encoding="utf-8")
    assert settings.parse_value(f"@{path}") == {"action": "block", "items": []}


def test_as_rows_reshapes_mapping():
    assert settings.as_rows({"a": 1, "b": [2]}) == {
        "data": [{"key": "a", "value": 1}, {"key": "b", "value": [2]}]
    }
    assert settings.as_rows(["not", "a", "dict"]) == ["not", "a", "dict"]


# -- list ------------------------------------------------------------------


def test_settings_list_json_is_verbatim(invoke, api):
    route = api.get(f"{WS}/settings").mock(return_value=httpx.Response(200, json=ALL_SETTINGS))
    result = invoke("settings", "list")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == ALL_SETTINGS
    request = route.calls.last.request
    assert request.method == "GET"
    assert request.url.path == f"/v1{WS}/settings"
    assert query_pairs(request) == []


def test_settings_list_table_shows_key_value_rows(invoke, api):
    api.get(f"{WS}/settings").mock(return_value=httpx.Response(200, json=ALL_SETTINGS))
    result = invoke("-o", "table", "settings", "list")
    assert result.exit_code == 0, result.output
    assert "key" in result.stdout and "value" in result.stdout
    assert "orgDescription" in result.stdout
    assert "fiscalYearOffset" in result.stdout and "3" in result.stdout


def test_settings_list_csv_rows(invoke, api):
    api.get(f"{WS}/settings").mock(return_value=httpx.Response(200, json=ALL_SETTINGS))
    result = invoke("-o", "csv", "settings", "list")
    assert result.exit_code == 0, result.output
    rows = list(csv.reader(io.StringIO(result.stdout)))
    assert rows[0] == ["key", "value"]
    assert rows[1] == ["orgDescription", "Acme Corp builds industrial hardware and software."]
    assert rows[2] == ["dealDetectionEnabled", "true"]
    assert rows[3] == ["fiscalYearOffset", "3"]
    assert rows[4] == ["companyEmailDomains", '["acme.com","acme.io"]']
    assert rows[6] == ["closedWonDealStage", ""]


def test_settings_list_ndjson_rows(invoke, api):
    api.get(f"{WS}/settings").mock(return_value=httpx.Response(200, json=ALL_SETTINGS))
    result = invoke("-o", "ndjson", "settings", "list")
    assert result.exit_code == 0, result.output
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert lines[0] == {"key": "orgDescription", "value": ALL_SETTINGS["orgDescription"]}
    assert len(lines) == len(ALL_SETTINGS)


def test_settings_list_forbidden_exit_3(invoke, api):
    api.get(f"{WS}/settings").mock(
        return_value=httpx.Response(
            403, json={"errors": [{"status": "403", "detail": "Forbidden"}]}
        )
    )
    result = invoke("settings", "list")
    assert result.exit_code == 3
    assert "HTTP 403" in result.stderr


# -- get -------------------------------------------------------------------


def test_settings_get(invoke, api):
    route = api.get(f"{WS}/settings/orgDescription").mock(
        return_value=httpx.Response(200, json={"value": "Acme Corp"})
    )
    result = invoke("settings", "get", "orgDescription")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"value": "Acme Corp"}
    request = route.calls.last.request
    assert request.method == "GET"
    assert request.url.path == f"/v1{WS}/settings/orgDescription"
    assert query_pairs(request) == []


def test_settings_get_normalises_key_case(invoke, api):
    route = api.get(f"{WS}/settings/dealDetectionEnabled").mock(
        return_value=httpx.Response(200, json={"value": True})
    )
    result = invoke("settings", "get", "dealdetectionenabled")
    assert result.exit_code == 0, result.output
    assert route.called


def test_settings_get_unknown_key_exit_2_lists_keys(invoke, api):
    route = api.get(f"{WS}/settings/bogus").mock(return_value=httpx.Response(200, json={}))
    result = invoke("settings", "get", "bogus")
    assert result.exit_code == 2
    assert "Unknown setting key 'bogus'" in result.stderr
    assert "Allowed keys:" in result.stderr and "orgDescription" in result.stderr
    assert not route.called


def test_settings_get_not_found_exit_4(invoke, api):
    api.get(f"{WS}/settings/orgDescription").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Workspace not found"}]}
        )
    )
    result = invoke("settings", "get", "orgDescription")
    assert result.exit_code == 4
    assert "Workspace not found" in result.stderr


# -- set -------------------------------------------------------------------


def test_settings_set_string(invoke, api):
    route = api.post(f"{WS}/settings").mock(return_value=httpx.Response(201))
    result = invoke("settings", "set", "orgDescription", "Acme builds industrial hardware.")
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "orgDescription updated" in result.stderr
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"/v1{WS}/settings"
    assert query_pairs(request) == []
    assert json_body(request) == {
        "key": "orgDescription",
        "value": "Acme builds industrial hardware.",
    }


def test_settings_set_boolean_and_silent(invoke, api):
    route = api.post(f"{WS}/settings").mock(return_value=httpx.Response(201, json={}))
    result = invoke("--silent", "settings", "set", "dealDetectionEnabled", "true")
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    request = route.calls.last.request
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {"key": "dealDetectionEnabled", "value": True}


def test_settings_set_number(invoke, api):
    route = api.post(f"{WS}/settings").mock(return_value=httpx.Response(201))
    result = invoke("settings", "set", "fiscalYearOffset", "3")
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {"key": "fiscalYearOffset", "value": 3}


def test_settings_set_json_array_inline(invoke, api):
    route = api.post(f"{WS}/settings").mock(return_value=httpx.Response(201))
    result = invoke("settings", "set", "companyEmailDomains", '["acme.com", "acme.io"]')
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "key": "companyEmailDomains",
        "value": ["acme.com", "acme.io"],
    }


def test_settings_set_json_object_from_file(invoke, api, tmp_path):
    rules = {"action": "block", "items": [{"type": "email_address", "value": "spam@x.com"}]}
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(rules), encoding="utf-8")
    route = api.post(f"{WS}/settings").mock(return_value=httpx.Response(201))
    result = invoke("settings", "set", "ingestionRules", f"@{path}")
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {"key": "ingestionRules", "value": rules}


def test_settings_set_value_from_stdin(invoke, api):
    route = api.post(f"{WS}/settings").mock(return_value=httpx.Response(201))
    result = invoke("settings", "set", "meetingTemplates", "-", input='[{"name": "1:1"}]')
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "key": "meetingTemplates",
        "value": [{"name": "1:1"}],
    }


def test_settings_set_emits_body_when_api_returns_one(invoke, api):
    api.post(f"{WS}/settings").mock(
        return_value=httpx.Response(201, json={"key": "fiscalYearOffset", "value": 3})
    )
    result = invoke("settings", "set", "fiscalYearOffset", "3")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"key": "fiscalYearOffset", "value": 3}


def test_settings_set_unknown_key_exit_2(invoke, api):
    route = api.post(f"{WS}/settings").mock(return_value=httpx.Response(201))
    result = invoke("settings", "set", "orgDescriptin", "x")
    assert result.exit_code == 2
    assert "Unknown setting key 'orgDescriptin'" in result.stderr
    assert "Did you mean orgDescription" in result.stderr
    assert not route.called


def test_settings_set_invalid_json_file_exit_2(invoke, api, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{nope", encoding="utf-8")
    route = api.post(f"{WS}/settings").mock(return_value=httpx.Response(201))
    result = invoke("settings", "set", "ingestionRules", f"@{path}")
    assert result.exit_code == 2
    assert "Invalid JSON value" in result.stderr
    assert not route.called


def test_settings_set_read_only_rejected_exit_1(invoke, api):
    api.post(f"{WS}/settings").mock(
        return_value=httpx.Response(
            400,
            json={
                "errors": [
                    {"status": "400", "detail": "Setting billingUseLegacyPricing is read-only"}
                ]
            },
        )
    )
    result = invoke("settings", "set", "billingUseLegacyPricing", "true")
    assert result.exit_code == 1
    assert "HTTP 400" in result.stderr and "read-only" in result.stderr


def test_settings_set_forbidden_exit_3(invoke, api):
    api.post(f"{WS}/settings").mock(
        return_value=httpx.Response(
            403, json={"errors": [{"status": "403", "detail": "Admin permissions required"}]}
        )
    )
    result = invoke("settings", "set", "billingOveragesDisabled", "true")
    assert result.exit_code == 3
    assert "Admin permissions required" in result.stderr


# -- reset -----------------------------------------------------------------


def test_settings_reset_with_yes(invoke, api):
    route = api.delete(f"{WS}/settings").mock(return_value=httpx.Response(200))
    result = invoke("--yes", "settings", "reset", "orgDescription")
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "orgDescription reset" in result.stderr
    request = route.calls.last.request
    assert request.method == "DELETE"
    assert request.url.path == f"/v1{WS}/settings"
    assert query_pairs(request) == []
    assert json_body(request) == {"key": "orgDescription"}


def test_settings_reset_silent_and_empty_json_body(invoke, api):
    route = api.delete(f"{WS}/settings").mock(return_value=httpx.Response(200, json={}))
    result = invoke("--silent", "-y", "settings", "reset", "dealDetectionPrompt")
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    request = route.calls.last.request
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {"key": "dealDetectionPrompt"}


def test_settings_reset_refuses_without_yes_when_not_a_tty(invoke, api):
    route = api.delete(f"{WS}/settings").mock(return_value=httpx.Response(200))
    result = invoke("settings", "reset", "orgDescription")
    assert result.exit_code == 2
    assert "--yes" in result.stderr
    assert not route.called


def test_settings_reset_unknown_key_exit_2(invoke, api):
    route = api.delete(f"{WS}/settings").mock(return_value=httpx.Response(200))
    result = invoke("-y", "settings", "reset", "nope")
    assert result.exit_code == 2
    assert "Unknown setting key 'nope'" in result.stderr
    assert not route.called


def test_settings_reset_forbidden_exit_3(invoke, api):
    api.delete(f"{WS}/settings").mock(
        return_value=httpx.Response(
            403, json={"errors": [{"status": "403", "detail": "Admin permissions required"}]}
        )
    )
    result = invoke("-y", "settings", "reset", "billingOveragesDisabled")
    assert result.exit_code == 3


# -- help ------------------------------------------------------------------


def _flat_help(text: str) -> str:
    """Collapse rich's panel borders and line wrapping so phrases can be matched."""
    return " ".join(text.replace("│", " ").split())


def test_settings_help_mentions_paths(invoke):
    result = invoke("settings", "--help")
    assert result.exit_code == 0
    text = _flat_help(result.stdout)
    for command in ("list", "get", "set", "reset"):
        assert command in text
    assert "GET /settings" in text
    assert "GET /settings/{key}" in text
    assert "POST /settings" in text
    assert "DELETE /settings" in text


def test_settings_subcommand_help_renders(invoke):
    for command in ("list", "get", "set", "reset"):
        result = invoke("settings", command, "--help")
        assert result.exit_code == 0, result.output
        assert "Usage:" in result.stdout
