from __future__ import annotations

import json

import httpx
import pytest

from clarify_cli.commands.layouts import OPERATIONS
from helpers import json_body, query_pairs

WS = "/workspaces/acme"
LAYOUT = "list__person"

TREE = {
    "version": 1,
    "children": [
        {
            "id": "views",
            "type": "NavGroup",
            "props": {"name": "Views"},
            "children": [{"id": "all-people", "type": "NavLink", "props": {"entity": "person"}}],
        }
    ],
}


def layout_row(tree: dict | None = None) -> dict:
    return {
        "_id": LAYOUT,
        "tree": tree or TREE,
        "_created_by": "7d4e2f9a-1b3c-4d5e-8f6a-9c0b2d4e6f81",
        "_updated_by": "7d4e2f9a-1b3c-4d5e-8f6a-9c0b2d4e6f81",
        "_created_at": "2026-01-15T09:30:00.000Z",
        "_updated_at": "2026-02-01T17:45:00.000Z",
    }


def document(tree: dict | None = None, layout_id: str = LAYOUT) -> dict:
    return {"data": {"type": "layout", "id": layout_id, "attributes": {"tree": tree or TREE}}}


def test_operations_manifest():
    assert OPERATIONS == {"getLayoutById": "get", "updateLayout": "update", "resetLayout": "reset"}


# -- get --------------------------------------------------------------------


def test_get(invoke, api):
    route = api.get(f"{WS}/layouts/{LAYOUT}").mock(
        return_value=httpx.Response(200, json=layout_row())
    )
    result = invoke("layouts", "get", LAYOUT)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == layout_row()
    request = route.calls.last.request
    assert request.method == "GET"
    assert request.url.path == f"/v1{WS}/layouts/{LAYOUT}"
    assert query_pairs(request) == []


def test_get_not_found_exit_4(invoke, api):
    api.get(f"{WS}/layouts/nope").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Layout not found"}]}
        )
    )
    result = invoke("layouts", "get", "nope")
    assert result.exit_code == 4
    assert "HTTP 404" in result.stderr and "Layout not found" in result.stderr


# -- update -----------------------------------------------------------------


def test_update_with_full_document(invoke, api):
    route = api.patch(f"{WS}/layouts/{LAYOUT}").mock(
        return_value=httpx.Response(200, json=layout_row())
    )
    result = invoke("layouts", "update", LAYOUT, "--data", json.dumps(document()))
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["_id"] == LAYOUT
    request = route.calls.last.request
    assert request.method == "PATCH"
    assert request.url.path == f"/v1{WS}/layouts/{LAYOUT}"
    assert query_pairs(request) == []
    assert json_body(request) == document()


@pytest.mark.parametrize(
    "payload",
    [
        TREE,  # bare tree
        {"tree": TREE},  # attributes object
        layout_row(),  # output of `layouts get`, round-tripped
        {"attributes": {"tree": TREE}},  # resource without type/id
    ],
    ids=["tree", "attributes", "fetched-layout", "resource"],
)
def test_update_wraps_shorthand_bodies(invoke, api, payload):
    route = api.patch(f"{WS}/layouts/{LAYOUT}").mock(
        return_value=httpx.Response(200, json=layout_row())
    )
    result = invoke("layouts", "update", LAYOUT, "--data", json.dumps(payload))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == document()


def test_update_from_file_with_silent(invoke, api, tmp_path):
    route = api.patch(f"{WS}/layouts/{LAYOUT}").mock(
        return_value=httpx.Response(200, json=layout_row())
    )
    path = tmp_path / "layout.json"
    path.write_text(json.dumps(layout_row()))
    result = invoke("--silent", "layouts", "update", LAYOUT, "-d", f"@{path}")
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == document()


def test_update_from_stdin(invoke, api):
    route = api.patch(f"{WS}/layouts/{LAYOUT}").mock(
        return_value=httpx.Response(200, json=layout_row())
    )
    result = invoke("layouts", "update", LAYOUT, "--data", "-", input=json.dumps(TREE))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == document()


def test_update_keeps_explicit_type_and_id(invoke, api):
    route = api.patch(f"{WS}/layouts/{LAYOUT}").mock(
        return_value=httpx.Response(200, json=layout_row())
    )
    doc = {"data": {"type": "custom", "id": "other", "attributes": {"tree": TREE}}}
    result = invoke("layouts", "update", LAYOUT, "--data", json.dumps(doc))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == doc


def test_update_requires_data(invoke, api):
    route = api.patch(f"{WS}/layouts/{LAYOUT}").mock(
        return_value=httpx.Response(200, json=layout_row())
    )
    result = invoke("layouts", "update", LAYOUT)
    assert result.exit_code == 2
    assert "--data" in result.stderr
    assert not route.called


@pytest.mark.parametrize(
    ("payload", "fragment"),
    [
        ("{not json", "Invalid JSON"),
        ("[1, 2]", "JSON object"),
        ('{"name": "x"}', "Unrecognised layout body"),
    ],
)
def test_update_rejects_bad_bodies(invoke, api, payload, fragment):
    route = api.patch(f"{WS}/layouts/{LAYOUT}").mock(
        return_value=httpx.Response(200, json=layout_row())
    )
    result = invoke("layouts", "update", LAYOUT, "--data", payload)
    assert result.exit_code == 2
    assert fragment in result.stderr
    assert not route.called


def test_update_unprocessable_exit_1(invoke, api):
    api.patch(f"{WS}/layouts/{LAYOUT}").mock(
        return_value=httpx.Response(
            422,
            json={
                "errors": [
                    {
                        "status": "422",
                        "detail": "tree.version must be 1",
                        "source": {"pointer": "/data/attributes/tree/version"},
                    }
                ]
            },
        )
    )
    result = invoke("layouts", "update", LAYOUT, "--data", json.dumps(TREE))
    assert result.exit_code == 1
    assert "HTTP 422" in result.stderr and "/data/attributes/tree/version" in result.stderr


# -- reset ------------------------------------------------------------------


def test_reset_with_yes(invoke, api):
    route = api.post(f"{WS}/layouts/{LAYOUT}/reset").mock(
        return_value=httpx.Response(200, json=layout_row())
    )
    result = invoke("--yes", "--silent", "layouts", "reset", LAYOUT)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["_id"] == LAYOUT
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"/v1{WS}/layouts/{LAYOUT}/reset"
    assert query_pairs(request) == [("silent", "true")]
    assert request.content == b""


def test_reset_empty_body_prints_confirmation(invoke, api):
    api.post(f"{WS}/layouts/{LAYOUT}/reset").mock(return_value=httpx.Response(204))
    result = invoke("-y", "layouts", "reset", LAYOUT)
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert f"Reset layout {LAYOUT}" in result.stderr


def test_reset_refuses_without_yes_when_not_a_tty(invoke, api):
    route = api.post(f"{WS}/layouts/{LAYOUT}/reset").mock(
        return_value=httpx.Response(200, json=layout_row())
    )
    result = invoke("layouts", "reset", LAYOUT)
    assert result.exit_code == 2
    assert "--yes" in result.stderr
    assert not route.called


def test_reset_not_found_exit_4(invoke, api):
    api.post(f"{WS}/layouts/nope/reset").mock(
        return_value=httpx.Response(404, json={"errors": [{"status": "404", "detail": "Gone"}]})
    )
    result = invoke("-y", "layouts", "reset", "nope")
    assert result.exit_code == 4
