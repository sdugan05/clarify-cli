from __future__ import annotations

import io
import json

import pytest

from clarify_cli.errors import UsageError
from clarify_cli.inputs import (
    body_from_options,
    coerce_scalar,
    load_json,
    load_records,
    parse_set,
    read_source,
    to_resources,
)


def test_coerce_scalar():
    assert coerce_scalar("100") == 100
    assert coerce_scalar("1.5") == 1.5
    assert coerce_scalar("true") is True
    assert coerce_scalar("null") is None
    assert coerce_scalar('["a","b"]') == ["a", "b"]
    assert coerce_scalar('{"a":1}') == {"a": 1}
    assert coerce_scalar("Jane") == "Jane"
    assert coerce_scalar('"100"') == "100"
    assert coerce_scalar("") == ""
    assert coerce_scalar("2024-01-01") == "2024-01-01"


def test_parse_set_nests_and_merges(tmp_path):
    note = tmp_path / "note.txt"
    note.write_text("hello")
    attrs = parse_set(
        [
            "name.first_name=Jane",
            "name.last_name=Doe",
            "amount=5",
            "notes=@" + str(note),
            'email_addresses={"items":["j@x.com"]}',
        ]
    )
    assert attrs == {
        "name": {"first_name": "Jane", "last_name": "Doe"},
        "amount": 5,
        "notes": "hello",
        "email_addresses": {"items": ["j@x.com"]},
    }
    with pytest.raises(UsageError):
        parse_set(["novalue"])


def test_read_source_and_load_json(tmp_path, monkeypatch):
    f = tmp_path / "b.json"
    f.write_text('{"a": 1}')
    assert read_source("@" + str(f)) == '{"a": 1}'
    assert load_json("@" + str(f)) == {"a": 1}
    assert load_json('{"b": 2}') == {"b": 2}
    assert load_json(None) is None
    monkeypatch.setattr("sys.stdin", io.StringIO("[1,2]"))
    assert load_json("-") == [1, 2]
    with pytest.raises(UsageError):
        load_json("{not json")
    with pytest.raises(UsageError):
        load_json("   ")
    with pytest.raises(UsageError):
        read_source("@" + str(tmp_path / "missing.json"))


def test_body_from_options_wraps_attributes():
    doc = body_from_options(
        "person",
        data='{"name": {"first_name": "A"}}',
        set_values=["name.last_name=B", "age=3"],
    )
    assert doc == {
        "data": {
            "type": "person",
            "attributes": {"name": {"first_name": "A", "last_name": "B"}, "age": 3},
        }
    }


def test_body_from_options_respects_full_documents():
    full = {
        "data": {"type": "person", "id": "1", "attributes": {"x": 1}},
        "meta": {"x": {"collection": "append"}},
    }
    doc = body_from_options("person", data=json.dumps(full), set_values=None)
    assert doc == full
    bare = body_from_options("deal", data='{"attributes": {"name": "N"}}', set_values=None, id="7")
    assert bare == {"data": {"type": "deal", "id": "7", "attributes": {"name": "N"}}}


def test_body_from_options_requires_input():
    with pytest.raises(UsageError):
        body_from_options("person", data=None, set_values=None)
    assert body_from_options("person", data=None, set_values=None, require=False) == {
        "data": {"type": "person", "attributes": {}}
    }
    with pytest.raises(UsageError):
        body_from_options("person", data="[1]", set_values=None)


def test_load_records_json_ndjson_csv(tmp_path):
    (tmp_path / "a.json").write_text(
        '[{"name": "A"}, {"type": "person", "attributes": {"name": "B"}}]'
    )
    (tmp_path / "b.json").write_text('{"data": [{"name": "C"}]}')
    (tmp_path / "c.ndjson").write_text('{"name": "D"}\n\n{"name": "E"}\n')
    (tmp_path / "d.csv").write_text(
        "id,name.first_name,name.last_name,email\n1,Jane,Doe,j@x.com\n2,Bob,,\n"
    )
    assert load_records(str(tmp_path / "a.json")) == [
        {"name": "A"},
        {"type": "person", "attributes": {"name": "B"}},
    ]
    assert load_records(str(tmp_path / "b.json")) == [{"name": "C"}]
    assert load_records(str(tmp_path / "c.ndjson")) == [{"name": "D"}, {"name": "E"}]
    assert load_records(str(tmp_path / "d.csv")) == [
        {"id": "1", "name": {"first_name": "Jane", "last_name": "Doe"}, "email": "j@x.com"},
        {"id": "2", "name": {"first_name": "Bob"}},
    ]
    (tmp_path / "e.txt").write_text('{"name": "F"}')
    assert load_records(str(tmp_path / "e.txt"), fmt="ndjson") == [{"name": "F"}]
    (tmp_path / "bad.json").write_text("[1]")
    with pytest.raises(UsageError):
        load_records(str(tmp_path / "bad.json"))
    with pytest.raises(UsageError):
        load_records(str(tmp_path / "missing.json"))


def test_to_resources_lifts_ids():
    out = to_resources(
        [{"id": 5, "name": "A"}, {"name": "B"}, {"attributes": {"name": "C"}}], "person"
    )
    assert out == [
        {"type": "person", "id": "5", "attributes": {"name": "A"}},
        {"type": "person", "attributes": {"name": "B"}},
        {"attributes": {"name": "C"}, "type": "person"},
    ]
