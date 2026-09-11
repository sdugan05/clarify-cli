from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from helpers import json_body, query_pairs, resource

ACCESS = "/workspaces/acme/objects/deal/records/r1/access"
TYPE = "object-record-access"


def grant(id_: str, **attributes):
    return resource(TYPE, id_, **attributes)


def test_operations_manifest_covers_record_access_tag():
    from clarify_cli.commands.access import OPERATIONS, app

    ops = json.loads((Path(__file__).parent / "fixtures" / "operations.json").read_text())
    expected = {op["operationId"] for op in ops if op["tag"] == "RecordAccess"}
    assert set(OPERATIONS) == expected
    registered = {
        info.name or info.callback.__name__.replace("_", "-") for info in app.registered_commands
    }
    assert set(OPERATIONS.values()) <= registered


# -- list --------------------------------------------------------------------


def test_access_list(invoke, api):
    route = api.get(ACCESS).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [grant("g1", grantee_type="user", grantee_id="u1", access_level="view")],
                "meta": {"viewerAccess": ["manage"]},
            },
        )
    )
    result = invoke("access", "list", "deal", "r1")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["data"][0]["id"] == "g1"
    assert body["meta"] == {"viewerAccess": ["manage"]}
    request = route.calls.last.request
    assert request.method == "GET"
    assert request.url.path == f"/v1{ACCESS}"
    assert query_pairs(request) == []


def test_access_list_forbidden_for_workspace_key_exit_3(invoke, api):
    api.get(ACCESS).mock(
        return_value=httpx.Response(
            403, json={"errors": [{"status": "403", "detail": "Forbidden"}]}
        )
    )
    result = invoke("access", "list", "deal", "r1")
    assert result.exit_code == 3
    assert "HTTP 403" in result.stderr and "Personal" in result.stderr


# -- grant -------------------------------------------------------------------


def test_access_grant_user(invoke, api):
    route = api.post(ACCESS).mock(
        return_value=httpx.Response(
            201,
            json={"data": grant("g1", grantee_type="user", grantee_id="u1", access_level="view")},
        )
    )
    result = invoke("access", "grant", "deal", "r1", "--user", "u1", "--level", "view")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["id"] == "g1"
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"/v1{ACCESS}"
    assert query_pairs(request) == []
    assert json_body(request) == {
        "data": {
            "type": TYPE,
            "attributes": {"grantee_type": "user", "grantee_id": "u1", "access_level": "view"},
        }
    }


def test_access_grant_workspace_no_notify_silent(invoke, api):
    path = "/workspaces/acme/objects/list/records/l1/access"
    route = api.post(path).mock(return_value=httpx.Response(201, json={"data": grant("g2")}))
    result = invoke(
        "--silent", "access", "grant", "list", "l1", "--everyone", "--level", "edit", "--no-notify"
    )
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert request.url.path == f"/v1{path}"
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {
        "data": {
            "type": TYPE,
            "attributes": {
                "grantee_type": "workspace",
                "grantee_id": None,
                "access_level": "edit",
                "notify": False,
            },
        }
    }


def test_access_grant_data_attributes_are_wrapped(invoke, api):
    route = api.post(ACCESS).mock(return_value=httpx.Response(201, json={"data": grant("g3")}))
    attrs = {"grantee_type": "user", "grantee_id": "u2", "access_level": "edit", "notify": False}
    result = invoke("access", "grant", "deal", "r1", "--data", json.dumps(attrs))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {"data": {"type": TYPE, "attributes": attrs}}


def test_access_grant_data_document_with_flag_override(invoke, api):
    route = api.post(ACCESS).mock(return_value=httpx.Response(201, json={"data": grant("g4")}))
    document = {
        "data": {
            "type": TYPE,
            "attributes": {"grantee_type": "user", "grantee_id": "u2", "access_level": "view"},
        }
    }
    result = invoke(
        "access", "grant", "deal", "r1", "--data", json.dumps(document), "--level", "edit"
    )
    assert result.exit_code == 0, result.output
    sent = json_body(route.calls.last.request)
    assert sent["data"]["attributes"] == {
        "grantee_type": "user",
        "grantee_id": "u2",
        "access_level": "edit",
    }


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--user", "u1", "--everyone", "--level", "view"], "mutually exclusive"),
        (["--level", "view"], "Choose a grantee"),
        (["--user", "u1"], "--level is required"),
        (["--user", "u1", "--level", "owner"], "view"),
        (["--data", "{not json"], "Invalid JSON"),
    ],
)
def test_access_grant_usage_errors_exit_2(invoke, api, args, message):
    route = api.post(ACCESS).mock(return_value=httpx.Response(201, json={"data": grant("x")}))
    result = invoke("access", "grant", "deal", "r1", *args)
    assert result.exit_code == 2, result.output
    assert message in result.stderr
    assert not route.called


def test_access_grant_api_error_exit_1(invoke, api):
    api.post(ACCESS).mock(
        return_value=httpx.Response(
            422,
            json={
                "errors": [
                    {
                        "status": "422",
                        "detail": "grantee not found",
                        "source": {"pointer": "/data/attributes/grantee_id"},
                    }
                ]
            },
        )
    )
    result = invoke("access", "grant", "deal", "r1", "--user", "nope", "--level", "view")
    assert result.exit_code == 1
    assert "HTTP 422" in result.stderr and "/data/attributes/grantee_id" in result.stderr


# -- grant-bulk --------------------------------------------------------------


def test_access_grant_bulk_from_flags(invoke, api):
    route = api.post(f"{ACCESS}/bulk").mock(
        return_value=httpx.Response(201, json={"data": [grant("g1"), grant("g2"), grant("g3")]})
    )
    result = invoke(
        "access",
        "grant-bulk",
        "deal",
        "r1",
        "--user",
        "u1",
        "--user",
        "u2",
        "--everyone",
        "--level",
        "view",
        "--no-notify",
    )
    assert result.exit_code == 0, result.output
    assert [item["id"] for item in json.loads(result.stdout)["data"]] == ["g1", "g2", "g3"]
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"/v1{ACCESS}/bulk"
    assert query_pairs(request) == []
    assert json_body(request) == {
        "data": [
            {
                "type": TYPE,
                "attributes": {
                    "grantee_type": "user",
                    "grantee_id": "u1",
                    "access_level": "view",
                    "notify": False,
                },
            },
            {
                "type": TYPE,
                "attributes": {
                    "grantee_type": "user",
                    "grantee_id": "u2",
                    "access_level": "view",
                    "notify": False,
                },
            },
            {
                "type": TYPE,
                "attributes": {
                    "grantee_type": "workspace",
                    "grantee_id": None,
                    "access_level": "view",
                    "notify": False,
                },
            },
        ]
    }


def test_access_grant_bulk_data_array_wraps_flat_items(invoke, api):
    route = api.post(f"{ACCESS}/bulk").mock(return_value=httpx.Response(201, json={"data": []}))
    items = [
        {"grantee_type": "user", "grantee_id": "u1", "access_level": "view"},
        {"type": TYPE, "attributes": {"grantee_type": "workspace", "access_level": "edit"}},
    ]
    result = invoke("--silent", "access", "grant-bulk", "deal", "r1", "--data", json.dumps(items))
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {
        "data": [
            {
                "type": TYPE,
                "attributes": {"grantee_type": "user", "grantee_id": "u1", "access_level": "view"},
            },
            {
                "type": TYPE,
                "attributes": {
                    "grantee_type": "workspace",
                    "access_level": "edit",
                    "grantee_id": None,
                },
            },
        ]
    }


def test_access_grant_bulk_data_document_passes_through(invoke, api):
    route = api.post(f"{ACCESS}/bulk").mock(return_value=httpx.Response(201, json={"data": []}))
    document = {
        "data": [
            {
                "type": TYPE,
                "attributes": {"grantee_type": "user", "grantee_id": "u1", "access_level": "edit"},
            }
        ]
    }
    result = invoke("access", "grant-bulk", "deal", "r1", "--data", json.dumps(document))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == document


def test_access_grant_bulk_data_single_document_is_unwrapped(invoke, api):
    route = api.post(f"{ACCESS}/bulk").mock(return_value=httpx.Response(201, json={"data": []}))
    single = {
        "type": TYPE,
        "attributes": {"grantee_type": "user", "grantee_id": "u1", "access_level": "view"},
    }
    result = invoke("access", "grant-bulk", "deal", "r1", "--data", json.dumps({"data": single}))
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"/v1{ACCESS}/bulk"
    assert json_body(request) == {"data": [single]}


def test_access_grant_bulk_file_single_document_is_unwrapped(invoke, api, tmp_path):
    route = api.post(f"{ACCESS}/bulk").mock(return_value=httpx.Response(201, json={"data": []}))
    single = {
        "type": TYPE,
        "attributes": {"grantee_type": "workspace", "grantee_id": None, "access_level": "edit"},
    }
    json_path = tmp_path / "grant.json"
    json_path.write_text(json.dumps({"data": single}), encoding="utf-8")
    result = invoke("access", "grant-bulk", "deal", "r1", "--file", str(json_path))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {"data": [single]}


def test_access_grant_bulk_from_csv_file(invoke, api, tmp_path):
    route = api.post(f"{ACCESS}/bulk").mock(return_value=httpx.Response(201, json={"data": []}))
    csv_path = tmp_path / "grants.csv"
    csv_path.write_text(
        "grantee_type,grantee_id,access_level\nuser,u1,view\nworkspace,,edit\n", encoding="utf-8"
    )
    result = invoke("access", "grant-bulk", "deal", "r1", "--file", str(csv_path))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "data": [
            {
                "type": TYPE,
                "attributes": {"grantee_type": "user", "grantee_id": "u1", "access_level": "view"},
            },
            {
                "type": TYPE,
                "attributes": {
                    "grantee_type": "workspace",
                    "access_level": "edit",
                    "grantee_id": None,
                },
            },
        ]
    }


def test_access_grant_bulk_ndjson_file_with_level_default(invoke, api, tmp_path):
    route = api.post(f"{ACCESS}/bulk").mock(return_value=httpx.Response(201, json={"data": []}))
    ndjson_path = tmp_path / "grants.ndjson"
    ndjson_path.write_text(
        '{"grantee_type": "user", "grantee_id": "u1"}\n'
        '{"grantee_type": "user", "grantee_id": "u2", "access_level": "view"}\n',
        encoding="utf-8",
    )
    result = invoke(
        "access", "grant-bulk", "deal", "r1", "--file", str(ndjson_path), "--level", "edit"
    )
    assert result.exit_code == 0, result.output
    sent = json_body(route.calls.last.request)["data"]
    assert [item["attributes"]["access_level"] for item in sent] == ["edit", "view"]


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ([], "exactly one of"),
        (["--data", "[]", "--user", "u1", "--level", "view"], "exactly one of"),
        (["--user", "u1"], "--level is required"),
        (["--data", "[]"], "No grants"),
        (["--data", "[1]"], "not a JSON object"),
        (["--data", '"str"'], "JSON array"),
        (["--data", "{bad"], "Invalid JSON"),
    ],
)
def test_access_grant_bulk_usage_errors_exit_2(invoke, api, args, message):
    route = api.post(f"{ACCESS}/bulk").mock(return_value=httpx.Response(201, json={"data": []}))
    result = invoke("access", "grant-bulk", "deal", "r1", *args)
    assert result.exit_code == 2, result.output
    assert message in result.stderr
    assert not route.called


def test_access_grant_bulk_rejects_more_than_1000(invoke, api):
    route = api.post(f"{ACCESS}/bulk").mock(return_value=httpx.Response(201, json={"data": []}))
    items = [
        {"grantee_type": "user", "grantee_id": f"u{i}", "access_level": "view"} for i in range(1001)
    ]
    result = invoke("access", "grant-bulk", "deal", "r1", "--data", json.dumps(items))
    assert result.exit_code == 2, result.output
    assert "at most 1000" in result.stderr
    assert not route.called


# -- update ------------------------------------------------------------------


def test_access_update_level(invoke, api):
    route = api.patch(f"{ACCESS}/g1").mock(
        return_value=httpx.Response(200, json={"data": grant("g1", access_level="edit")})
    )
    result = invoke("access", "update", "deal", "r1", "g1", "--level", "edit")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["attributes"]["access_level"] == "edit"
    request = route.calls.last.request
    assert request.method == "PATCH"
    assert request.url.path == f"/v1{ACCESS}/g1"
    assert query_pairs(request) == []
    assert json_body(request) == {"data": {"type": TYPE, "attributes": {"access_level": "edit"}}}


def test_access_update_data_and_silent(invoke, api):
    route = api.patch(f"{ACCESS}/g1").mock(
        return_value=httpx.Response(200, json={"data": grant("g1")})
    )
    result = invoke(
        "--silent", "access", "update", "deal", "r1", "g1", "--data", '{"access_level":"view"}'
    )
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {"data": {"type": TYPE, "attributes": {"access_level": "view"}}}


def test_access_update_requires_level_exit_2(invoke, api):
    route = api.patch(f"{ACCESS}/g1").mock(
        return_value=httpx.Response(200, json={"data": grant("g1")})
    )
    result = invoke("access", "update", "deal", "r1", "g1")
    assert result.exit_code == 2
    assert "--level" in result.stderr
    assert not route.called


def test_access_update_not_found_exit_4(invoke, api):
    api.patch(f"{ACCESS}/nope").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Grant not found"}]}
        )
    )
    result = invoke("access", "update", "deal", "r1", "nope", "--level", "view")
    assert result.exit_code == 4
    assert "Grant not found" in result.stderr


# -- revoke ------------------------------------------------------------------


def test_access_revoke_with_yes(invoke, api):
    route = api.delete(f"{ACCESS}/g1").mock(return_value=httpx.Response(202))
    result = invoke("-y", "access", "revoke", "deal", "r1", "g1")
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "Revoked grant g1" in result.stderr
    request = route.calls.last.request
    assert request.method == "DELETE"
    assert request.url.path == f"/v1{ACCESS}/g1"
    assert query_pairs(request) == []


def test_access_revoke_silent_and_empty_json_body(invoke, api):
    route = api.delete(f"{ACCESS}/g1").mock(return_value=httpx.Response(202, json={}))
    result = invoke("--silent", "--yes", "access", "revoke", "deal", "r1", "g1")
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "Revoked grant g1" in result.stderr
    assert query_pairs(route.calls.last.request) == [("silent", "true")]


def test_access_revoke_refuses_without_yes_when_not_a_tty(invoke, api):
    route = api.delete(f"{ACCESS}/g1").mock(return_value=httpx.Response(202))
    result = invoke("access", "revoke", "deal", "r1", "g1")
    assert result.exit_code == 2
    assert "Refusing" in result.stderr and "--yes" in result.stderr
    assert not route.called


def test_access_revoke_not_found_exit_4(invoke, api):
    api.delete(f"{ACCESS}/nope").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Grant not found"}]}
        )
    )
    result = invoke("-y", "access", "revoke", "deal", "r1", "nope")
    assert result.exit_code == 4
    assert "HTTP 404" in result.stderr
