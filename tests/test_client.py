from __future__ import annotations

import httpx
import pytest
import respx

from clarify_cli.client import ClarifyClient, normalize_params
from clarify_cli.errors import (
    EXIT_AUTH,
    EXIT_GENERAL,
    EXIT_NOT_FOUND,
    EXIT_RATE_LIMITED,
    APIError,
    ClarifyError,
    ConfigError,
)
from helpers import page, query_pairs, resource

BASE = "https://api.clarify.ai/v1"


@pytest.fixture
def client():
    with ClarifyClient(base_url=BASE, api_key="k", workspace="acme", sleep=lambda _s: None) as c:
        yield c


def test_normalize_params_handles_mappings_lists_and_none():
    pairs = normalize_params({"a": 1, "b": None, "c": ["x", "y"], "d": True})
    assert pairs == [("a", "1"), ("c", "x"), ("c", "y"), ("d", "true")]
    assert normalize_params(None) == []
    assert normalize_params([("k", "v")]) == [("k", "v")]


def test_url_for_variants(client):
    assert client.url_for("/users") == f"{BASE}/workspaces/acme/users"
    assert client.url_for("users") == f"{BASE}/workspaces/acme/users"
    assert client.url_for("/workspaces/other/users") == f"{BASE}/workspaces/other/users"
    assert client.url_for("https://elsewhere/x?y=1") == "https://elsewhere/x?y=1"


def test_url_for_requires_workspace():
    c = ClarifyClient(base_url=BASE, api_key="k", workspace=None)
    with pytest.raises(ConfigError):
        c.url_for("/users")


def test_sends_api_key_scheme_and_brackets(api, client):
    route = api.get("/workspaces/acme/users").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    body = client.get("/users", params=[("page[limit]", "5"), ("filter[a][Is]", "x y")])
    assert body == {"data": []}
    request = route.calls.last.request
    assert request.headers["Authorization"] == "api-key k"
    assert request.headers["User-Agent"].startswith("clarify-cli/")
    assert request.headers["Accept"] == "application/json"
    assert query_pairs(request) == [("page[limit]", "5"), ("filter[a][Is]", "x y")]
    assert "page%5Blimit%5D=5" in str(request.url)


def test_silent_adds_query_param(api, client):
    route = api.post("/workspaces/acme/comments").mock(
        return_value=httpx.Response(201, json={"ok": 1})
    )
    client.post("/comments", json_body={"x": 1}, silent=True)
    assert query_pairs(route.calls.last.request) == [("silent", "true")]


def test_empty_body_returns_none(api, client):
    api.delete("/workspaces/acme/lists/1").mock(return_value=httpx.Response(202))
    assert client.delete("/lists/1") is None


def test_non_json_body_returns_text(api, client):
    api.post("/workspaces/acme/csv").mock(
        return_value=httpx.Response(200, text="a,b\n1,2\n", headers={"content-type": "text/csv"})
    )
    assert client.post("/csv", json_body={}) == "a,b\n1,2\n"


def test_retries_429_using_retry_after(api):
    sleeps: list[float] = []
    c = ClarifyClient(base_url=BASE, api_key="k", workspace="acme", sleep=sleeps.append)
    route = api.get("/workspaces/acme/users").mock(
        side_effect=[
            httpx.Response(
                429,
                json={"errors": [{"status": "429", "detail": "slow down"}]},
                headers={"Retry-After": "7"},
            ),
            httpx.Response(429, json={"errors": []}),
            httpx.Response(200, json={"data": []}),
        ]
    )
    assert c.get("/users") == {"data": []}
    assert route.call_count == 3
    assert sleeps == [7.0, 2.0]  # Retry-After honoured, then exponential fallback (2**1)


def test_429_gives_up_after_max_retries(api):
    c = ClarifyClient(
        base_url=BASE, api_key="k", workspace="acme", max_retries=1, sleep=lambda _s: None
    )
    route = api.get("/workspaces/acme/users").mock(
        return_value=httpx.Response(
            429, json={"errors": [{"status": "429", "detail": "API rate limit exceeded"}]}
        )
    )
    with pytest.raises(APIError) as exc:
        c.get("/users")
    assert route.call_count == 2
    assert exc.value.exit_code == EXIT_RATE_LIMITED
    assert "rate limit" in exc.value.message.lower()


def test_5xx_retried_only_for_get(api):
    c = ClarifyClient(base_url=BASE, api_key="k", workspace="acme", sleep=lambda _s: None)
    get_route = api.get("/workspaces/acme/users").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"data": []})]
    )
    assert c.get("/users") == {"data": []}
    assert get_route.call_count == 2
    post_route = api.post("/workspaces/acme/comments").mock(
        return_value=httpx.Response(503, text="boom")
    )
    with pytest.raises(APIError) as exc:
        c.post("/comments", json_body={})
    assert post_route.call_count == 1
    assert exc.value.status == 503 and "boom" in exc.value.message


def test_error_parsing_and_exit_codes(api, client):
    api.post("/workspaces/acme/objects/person/records").mock(
        return_value=httpx.Response(
            422,
            json={
                "errors": [
                    {
                        "status": "422",
                        "title": "Invalid input",
                        "detail": "/data/attributes/email: invalid email",
                        "source": {"pointer": "/data/attributes/email"},
                    }
                ]
            },
        )
    )
    with pytest.raises(APIError) as exc:
        client.post("/objects/person/records", json_body={})
    err = exc.value
    assert err.status == 422 and err.exit_code == EXIT_GENERAL
    assert "HTTP 422 from POST" in err.message
    assert "Invalid input: /data/attributes/email: invalid email" in err.message
    assert err.errors[0]["source"]["pointer"] == "/data/attributes/email"

    api.get("/workspaces/acme/users/u").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Workspace not found"}]}
        )
    )
    with pytest.raises(APIError) as exc:
        client.get("/users/u")
    assert exc.value.exit_code == EXIT_NOT_FOUND and "workspace slug" in (exc.value.hint or "")

    api.get("/workspaces/acme/users/x").mock(
        return_value=httpx.Response(
            401, json={"errors": [{"status": "401", "detail": "Unauthorized"}]}
        )
    )
    with pytest.raises(APIError) as exc:
        client.get("/users/x")
    assert exc.value.exit_code == EXIT_AUTH and "api-key" in (exc.value.hint or "")


def test_error_parsing_nest_style_message(api, client):
    api.get("/workspaces/acme/users/n").mock(
        return_value=httpx.Response(
            400, json={"statusCode": 400, "message": ["x must be a string"], "error": "Bad Request"}
        )
    )
    with pytest.raises(APIError) as exc:
        client.get("/users/n")
    assert "x must be a string" in exc.value.message


def test_transport_errors_become_clarify_errors(api, client):
    api.get("/workspaces/acme/users").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(ClarifyError) as exc:
        client.get("/users")
    assert "Connection error" in exc.value.message
    api.get("/workspaces/acme/users").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ClarifyError) as exc:
        client.get("/users")
    assert "timed out" in exc.value.message


def test_collect_pages_by_offset_and_merges(api, client):
    next_url = (
        f"{BASE}/workspaces/acme/objects/person/resources?page%5Blimit%5D=2&page%5Boffset%5D=2"
    )
    first = page(
        [resource("person", "1", name="A"), resource("person", "2", name="B")],
        total=3,
        next_url=next_url,
        included=[resource("company", "c1")],
    )
    second = page(
        [resource("person", "3", name="C")],
        total=3,
        included=[resource("company", "c1"), resource("company", "c2")],
    )
    route = api.get("/workspaces/acme/objects/person/resources").mock(
        side_effect=[httpx.Response(200, json=first), httpx.Response(200, json=second)]
    )
    out = client.collect("/objects/person/resources", [("filter[x]", "1")], all_pages=True)
    assert [r["id"] for r in out["data"]] == ["1", "2", "3"]
    assert [r["id"] for r in out["included"]] == ["c1", "c2"]
    assert out["meta"] == {"total_records": 3, "returned": 3}
    assert "links" not in out
    assert query_pairs(route.calls[0].request) == [("filter[x]", "1"), ("page[limit]", "500")]
    # the next page re-sends our query with page[offset] advanced by the server's limit
    assert query_pairs(route.calls[1].request) == [
        ("filter[x]", "1"),
        ("page[limit]", "500"),
        ("page[offset]", "2"),
    ]


def test_pages_stay_on_base_url_when_next_link_is_http(api, client):
    """The live API emits ``links.next`` as plain http, which does not answer."""
    http_next = (
        "http://api.clarify.ai/v1/workspaces/acme/objects/deal/resources"
        "?page%5Boffset%5D=1&page%5Blimit%5D=1&filter%5Bname%5D=%2Aa%2A"
    )
    route = api.get("/workspaces/acme/objects/deal/resources").mock(
        side_effect=[
            httpx.Response(200, json=page([resource("deal", "1")], total=2, next_url=http_next)),
            httpx.Response(200, json=page([resource("deal", "2")], total=2)),
        ]
    )
    out = client.collect(
        "/objects/deal/resources", [("filter[name]", "*a*")], all_pages=True, page_size=1
    )
    assert [r["id"] for r in out["data"]] == ["1", "2"]
    assert route.call_count == 2
    second = route.calls[1].request
    assert second.url.scheme == "https" and second.url.host == "api.clarify.ai"
    assert query_pairs(second) == [
        ("filter[name]", "*a*"),
        ("page[limit]", "1"),
        ("page[offset]", "1"),
    ]


def test_pages_advance_from_an_explicit_offset(api, client):
    first = page(
        [resource("user", "4")],
        total=5,
        next_url=f"{BASE}/workspaces/acme/users?page%5Boffset%5D=4&page%5Blimit%5D=1",
    )
    first["meta"]["offset"] = 3
    route = api.get("/workspaces/acme/users").mock(
        side_effect=[
            httpx.Response(200, json=first),
            httpx.Response(200, json=page([resource("user", "5")], total=5)),
        ]
    )
    ids = [r["id"] for p in client.pages("/users", page_size=1, offset=3) for r in p["data"]]
    assert ids == ["4", "5"]
    assert query_pairs(route.calls[0].request) == [("page[limit]", "1"), ("page[offset]", "3")]
    assert query_pairs(route.calls[1].request) == [("page[limit]", "1"), ("page[offset]", "4")]


def test_pages_follow_next_links_without_offset_meta_on_base_scheme(api, client):
    route = api.get("/workspaces/acme/schemas").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "data": [resource("schema", "a")],
                    "links": {
                        "next": "http://api.clarify.ai/v1/workspaces/acme/schemas?cursor=abc"
                    },
                },
            ),
            httpx.Response(200, json={"data": [resource("schema", "b")], "links": {"next": None}}),
        ]
    )
    ids = [r["id"] for p in client.pages("/schemas") for r in p["data"]]
    assert ids == ["a", "b"]
    assert str(route.calls[1].request.url) == f"{BASE}/workspaces/acme/schemas?cursor=abc"


def test_pages_leave_next_links_on_other_hosts_alone(api, client):
    api.get("/workspaces/acme/schemas").mock(
        return_value=httpx.Response(
            200,
            json={"data": [resource("schema", "a")], "links": {"next": "https://elsewhere/x?y=1"}},
        )
    )
    with respx.mock(assert_all_mocked=True) as other:
        route = other.get("https://elsewhere/x").mock(
            return_value=httpx.Response(200, json={"data": [resource("schema", "b")]})
        )
        ids = [r["id"] for p in client.pages("/schemas") for r in p["data"]]
    assert ids == ["a", "b"]
    assert str(route.calls.last.request.url) == "https://elsewhere/x?y=1"


def test_pages_stop_at_total_records_empty_data_or_stalled_offset(api, client):
    base = f"{BASE}/workspaces/acme/users"
    # meta says every record was returned: a stray next link is not followed
    route = api.get("/workspaces/acme/users").mock(
        return_value=httpx.Response(
            200,
            json=page(
                [resource("user", "1"), resource("user", "2")],
                total=2,
                next_url=f"{base}?page%5Boffset%5D=2",
            ),
        )
    )
    assert len(list(client.pages("/users", page_size=2))) == 1
    # an empty page ends iteration even when the API still advertises a next link
    route.mock(
        return_value=httpx.Response(
            200, json=page([], total=5, next_url=f"{base}?page%5Boffset%5D=1")
        )
    )
    assert len(list(client.pages("/users"))) == 1
    # an offset that does not advance (page[offset] ignored) ends iteration
    route.mock(
        return_value=httpx.Response(
            200, json=page([resource("user", "1")], total=5, next_url=f"{base}?page%5Boffset%5D=1")
        )
    )
    assert len(list(client.pages("/users"))) == 2
    assert route.call_count == 4


def test_collect_limit_bounds_page_size_and_truncates(api, client):
    route = api.get("/workspaces/acme/users").mock(
        return_value=httpx.Response(
            200,
            json=page(
                [resource("user", str(i)) for i in range(5)],
                total=50,
                next_url=f"{BASE}/workspaces/acme/users?page%5Boffset%5D=5",
            ),
        )
    )
    out = client.collect("/users", limit=3, offset=10)
    assert len(out["data"]) == 3 and out["meta"]["returned"] == 3
    assert route.call_count == 1
    assert query_pairs(route.calls.last.request) == [("page[limit]", "3"), ("page[offset]", "10")]


def test_collect_explicit_page_size(api, client):
    route = api.get("/workspaces/acme/users").mock(return_value=httpx.Response(200, json=page([])))
    client.collect("/users", limit=50, page_size=7)
    assert query_pairs(route.calls.last.request) == [("page[limit]", "7")]


def test_collect_caps_explicit_page_size_at_500(api, client):
    route = api.get("/workspaces/acme/users").mock(return_value=httpx.Response(200, json=page([])))
    client.collect("/users", limit=50, page_size=900)
    assert query_pairs(route.calls.last.request) == [("page[limit]", "500")]


def test_empty_object_body_is_treated_as_empty(api, client):
    api.delete("/workspaces/acme/objects/person/records/1").mock(
        return_value=httpx.Response(200, json={})
    )
    assert client.delete("/objects/person/records/1") is None
