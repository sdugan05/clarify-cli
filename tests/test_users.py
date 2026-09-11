from __future__ import annotations

import json

import httpx

from helpers import page, query_pairs, resource


def test_users_list_defaults(invoke, api):
    route = api.get("/workspaces/acme/users").mock(
        return_value=httpx.Response(
            200, json=page([resource("user", "u1", name="Ann", roles=["admin"])], total=1)
        )
    )
    result = invoke("users", "list")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["data"][0]["id"] == "u1" and body["meta"] == {"total_records": 1, "returned": 1}
    assert query_pairs(route.calls.last.request) == [("page[limit]", "50")]


def test_users_list_options(invoke, api):
    route = api.get("/workspaces/acme/users").mock(return_value=httpx.Response(200, json=page([])))
    result = invoke(
        "users", "list", "-n", "5", "--offset", "10", "--sort", "name:desc", "--page-size", "2"
    )
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [
        ("sortOrder[column]", "name"),
        ("sortOrder[dir]", "DESC"),
        ("page[limit]", "2"),
        ("page[offset]", "10"),
    ]


def test_users_list_all_follows_pages(invoke, api):
    base = "https://api.clarify.ai/v1/workspaces/acme/users"
    route = api.get("/workspaces/acme/users").mock(
        side_effect=[
            httpx.Response(
                200,
                json=page([resource("user", "1")], total=2, next_url=f"{base}?page%5Boffset%5D=1"),
            ),
            httpx.Response(200, json=page([resource("user", "2")], total=2)),
        ]
    )
    result = invoke("-o", "ndjson", "users", "list", "--all")
    assert result.exit_code == 0, result.output
    assert [json.loads(line)["id"] for line in result.stdout.splitlines()] == ["1", "2"]
    assert route.call_count == 2


def test_users_get(invoke, api):
    route = api.get("/workspaces/acme/users/u9").mock(
        return_value=httpx.Response(200, json={"data": resource("user", "u9", name="Bo")})
    )
    result = invoke("users", "get", "u9")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["id"] == "u9"
    assert route.called


def test_users_get_not_found_exit_4(invoke, api):
    api.get("/workspaces/acme/users/nope").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "User not found"}]}
        )
    )
    result = invoke("users", "get", "nope")
    assert result.exit_code == 4
    assert "HTTP 404" in result.stderr and "User not found" in result.stderr
