from __future__ import annotations

import json

import httpx

from helpers import page, query_pairs, resource

PATH = "/workspaces/acme/objects/person/records/r1/activities"


def activity(id_: str) -> dict:
    return resource(
        "activity",
        id_,
        _created_at="2026-01-01T00:00:00Z",
        aggKey=f"r1:update:{id_}",
        data=[{"_id": id_, "type": "update"}],
    )


def test_activities_list_defaults(invoke, api):
    route = api.get(PATH).mock(
        return_value=httpx.Response(200, json=page([activity("a1")], total=1))
    )
    result = invoke("activities", "list", "person", "r1")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["data"][0]["id"] == "a1"
    assert body["meta"] == {"total_records": 1, "returned": 1}
    request = route.calls.last.request
    assert request.method == "GET"
    assert request.url.path == "/v1" + PATH
    assert query_pairs(request) == [("page[limit]", "50")]


def test_activities_list_options(invoke, api):
    route = api.get(PATH).mock(return_value=httpx.Response(200, json=page([])))
    result = invoke(
        "activities",
        "list",
        "person",
        "r1",
        "-n",
        "5",
        "--offset",
        "10",
        "--sort",
        "_created_at:desc",
        "--page-size",
        "2",
    )
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [
        ("sortOrder[column]", "_created_at"),
        ("sortOrder[dir]", "DESC"),
        ("page[limit]", "2"),
        ("page[offset]", "10"),
    ]


def test_activities_list_caps_page_size_at_endpoint_maximum(invoke, api):
    route = api.get(PATH).mock(return_value=httpx.Response(200, json=page([])))
    result = invoke("activities", "list", "person", "r1", "-n", "600")
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [("page[limit]", "500")]


def test_activities_list_custom_object_path(invoke, api):
    path = "/workspaces/acme/objects/c_sales_order/records/so-9/activities"
    route = api.get(path).mock(return_value=httpx.Response(200, json=page([])))
    result = invoke("activities", "list", "c_sales_order", "so-9")
    assert result.exit_code == 0, result.output
    assert route.calls.last.request.url.path == "/v1" + path


def test_activities_list_all_follows_pages(invoke, api):
    base = f"https://api.clarify.ai/v1{PATH}"
    route = api.get(PATH).mock(
        side_effect=[
            httpx.Response(
                200, json=page([activity("a1")], total=2, next_url=f"{base}?page%5Boffset%5D=1")
            ),
            httpx.Response(200, json=page([activity("a2")], total=2)),
        ]
    )
    result = invoke("-o", "ndjson", "activities", "list", "person", "r1", "--all")
    assert result.exit_code == 0, result.output
    assert [json.loads(line)["id"] for line in result.stdout.splitlines()] == ["a1", "a2"]
    assert route.call_count == 2
    assert query_pairs(route.calls[0].request) == [("page[limit]", "500")]


def test_activities_list_not_found_exit_4(invoke, api):
    api.get("/workspaces/acme/objects/person/records/nope/activities").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Record not found"}]}
        )
    )
    result = invoke("activities", "list", "person", "nope")
    assert result.exit_code == 4
    assert "HTTP 404" in result.stderr and "Record not found" in result.stderr


def test_activities_list_requires_record(invoke):
    result = invoke("activities", "list", "person")
    assert result.exit_code == 2
