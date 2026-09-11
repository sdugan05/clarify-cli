from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from helpers import json_body, query_pairs, resource

MEETING = "/workspaces/acme/objects/meeting/access"
TYPE = "object-access"


def delegation(id_: str, **attributes):
    return resource(TYPE, id_, **attributes)


def test_operations_manifest_covers_object_access_tag():
    from clarify_cli.commands.object_access import OPERATIONS, app

    ops = json.loads((Path(__file__).parent / "fixtures" / "operations.json").read_text())
    expected = {op["operationId"] for op in ops if op["tag"] == "ObjectAccess"}
    assert set(OPERATIONS) == expected
    registered = {
        info.name or info.callback.__name__.replace("_", "-") for info in app.registered_commands
    }
    assert set(OPERATIONS.values()) <= registered


# -- list --------------------------------------------------------------------


def test_object_access_list(invoke, api):
    route = api.get(MEETING).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    delegation("d1", owner_id="me", delegate_id="u1", entity="meeting"),
                ]
            },
        )
    )
    result = invoke("object-access", "list", "meeting")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["data"][0]["id"] == "d1"
    assert body["data"][0]["attributes"]["delegate_id"] == "u1"
    request = route.calls.last.request
    assert request.method == "GET"
    assert request.url.path == f"/v1{MEETING}"
    assert query_pairs(request) == []


def test_object_access_list_forbidden_for_workspace_key_exit_3(invoke, api):
    api.get("/workspaces/acme/objects/message/access").mock(
        return_value=httpx.Response(
            403, json={"errors": [{"status": "403", "detail": "Forbidden"}]}
        )
    )
    result = invoke("object-access", "list", "message")
    assert result.exit_code == 3
    assert "HTTP 403" in result.stderr and "Personal" in result.stderr


# -- grant -------------------------------------------------------------------


def test_object_access_grant_user(invoke, api):
    route = api.post(MEETING).mock(
        return_value=httpx.Response(
            201, json={"data": delegation("d1", owner_id="me", delegate_id="u1", entity="meeting")}
        )
    )
    result = invoke("object-access", "grant", "meeting", "--user", "u1")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["id"] == "d1"
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"/v1{MEETING}"
    assert query_pairs(request) == []
    assert json_body(request) == {"data": {"type": TYPE, "attributes": {"delegate_id": "u1"}}}


def test_object_access_grant_silent(invoke, api):
    path = "/workspaces/acme/objects/message/access"
    route = api.post(path).mock(return_value=httpx.Response(201, json={"data": delegation("d2")}))
    result = invoke("--silent", "object-access", "grant", "message", "--user", "u2")
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert request.url.path == f"/v1{path}"
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {"data": {"type": TYPE, "attributes": {"delegate_id": "u2"}}}


def test_object_access_grant_data_attributes_are_wrapped(invoke, api):
    route = api.post(MEETING).mock(
        return_value=httpx.Response(201, json={"data": delegation("d3")})
    )
    result = invoke("object-access", "grant", "meeting", "--data", '{"delegate_id": "u3"}')
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "data": {"type": TYPE, "attributes": {"delegate_id": "u3"}}
    }


def test_object_access_grant_data_document_with_user_override(invoke, api):
    route = api.post(MEETING).mock(
        return_value=httpx.Response(201, json={"data": delegation("d4")})
    )
    document = {"data": {"type": TYPE, "attributes": {"delegate_id": "old"}}}
    result = invoke(
        "object-access", "grant", "meeting", "--data", json.dumps(document), "--user", "new"
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "data": {"type": TYPE, "attributes": {"delegate_id": "new"}}
    }


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ([], "--user USER_ID"),
        (["--data", "{not json"], "Invalid JSON"),
        (
            ["--data", '{"data": {"type": "object-access", "attributes": "nope"}}'],
            "must be a JSON object",
        ),
    ],
)
def test_object_access_grant_usage_errors_exit_2(invoke, api, args, message):
    route = api.post(MEETING).mock(return_value=httpx.Response(201, json={"data": delegation("x")}))
    result = invoke("object-access", "grant", "meeting", *args)
    assert result.exit_code == 2, result.output
    assert message in result.stderr
    assert not route.called


def test_object_access_grant_api_error_exit_1(invoke, api):
    api.post(MEETING).mock(
        return_value=httpx.Response(
            422,
            json={
                "errors": [
                    {
                        "status": "422",
                        "detail": "Access delegation is not enabled on this plan",
                    }
                ]
            },
        )
    )
    result = invoke("object-access", "grant", "meeting", "--user", "u1")
    assert result.exit_code == 1
    assert "HTTP 422" in result.stderr and "not enabled" in result.stderr


# -- revoke ------------------------------------------------------------------


def test_object_access_revoke_with_yes(invoke, api):
    route = api.delete(f"{MEETING}/d1").mock(return_value=httpx.Response(202))
    result = invoke("-y", "object-access", "revoke", "meeting", "d1")
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "Revoked meeting access delegation d1" in result.stderr
    request = route.calls.last.request
    assert request.method == "DELETE"
    assert request.url.path == f"/v1{MEETING}/d1"
    assert query_pairs(request) == []


def test_object_access_revoke_silent_and_empty_json_body(invoke, api):
    path = "/workspaces/acme/objects/message/access/d9"
    route = api.delete(path).mock(return_value=httpx.Response(202, json={}))
    result = invoke("--silent", "--yes", "object-access", "revoke", "message", "d9")
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "Revoked message access delegation d9" in result.stderr
    request = route.calls.last.request
    assert request.url.path == f"/v1{path}"
    assert query_pairs(request) == [("silent", "true")]


def test_object_access_revoke_refuses_without_yes_when_not_a_tty(invoke, api):
    route = api.delete(f"{MEETING}/d1").mock(return_value=httpx.Response(202))
    result = invoke("object-access", "revoke", "meeting", "d1")
    assert result.exit_code == 2
    assert "Refusing" in result.stderr and "--yes" in result.stderr
    assert not route.called


def test_object_access_revoke_not_found_exit_4(invoke, api):
    api.delete(f"{MEETING}/nope").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Delegation not found"}]}
        )
    )
    result = invoke("-y", "object-access", "revoke", "meeting", "nope")
    assert result.exit_code == 4
    assert "HTTP 404" in result.stderr and "Delegation not found" in result.stderr
