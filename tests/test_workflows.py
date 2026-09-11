from __future__ import annotations

import json

import httpx

from clarify_cli.commands import workflows
from helpers import json_body, page, query_pairs, resource

WS = "/workspaces/acme"
WF_ID = "f2a4c6e8-0b1d-4e3f-8a5c-7d9e1f3a5b7c"

ATTRIBUTES = {
    "name": "Create a task for every new deal",
    "description": "When a deal is created, add a follow-up task for the owner.",
    "enabled": False,
    "exits": {},
    "run_limits": {},
    "type": "workflow",
    "trigger": {
        "_id": "trigger",
        "plugin_id": "on:clarify:create:record",
        "filters": [],
        "input": {"entity": "deal"},
        "prev": None,
        "next": "create_task",
    },
    "blocks": {
        "create_task": {
            "_id": "create_task",
            "plugin_id": "clarify:create:record",
            "filters": [],
            "input": {"entity": "task", "attributes": {"name": "Follow up on new deal"}},
            "prev": "trigger",
            "next": None,
        }
    },
}


def test_operations_manifest_covers_every_workflow_operation():
    assert workflows.OPERATIONS == {
        "getWorkflows": "list",
        "getWorkflow": "get",
        "createWorkflow": "create",
        "updateWorkflow": "update",
        "deleteWorkflow": "delete",
    }


# -- list ------------------------------------------------------------------


def test_workflows_list_defaults(invoke, api):
    route = api.get(f"{WS}/workflows").mock(
        return_value=httpx.Response(
            200, json=page([resource("workflow", WF_ID, name="Nightly", enabled=True)], total=1)
        )
    )
    result = invoke("workflows", "list")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["data"][0]["id"] == WF_ID
    assert body["meta"] == {"total_records": 1, "returned": 1}
    assert route.calls.last.request.method == "GET"
    assert route.calls.last.request.url.path == f"/v1{WS}/workflows"
    assert query_pairs(route.calls.last.request) == [("page[limit]", "50")]


def test_workflows_list_type_filter_sort_and_paging(invoke, api):
    route = api.get(f"{WS}/workflows").mock(return_value=httpx.Response(200, json=page([])))
    result = invoke(
        "workflows",
        "list",
        "--type",
        "sequence",
        "-f",
        "enabled=true",
        "--sort",
        "-_created_at",
        "-n",
        "5",
        "--offset",
        "10",
    )
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [
        ("filter[enabled]", "true"),
        ("sortOrder[column]", "_created_at"),
        ("sortOrder[dir]", "DESC"),
        ("filter[type]", "sequence"),
        ("page[limit]", "5"),
        ("page[offset]", "10"),
    ]


def test_workflows_list_caps_page_size_at_500(invoke, api):
    route = api.get(f"{WS}/workflows").mock(return_value=httpx.Response(200, json=page([])))
    result = invoke("workflows", "list", "-n", "1000")
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [("page[limit]", "500")]


def test_workflows_list_explicit_page_size_wins(invoke, api):
    route = api.get(f"{WS}/workflows").mock(return_value=httpx.Response(200, json=page([])))
    result = invoke("workflows", "list", "-n", "3", "--page-size", "2")
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [("page[limit]", "2")]


def test_workflows_list_all_follows_pages(invoke, api):
    base = f"https://api.clarify.ai/v1{WS}/workflows"
    route = api.get(f"{WS}/workflows").mock(
        side_effect=[
            httpx.Response(
                200,
                json=page(
                    [resource("workflow", "1")], total=2, next_url=f"{base}?page%5Boffset%5D=1"
                ),
            ),
            httpx.Response(200, json=page([resource("workflow", "2")], total=2)),
        ]
    )
    result = invoke("-o", "ndjson", "workflows", "list", "--all")
    assert result.exit_code == 0, result.output
    assert [json.loads(line)["id"] for line in result.stdout.splitlines()] == ["1", "2"]
    assert route.call_count == 2
    assert query_pairs(route.calls[0].request) == [("page[limit]", "500")]


def test_workflows_list_rejects_unknown_type(invoke, api):
    route = api.get(f"{WS}/workflows").mock(return_value=httpx.Response(200, json=page([])))
    result = invoke("workflows", "list", "--type", "campaign")
    assert result.exit_code == 2
    assert not route.called


# -- get -------------------------------------------------------------------


def test_workflows_get(invoke, api):
    route = api.get(f"{WS}/workflows/{WF_ID}").mock(
        return_value=httpx.Response(200, json={"data": resource("workflow", WF_ID, **ATTRIBUTES)})
    )
    result = invoke("workflows", "get", WF_ID)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["id"] == WF_ID
    assert route.calls.last.request.method == "GET"
    assert route.calls.last.request.url.path == f"/v1{WS}/workflows/{WF_ID}"
    assert query_pairs(route.calls.last.request) == []


def test_workflows_get_not_found_exit_4(invoke, api):
    api.get(f"{WS}/workflows/nope").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Workflow not found"}]}
        )
    )
    result = invoke("workflows", "get", "nope")
    assert result.exit_code == 4
    assert "HTTP 404" in result.stderr and "Workflow not found" in result.stderr


# -- create ----------------------------------------------------------------


def test_workflows_create_from_file_passes_document_through(invoke, api, tmp_path):
    document = {"data": {"type": "workflow", "attributes": ATTRIBUTES}}
    path = tmp_path / "workflow.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    route = api.post(f"{WS}/workflows").mock(
        return_value=httpx.Response(201, json={"data": resource("workflow", WF_ID, **ATTRIBUTES)})
    )
    result = invoke("workflows", "create", "--data", f"@{path}")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["id"] == WF_ID
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"/v1{WS}/workflows"
    assert query_pairs(request) == []
    assert json_body(request) == document


def test_workflows_create_wraps_bare_attributes_and_applies_set(invoke, api):
    route = api.post(f"{WS}/workflows").mock(
        return_value=httpx.Response(201, json={"data": resource("workflow", WF_ID)})
    )
    result = invoke(
        "--silent",
        "workflows",
        "create",
        "--data",
        json.dumps({**ATTRIBUTES, "enabled": True}),
        "--set",
        "enabled=false",
    )
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {"data": {"type": "workflow", "attributes": ATTRIBUTES}}


def test_workflows_create_requires_body(invoke, api):
    route = api.post(f"{WS}/workflows").mock(return_value=httpx.Response(201, json={}))
    result = invoke("workflows", "create")
    assert result.exit_code == 2
    assert "--data" in result.stderr
    assert not route.called


def test_workflows_create_invalid_json_exit_2(invoke, api):
    route = api.post(f"{WS}/workflows").mock(return_value=httpx.Response(201, json={}))
    result = invoke("workflows", "create", "--data", "{not json")
    assert result.exit_code == 2
    assert "Invalid JSON" in result.stderr
    assert not route.called


def test_workflows_create_validation_error_exit_1(invoke, api):
    api.post(f"{WS}/workflows").mock(
        return_value=httpx.Response(
            422,
            json={
                "errors": [
                    {
                        "status": "422",
                        "detail": "trigger is required",
                        "source": {"pointer": "/data/attributes/trigger"},
                    }
                ]
            },
        )
    )
    result = invoke("workflows", "create", "--data", '{"name": "x"}')
    assert result.exit_code == 1
    assert "HTTP 422" in result.stderr and "trigger is required" in result.stderr


# -- update ----------------------------------------------------------------


def test_workflows_update_enable(invoke, api):
    route = api.patch(f"{WS}/workflows/{WF_ID}").mock(
        return_value=httpx.Response(200, json={"data": resource("workflow", WF_ID, enabled=True)})
    )
    result = invoke("workflows", "update", WF_ID, "--enable")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["attributes"]["enabled"] is True
    request = route.calls.last.request
    assert request.method == "PATCH"
    assert request.url.path == f"/v1{WS}/workflows/{WF_ID}"
    assert query_pairs(request) == []
    assert json_body(request) == {
        "data": {"type": "workflow", "id": WF_ID, "attributes": {"enabled": True}}
    }


def test_workflows_update_disable_silent(invoke, api):
    route = api.patch(f"{WS}/workflows/{WF_ID}").mock(
        return_value=httpx.Response(200, json={"data": resource("workflow", WF_ID)})
    )
    result = invoke("--silent", "workflows", "update", WF_ID, "--disable")
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {
        "data": {"type": "workflow", "id": WF_ID, "attributes": {"enabled": False}}
    }


def test_workflows_update_data_set_and_enable_combine(invoke, api):
    route = api.patch(f"{WS}/workflows/{WF_ID}").mock(
        return_value=httpx.Response(200, json={"data": resource("workflow", WF_ID)})
    )
    result = invoke(
        "workflows",
        "update",
        WF_ID,
        "--data",
        '{"description": "Runs nightly", "enabled": false}',
        "--set",
        "name=Nightly sync",
        "--enable",
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "data": {
            "type": "workflow",
            "id": WF_ID,
            "attributes": {"description": "Runs nightly", "enabled": True, "name": "Nightly sync"},
        }
    }


def test_workflows_update_full_document_keeps_id(invoke, api):
    route = api.patch(f"{WS}/workflows/{WF_ID}").mock(
        return_value=httpx.Response(200, json={"data": resource("workflow", WF_ID)})
    )
    document = {"data": {"type": "workflow", "id": WF_ID, "attributes": {"name": "Renamed"}}}
    result = invoke("workflows", "update", WF_ID, "--data", json.dumps(document))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == document


def test_workflows_update_enable_and_disable_conflict(invoke, api):
    route = api.patch(f"{WS}/workflows/{WF_ID}").mock(return_value=httpx.Response(200, json={}))
    result = invoke("workflows", "update", WF_ID, "--enable", "--disable")
    assert result.exit_code == 2
    assert "mutually exclusive" in result.stderr
    assert not route.called


def test_workflows_update_requires_some_change(invoke, api):
    route = api.patch(f"{WS}/workflows/{WF_ID}").mock(return_value=httpx.Response(200, json={}))
    result = invoke("workflows", "update", WF_ID)
    assert result.exit_code == 2
    assert not route.called


# -- delete ----------------------------------------------------------------


def test_workflows_delete_with_yes(invoke, api):
    route = api.delete(f"{WS}/workflows/{WF_ID}").mock(return_value=httpx.Response(202))
    result = invoke("--yes", "workflows", "delete", WF_ID)
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "deletion accepted" in result.stderr
    request = route.calls.last.request
    assert request.method == "DELETE"
    assert request.url.path == f"/v1{WS}/workflows/{WF_ID}"
    assert query_pairs(request) == []


def test_workflows_delete_silent_and_empty_json_body(invoke, api):
    route = api.delete(f"{WS}/workflows/{WF_ID}").mock(return_value=httpx.Response(202, json={}))
    result = invoke("--silent", "-y", "workflows", "delete", WF_ID)
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "deletion accepted" in result.stderr
    assert query_pairs(route.calls.last.request) == [("silent", "true")]


def test_workflows_delete_refuses_without_yes_when_not_a_tty(invoke, api):
    route = api.delete(f"{WS}/workflows/{WF_ID}").mock(return_value=httpx.Response(202))
    result = invoke("workflows", "delete", WF_ID)
    assert result.exit_code == 2
    assert "--yes" in result.stderr
    assert not route.called


def test_workflows_delete_not_found_exit_4(invoke, api):
    api.delete(f"{WS}/workflows/nope").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Workflow not found"}]}
        )
    )
    result = invoke("-y", "workflows", "delete", "nope")
    assert result.exit_code == 4


# -- help ------------------------------------------------------------------


def _flat_help(text: str) -> str:
    """Collapse rich's panel borders and line wrapping so phrases can be matched."""
    return " ".join(text.replace("│", " ").split())


def test_workflows_help_mentions_paths(invoke):
    result = invoke("workflows", "--help")
    assert result.exit_code == 0
    text = _flat_help(result.stdout)
    for command in ("list", "get", "create", "update", "delete"):
        assert command in text
    assert "GET /workflows" in text
    assert "POST /workflows" in text
    assert "PATCH /workflows/{id}" in text
    assert "DELETE /workflows/{id}" in text


def test_workflows_subcommand_help_renders(invoke):
    for command in ("list", "get", "create", "update", "delete"):
        result = invoke("workflows", command, "--help")
        assert result.exit_code == 0, result.output
        assert "Usage:" in result.stdout
