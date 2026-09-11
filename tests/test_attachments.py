from __future__ import annotations

import json
from pathlib import Path

import httpx

from clarify_cli.commands.attachments import OPERATIONS
from helpers import json_body, page, query_pairs, resource

RECORD = "/workspaces/acme/objects/person/records/p1"
ATTACHMENTS = f"{RECORD}/attachments"
STORAGE = "https://storage.example.com/acme/person/att1/proposal.pdf?signature=abc"

ATTACHMENT = {
    "_id": "att1",
    "name": "proposal.pdf",
    "_created_at": "2026-01-15T09:30:00.000Z",
    "_created_by": None,
    "source": "user",
    "mime_type": "application/pdf",
    "size_bytes": 8,
}
TICKET = {
    "data": {
        "signedUrl": STORAGE,
        "key": "attachments/acme/person/att1/proposal.pdf",
        "attachmentId": "att1",
        "entity": "person",
        "_id": "p1",
    }
}


def record_body() -> dict:
    return {"data": resource("person", "p1", name={"first_name": "Jane"})}


# -- manifest ---------------------------------------------------------------


def test_operations_cover_the_spec_tag(invoke):
    spec = json.loads((Path(__file__).parent / "fixtures" / "operations.json").read_text())
    expected = {op["operationId"] for op in spec if op["tag"] == "RecordAttachments"}
    assert set(OPERATIONS) == expected
    for command in [*OPERATIONS.values(), "upload"]:
        result = invoke("attachments", command, "--help")
        assert result.exit_code == 0, result.output


# -- list -------------------------------------------------------------------


def test_list_defaults_send_page_limit_50(invoke, api):
    route = api.get(ATTACHMENTS).mock(
        return_value=httpx.Response(
            200,
            json={
                "links": {"next": None, "prev": None},
                "meta": {"total_records": 1, "total_pages": 1},
                "data": [ATTACHMENT],
            },
        )
    )
    result = invoke("attachments", "list", "person", "p1")
    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    assert route.calls.last.request.method == "GET"
    assert query_pairs(route.calls.last.request) == [("page[limit]", "50")]
    body = json.loads(result.stdout)
    assert body == {
        "data": [ATTACHMENT],
        "meta": {"total_records": 1, "total_pages": 1, "returned": 1},
    }


def test_list_with_limit_sends_page_params(invoke, api):
    route = api.get(ATTACHMENTS).mock(return_value=httpx.Response(200, json=page([ATTACHMENT])))
    result = invoke("attachments", "list", "person", "p1", "-n", "5")
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [("page[limit]", "5")]
    assert json.loads(result.stdout)["meta"] == {"total_records": 1, "returned": 1}


def test_list_offset_and_page_size(invoke, api):
    route = api.get(ATTACHMENTS).mock(return_value=httpx.Response(200, json=page([])))
    result = invoke("attachments", "list", "person", "p1", "--offset", "10", "--page-size", "2")
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [("page[limit]", "2"), ("page[offset]", "10")]


def test_list_all_follows_pages(invoke, api):
    base = f"https://api.clarify.ai/v1{ATTACHMENTS}"
    route = api.get(ATTACHMENTS).mock(
        side_effect=[
            httpx.Response(
                200,
                json=page(
                    [{**ATTACHMENT, "_id": "a"}], total=2, next_url=f"{base}?page%5Boffset%5D=1"
                ),
            ),
            httpx.Response(200, json=page([{**ATTACHMENT, "_id": "b"}], total=2)),
        ]
    )
    result = invoke("-o", "ndjson", "attachments", "list", "person", "p1", "--all")
    assert result.exit_code == 0, result.output
    assert [json.loads(line)["_id"] for line in result.stdout.splitlines()] == ["a", "b"]
    assert route.call_count == 2
    assert query_pairs(route.calls[0].request) == [("page[limit]", "500")]


def test_list_default_columns_include_attachment_id(invoke, api):
    api.get(ATTACHMENTS).mock(return_value=httpx.Response(200, json=page([ATTACHMENT])))
    result = invoke("-o", "csv", "attachments", "list", "person", "p1")
    assert result.exit_code == 0, result.output
    header, row = result.stdout.splitlines()
    assert header == "_id,name,source,mime_type,size_bytes,_created_at"
    assert row.startswith("att1,proposal.pdf,user,application/pdf,8,")


def test_list_fields_override_default_columns(invoke, api):
    api.get(ATTACHMENTS).mock(return_value=httpx.Response(200, json=page([ATTACHMENT])))
    result = invoke("-o", "csv", "--fields", "name,_id", "attachments", "list", "person", "p1")
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == ["name,_id", "proposal.pdf,att1"]


def test_list_table_shows_attachment_id(invoke, api, monkeypatch):
    monkeypatch.setenv("COLUMNS", "200")  # rich folds columns on a narrow terminal
    api.get(ATTACHMENTS).mock(return_value=httpx.Response(200, json=page([ATTACHMENT])))
    result = invoke("-o", "table", "attachments", "list", "person", "p1")
    assert result.exit_code == 0, result.output
    assert "att1" in result.stdout and "proposal.pdf" in result.stdout


def test_list_not_found_exit_4(invoke, api):
    api.get(ATTACHMENTS).mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Record not found"}]}
        )
    )
    result = invoke("attachments", "list", "person", "p1")
    assert result.exit_code == 4
    assert "HTTP 404" in result.stderr and "Record not found" in result.stderr


# -- get --------------------------------------------------------------------


def test_get_emits_signed_url(invoke, api):
    route = api.get(f"{ATTACHMENTS}/att1").mock(
        return_value=httpx.Response(200, json={"data": {"url": STORAGE}})
    )
    result = invoke("attachments", "get", "person", "p1", "att1")
    assert result.exit_code == 0, result.output
    assert route.calls.last.request.method == "GET"
    assert query_pairs(route.calls.last.request) == []
    assert json.loads(result.stdout) == {"data": {"url": STORAGE}}


def test_get_download_writes_file(invoke, api, tmp_path, monkeypatch):
    monkeypatch.setenv("COLUMNS", "400")  # keep the long tmp path on one stderr line
    api.get(f"{ATTACHMENTS}/att1").mock(
        return_value=httpx.Response(200, json={"data": {"url": STORAGE}})
    )
    storage = api.get(STORAGE).mock(return_value=httpx.Response(200, content=b"%PDF-1.4"))
    target = tmp_path / "proposal.pdf"
    result = invoke("attachments", "get", "person", "p1", "att1", "--download", str(target))
    assert result.exit_code == 0, result.output
    assert storage.call_count == 1
    assert "Authorization" not in storage.calls.last.request.headers
    assert target.read_bytes() == b"%PDF-1.4"
    assert result.stdout == ""
    assert f"Wrote 8 bytes to {target}" in result.stderr


def test_get_download_failure_exit_1(invoke, api, tmp_path):
    api.get(f"{ATTACHMENTS}/att1").mock(
        return_value=httpx.Response(200, json={"data": {"url": STORAGE}})
    )
    api.get(STORAGE).mock(return_value=httpx.Response(403, text="expired"))
    target = tmp_path / "proposal.pdf"
    result = invoke("attachments", "get", "person", "p1", "att1", "--download", str(target))
    assert result.exit_code == 1
    assert "HTTP 403" in result.stderr
    assert not target.exists()


def test_get_not_found_exit_4(invoke, api):
    api.get(f"{ATTACHMENTS}/nope").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Attachment not found"}]}
        )
    )
    result = invoke("attachments", "get", "person", "p1", "nope")
    assert result.exit_code == 4
    assert "Attachment not found" in result.stderr


# -- request-upload ---------------------------------------------------------


def test_request_upload(invoke, api):
    route = api.put(ATTACHMENTS).mock(return_value=httpx.Response(200, json=TICKET))
    result = invoke("attachments", "request-upload", "person", "p1", "--name", "proposal.pdf")
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert request.method == "PUT"
    assert query_pairs(request) == []
    assert json_body(request) == {"name": "proposal.pdf"}
    assert json.loads(result.stdout) == TICKET


def test_request_upload_silent(invoke, api):
    route = api.put(ATTACHMENTS).mock(return_value=httpx.Response(200, json=TICKET))
    result = invoke(
        "--silent", "attachments", "request-upload", "person", "p1", "--name", "proposal.pdf"
    )
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [("silent", "true")]


def test_request_upload_requires_name(invoke, api):
    route = api.put(ATTACHMENTS).mock(return_value=httpx.Response(200, json=TICKET))
    result = invoke("attachments", "request-upload", "person", "p1")
    assert result.exit_code == 2
    assert not route.called


# -- add --------------------------------------------------------------------


def test_add(invoke, api):
    route = api.post(ATTACHMENTS).mock(return_value=httpx.Response(201, json=record_body()))
    result = invoke(
        "attachments",
        "add",
        "person",
        "p1",
        "--name",
        "proposal.pdf",
        "--key",
        "attachments/acme/person/att1/proposal.pdf",
        "--attachment-id",
        "att1",
    )
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert request.method == "POST"
    assert query_pairs(request) == []
    assert json_body(request) == {
        "name": "proposal.pdf",
        "key": "attachments/acme/person/att1/proposal.pdf",
        "attachmentId": "att1",
    }
    assert json.loads(result.stdout)["data"]["id"] == "p1"


def test_add_silent_and_validation_error(invoke, api):
    route = api.post(ATTACHMENTS).mock(
        return_value=httpx.Response(
            422, json={"errors": [{"status": "422", "detail": "Unknown key"}]}
        )
    )
    result = invoke(
        "--silent",
        "attachments",
        "add",
        "person",
        "p1",
        "--name",
        "x.pdf",
        "--key",
        "bad",
        "--attachment-id",
        "att1",
    )
    assert result.exit_code == 1
    assert query_pairs(route.calls.last.request) == [("silent", "true")]
    assert "HTTP 422" in result.stderr and "Unknown key" in result.stderr


# -- upload (convenience) ---------------------------------------------------


def test_upload_runs_all_three_steps(invoke, api, tmp_path):
    source = tmp_path / "proposal.pdf"
    source.write_bytes(b"%PDF-1.4")
    ticket = api.put(ATTACHMENTS).mock(return_value=httpx.Response(200, json=TICKET))
    storage = api.put(STORAGE).mock(return_value=httpx.Response(200))
    add = api.post(ATTACHMENTS).mock(return_value=httpx.Response(201, json=record_body()))

    result = invoke("attachments", "upload", "person", "p1", str(source))
    assert result.exit_code == 0, result.output

    assert [(c.request.method, c.request.url.host) for c in api.calls] == [
        ("PUT", "api.clarify.ai"),
        ("PUT", "storage.example.com"),
        ("POST", "api.clarify.ai"),
    ]
    assert json_body(ticket.calls.last.request) == {"name": "proposal.pdf"}
    assert query_pairs(ticket.calls.last.request) == []

    upload = storage.calls.last.request
    assert upload.content == b"%PDF-1.4"
    assert upload.headers["Content-Type"] == "application/pdf"
    assert "Authorization" not in upload.headers

    assert json_body(add.calls.last.request) == {
        "name": "proposal.pdf",
        "key": "attachments/acme/person/att1/proposal.pdf",
        "attachmentId": "att1",
    }
    assert query_pairs(add.calls.last.request) == []
    assert json.loads(result.stdout) == record_body()


def test_upload_silent_applies_to_api_calls_only(invoke, api, tmp_path):
    source = tmp_path / "proposal.pdf"
    source.write_bytes(b"x")
    ticket = api.put(ATTACHMENTS).mock(return_value=httpx.Response(200, json=TICKET))
    storage = api.put(STORAGE).mock(return_value=httpx.Response(200))
    add = api.post(ATTACHMENTS).mock(return_value=httpx.Response(201, json=record_body()))

    result = invoke("--silent", "attachments", "upload", "person", "p1", str(source))
    assert result.exit_code == 0, result.output
    assert query_pairs(ticket.calls.last.request) == [("silent", "true")]
    assert query_pairs(add.calls.last.request) == [("silent", "true")]
    assert query_pairs(storage.calls.last.request) == [("signature", "abc")]


def test_upload_name_and_content_type_overrides(invoke, api, tmp_path):
    source = tmp_path / "notes"
    source.write_bytes(b"hello")
    ticket = api.put(ATTACHMENTS).mock(return_value=httpx.Response(200, json=TICKET))
    storage = api.put(STORAGE).mock(return_value=httpx.Response(200))
    add = api.post(ATTACHMENTS).mock(return_value=httpx.Response(201, json=record_body()))

    result = invoke(
        "attachments",
        "upload",
        "person",
        "p1",
        str(source),
        "--name",
        "notes.txt",
        "--content-type",
        "text/markdown",
    )
    assert result.exit_code == 0, result.output
    assert json_body(ticket.calls.last.request) == {"name": "notes.txt"}
    assert storage.calls.last.request.headers["Content-Type"] == "text/markdown"
    assert json_body(add.calls.last.request)["name"] == "notes.txt"


def test_upload_guesses_octet_stream_for_unknown_extension(invoke, api, tmp_path):
    source = tmp_path / "blob"
    source.write_bytes(b"\x00\x01")
    api.put(ATTACHMENTS).mock(return_value=httpx.Response(200, json=TICKET))
    storage = api.put(STORAGE).mock(return_value=httpx.Response(200))
    api.post(ATTACHMENTS).mock(return_value=httpx.Response(201, json=record_body()))

    result = invoke("attachments", "upload", "person", "p1", str(source))
    assert result.exit_code == 0, result.output
    assert storage.calls.last.request.headers["Content-Type"] == "application/octet-stream"


def test_upload_storage_failure_stops_before_add(invoke, api, tmp_path):
    source = tmp_path / "proposal.pdf"
    source.write_bytes(b"x")
    api.put(ATTACHMENTS).mock(return_value=httpx.Response(200, json=TICKET))
    api.put(STORAGE).mock(return_value=httpx.Response(403, text="SignatureDoesNotMatch"))
    add = api.post(ATTACHMENTS).mock(return_value=httpx.Response(201, json=record_body()))

    result = invoke("attachments", "upload", "person", "p1", str(source))
    assert result.exit_code == 1
    assert "HTTP 403" in result.stderr and "SignatureDoesNotMatch" in result.stderr
    assert not add.called


def test_upload_api_error_on_ticket_stops_early(invoke, api, tmp_path):
    source = tmp_path / "proposal.pdf"
    source.write_bytes(b"x")
    api.put(ATTACHMENTS).mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Record not found"}]}
        )
    )
    storage = api.put(STORAGE).mock(return_value=httpx.Response(200))
    result = invoke("attachments", "upload", "person", "p1", str(source))
    assert result.exit_code == 4
    assert not storage.called


def test_upload_missing_file_is_usage_error(invoke, api, tmp_path):
    ticket = api.put(ATTACHMENTS).mock(return_value=httpx.Response(200, json=TICKET))
    result = invoke("attachments", "upload", "person", "p1", str(tmp_path / "missing.pdf"))
    assert result.exit_code == 2
    assert not ticket.called


# -- delete -----------------------------------------------------------------


def test_delete_with_yes(invoke, api):
    route = api.delete(f"{ATTACHMENTS}/att1").mock(
        return_value=httpx.Response(200, json=record_body())
    )
    result = invoke("--yes", "--silent", "attachments", "delete", "person", "p1", "att1")
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert request.method == "DELETE"
    assert query_pairs(request) == [("silent", "true")]
    assert json.loads(result.stdout) == record_body()


def test_delete_empty_body_confirms_on_stderr(invoke, api):
    api.delete(f"{ATTACHMENTS}/att1").mock(return_value=httpx.Response(204))
    result = invoke("-y", "attachments", "delete", "person", "p1", "att1")
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "Deleted attachment att1" in result.stderr


def test_delete_refuses_without_confirmation(invoke, api):
    route = api.delete(f"{ATTACHMENTS}/att1").mock(
        return_value=httpx.Response(200, json=record_body())
    )
    result = invoke("attachments", "delete", "person", "p1", "att1")
    assert result.exit_code == 2
    assert "--yes" in result.stderr
    assert not route.called


def test_delete_not_found_exit_4(invoke, api):
    api.delete(f"{ATTACHMENTS}/nope").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Attachment not found"}]}
        )
    )
    result = invoke("-y", "attachments", "delete", "person", "p1", "nope")
    assert result.exit_code == 4
    assert "Attachment not found" in result.stderr
