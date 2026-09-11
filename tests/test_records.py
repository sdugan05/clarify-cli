from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

from clarify_cli.commands import records
from helpers import json_body, page, query_pairs, resource

WS = "/workspaces/acme"
FIXTURE = Path(__file__).parent / "fixtures" / "operations.json"


def error_response(status: int, detail: str) -> httpx.Response:
    return httpx.Response(status, json={"errors": [{"status": str(status), "detail": detail}]})


def flat(text: str) -> str:
    """Strip rich's error-panel borders and line wrapping so substring assertions are stable."""
    return " ".join(re.sub(r"[\u2500-\u257f]", " ", text).split())


# -- manifest ----------------------------------------------------------------


def test_records_operations_cover_records_and_resources_tags():
    spec = json.loads(FIXTURE.read_text())
    expected = {op["operationId"] for op in spec if op["tag"] in ("Records", "Resources")} - {
        "getListResources"
    }
    assert set(records.OPERATIONS) == expected
    registered = {
        cmd.name or cmd.callback.__name__.replace("_", "-")
        for cmd in records.app.registered_commands
    }
    assert set(records.OPERATIONS.values()) <= registered
    assert registered == {
        "list",
        "get",
        "create",
        "update",
        "delete",
        "bulk-create",
        "bulk-update",
        "bulk-delete",
        "merge",
        "deleted",
    }


# -- list --------------------------------------------------------------------


def test_records_list_defaults(invoke, api):
    route = api.get(f"{WS}/objects/person/resources").mock(
        return_value=httpx.Response(
            200, json=page([resource("person", "p1", job_title="VP")], total=1)
        )
    )
    result = invoke("records", "list", "person")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["data"][0]["id"] == "p1"
    assert body["meta"] == {"total_records": 1, "returned": 1}
    request = route.calls.last.request
    assert request.method == "GET"
    assert query_pairs(request) == [("page[limit]", "50")]


def test_records_list_options(invoke, api):
    route = api.get(f"{WS}/objects/deal/resources").mock(
        return_value=httpx.Response(200, json=page([]))
    )
    result = invoke(
        "records",
        "list",
        "deal",
        "-f",
        "amount[Greater than]=50000",
        "-f",
        "stage=Won,Negotiation",
        "-s",
        "-amount",
        "-i",
        "company_id, owner",
        "-n",
        "5",
        "--offset",
        "10",
        "--page-size",
        "2",
    )
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [
        ("filter[amount][Greater than]", "50000"),
        ("filter[stage]", "Won,Negotiation"),
        ("sortOrder[column]", "amount"),
        ("sortOrder[dir]", "DESC"),
        ("include", "company_id,owner"),
        ("page[limit]", "2"),
        ("page[offset]", "10"),
    ]


def test_records_list_all_follows_links(invoke, api):
    base = f"https://api.clarify.ai/v1{WS}/objects/company/resources"
    route = api.get(f"{WS}/objects/company/resources").mock(
        side_effect=[
            httpx.Response(
                200,
                json=page(
                    [resource("company", "c1")], total=2, next_url=f"{base}?page%5Boffset%5D=1"
                ),
            ),
            httpx.Response(200, json=page([resource("company", "c2")], total=2)),
        ]
    )
    result = invoke("-o", "ndjson", "records", "list", "company", "--all")
    assert result.exit_code == 0, result.output
    assert [json.loads(line)["id"] for line in result.stdout.splitlines()] == ["c1", "c2"]
    assert route.call_count == 2
    assert query_pairs(route.calls[0].request) == [("page[limit]", "500")]
    assert str(route.calls[1].request.url) == f"{base}?page%5Boffset%5D=1"


def test_records_list_bad_filter_is_usage_error(invoke, api):
    route = api.get(f"{WS}/objects/person/resources").mock(
        return_value=httpx.Response(200, json=page([]))
    )
    result = invoke("records", "list", "person", "-f", "novalue")
    assert result.exit_code == 2
    assert not route.called


# -- get ---------------------------------------------------------------------


def test_records_get_resources_endpoint_by_default(invoke, api):
    route = api.get(f"{WS}/objects/person/resources/p1").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": resource("person", "p1", job_title="VP"),
                "included": [resource("company", "c1")],
            },
        )
    )
    result = invoke("records", "get", "person", "p1", "-i", "company_id, deals")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["data"]["id"] == "p1" and body["included"][0]["id"] == "c1"
    request = route.calls.last.request
    assert request.method == "GET"
    assert query_pairs(request) == [("include", "company_id,deals")]


def test_records_get_records_endpoint(invoke, api):
    route = api.get(f"{WS}/objects/person/records/p1").mock(
        return_value=httpx.Response(200, json={"data": resource("person", "p1")})
    )
    result = invoke("records", "get", "person", "p1", "--endpoint", "records")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["id"] == "p1"
    assert query_pairs(route.calls.last.request) == []


def test_records_get_not_found_exit_4(invoke, api):
    api.get(f"{WS}/objects/person/resources/nope").mock(
        return_value=error_response(404, "Record not found")
    )
    result = invoke("records", "get", "person", "nope")
    assert result.exit_code == 4
    assert "HTTP 404" in result.stderr and "Record not found" in result.stderr


def test_records_get_rejects_unknown_endpoint(invoke, api):
    result = invoke("records", "get", "person", "p1", "--endpoint", "things")
    assert result.exit_code == 2


# -- create ------------------------------------------------------------------


def test_records_create_with_set_match_on_and_silent(invoke, api):
    route = api.post(f"{WS}/objects/person/records").mock(
        return_value=httpx.Response(201, json={"data": resource("person", "p1")})
    )
    result = invoke(
        "--silent",
        "records",
        "create",
        "person",
        "--set",
        "name.first_name=Jane",
        "--set",
        'email_addresses={"items": ["jane@acme.com"]}',
        "--match-on",
        "email_addresses",
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["id"] == "p1"
    request = route.calls.last.request
    assert request.method == "POST"
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {
        "data": {
            "type": "person",
            "attributes": {
                "name": {"first_name": "Jane"},
                "email_addresses": {"items": ["jane@acme.com"]},
            },
        },
        "match_on": "email_addresses",
    }


def test_records_create_with_data_wraps_attributes(invoke, api):
    route = api.post(f"{WS}/objects/deal/records").mock(
        return_value=httpx.Response(201, json={"data": resource("deal", "d1")})
    )
    result = invoke("records", "create", "deal", "-d", '{"name": "Acme Renewal", "amount": 12000}')
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert query_pairs(request) == []
    assert json_body(request) == {
        "data": {"type": "deal", "attributes": {"name": "Acme Renewal", "amount": 12000}}
    }


def test_records_create_full_document_passes_through(invoke, api):
    route = api.post(f"{WS}/objects/person/records").mock(
        return_value=httpx.Response(201, json={"data": resource("person", "p1")})
    )
    document = {
        "data": {"type": "person", "attributes": {"job_title": "CMO"}},
        "match_on": "email_addresses",
    }
    result = invoke("records", "create", "person", "-d", json.dumps(document))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == document


def test_records_create_resources_endpoint(invoke, api):
    route = api.post(f"{WS}/objects/company/resources").mock(
        return_value=httpx.Response(201, json={"data": resource("company", "c1")})
    )
    result = invoke("records", "create", "company", "--set", "name=Acme", "--endpoint", "resources")
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert request.method == "POST"
    assert json_body(request) == {"data": {"type": "company", "attributes": {"name": "Acme"}}}


def test_records_create_resources_rejects_match_on(invoke, api):
    route = api.post(f"{WS}/objects/company/resources").mock(
        return_value=httpx.Response(201, json={"data": resource("company", "c1")})
    )
    result = invoke(
        "records",
        "create",
        "company",
        "--set",
        "name=Acme",
        "--endpoint",
        "resources",
        "--match-on",
        "domains",
    )
    assert result.exit_code == 2
    assert "--match-on" in result.stderr
    assert not route.called
    # A full document carrying match_on is rejected the same way.
    document = {"data": {"type": "company", "attributes": {}}, "match_on": "domains"}
    result = invoke(
        "records", "create", "company", "-d", json.dumps(document), "--endpoint", "resources"
    )
    assert result.exit_code == 2
    assert not route.called


def test_records_create_requires_a_body(invoke, api):
    route = api.post(f"{WS}/objects/person/records").mock(
        return_value=httpx.Response(201, json={"data": resource("person", "p1")})
    )
    result = invoke("records", "create", "person")
    assert result.exit_code == 2
    assert not route.called


def test_records_create_duplicate_is_exit_1(invoke, api):
    api.post(f"{WS}/objects/person/records").mock(
        return_value=error_response(400, "Duplicate email address")
    )
    result = invoke("records", "create", "person", "--set", "job_title=CMO")
    assert result.exit_code == 1
    assert "HTTP 400" in result.stderr and "Duplicate email address" in result.stderr


# -- update ------------------------------------------------------------------


def test_records_update_with_set(invoke, api):
    route = api.patch(f"{WS}/objects/person/records/p1").mock(
        return_value=httpx.Response(200, json={"data": resource("person", "p1", job_title="CMO")})
    )
    result = invoke("records", "update", "person", "p1", "--set", "job_title=CMO")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["attributes"]["job_title"] == "CMO"
    request = route.calls.last.request
    assert request.method == "PATCH"
    assert query_pairs(request) == []
    assert json_body(request) == {
        "data": {"type": "person", "id": "p1", "attributes": {"job_title": "CMO"}}
    }


def test_records_update_write_strategies_build_meta(invoke, api):
    route = api.patch(f"{WS}/objects/person/records/p1").mock(
        return_value=httpx.Response(200, json={"data": resource("person", "p1")})
    )
    result = invoke(
        "--silent",
        "records",
        "update",
        "person",
        "p1",
        "--set",
        'email_addresses={"items": ["jane@newco.com"]}',
        "--append",
        "email_addresses",
        "--set",
        'tags=["vip"]',
        "--append",
        "tags",
        "--set",
        'domains={"items": ["old.com"]}',
        "--remove",
        "domains",
        "--set",
        'custom={"k": 1}',
        "--merge",
        "custom",
    )
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert query_pairs(request) == [("silent", "true")]
    body = json_body(request)
    assert body["data"] == {
        "type": "person",
        "id": "p1",
        "attributes": {
            "email_addresses": {"items": ["jane@newco.com"]},
            "tags": ["vip"],
            "domains": {"items": ["old.com"]},
            "custom": {"k": 1},
        },
    }
    assert body["meta"] == {
        "email_addresses": {"collection": "append"},
        "tags": {"array": "append"},
        "domains": {"collection": "remove"},
        "custom": {"object": "merge"},
    }


def test_records_update_keeps_meta_from_document(invoke, api):
    route = api.patch(f"{WS}/objects/person/records/p1").mock(
        return_value=httpx.Response(200, json={"data": resource("person", "p1")})
    )
    document = {
        "data": {
            "type": "person",
            "id": "p1",
            "attributes": {"labels": {"items": ["a"]}, "domains": {"items": ["x.com"]}},
        },
        "meta": {"labels": {"collection": "append"}},
    }
    result = invoke(
        "records", "update", "person", "p1", "-d", json.dumps(document), "--remove", "domains"
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request)["meta"] == {
        "labels": {"collection": "append"},
        "domains": {"collection": "remove"},
    }


def test_records_update_strategy_needs_the_field_in_the_body(invoke, api):
    route = api.patch(f"{WS}/objects/person/records/p1").mock(
        return_value=httpx.Response(200, json={"data": resource("person", "p1")})
    )
    result = invoke(
        "records", "update", "person", "p1", "--set", "job_title=CMO", "--append", "phone_numbers"
    )
    assert result.exit_code == 2
    assert "--append phone_numbers" in flat(result.stderr)
    assert not route.called


def test_records_update_not_found_exit_4(invoke, api):
    api.patch(f"{WS}/objects/person/records/nope").mock(
        return_value=error_response(404, "Record not found")
    )
    result = invoke("records", "update", "person", "nope", "--set", "job_title=CMO")
    assert result.exit_code == 4


# -- delete ------------------------------------------------------------------


def test_records_delete_with_yes(invoke, api):
    route = api.delete(f"{WS}/objects/person/records/p1").mock(return_value=httpx.Response(200))
    result = invoke("--yes", "--silent", "records", "delete", "person", "p1")
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "Deleted person p1" in result.stderr
    request = route.calls.last.request
    assert request.method == "DELETE"
    assert query_pairs(request) == [("silent", "true")]


def test_records_delete_refuses_without_yes(invoke, api):
    route = api.delete(f"{WS}/objects/person/records/p1").mock(return_value=httpx.Response(200))
    result = invoke("records", "delete", "person", "p1")
    assert result.exit_code == 2
    assert "--yes" in result.stderr
    assert not route.called


def test_records_delete_not_found_exit_4(invoke, api):
    api.delete(f"{WS}/objects/person/records/nope").mock(
        return_value=error_response(404, "Record not found")
    )
    result = invoke("--yes", "records", "delete", "person", "nope")
    assert result.exit_code == 4


# -- bulk-create -------------------------------------------------------------


def test_records_bulk_create_batches_and_merges(invoke, api, tmp_path):
    people = tmp_path / "people.json"
    people.write_text(
        json.dumps(
            [
                {"name": {"first_name": "A"}, "email_addresses": {"items": ["a@x.com"]}},
                {"type": "person", "attributes": {"name": {"first_name": "B"}}},
                {"name": {"first_name": "C"}},
            ]
        )
    )
    route = api.post(f"{WS}/objects/person/records/bulk").mock(
        side_effect=[
            httpx.Response(
                201, json={"data": [resource("person", "p1"), resource("person", "p2")]}
            ),
            httpx.Response(201, json={"data": [resource("person", "p3")]}),
        ]
    )
    result = invoke(
        "--silent",
        "records",
        "bulk-create",
        "person",
        "-F",
        str(people),
        "--batch-size",
        "2",
        "--match-on",
        "email_addresses",
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {
        "data": [resource("person", "p1"), resource("person", "p2"), resource("person", "p3")],
        "meta": {"batches": 2, "records": 3},
    }
    assert route.call_count == 2
    first, second = (call.request for call in route.calls)
    assert first.method == "POST" and second.method == "POST"
    assert query_pairs(first) == [("silent", "true")]
    assert json_body(first) == {
        "data": [
            {
                "type": "person",
                "attributes": {
                    "name": {"first_name": "A"},
                    "email_addresses": {"items": ["a@x.com"]},
                },
            },
            {"type": "person", "attributes": {"name": {"first_name": "B"}}},
        ],
        "match_on": "email_addresses",
    }
    assert json_body(second) == {
        "data": [{"type": "person", "attributes": {"name": {"first_name": "C"}}}],
        "match_on": "email_addresses",
    }


def test_records_bulk_create_csv_single_batch(invoke, api, tmp_path):
    companies = tmp_path / "companies.csv"
    companies.write_text('name,domains.items\nAcme,"[""acme.com""]"\nGlobex,\n')
    route = api.post(f"{WS}/objects/company/records/bulk").mock(
        return_value=httpx.Response(201, json={"data": [resource("company", "c1")]})
    )
    result = invoke("records", "bulk-create", "company", "-F", str(companies))
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["meta"] == {"batches": 1, "records": 2}
    assert route.call_count == 1
    request = route.calls.last.request
    assert query_pairs(request) == []
    assert json_body(request) == {
        "data": [
            {
                "type": "company",
                "attributes": {"name": "Acme", "domains": {"items": '["acme.com"]'}},
            },
            {"type": "company", "attributes": {"name": "Globex"}},
        ]
    }


def test_records_bulk_create_from_stdin(invoke, api):
    route = api.post(f"{WS}/objects/task/records/bulk").mock(
        return_value=httpx.Response(201, json={"data": [resource("task", "t1")]})
    )
    result = invoke(
        "records", "bulk-create", "task", "-F", "-", input='{"data": [{"title": "Call"}]}'
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "data": [{"type": "task", "attributes": {"title": "Call"}}]
    }


def test_records_bulk_create_failing_batch_names_range(invoke, api, tmp_path):
    people = tmp_path / "people.ndjson"
    people.write_text('{"name": "A"}\n{"name": "B"}\n{"name": "C"}\n')
    route = api.post(f"{WS}/objects/person/records/bulk").mock(
        side_effect=[
            httpx.Response(201, json={"data": [resource("person", "p1")]}),
            error_response(422, "email_addresses must be unique"),
            httpx.Response(201, json={"data": [resource("person", "p3")]}),
        ]
    )
    result = invoke("records", "bulk-create", "person", "-F", str(people), "--batch-size", "1")
    assert result.exit_code == 1
    assert route.call_count == 2  # stops at the failing batch
    stderr = flat(result.stderr)
    assert "Batch 2/3 (records 2-2 of the file) failed" in stderr
    assert "1 records from earlier batches were created" in stderr
    assert "HTTP 422" in stderr and "email_addresses must be unique" in stderr
    assert "--batch-size 1" in stderr
    # Results of the batches that succeeded are still printed.
    assert json.loads(result.stdout) == {
        "data": [resource("person", "p1")],
        "meta": {"batches": 1, "records": 1},
    }


def test_records_bulk_create_first_batch_failure_prints_nothing(invoke, api, tmp_path):
    people = tmp_path / "people.json"
    people.write_text('[{"name": "A"}]')
    api.post(f"{WS}/objects/person/records/bulk").mock(
        return_value=error_response(400, "Duplicate record")
    )
    result = invoke("records", "bulk-create", "person", "-F", str(people))
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Batch 1/1 (records 1-1 of the file) failed" in flat(result.stderr)


def test_records_bulk_create_empty_file_is_usage_error(invoke, api, tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text("[]")
    route = api.post(f"{WS}/objects/person/records/bulk").mock(
        return_value=httpx.Response(201, json={"data": []})
    )
    result = invoke("records", "bulk-create", "person", "-F", str(empty))
    assert result.exit_code == 2
    assert not route.called


def test_records_bulk_create_timeout_mid_run_keeps_created_ids(invoke, api, tmp_path):
    people = tmp_path / "people.ndjson"
    people.write_text('{"name": "A"}\n{"name": "B"}\n{"name": "C"}\n')
    route = api.post(f"{WS}/objects/person/records/bulk").mock(
        side_effect=[
            httpx.Response(201, json={"data": [resource("person", "p1")]}),
            httpx.TimeoutException("boom"),
            httpx.Response(201, json={"data": [resource("person", "p3")]}),
        ]
    )
    result = invoke("records", "bulk-create", "person", "-F", str(people), "--batch-size", "1")
    assert result.exit_code == 1
    assert route.call_count == 2  # stops at the batch that got no response
    # The IDs created by batch 1 are still printed.
    assert json.loads(result.stdout) == {
        "data": [resource("person", "p1")],
        "meta": {"batches": 1, "records": 1},
    }
    stderr = flat(result.stderr)
    assert "Batch 2/3 (records 2-2 of the file) got no response" in stderr
    assert "1 records from earlier batches were created" in stderr
    assert "Request timed out" in stderr
    assert "Raise --timeout" in stderr and "re-run from record 2" in stderr


# -- bulk-update -------------------------------------------------------------


def test_records_bulk_update_sends_update_records_dto(invoke, api, tmp_path):
    deals = tmp_path / "deals.ndjson"
    deals.write_text(
        '{"id": "d1", "stage": "Won"}\n'
        '{"type": "deal", "id": "d2", "attributes": {"stage": "Lost"}}\n'
        '{"id": 3, "amount": 5}\n'
    )
    route = api.patch(f"{WS}/objects/deal/records").mock(
        side_effect=[
            httpx.Response(200, json={"data": [resource("deal", "d1"), resource("deal", "d2")]}),
            httpx.Response(200, json={"data": [resource("deal", "3")]}),
        ]
    )
    result = invoke(
        "--silent", "records", "bulk-update", "deal", "-F", str(deals), "--batch-size", "2"
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["meta"] == {"batches": 2, "records": 3}
    assert [r["id"] for r in json.loads(result.stdout)["data"]] == ["d1", "d2", "3"]
    first, second = (call.request for call in route.calls)
    assert first.method == "PATCH" and query_pairs(first) == [("silent", "true")]
    assert json_body(first) == {
        "data": [
            {"type": "deal", "id": "d1", "attributes": {"stage": "Won"}},
            {"type": "deal", "id": "d2", "attributes": {"stage": "Lost"}},
        ]
    }
    assert json_body(second) == {"data": [{"type": "deal", "id": "3", "attributes": {"amount": 5}}]}


def test_records_bulk_update_requires_ids(invoke, api, tmp_path):
    deals = tmp_path / "deals.json"
    deals.write_text('[{"id": "d1", "stage": "Won"}, {"stage": "Lost"}, {"amount": 1}]')
    route = api.patch(f"{WS}/objects/deal/records").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    result = invoke("records", "bulk-update", "deal", "-F", str(deals))
    assert result.exit_code == 2
    assert "missing on record(s) 2, 3" in flat(result.stderr)
    assert not route.called


def test_records_bulk_update_failing_batch_keeps_status_exit_code(invoke, api, tmp_path):
    deals = tmp_path / "deals.csv"
    deals.write_text("id,stage\nd1,Won\nd2,Lost\n")
    route = api.patch(f"{WS}/objects/deal/records").mock(
        return_value=error_response(404, "Record d2 not found")
    )
    result = invoke("records", "bulk-update", "deal", "-F", str(deals))
    assert result.exit_code == 4
    assert route.call_count == 1
    stderr = flat(result.stderr)
    assert "Batch 1/1 (records 1-2 of the file) failed" in stderr
    assert "none of its records were updated" in stderr
    assert "HTTP 404" in stderr


def test_records_bulk_update_append_sends_meta_in_every_batch(invoke, api, tmp_path):
    people = tmp_path / "emails.ndjson"
    people.write_text(
        '{"id": "p1", "email_addresses": {"items": ["a@new.com"]}}\n'
        '{"id": "p2", "email_addresses": {"items": ["b@new.com"]}}\n'
    )
    route = api.patch(f"{WS}/objects/person/records").mock(
        side_effect=[
            httpx.Response(200, json={"data": [resource("person", "p1")]}),
            httpx.Response(200, json={"data": [resource("person", "p2")]}),
        ]
    )
    result = invoke(
        "--silent",
        "records",
        "bulk-update",
        "person",
        "-F",
        str(people),
        "--batch-size",
        "1",
        "--append",
        "email_addresses",
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["meta"] == {"batches": 2, "records": 2}
    first, second = (call.request for call in route.calls)
    assert first.method == "PATCH" and query_pairs(first) == [("silent", "true")]
    assert json_body(first) == {
        "data": [
            {
                "type": "person",
                "id": "p1",
                "attributes": {"email_addresses": {"items": ["a@new.com"]}},
            }
        ],
        "meta": {"email_addresses": {"collection": "append"}},
    }
    assert json_body(second) == {
        "data": [
            {
                "type": "person",
                "id": "p2",
                "attributes": {"email_addresses": {"items": ["b@new.com"]}},
            }
        ],
        "meta": {"email_addresses": {"collection": "append"}},
    }


def test_records_bulk_update_keeps_document_meta_and_merges_flags(invoke, api):
    route = api.patch(f"{WS}/objects/person/records").mock(
        return_value=httpx.Response(200, json={"data": [resource("person", "p1")]})
    )
    document = {
        "data": [
            {
                "type": "person",
                "id": "p1",
                "attributes": {"labels": {"items": ["a"]}, "domains": {"items": ["x.com"]}},
            },
            {"id": "p2", "tags": ["vip"], "custom": {"k": 1}},
        ],
        "meta": {"labels": {"collection": "append"}},
    }
    result = invoke(
        "records",
        "bulk-update",
        "person",
        "-F",
        "-",
        "--remove",
        "domains",
        "--append",
        "tags",
        "--merge",
        "custom",
        input=json.dumps(document),
    )
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert query_pairs(request) == []
    assert json_body(request) == {
        "data": [
            document["data"][0],
            {"type": "person", "id": "p2", "attributes": {"tags": ["vip"], "custom": {"k": 1}}},
        ],
        "meta": {
            "labels": {"collection": "append"},
            "domains": {"collection": "remove"},
            "tags": {"array": "append"},
            "custom": {"object": "merge"},
        },
    }


def test_records_bulk_update_strategy_needs_the_field_in_some_record(invoke, api, tmp_path):
    deals = tmp_path / "deals.csv"
    deals.write_text("id,stage\nd1,Won\n")
    route = api.patch(f"{WS}/objects/deal/records").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    result = invoke("records", "bulk-update", "deal", "-F", str(deals), "--append", "labels")
    assert result.exit_code == 2
    assert "--append labels" in flat(result.stderr)
    assert not route.called


def test_records_bulk_update_append_rejects_mixed_field_shapes(invoke, api, tmp_path):
    people = tmp_path / "people.json"
    people.write_text(
        json.dumps([{"id": "p1", "tags": ["a"]}, {"id": "p2", "tags": {"items": ["b"]}}])
    )
    route = api.patch(f"{WS}/objects/person/records").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    result = invoke("records", "bulk-update", "person", "-F", str(people), "--append", "tags")
    assert result.exit_code == 2
    assert "--append tags" in flat(result.stderr)
    assert not route.called


def test_records_bulk_update_connection_error_on_first_batch_prints_nothing(invoke, api, tmp_path):
    deals = tmp_path / "deals.csv"
    deals.write_text("id,stage\nd1,Won\nd2,Lost\n")
    route = api.patch(f"{WS}/objects/deal/records").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    result = invoke("records", "bulk-update", "deal", "-F", str(deals))
    assert result.exit_code == 1
    assert route.call_count == 1
    assert result.stdout == ""
    stderr = flat(result.stderr)
    assert "Batch 1/1 (records 1-2 of the file) got no response" in stderr
    assert "0 records from earlier batches were updated" in stderr
    assert "Connection error" in stderr and "re-run from record 1" in stderr


# -- bulk-delete -------------------------------------------------------------


def test_records_bulk_delete_args_and_txt_file(invoke, api, tmp_path):
    ids = tmp_path / "ids.txt"
    ids.write_text("# stale\nb\n\n  c  \na\n")
    route = api.delete(f"{WS}/objects/person/records").mock(return_value=httpx.Response(200))
    result = invoke(
        "--yes", "--silent", "records", "bulk-delete", "person", "a", "d", "-F", str(ids)
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "Deleted 4 person record(s)" in result.stderr
    request = route.calls.last.request
    assert request.method == "DELETE"
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {"items": ["a", "d", "b", "c"]}


def test_records_bulk_delete_from_records_file(invoke, api, tmp_path):
    export = tmp_path / "export.json"
    export.write_text(
        json.dumps(
            {
                "data": [
                    {"id": "x", "name": "X"},
                    {"type": "person", "id": "y", "attributes": {"name": "Y"}},
                ]
            }
        )
    )
    route = api.delete(f"{WS}/objects/person/records").mock(return_value=httpx.Response(200))
    result = invoke("--yes", "records", "bulk-delete", "person", "-F", str(export))
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert query_pairs(request) == []
    assert json_body(request) == {"items": ["x", "y"]}


def test_records_bulk_delete_from_stdin_ndjson(invoke, api):
    route = api.delete(f"{WS}/objects/deal/records").mock(return_value=httpx.Response(200))
    result = invoke(
        "--yes",
        "records",
        "bulk-delete",
        "deal",
        "-F",
        "-",
        "--format",
        "ndjson",
        input='{"id": "1", "attributes": {}}\n{"id": "2"}\n',
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {"items": ["1", "2"]}


def test_records_bulk_delete_records_file_without_ids_is_usage_error(invoke, api, tmp_path):
    export = tmp_path / "export.json"
    export.write_text('[{"id": "x"}, {"name": "no id"}]')
    route = api.delete(f"{WS}/objects/person/records").mock(return_value=httpx.Response(200))
    result = invoke("--yes", "records", "bulk-delete", "person", "-F", str(export))
    assert result.exit_code == 2
    assert "Record(s) 2" in flat(result.stderr)
    assert not route.called


def test_records_bulk_delete_without_ids_is_usage_error(invoke, api):
    route = api.delete(f"{WS}/objects/person/records").mock(return_value=httpx.Response(200))
    result = invoke("--yes", "records", "bulk-delete", "person")
    assert result.exit_code == 2
    assert not route.called


def test_records_bulk_delete_refuses_without_yes(invoke, api):
    route = api.delete(f"{WS}/objects/person/records").mock(return_value=httpx.Response(200))
    result = invoke("records", "bulk-delete", "person", "a", "b")
    assert result.exit_code == 2
    assert "2 person record(s)" in flat(result.stderr)
    assert not route.called


# -- merge -------------------------------------------------------------------


def test_records_merge(invoke, api):
    route = api.post(f"{WS}/objects/company/records/t1/merges").mock(
        return_value=httpx.Response(204)
    )
    result = invoke(
        "--yes",
        "--silent",
        "records",
        "merge",
        "company",
        "t1",
        "--source",
        "s1",
        "--source",
        "s2",
        "--source",
        "s1",
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "Merged 2 record(s) into company t1" in result.stderr
    request = route.calls.last.request
    assert request.method == "POST"
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {
        "data": {"type": "company", "attributes": {"sources": ["s1", "s2"]}}
    }


def test_records_merge_requires_source(invoke, api):
    route = api.post(f"{WS}/objects/company/records/t1/merges").mock(
        return_value=httpx.Response(204)
    )
    result = invoke("--yes", "records", "merge", "company", "t1")
    assert result.exit_code == 2
    assert not route.called


def test_records_merge_rejects_target_as_source(invoke, api):
    route = api.post(f"{WS}/objects/company/records/t1/merges").mock(
        return_value=httpx.Response(204)
    )
    result = invoke("--yes", "records", "merge", "company", "t1", "--source", "t1")
    assert result.exit_code == 2
    assert not route.called


def test_records_merge_refuses_without_yes(invoke, api):
    route = api.post(f"{WS}/objects/company/records/t1/merges").mock(
        return_value=httpx.Response(204)
    )
    result = invoke("records", "merge", "company", "t1", "--source", "s1")
    assert result.exit_code == 2
    assert not route.called


def test_records_merge_api_error_exit_1(invoke, api):
    api.post(f"{WS}/objects/company/records/t1/merges").mock(
        return_value=error_response(422, "sources must not be empty")
    )
    result = invoke("--yes", "records", "merge", "company", "t1", "--source", "s1")
    assert result.exit_code == 1
    assert "HTTP 422" in result.stderr


# -- deleted -----------------------------------------------------------------


def test_records_deleted_defaults(invoke, api):
    route = api.get(f"{WS}/objects/person/deleted-resources").mock(
        return_value=httpx.Response(
            200, json=page([resource("person", "p1", _deleted_at=1787273241)], total=1)
        )
    )
    result = invoke("records", "deleted", "person")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["data"][0]["attributes"]["_deleted_at"] == 1787273241
    assert body["meta"] == {"total_records": 1, "returned": 1}
    request = route.calls.last.request
    assert request.method == "GET"
    assert query_pairs(request) == [("page[limit]", "50")]


def test_records_deleted_filter_and_paging(invoke, api):
    route = api.get(f"{WS}/objects/deal/deleted-resources").mock(
        return_value=httpx.Response(200, json=page([]))
    )
    result = invoke(
        "records",
        "deleted",
        "deal",
        "-f",
        "_deleted_at[Less than]=1787273241",
        "-n",
        "20",
        "--offset",
        "5",
    )
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [
        ("filter[_deleted_at][Less than]", "1787273241"),
        ("page[limit]", "20"),
        ("page[offset]", "5"),
    ]


def test_records_deleted_caps_page_size_at_500(invoke, api):
    route = api.get(f"{WS}/objects/deal/deleted-resources").mock(
        return_value=httpx.Response(200, json=page([]))
    )
    assert invoke("records", "deleted", "deal", "-n", "1000").exit_code == 0
    assert query_pairs(route.calls.last.request) == [("page[limit]", "500")]
    assert invoke("records", "deleted", "deal", "-n", "1000", "--page-size", "7").exit_code == 0
    assert query_pairs(route.calls.last.request) == [("page[limit]", "7")]


def test_records_deleted_has_no_include_or_sort(invoke, api):
    route = api.get(f"{WS}/objects/deal/deleted-resources").mock(
        return_value=httpx.Response(200, json=page([]))
    )
    assert invoke("records", "deleted", "deal", "--include", "company_id").exit_code == 2
    assert invoke("records", "deleted", "deal", "--sort", "_deleted_at").exit_code == 2
    assert not route.called
