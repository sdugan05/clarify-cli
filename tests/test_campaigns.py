from __future__ import annotations

import json

import httpx

from helpers import page, query_pairs, resource

CAMPAIGN = "9a1f3b7e-2c4d-4e5f-8a6b-7c8d9e0f1a2b"
PATH = f"/workspaces/acme/campaigns/{CAMPAIGN}/recipients"
#: Captured requests carry the base URL's /v1 prefix in their path.
FULL_PATH = f"/v1{PATH}"


def recipient(id_: str, **overrides):
    attrs = {
        "workflow_run_id": id_,
        "person": {"_id": f"p-{id_}", "name": {"full_name": "Jane Doe"}},
        "status": "success",
        "has_opened": True,
        "has_clicked": False,
        "has_replied": False,
        "has_unsubscribed": False,
        "_created_at": "2026-01-15T09:30:00.000Z",
    }
    attrs.update(overrides)
    return resource("campaign_recipient", id_, **attrs)


def test_recipients_defaults(invoke, api):
    route = api.get(PATH).mock(
        return_value=httpx.Response(200, json=page([recipient("r1")], total=1))
    )
    result = invoke("campaigns", "recipients", CAMPAIGN)
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["data"][0]["id"] == "r1"
    assert body["data"][0]["type"] == "campaign_recipient"
    assert body["meta"] == {"total_records": 1, "returned": 1}
    request = route.calls.last.request
    assert request.method == "GET"
    assert request.url.path == FULL_PATH
    assert query_pairs(request) == [("page[limit]", "50")]


def test_recipients_filters_sort_and_paging(invoke, api):
    route = api.get(PATH).mock(return_value=httpx.Response(200, json=page([])))
    result = invoke(
        "campaigns",
        "recipients",
        CAMPAIGN,
        "-f",
        "event=clicked,replied",
        "-f",
        "status=completed",
        "-f",
        "q=jane",
        "-s",
        "_created_at:desc",
        "-n",
        "5",
        "--offset",
        "10",
    )
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [
        ("filter[event]", "clicked,replied"),
        ("filter[status]", "completed"),
        ("filter[q]", "jane"),
        ("sortOrder[column]", "_created_at"),
        ("sortOrder[dir]", "DESC"),
        ("page[limit]", "5"),
        ("page[offset]", "10"),
    ]


def test_recipients_page_size_capped_at_500(invoke, api):
    route = api.get(PATH).mock(return_value=httpx.Response(200, json=page([])))
    result = invoke("campaigns", "recipients", CAMPAIGN, "-n", "1000")
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [("page[limit]", "500")]


def test_recipients_explicit_page_size_is_respected(invoke, api):
    route = api.get(PATH).mock(return_value=httpx.Response(200, json=page([])))
    result = invoke("campaigns", "recipients", CAMPAIGN, "--page-size", "25")
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [("page[limit]", "25")]


def test_recipients_all_follows_pages(invoke, api):
    base = f"https://api.clarify.ai/v1{PATH}"
    route = api.get(PATH).mock(
        side_effect=[
            httpx.Response(
                200,
                json=page([recipient("1")], total=2, next_url=f"{base}?page%5Boffset%5D=1"),
            ),
            httpx.Response(200, json=page([recipient("2")], total=2)),
        ]
    )
    result = invoke("-o", "ndjson", "campaigns", "recipients", CAMPAIGN, "--all")
    assert result.exit_code == 0, result.output
    assert [json.loads(line)["id"] for line in result.stdout.splitlines()] == ["1", "2"]
    assert route.call_count == 2
    assert query_pairs(route.calls[0].request) == [("page[limit]", "500")]


def test_recipients_no_unsupported_options(invoke):
    for flag in ("--include", "--search"):
        result = invoke("campaigns", "recipients", CAMPAIGN, flag, "x")
        assert result.exit_code == 2, flag


def test_recipients_invalid_filter_is_usage_error(invoke, api):
    route = api.get(PATH).mock(return_value=httpx.Response(200, json=page([])))
    result = invoke("campaigns", "recipients", CAMPAIGN, "-f", "novalue")
    assert result.exit_code == 2
    assert "Invalid --filter" in result.stderr
    assert not route.called


def test_recipients_not_found_exit_4(invoke, api):
    api.get(PATH).mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Campaign not found"}]}
        )
    )
    result = invoke("campaigns", "recipients", CAMPAIGN)
    assert result.exit_code == 4
    assert "HTTP 404" in result.stderr and "Campaign not found" in result.stderr
