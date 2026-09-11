from __future__ import annotations

import json

import httpx
import pytest

from clarify_cli.commands.relationships import default_type
from helpers import json_body, page, query_pairs, resource

PATH = "/workspaces/acme/objects/person/records/p1/relationships/deals"


# -- list -------------------------------------------------------------------


def test_relationships_list_defaults(invoke, api):
    route = api.get(PATH).mock(
        return_value=httpx.Response(200, json=page([resource("resource", "d1", name="Big")]))
    )
    result = invoke("relationships", "list", "person", "p1", "deals")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["data"][0]["id"] == "d1"
    assert body["meta"] == {"total_records": 1, "returned": 1}
    request = route.calls.last.request
    assert request.method == "GET"
    assert request.url.path == "/v1" + PATH
    assert query_pairs(request) == [("page[limit]", "50")]


def test_relationships_list_options(invoke, api):
    route = api.get(PATH).mock(return_value=httpx.Response(200, json=page([])))
    result = invoke(
        "relationships",
        "list",
        "person",
        "p1",
        "deals",
        "-n",
        "5",
        "--offset",
        "10",
        "-s",
        "-_created_at",
        "-i",
        "companies.deals",
    )
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [
        ("sortOrder[column]", "_created_at"),
        ("sortOrder[dir]", "DESC"),
        ("include", "companies.deals"),
        ("page[limit]", "5"),
        ("page[offset]", "10"),
    ]


def test_relationships_list_caps_page_size_at_endpoint_maximum(invoke, api):
    route = api.get(PATH).mock(return_value=httpx.Response(200, json=page([])))
    result = invoke("relationships", "list", "person", "p1", "deals", "-n", "600")
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [("page[limit]", "500")]


def test_relationships_list_all_follows_pages(invoke, api):
    base = f"https://api.clarify.ai/v1{PATH}"
    route = api.get(PATH).mock(
        side_effect=[
            httpx.Response(
                200,
                json=page(
                    [resource("resource", "d1")], total=2, next_url=f"{base}?page%5Boffset%5D=1"
                ),
            ),
            httpx.Response(200, json=page([resource("resource", "d2")], total=2)),
        ]
    )
    result = invoke("-o", "ndjson", "relationships", "list", "person", "p1", "deals", "--all")
    assert result.exit_code == 0, result.output
    assert [json.loads(line)["id"] for line in result.stdout.splitlines()] == ["d1", "d2"]
    assert route.call_count == 2


def test_relationships_list_not_found_exit_4(invoke, api):
    api.get("/workspaces/acme/objects/person/records/nope/relationships/deals").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Record not found"}]}
        )
    )
    result = invoke("relationships", "list", "person", "nope", "deals")
    assert result.exit_code == 4
    assert "HTTP 404" in result.stderr and "Record not found" in result.stderr


# -- type derivation --------------------------------------------------------


@pytest.mark.parametrize(
    ("relationship", "expected"),
    [
        ("deals", "deal"),
        ("companies", "company"),
        ("people", "person"),
        ("company_id", "company"),
        ("deal_ids", "deal"),
        ("c_sales_orders", "c_sales_order"),
        ("meeting", "meeting"),
    ],
)
def test_default_type(relationship, expected):
    assert default_type(relationship) == expected


# -- set --------------------------------------------------------------------


def test_relationships_set_ids_with_explicit_type(invoke, api):
    route = api.patch(PATH).mock(return_value=httpx.Response(200))
    result = invoke(
        "relationships",
        "set",
        "person",
        "p1",
        "deals",
        "--id",
        "d1",
        "--id",
        "d2",
        "--type",
        "deal",
    )
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert request.method == "PATCH"
    assert request.url.path == "/v1" + PATH
    assert query_pairs(request) == []
    assert json_body(request) == {
        "data": [{"type": "deal", "id": "d1"}, {"type": "deal", "id": "d2"}]
    }
    assert result.stdout == ""
    assert "Updated deals on person p1 (2 item(s))" in result.stderr


def test_relationships_set_derives_type_from_field(invoke, api):
    path = "/workspaces/acme/objects/person/records/p1/relationships/company_id"
    route = api.patch(path).mock(return_value=httpx.Response(200, json={}))
    result = invoke("relationships", "set", "person", "p1", "company_id", "--id", "c1")
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {"data": [{"type": "company", "id": "c1"}]}
    assert result.stdout == ""
    assert "Updated company_id on person p1" in result.stderr


def test_relationships_set_silent(invoke, api):
    route = api.patch(PATH).mock(return_value=httpx.Response(200))
    result = invoke("--silent", "relationships", "set", "person", "p1", "deals", "--id", "d1")
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [("silent", "true")]


def test_relationships_set_clear_only(invoke, api):
    path = "/workspaces/acme/objects/person/records/p1/relationships/company_id"
    route = api.patch(path).mock(return_value=httpx.Response(200))
    result = invoke("-y", "relationships", "set", "person", "p1", "company_id", "--clear")
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {"data": [{"type": "company", "id": None}]}


def test_relationships_set_clear_then_ids(invoke, api):
    path = "/workspaces/acme/objects/company/records/c1/relationships/people"
    route = api.patch(path).mock(return_value=httpx.Response(200))
    result = invoke(
        "--yes", "relationships", "set", "company", "c1", "people", "--clear", "--id", "x1"
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "data": [{"type": "person", "id": None}, {"type": "person", "id": "x1"}]
    }


def test_relationships_set_clear_requires_confirmation(invoke, api):
    route = api.patch(PATH).mock(return_value=httpx.Response(200))
    result = invoke("relationships", "set", "person", "p1", "deals", "--clear")
    assert result.exit_code == 2
    assert "Refusing to continue without confirmation" in result.stderr
    assert not route.called


def test_relationships_set_data_document_passthrough(invoke, api):
    route = api.patch(PATH).mock(return_value=httpx.Response(200))
    document = {"data": [{"type": "deal", "id": "d1"}, {"type": "deal", "id": None}]}
    result = invoke(
        "-y", "relationships", "set", "person", "p1", "deals", "--data", json.dumps(document)
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == document


UNLINK_ALL_BODIES = [
    "[]",
    '{"data": []}',
    '[{"type": "deal", "id": null}]',
    '{"data": [{"type": "deal", "id": "d1"}, {"type": "deal", "id": null}]}',
]


@pytest.mark.parametrize("data", UNLINK_ALL_BODIES)
def test_relationships_set_data_unlink_all_requires_confirmation(invoke, api, data):
    route = api.patch(PATH).mock(return_value=httpx.Response(200))
    result = invoke("relationships", "set", "person", "p1", "deals", "--data", data)
    assert result.exit_code == 2
    assert "Refusing to continue without confirmation" in result.stderr
    assert "--yes" in result.stderr
    assert not route.called


@pytest.mark.parametrize("data", UNLINK_ALL_BODIES)
def test_relationships_set_data_unlink_all_with_yes(invoke, api, data):
    route = api.patch(PATH).mock(return_value=httpx.Response(200))
    result = invoke("-y", "relationships", "set", "person", "p1", "deals", "--data", data)
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert request.method == "PATCH"
    assert request.url.path == "/v1" + PATH
    parsed = json.loads(data)
    expected = parsed if isinstance(parsed, dict) else {"data": parsed}
    assert json_body(request) == expected


def test_relationships_set_data_with_ids_does_not_prompt(invoke, api):
    route = api.patch(PATH).mock(return_value=httpx.Response(200))
    result = invoke(
        "relationships",
        "set",
        "person",
        "p1",
        "deals",
        "--data",
        '[{"type": "deal", "id": "d1"}, {"type": "deal", "id": "d2"}]',
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "data": [{"type": "deal", "id": "d1"}, {"type": "deal", "id": "d2"}]
    }


def test_relationships_set_data_bare_array_is_wrapped(invoke, api):
    route = api.patch(PATH).mock(return_value=httpx.Response(200))
    result = invoke(
        "relationships", "set", "person", "p1", "deals", "-d", '[{"type": "deal", "id": "d1"}]'
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {"data": [{"type": "deal", "id": "d1"}]}


def test_relationships_set_data_single_object_is_wrapped(invoke, api):
    route = api.patch(PATH).mock(return_value=httpx.Response(200))
    result = invoke(
        "relationships", "set", "person", "p1", "deals", "-d", '{"type": "deal", "id": "d1"}'
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {"data": [{"type": "deal", "id": "d1"}]}


def test_relationships_set_data_from_file_and_stdin(invoke, api, tmp_path):
    route = api.patch(PATH).mock(return_value=httpx.Response(200))
    document = {"data": [{"type": "deal", "id": "d1"}]}
    path = tmp_path / "deals.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    result = invoke("relationships", "set", "person", "p1", "deals", "--data", f"@{path}")
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == document

    result = invoke(
        "relationships", "set", "person", "p1", "deals", "--data", "-", input=json.dumps(document)
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == document


def test_relationships_set_emits_returned_body(invoke, api):
    payload = {"data": [{"type": "deal", "id": "d1", "attributes": {"name": "Big"}}]}
    api.patch(PATH).mock(return_value=httpx.Response(200, json=payload))
    result = invoke("relationships", "set", "person", "p1", "deals", "--id", "d1")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == payload


def test_relationships_set_requires_input(invoke, api):
    route = api.patch(PATH).mock(return_value=httpx.Response(200))
    result = invoke("relationships", "set", "person", "p1", "deals")
    assert result.exit_code == 2
    assert "--id" in result.stderr and "--clear" in result.stderr and "--data" in result.stderr
    assert not route.called


@pytest.mark.parametrize(
    "extra",
    [("--id", "d1"), ("--type", "deal"), ("--clear",)],
)
def test_relationships_set_rejects_data_with_builder_options(invoke, api, extra):
    route = api.patch(PATH).mock(return_value=httpx.Response(200))
    result = invoke(
        "-y", "relationships", "set", "person", "p1", "deals", "--data", '{"data": []}', *extra
    )
    assert result.exit_code == 2
    assert "--data cannot be combined" in result.stderr
    assert not route.called


@pytest.mark.parametrize("data", ["not json", '"string"', "42"])
def test_relationships_set_rejects_bad_data(invoke, api, data):
    route = api.patch(PATH).mock(return_value=httpx.Response(200))
    result = invoke("relationships", "set", "person", "p1", "deals", "--data", data)
    assert result.exit_code == 2
    assert not route.called


def test_relationships_set_api_error_exit_1(invoke, api):
    api.patch(PATH).mock(
        return_value=httpx.Response(
            422,
            json={
                "errors": [
                    {
                        "status": "422",
                        "detail": "Unknown relationship",
                        "source": {"pointer": "/data/0/type"},
                    }
                ]
            },
        )
    )
    result = invoke("relationships", "set", "person", "p1", "deals", "--id", "d1")
    assert result.exit_code == 1
    assert "HTTP 422" in result.stderr and "Unknown relationship" in result.stderr
    assert "/data/0/type" in result.stderr


# -- unlink -----------------------------------------------------------------


def test_relationships_unlink_ids(invoke, api):
    route = api.delete(PATH).mock(return_value=httpx.Response(200))
    result = invoke("-y", "relationships", "unlink", "person", "p1", "deals", "--id", "d1")
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert request.method == "DELETE"
    assert request.url.path == "/v1" + PATH
    assert query_pairs(request) == []
    assert json_body(request) == {"data": [{"type": "deal", "id": "d1"}]}
    assert result.stdout == ""
    assert "Unlinked 1 record(s) from deals on person p1" in result.stderr


def test_relationships_unlink_explicit_type_and_silent(invoke, api):
    path = "/workspaces/acme/objects/deal/records/d1/relationships/contacts"
    route = api.delete(path).mock(return_value=httpx.Response(200))
    result = invoke(
        "--silent",
        "--yes",
        "relationships",
        "unlink",
        "deal",
        "d1",
        "contacts",
        "--id",
        "p1",
        "--id",
        "p2",
        "--type",
        "person",
    )
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {
        "data": [{"type": "person", "id": "p1"}, {"type": "person", "id": "p2"}]
    }


def test_relationships_unlink_data(invoke, api):
    route = api.delete(PATH).mock(return_value=httpx.Response(200))
    document = {"data": [{"type": "deal", "id": "d1"}]}
    result = invoke(
        "-y", "relationships", "unlink", "person", "p1", "deals", "--data", json.dumps(document)
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == document


def test_relationships_unlink_requires_confirmation(invoke, api):
    route = api.delete(PATH).mock(return_value=httpx.Response(200))
    result = invoke("relationships", "unlink", "person", "p1", "deals", "--id", "d1")
    assert result.exit_code == 2
    assert "Refusing to continue without confirmation" in result.stderr
    assert "--yes" in result.stderr
    assert not route.called


def test_relationships_unlink_requires_input(invoke, api):
    route = api.delete(PATH).mock(return_value=httpx.Response(200))
    result = invoke("-y", "relationships", "unlink", "person", "p1", "deals")
    assert result.exit_code == 2
    assert not route.called


def test_relationships_unlink_has_no_clear_option(invoke, api):
    route = api.delete(PATH).mock(return_value=httpx.Response(200))
    result = invoke("-y", "relationships", "unlink", "person", "p1", "deals", "--clear")
    assert result.exit_code == 2
    assert not route.called


def test_relationships_unlink_not_found_exit_4(invoke, api):
    api.delete(PATH).mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Record not found"}]}
        )
    )
    result = invoke("-y", "relationships", "unlink", "person", "p1", "deals", "--id", "d1")
    assert result.exit_code == 4
    assert "HTTP 404" in result.stderr
