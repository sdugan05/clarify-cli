from __future__ import annotations

import json

from clarify_cli.config import Settings
from clarify_cli.output import default_columns, emit, flatten_item, items_of, render_value
from clarify_cli.state import AppState


def make_state(**kwargs) -> AppState:
    settings = Settings(
        api_key="k",
        workspace="acme",
        base_url="https://api.clarify.ai/v1",
        profile="default",
        sources={},
    )
    return AppState(settings=settings, **kwargs)


PERSON = {
    "type": "person",
    "id": "p1",
    "attributes": {
        "name": {"first_name": "Jane", "last_name": "Doe"},
        "email_addresses": {"items": ["j@x.com", "jane@y.com"]},
        "active": True,
        "score": None,
        "_created_at": "2024-01-01",
        "amount": 12.5,
    },
}


def test_items_of_and_flatten():
    assert items_of({"data": [PERSON]}) == ([PERSON], False)
    assert items_of({"data": PERSON}) == ([PERSON], True)
    assert items_of([1, 2]) == ([1, 2], False)
    assert items_of({"a": 1}) == ([{"a": 1}], True)
    row = flatten_item(PERSON)
    assert row["id"] == "p1" and row["type"] == "person" and row["active"] is True
    assert flatten_item({"plain": 1}) == {"plain": 1}
    assert flatten_item("x") == {"value": "x"}


def test_render_value():
    assert render_value(None) == ""
    assert render_value(True) == "true"
    assert render_value(3) == "3"
    assert render_value({"items": ["a", "b"]}) == "a, b"
    assert render_value({"first_name": "J"}) == '{"first_name":"J"}'
    assert render_value([1, "x"]) == '[1,"x"]'


def test_default_columns_skip_system_fields():
    rows = [flatten_item(PERSON)]
    assert default_columns(rows) == ["id", "name", "email_addresses", "active", "score", "amount"]


def test_emit_json(capsys):
    emit(make_state(output="json"), {"data": [PERSON]})
    assert json.loads(capsys.readouterr().out) == {"data": [PERSON]}


def test_emit_ndjson(capsys):
    emit(make_state(output="ndjson"), {"data": [PERSON, PERSON]})
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2 and json.loads(lines[0]) == PERSON


def test_emit_csv_with_fields(capsys):
    emit(
        make_state(output="csv", fields=["id", "name.first_name", "email_addresses"]),
        {"data": [PERSON]},
    )
    out = capsys.readouterr().out
    assert out == 'id,name.first_name,email_addresses\np1,Jane,"j@x.com, jane@y.com"\n'


def test_emit_table_list_and_footer(capsys):
    emit(make_state(output="table"), {"data": [PERSON], "meta": {"total_records": 9}})
    captured = capsys.readouterr()
    assert "p1" in captured.out and "Jane" in captured.out
    assert "Showing 1 of 9" in captured.err


def test_emit_table_single_is_key_value(capsys):
    emit(make_state(output="table"), {"data": PERSON})
    out = capsys.readouterr().out
    assert "email_addresses" in out and "j@x.com, jane@y.com" in out


def test_emit_none_prints_nothing(capsys):
    emit(make_state(output="json"), None)
    assert capsys.readouterr().out == ""


def test_emit_defaults_to_json_when_not_a_tty(capsys):
    emit(make_state(), {"a": 1})
    assert json.loads(capsys.readouterr().out) == {"a": 1}
