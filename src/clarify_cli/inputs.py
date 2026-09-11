"""Reading request bodies from ``--data``, ``--set KEY=VALUE``, and record files."""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path
from typing import Any

from .errors import UsageError


def read_source(value: str | None) -> str | None:
    """Resolve ``--data`` style input: ``-`` reads stdin, ``@path`` reads a file."""
    if value is None:
        return None
    if value == "-":
        return sys.stdin.read()
    if value.startswith("@"):
        path = Path(value[1:]).expanduser()
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise UsageError(f"Cannot read {path}: {exc}") from exc
    return value


def load_json(value: str | None, *, what: str = "body") -> Any:
    """Parse JSON from an inline value, ``@file`` or ``-`` (stdin)."""
    text = read_source(value)
    if text is None:
        return None
    if not text.strip():
        raise UsageError(f"Empty JSON {what}.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise UsageError(
            f"Invalid JSON {what}: {exc.msg} (line {exc.lineno}, column {exc.colno})."
        ) from exc


def coerce_scalar(text: str) -> Any:
    """Interpret ``--set`` values: JSON when it parses, otherwise the raw string.

    ``100`` → ``100``, ``true`` → ``True``, ``null`` → ``None``, ``[1,2]`` → list,
    ``Jane`` → ``"Jane"``, ``'"100"'`` → ``"100"``.
    """
    stripped = text.strip()
    if not stripped:
        return text
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return text
    return parsed


def deep_set(target: dict[str, Any], dotted_key: str, value: Any) -> None:
    """Assign ``value`` at ``a.b.c`` inside ``target``, creating nested dicts."""
    parts = [p for p in dotted_key.split(".") if p]
    if not parts:
        raise UsageError(f"Invalid key {dotted_key!r}.")
    node = target
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def parse_set(values: list[str] | None) -> dict[str, Any]:
    """Parse repeatable ``--set KEY=VALUE`` options into a (nested) attributes dict.

    A value of the form ``@path`` is replaced by that file's text.
    """
    out: dict[str, Any] = {}
    for raw in values or []:
        key, sep, value = raw.partition("=")
        key = key.strip()
        if not sep or not key:
            raise UsageError(f"Invalid --set {raw!r}; expected KEY=VALUE.")
        if value.startswith("@"):
            deep_set(out, key, read_source(value))
        else:
            deep_set(out, key, coerce_scalar(value))
    return out


def resource(
    object_type: str, attributes: dict[str, Any], *, id: str | None = None
) -> dict[str, Any]:
    """Build a JSON:API resource object."""
    doc: dict[str, Any] = {"type": object_type}
    if id is not None:
        doc["id"] = id
    doc["attributes"] = attributes
    return doc


def body_from_options(
    object_type: str,
    *,
    data: str | None,
    set_values: list[str] | None,
    id: str | None = None,
    require: bool = True,
) -> dict[str, Any]:
    """Combine ``--data`` and ``--set`` into a ``{"data": {...}}`` document.

    ``--data`` may be a full document (has a top-level ``data`` key), a bare
    resource (has ``attributes``), or just the attributes object. ``--set``
    values are merged over the attributes.
    """
    parsed = load_json(data) if data is not None else None
    overrides = parse_set(set_values)
    if parsed is None and not overrides:
        if require:
            raise UsageError("Provide a body with --data JSON|@file|- and/or --set KEY=VALUE.")
        parsed = {}
    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        raise UsageError("The request body must be a JSON object.")

    if "data" in parsed and isinstance(parsed["data"], dict):
        document = parsed
        res = document["data"]
    elif "attributes" in parsed and isinstance(parsed["attributes"], dict):
        document = {"data": parsed}
        res = parsed
    else:
        res = resource(object_type, parsed, id=id)
        document = {"data": res}
    res.setdefault("type", object_type)
    if id is not None:
        res.setdefault("id", id)
    if overrides:
        attrs = res.setdefault("attributes", {})
        if not isinstance(attrs, dict):
            raise UsageError("`attributes` must be a JSON object.")
        for key, value in overrides.items():
            _merge(attrs, key, value)
    return document


def _merge(attrs: dict[str, Any], key: str, value: Any) -> None:
    existing = attrs.get(key)
    if isinstance(existing, dict) and isinstance(value, dict):
        for sub_key, sub_value in value.items():
            _merge(existing, sub_key, sub_value)
    else:
        attrs[key] = value


def load_records(source: str, *, fmt: str | None = None) -> list[dict[str, Any]]:
    """Load records from a JSON array, ``{"data": [...]}``, NDJSON, or CSV file.

    ``source`` is a path or ``-`` for stdin. ``fmt`` (``json``/``ndjson``/``csv``)
    overrides detection by file suffix. Each returned item is either a JSON:API
    resource (has ``attributes``) or a flat attributes mapping.
    """
    if source == "-":
        text = sys.stdin.read()
        detected = fmt or "json"
    else:
        path = Path(source).expanduser()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise UsageError(f"Cannot read {path}: {exc}") from exc
        suffix = path.suffix.lower()
        detected = fmt or {
            ".json": "json",
            ".ndjson": "ndjson",
            ".jsonl": "ndjson",
            ".csv": "csv",
        }.get(suffix, "json")

    if detected == "csv":
        return _records_from_csv(text)
    if detected == "ndjson":
        items = []
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise UsageError(f"Invalid JSON on line {number}: {exc.msg}.") from exc
        return _check_items(items)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UsageError(f"Invalid JSON records file: {exc.msg} (line {exc.lineno}).") from exc
    if isinstance(parsed, dict) and isinstance(parsed.get("data"), list):
        parsed = parsed["data"]
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        raise UsageError('Records file must contain a JSON array, an object, or {"data": [...]}.')
    return _check_items(parsed)


def _check_items(items: list[Any]) -> list[dict[str, Any]]:
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise UsageError(f"Record #{index + 1} is not a JSON object.")
    return items


def _records_from_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    records: list[dict[str, Any]] = []
    for row in reader:
        item: dict[str, Any] = {}
        for header, cell in row.items():
            if header is None or cell is None or cell == "":
                continue
            deep_set(item, header.strip(), cell)
        if item:
            records.append(item)
    return records


def to_resources(items: list[dict[str, Any]], object_type: str) -> list[dict[str, Any]]:
    """Normalise loaded records into JSON:API resources of ``object_type``.

    Flat mappings become ``{"type", "attributes"}``; an ``id`` key on a flat
    mapping is lifted to the resource level (needed for bulk updates).
    """
    resources: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item.get("attributes"), dict):
            res = dict(item)
            res.setdefault("type", object_type)
            resources.append(res)
            continue
        attrs = dict(item)
        rid = attrs.pop("id", None)
        resources.append(resource(object_type, attrs, id=str(rid) if rid is not None else None))
    return resources
