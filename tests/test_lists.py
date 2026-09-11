from __future__ import annotations

import json
from pathlib import Path

import httpx
from typer.main import get_command

from clarify_cli.commands import lists
from helpers import json_body, page, query_pairs, resource

LIST_ID = "9d2c4e6f-8a1b-4c3d-9e5f-7a9b1c3d5e7f"
LIST_PATH = f"/workspaces/acme/objects/deal/lists/{LIST_ID}"
OPERATIONS_FIXTURE = Path(__file__).parent / "fixtures" / "operations.json"


def list_resource(id_: str = LIST_ID, **overrides):
    attrs = {
        "_id": id_,
        "entity": "deal",
        "title": "Enterprise deals",
        "emoji": None,
        "description": "Open deals with enterprise accounts.",
        "type": "dynamic",
        "state": "published",
        "layout": "table",
        "options": {},
        "query": {"sql": "SELECT * FROM deal WHERE amount >= 50000"},
        "rank": 0,
    }
    attrs.update(overrides)
    return resource("list", id_, **attrs)


# -- manifest --------------------------------------------------------------
def test_operations_manifest_covers_unit_and_names_real_commands():
    spec = json.loads(OPERATIONS_FIXTURE.read_text())
    expected = {
        op["operationId"]
        for op in spec
        if op["tag"] in ("Lists", "ListRows") or op["operationId"] == "getListResources"
    }
    assert set(lists.OPERATIONS) == expected
    registered = set(get_command(lists.app).commands)
    assert set(lists.OPERATIONS.values()) <= registered


# -- list ------------------------------------------------------------------
def test_list_workspace_wide_defaults(invoke, api):
    route = api.get("/workspaces/acme/lists").mock(
        return_value=httpx.Response(200, json=page([list_resource()], total=1))
    )
    result = invoke("lists", "list")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["data"][0]["id"] == LIST_ID
    assert body["meta"] == {"total_records": 1, "returned": 1}
    assert query_pairs(route.calls.last.request) == [("page[limit]", "50")]


def test_list_workspace_wide_filters_search_sort_paging(invoke, api):
    route = api.get("/workspaces/acme/lists").mock(return_value=httpx.Response(200, json=page([])))
    result = invoke(
        "lists",
        "list",
        "-f",
        "entity=deal,company",
        "-f",
        "type=static",
        "--search",
        "enterprise",
        "-s",
        "-_created_at",
        "-n",
        "5",
        "--offset",
        "10",
        "--page-size",
        "2",
    )
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [
        ("filter[entity]", "deal,company"),
        ("filter[type]", "static"),
        ("sortOrder[column]", "_created_at"),
        ("sortOrder[dir]", "DESC"),
        ("search", "enterprise"),
        ("page[limit]", "2"),
        ("page[offset]", "10"),
    ]


def test_list_for_object(invoke, api):
    route = api.get("/workspaces/acme/objects/deal/lists").mock(
        return_value=httpx.Response(200, json=page([list_resource()], total=1))
    )
    result = invoke("lists", "list", "deal", "-f", "type=dynamic", "-f", "state[Is]=published")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"][0]["attributes"]["type"] == "dynamic"
    assert query_pairs(route.calls.last.request) == [
        ("filter[type]", "dynamic"),
        ("filter[state][Is]", "published"),
        ("page[limit]", "50"),
    ]


def test_list_caps_page_limit_at_500(invoke, api):
    route = api.get("/workspaces/acme/lists").mock(return_value=httpx.Response(200, json=page([])))
    result = invoke("lists", "list", "-n", "1000")
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [("page[limit]", "500")]


def test_list_all_follows_next_links(invoke, api):
    base = "https://api.clarify.ai/v1/workspaces/acme/objects/deal/lists"
    route = api.get("/workspaces/acme/objects/deal/lists").mock(
        side_effect=[
            httpx.Response(
                200,
                json=page([list_resource("l1")], total=2, next_url=f"{base}?page%5Boffset%5D=1"),
            ),
            httpx.Response(200, json=page([list_resource("l2")], total=2)),
        ]
    )
    result = invoke("-o", "ndjson", "lists", "list", "deal", "--all")
    assert result.exit_code == 0, result.output
    assert [json.loads(line)["id"] for line in result.stdout.splitlines()] == ["l1", "l2"]
    assert route.call_count == 2
    assert query_pairs(route.calls[0].request) == [("page[limit]", "500")]


def test_list_rejects_bad_filter(invoke, api):
    result = invoke("lists", "list", "-f", "novalue")
    assert result.exit_code == 2
    assert "Invalid --filter" in result.stderr


# -- get -------------------------------------------------------------------
def test_get(invoke, api):
    route = api.get(LIST_PATH).mock(
        return_value=httpx.Response(200, json={"data": list_resource()})
    )
    result = invoke("lists", "get", "deal", LIST_ID)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["id"] == LIST_ID
    assert route.called
    assert query_pairs(route.calls.last.request) == []


def test_get_not_found_exit_4(invoke, api):
    api.get("/workspaces/acme/objects/deal/lists/nope").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "List not found"}]}
        )
    )
    result = invoke("lists", "get", "deal", "nope")
    assert result.exit_code == 4
    assert "HTTP 404" in result.stderr and "List not found" in result.stderr


# -- create ----------------------------------------------------------------
def test_create_with_convenience_flags(invoke, api):
    route = api.post("/workspaces/acme/objects/deal/lists").mock(
        return_value=httpx.Response(201, json={"data": list_resource()})
    )
    result = invoke(
        "--silent",
        "lists",
        "create",
        "deal",
        "--title",
        "Enterprise deals",
        "--description",
        "Open deals with enterprise accounts.",
        "--query",
        "SELECT * FROM deal WHERE amount >= 50000",
        "--emoji",
        "\U0001f3e2",
        "--layout",
        "board",
        "--type",
        "dynamic",
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["id"] == LIST_ID
    request = route.calls.last.request
    assert request.method == "POST"
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {
        "title": "Enterprise deals",
        "description": "Open deals with enterprise accounts.",
        "emoji": "\U0001f3e2",
        "layout": "board",
        "type": "dynamic",
        "query": {"sql": "SELECT * FROM deal WHERE amount >= 50000", "version": 6},
    }


def test_create_defaults_layout_and_type(invoke, api):
    route = api.post("/workspaces/acme/objects/person/lists").mock(
        return_value=httpx.Response(201, json={"data": list_resource(entity="person")})
    )
    result = invoke(
        "lists", "create", "person", "--title", "Prospects", "--description", "Hand-picked"
    )
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == []
    assert json_body(route.calls.last.request) == {
        "title": "Prospects",
        "description": "Hand-picked",
        "layout": "table",
        "type": "static",
    }


def test_create_infers_dynamic_from_query_and_merges_data_and_set(invoke, api, tmp_path):
    sql_file = tmp_path / "big.sql"
    sql_file.write_text("SELECT * FROM deal WHERE amount >= 50000\n")
    route = api.post("/workspaces/acme/objects/deal/lists").mock(
        return_value=httpx.Response(201, json={"data": list_resource()})
    )
    result = invoke(
        "lists",
        "create",
        "deal",
        "-d",
        '{"title": "Big deals", "description": "Over 50k", "options": {"hiddenPrimaryCell": true}}',
        "--query",
        f"@{sql_file}",
        "--set",
        "options.segmentedByInBoard=stage",
        "--set",
        "query.version=5",
        "--set",
        "state=draft",
        "--set",
        "rank=3",
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "title": "Big deals",
        "description": "Over 50k",
        "options": {"hiddenPrimaryCell": True, "segmentedByInBoard": "stage"},
        "query": {"sql": "SELECT * FROM deal WHERE amount >= 50000\n", "version": 5},
        "layout": "table",
        "type": "dynamic",
        "state": "draft",
        "rank": 3,
    }


def test_create_missing_required_fields_is_usage_error(invoke, api):
    route = api.post("/workspaces/acme/objects/deal/lists").mock(
        return_value=httpx.Response(201, json={"data": list_resource()})
    )
    result = invoke("lists", "create", "deal", "--title", "No description")
    assert result.exit_code == 2
    assert "description" in result.stderr
    assert not route.called


def test_create_rejects_non_object_body_and_bad_layout(invoke, api):
    assert invoke("lists", "create", "deal", "-d", "[1]").exit_code == 2
    assert invoke("lists", "create", "deal", "-d", "{not json").exit_code == 2
    result = invoke(
        "lists", "create", "deal", "--title", "x", "--description", "y", "--layout", "grid"
    )
    assert result.exit_code == 2


def test_create_api_error_exit_1(invoke, api):
    api.post("/workspaces/acme/objects/deal/lists").mock(
        return_value=httpx.Response(
            400,
            json={
                "errors": [
                    {
                        "status": "400",
                        "detail": "query.sql is invalid",
                        "source": {"pointer": "/query/sql"},
                    }
                ]
            },
        )
    )
    result = invoke("lists", "create", "deal", "--title", "t", "--description", "d", "--query", "x")
    assert result.exit_code == 1
    assert "HTTP 400" in result.stderr and "query.sql is invalid" in result.stderr


# -- update ----------------------------------------------------------------
def test_update_partial_body(invoke, api):
    route = api.patch(LIST_PATH).mock(
        return_value=httpx.Response(
            200, json={"data": list_resource(title="Enterprise deals (FY26)")}
        )
    )
    result = invoke(
        "--silent",
        "lists",
        "update",
        "deal",
        LIST_ID,
        "--title",
        "Enterprise deals (FY26)",
        "--set",
        "emoji=null",
        "--set",
        "rank=0",
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["attributes"]["title"] == "Enterprise deals (FY26)"
    request = route.calls.last.request
    assert request.method == "PATCH"
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {"title": "Enterprise deals (FY26)", "emoji": None, "rank": 0}


def test_update_query_from_stdin_and_layout(invoke, api):
    route = api.patch(LIST_PATH).mock(
        return_value=httpx.Response(200, json={"data": list_resource()})
    )
    result = invoke(
        "lists", "update", "deal", LIST_ID, "--query", "-", "--layout", "table", input="SELECT 1"
    )
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == []
    assert json_body(route.calls.last.request) == {
        "query": {"sql": "SELECT 1", "version": 6},
        "layout": "table",
    }


def test_update_without_fields_is_usage_error(invoke, api):
    route = api.patch(LIST_PATH).mock(
        return_value=httpx.Response(200, json={"data": list_resource()})
    )
    result = invoke("lists", "update", "deal", LIST_ID)
    assert result.exit_code == 2
    assert "Nothing to update" in result.stderr
    assert not route.called


# -- delete ----------------------------------------------------------------
def test_delete_with_yes_sends_delete_and_confirms_on_stderr(invoke, api):
    route = api.delete(LIST_PATH).mock(return_value=httpx.Response(202))
    result = invoke("--yes", "--silent", "lists", "delete", "deal", LIST_ID)
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert f"Deleted list {LIST_ID} on deal" in result.stderr
    request = route.calls.last.request
    assert request.method == "DELETE"
    assert query_pairs(request) == [("silent", "true")]
    assert request.content == b""


def test_delete_refuses_without_confirmation(invoke, api):
    route = api.delete(LIST_PATH).mock(return_value=httpx.Response(202))
    result = invoke("lists", "delete", "deal", LIST_ID)
    assert result.exit_code == 2
    assert "Refusing to continue without confirmation" in result.stderr
    assert not route.called


def test_delete_not_found_exit_4(invoke, api):
    api.delete(LIST_PATH).mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "List not found"}]}
        )
    )
    result = invoke("-y", "lists", "delete", "deal", LIST_ID)
    assert result.exit_code == 4
    assert "List not found" in result.stderr


# -- publish / unpublish ---------------------------------------------------
def test_publish(invoke, api):
    route = api.post(f"{LIST_PATH}/publish").mock(
        return_value=httpx.Response(201, json={"data": list_resource(state="published")})
    )
    result = invoke("--silent", "lists", "publish", "deal", LIST_ID)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["attributes"]["state"] == "published"
    request = route.calls.last.request
    assert request.method == "POST"
    assert query_pairs(request) == [("silent", "true")]
    assert request.content == b""


def test_unpublish(invoke, api):
    route = api.post(f"{LIST_PATH}/unpublish").mock(
        return_value=httpx.Response(201, json={"data": list_resource(state="draft")})
    )
    result = invoke("lists", "unpublish", "deal", LIST_ID)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["attributes"]["state"] == "draft"
    request = route.calls.last.request
    assert request.method == "POST"
    assert query_pairs(request) == []
    assert request.content == b""


def test_publish_forbidden_exit_3(invoke, api):
    api.post(f"{LIST_PATH}/publish").mock(
        return_value=httpx.Response(
            403, json={"errors": [{"status": "403", "detail": "No access to this list"}]}
        )
    )
    result = invoke("lists", "publish", "deal", LIST_ID)
    assert result.exit_code == 3
    assert "No access to this list" in result.stderr


# -- records ---------------------------------------------------------------
def test_records_defaults(invoke, api):
    route = api.get(f"{LIST_PATH}/resources").mock(
        return_value=httpx.Response(
            200, json=page([resource("deal", "d1", name="Acme Renewal", amount=50000)], total=1)
        )
    )
    result = invoke("lists", "records", "deal", LIST_ID)
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["data"][0]["id"] == "d1"
    assert body["meta"] == {"total_records": 1, "returned": 1}
    assert query_pairs(route.calls.last.request) == [("page[limit]", "50")]


def test_records_filter_sort_include_paging(invoke, api):
    route = api.get(f"{LIST_PATH}/resources").mock(
        return_value=httpx.Response(
            200,
            json=page(
                [resource("deal", "d1", name="Acme")],
                total=1,
                included=[resource("company", "c1", name="Acme Inc")],
            ),
        )
    )
    result = invoke(
        "lists",
        "records",
        "deal",
        LIST_ID,
        "-f",
        "amount[Greater than]=10000",
        "-f",
        "stage=Won,Negotiation",
        "-s",
        "amount:desc",
        "-i",
        "company_id, owner_id",
        "-n",
        "20",
        "--offset",
        "40",
    )
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["included"][0]["id"] == "c1"
    assert query_pairs(route.calls.last.request) == [
        ("filter[amount][Greater than]", "10000"),
        ("filter[stage]", "Won,Negotiation"),
        ("sortOrder[column]", "amount"),
        ("sortOrder[dir]", "DESC"),
        ("include", "company_id,owner_id"),
        ("page[limit]", "20"),
        ("page[offset]", "40"),
    ]


def test_records_caps_page_limit_at_500(invoke, api):
    route = api.get(f"{LIST_PATH}/resources").mock(return_value=httpx.Response(200, json=page([])))
    result = invoke("lists", "records", "deal", LIST_ID, "-n", "800")
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [("page[limit]", "500")]


def test_records_not_found_exit_4(invoke, api):
    api.get("/workspaces/acme/objects/deal/lists/nope/resources").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "List not found"}]}
        )
    )
    result = invoke("lists", "records", "deal", "nope")
    assert result.exit_code == 4


# -- export-csv ------------------------------------------------------------
CSV = "_id,name,stage,amount\ne7c9a1f4,Acme Renewal Q1,In progress,50000\n"


def test_export_csv_default_body_and_verbatim_stdout(invoke, api):
    route = api.post(f"{LIST_PATH}/rows/csv").mock(
        return_value=httpx.Response(200, text=CSV, headers={"content-type": "text/csv"})
    )
    result = invoke("lists", "export-csv", "deal", LIST_ID)
    assert result.exit_code == 0, result.output
    assert result.stdout == CSV
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.headers["accept"] == "text/csv"
    assert request.headers["authorization"] == "api-key test-key"
    assert query_pairs(request) == []
    assert json_body(request) == {}


def test_export_csv_ignores_output_format(invoke, api):
    api.post(f"{LIST_PATH}/rows/csv").mock(
        return_value=httpx.Response(200, text=CSV, headers={"content-type": "text/csv"})
    )
    result = invoke("-o", "table", "lists", "export-csv", "deal", LIST_ID)
    assert result.exit_code == 0, result.output
    assert result.stdout == CSV


def test_export_csv_with_sql_search_silent_and_out_file(invoke, api, tmp_path):
    sql_file = tmp_path / "rows.sql"
    sql_file.write_text("SELECT * FROM deal WHERE amount >= 50000")
    target = tmp_path / "rows.csv"
    route = api.post(f"{LIST_PATH}/rows/csv").mock(
        return_value=httpx.Response(200, text=CSV, headers={"content-type": "text/csv"})
    )
    result = invoke(
        "--silent",
        "lists",
        "export-csv",
        "deal",
        LIST_ID,
        "--sql",
        f"@{sql_file}",
        "--search",
        "acme",
        "--out",
        str(target),
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert f"Wrote {len(CSV.encode())} bytes to {target}" in result.stderr
    assert target.read_text() == CSV
    request = route.calls.last.request
    assert request.headers["accept"] == "text/csv"
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {
        "sql": "SELECT * FROM deal WHERE amount >= 50000",
        "search": {"query": "acme"},
    }


def test_export_csv_never_parses_json_looking_body(invoke, api):
    weird = '{"not": "parsed"}\n'
    api.post(f"{LIST_PATH}/rows/csv").mock(
        return_value=httpx.Response(200, text=weird, headers={"content-type": "text/csv"})
    )
    result = invoke("lists", "export-csv", "deal", LIST_ID)
    assert result.exit_code == 0, result.output
    assert result.stdout == weird


def test_export_csv_not_found_exit_4(invoke, api):
    api.post("/workspaces/acme/objects/deal/lists/nope/rows/csv").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "List not found"}]}
        )
    )
    result = invoke("lists", "export-csv", "deal", "nope")
    assert result.exit_code == 4
    assert "List not found" in result.stderr
