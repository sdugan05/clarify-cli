from __future__ import annotations

import json

import httpx

from helpers import json_body, page, query_pairs, resource


def test_api_get_with_params(invoke, api):
    route = api.get("/workspaces/acme/objects/person/resources").mock(
        return_value=httpx.Response(200, json=page([resource("person", "1")]))
    )
    result = invoke(
        "api", "get", "/objects/person/resources", "-P", "page[limit]=5", "-P", "filter[name]=*S*"
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"][0]["id"] == "1"
    assert query_pairs(route.calls.last.request) == [("page[limit]", "5"), ("filter[name]", "*S*")]


def test_api_post_with_body_silent_and_header(invoke, api):
    route = api.post("/workspaces/acme/comments").mock(
        return_value=httpx.Response(201, json={"data": {"id": "c"}})
    )
    result = invoke(
        "--silent", "api", "POST", "/comments", "-d", '{"message": "hi"}', "-H", "X-Test: 1"
    )
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert json_body(request) == {"message": "hi"}
    assert query_pairs(request) == [("silent", "true")]
    assert request.headers["X-Test"] == "1"


def test_api_silent_not_applied_to_get(invoke, api):
    route = api.get("/workspaces/acme/users").mock(return_value=httpx.Response(200, json=page([])))
    assert invoke("--silent", "api", "GET", "/users").exit_code == 0
    assert query_pairs(route.calls.last.request) == []


def test_api_all_follows_links(invoke, api):
    base = "https://api.clarify.ai/v1/workspaces/acme/users"
    api.get("/workspaces/acme/users").mock(
        side_effect=[
            httpx.Response(
                200,
                json=page([resource("user", "1")], total=2, next_url=f"{base}?page%5Boffset%5D=1"),
            ),
            httpx.Response(200, json=page([resource("user", "2")], total=2)),
        ]
    )
    result = invoke("api", "GET", "/users", "--all")
    assert result.exit_code == 0, result.output
    assert [r["id"] for r in json.loads(result.stdout)["data"]] == ["1", "2"]


def test_api_full_url_and_text_response(invoke, api):
    api.post("/workspaces/acme/objects/deal/lists/l1/rows/csv").mock(
        return_value=httpx.Response(200, text="a,b\n1,2\n", headers={"content-type": "text/csv"})
    )
    result = invoke(
        "api",
        "post",
        "https://api.clarify.ai/v1/workspaces/acme/objects/deal/lists/l1/rows/csv",
        "-d",
        "{}",
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == "a,b\n1,2\n"


def test_api_out_file(invoke, api, tmp_path):
    api.get("/workspaces/acme/users").mock(return_value=httpx.Response(200, json={"data": []}))
    target = tmp_path / "out.json"
    result = invoke("api", "GET", "/users", "--out", str(target))
    assert result.exit_code == 0, result.output
    assert json.loads(target.read_text()) == {"data": []}


def test_api_empty_body(invoke, api):
    api.delete("/workspaces/acme/lists/1").mock(return_value=httpx.Response(202))
    result = invoke("api", "DELETE", "/lists/1")
    assert result.exit_code == 0 and result.stdout == ""
    assert "202" in result.stderr


def test_api_rejects_bad_method_and_all_on_post(invoke, api):
    assert invoke("api", "FETCH", "/users").exit_code == 2
    assert invoke("api", "POST", "/users", "--all").exit_code == 2
    assert invoke("api", "GET", "/users", "-H", "bad").exit_code == 2
