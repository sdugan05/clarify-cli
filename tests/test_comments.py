from __future__ import annotations

import json

import httpx
import pytest

from clarify_cli.commands.comments import OPERATIONS, plain_message
from helpers import json_body, query_pairs

WS = "/workspaces/acme"
RECORD = "5f8b7d2e-9c4a-4e1b-8f3d-2a6c9e0b4d71"
COMMENT = "9d3e1f7a-2c4b-4e6d-8a1f-5b7c9e0d2a46"


def blocks(text: str, **styles) -> list[dict]:
    return [{"type": "paragraph", "content": [{"type": "text", "text": text, "styles": styles}]}]


def comment_row(**overrides) -> dict:
    row = {
        "_id": COMMENT,
        "message": blocks("Followed up after the QBR."),
        "owner_id": RECORD,
        "entity": "person",
        "_created_at": "2026-01-15T09:30:00.000Z",
        "_created_by": "7d4e2f9a-1b3c-4d5e-8f6a-9c0b2d4e6f81",
        "_updated_at": None,
        "_updated_by": None,
    }
    row.update(overrides)
    return row


def test_operations_manifest():
    assert OPERATIONS == {
        "createComment": "create",
        "getComment": "get",
        "updateComment": "update",
        "deleteComment": "delete",
    }


def test_plain_message_is_minimal_blocknote():
    assert plain_message("Hello") == [
        {"type": "paragraph", "content": [{"type": "text", "text": "Hello", "styles": {}}]}
    ]


# -- create -----------------------------------------------------------------


def test_create_from_options(invoke, api):
    route = api.post(f"{WS}/comments").mock(
        return_value=httpx.Response(201, json=comment_row(message=blocks("Called Jane.")))
    )
    result = invoke("comments", "create", "person", RECORD, "-m", "Called Jane.")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["_id"] == COMMENT
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"/v1{WS}/comments"
    assert query_pairs(request) == []
    assert json_body(request) == {
        "entity": "person",
        "owner_id": RECORD,
        "message": blocks("Called Jane."),
    }


def test_create_from_data_file_with_silent(invoke, api, tmp_path):
    route = api.post(f"{WS}/comments").mock(return_value=httpx.Response(201, json=comment_row()))
    dto = {"message": blocks("Hot lead", bold=True)}
    path = tmp_path / "comment.json"
    path.write_text(json.dumps(dto))
    result = invoke("--silent", "comments", "create", "deal", RECORD, "--data", f"@{path}")
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert request.url.path == f"/v1{WS}/comments"
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {"entity": "deal", "owner_id": RECORD, **dto}


def test_create_positionals_override_entity_and_owner_in_data(invoke, api):
    route = api.post(f"{WS}/comments").mock(return_value=httpx.Response(201, json=comment_row()))
    dto = {"entity": "person", "owner_id": "someone-else", "message": blocks("x")}
    result = invoke("comments", "create", "deal", RECORD, "--data", json.dumps(dto))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "entity": "deal",
        "owner_id": RECORD,
        "message": blocks("x"),
    }


def test_create_data_array_is_message(invoke, api):
    route = api.post(f"{WS}/comments").mock(return_value=httpx.Response(201, json=comment_row()))
    rich = blocks("Styled", italic=True)
    result = invoke("comments", "create", "c_dog", "r1", "--data", json.dumps(rich))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "entity": "c_dog",
        "owner_id": "r1",
        "message": rich,
    }


def test_create_message_option_overrides_data_message(invoke, api):
    route = api.post(f"{WS}/comments").mock(return_value=httpx.Response(201, json=comment_row()))
    dto = {"message": blocks("old")}
    result = invoke(
        "comments", "create", "person", RECORD, "--data", json.dumps(dto), "--message", "new"
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request)["message"] == blocks("new")


def test_create_message_from_stdin(invoke, api):
    route = api.post(f"{WS}/comments").mock(return_value=httpx.Response(201, json=comment_row()))
    result = invoke("comments", "create", "person", RECORD, "--message", "-", input="From stdin\n")
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request)["message"] == blocks("From stdin\n")


def test_create_missing_message_is_usage_error(invoke, api):
    route = api.post(f"{WS}/comments").mock(return_value=httpx.Response(201, json=comment_row()))
    result = invoke("comments", "create", "person", RECORD)
    assert result.exit_code == 2
    assert "--message" in result.stderr
    assert not route.called


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["-m", "x"], "OBJECT"),
        (["person", "-m", "x"], "RECORD_ID"),
    ],
)
def test_create_missing_positionals_is_usage_error(invoke, api, args, expected):
    route = api.post(f"{WS}/comments").mock(return_value=httpx.Response(201, json=comment_row()))
    result = invoke("comments", "create", *args)
    assert result.exit_code == 2
    assert expected in result.output
    assert not route.called


def test_create_empty_message_is_usage_error(invoke, api):
    route = api.post(f"{WS}/comments").mock(return_value=httpx.Response(201, json=comment_row()))
    result = invoke("comments", "create", "person", RECORD, "-m", "  ")
    assert result.exit_code == 2
    assert "must not be empty" in result.stderr
    assert not route.called


def test_create_empty_message_array_is_usage_error(invoke, api):
    route = api.post(f"{WS}/comments").mock(return_value=httpx.Response(201, json=comment_row()))
    result = invoke("comments", "create", "person", RECORD, "--data", "[]")
    assert result.exit_code == 2
    assert "non-empty array" in result.stderr
    assert not route.called


def test_create_invalid_json_is_usage_error(invoke, api):
    result = invoke("comments", "create", "person", RECORD, "--data", "{not json")
    assert result.exit_code == 2
    assert "Invalid JSON" in result.stderr


def test_create_unprocessable_is_exit_1(invoke, api):
    api.post(f"{WS}/comments").mock(
        return_value=httpx.Response(
            422,
            json={"errors": [{"status": "422", "detail": "Entity tam_person has no comments"}]},
        )
    )
    result = invoke("comments", "create", "tam_person", RECORD, "-m", "x")
    assert result.exit_code == 1
    assert "HTTP 422" in result.stderr and "tam_person" in result.stderr


# -- get --------------------------------------------------------------------


def test_get(invoke, api):
    route = api.get(f"{WS}/comments/{COMMENT}").mock(
        return_value=httpx.Response(200, json=comment_row())
    )
    result = invoke("comments", "get", COMMENT)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == comment_row()
    request = route.calls.last.request
    assert request.method == "GET"
    assert request.url.path == f"/v1{WS}/comments/{COMMENT}"
    assert query_pairs(request) == []


def test_get_not_found_exit_4(invoke, api):
    api.get(f"{WS}/comments/nope").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Comment not found"}]}
        )
    )
    result = invoke("comments", "get", "nope")
    assert result.exit_code == 4
    assert "HTTP 404" in result.stderr and "Comment not found" in result.stderr


# -- update -----------------------------------------------------------------


def test_update_with_message(invoke, api):
    route = api.patch(f"{WS}/comments/{COMMENT}").mock(
        return_value=httpx.Response(200, json=comment_row(message=blocks("Edited")))
    )
    result = invoke("comments", "update", COMMENT, "-m", "Edited")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["message"] == blocks("Edited")
    request = route.calls.last.request
    assert request.method == "PATCH"
    assert request.url.path == f"/v1{WS}/comments/{COMMENT}"
    assert query_pairs(request) == []
    assert json_body(request) == {"message": blocks("Edited")}


def test_update_with_data_sends_only_message(invoke, api):
    """A comment fetched with `get` can be edited and written back."""
    route = api.patch(f"{WS}/comments/{COMMENT}").mock(
        return_value=httpx.Response(200, json=comment_row())
    )
    fetched = comment_row(message=blocks("Round trip", bold=True))
    result = invoke("--silent", "comments", "update", COMMENT, "--data", json.dumps(fetched))
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {"message": blocks("Round trip", bold=True)}


def test_update_with_bare_array(invoke, api):
    route = api.patch(f"{WS}/comments/{COMMENT}").mock(
        return_value=httpx.Response(200, json=comment_row())
    )
    result = invoke("comments", "update", COMMENT, "--data", json.dumps(blocks("arr")))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {"message": blocks("arr")}


def test_update_requires_body(invoke, api):
    route = api.patch(f"{WS}/comments/{COMMENT}").mock(
        return_value=httpx.Response(200, json=comment_row())
    )
    result = invoke("comments", "update", COMMENT)
    assert result.exit_code == 2
    assert "--message" in result.stderr
    assert not route.called


def test_update_forbidden_exit_3(invoke, api):
    api.patch(f"{WS}/comments/{COMMENT}").mock(
        return_value=httpx.Response(
            403, json={"errors": [{"status": "403", "detail": "Not the author"}]}
        )
    )
    result = invoke("comments", "update", COMMENT, "-m", "x")
    assert result.exit_code == 3
    assert "HTTP 403" in result.stderr


# -- delete -----------------------------------------------------------------


def test_delete_with_yes(invoke, api):
    route = api.delete(f"{WS}/comments/{COMMENT}").mock(
        return_value=httpx.Response(200, json=comment_row())
    )
    result = invoke("--yes", "--silent", "comments", "delete", COMMENT)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["_id"] == COMMENT
    request = route.calls.last.request
    assert request.method == "DELETE"
    assert request.url.path == f"/v1{WS}/comments/{COMMENT}"
    assert query_pairs(request) == [("silent", "true")]
    assert request.content == b""


def test_delete_empty_body_prints_confirmation(invoke, api):
    api.delete(f"{WS}/comments/{COMMENT}").mock(return_value=httpx.Response(204))
    result = invoke("-y", "comments", "delete", COMMENT)
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert f"Deleted comment {COMMENT}" in result.stderr


def test_delete_refuses_without_yes_when_not_a_tty(invoke, api):
    route = api.delete(f"{WS}/comments/{COMMENT}").mock(
        return_value=httpx.Response(200, json=comment_row())
    )
    result = invoke("comments", "delete", COMMENT)
    assert result.exit_code == 2
    assert "--yes" in result.stderr
    assert not route.called


def test_delete_not_found_exit_4(invoke, api):
    api.delete(f"{WS}/comments/nope").mock(
        return_value=httpx.Response(404, json={"errors": [{"status": "404", "detail": "Gone"}]})
    )
    result = invoke("-y", "comments", "delete", "nope")
    assert result.exit_code == 4


def test_create_message_starting_with_at_is_literal(invoke, api):
    route = api.post("/workspaces/acme/comments").mock(
        return_value=httpx.Response(201, json={"data": {"id": "c1"}})
    )
    result = invoke("comments", "create", "person", RECORD, "--message", "@jane please review")
    assert result.exit_code == 0, result.output
    body = json_body(route.calls.last.request)
    assert body["message"][0]["content"][0]["text"] == "@jane please review"


def test_create_message_file(invoke, api, tmp_path):
    note = tmp_path / "note.txt"
    note.write_text("From a file")
    route = api.post("/workspaces/acme/comments").mock(
        return_value=httpx.Response(201, json={"data": {"id": "c1"}})
    )
    result = invoke("comments", "create", "person", RECORD, "--message-file", str(note))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request)["message"][0]["content"][0]["text"] == "From a file"
    both = invoke("comments", "create", "person", RECORD, "-m", "x", "--message-file", str(note))
    assert both.exit_code == 2
