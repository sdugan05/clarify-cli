"""Rendering results as JSON, NDJSON, tables, or CSV."""

from __future__ import annotations

import csv
import json
import sys
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from rich import box
from rich.table import Table

from .console import console, err_console

if TYPE_CHECKING:
    from .state import AppState

DEFAULT_COLUMN_COUNT = 6
MAX_COLUMN_WIDTH = 48
ID_COLUMN_WIDTH = 36


class OutputFormat(StrEnum):
    json = "json"
    table = "table"
    ndjson = "ndjson"
    csv = "csv"


def resolve_format(state: AppState) -> OutputFormat:
    if state.output:
        return OutputFormat(state.output)
    return OutputFormat.table if sys.stdout.isatty() else OutputFormat.json


def items_of(payload: Any) -> tuple[list[Any], bool]:
    """Return ``(items, is_single)`` for a JSON:API envelope, list, or bare value."""
    if isinstance(payload, dict) and "data" in payload:
        data = payload["data"]
        if isinstance(data, list):
            return data, False
        return [data], True
    if isinstance(payload, list):
        return payload, False
    return [payload], True


def flatten_item(item: Any) -> dict[str, Any]:
    """Flatten a JSON:API resource to ``{id, type, **attributes}``."""
    if isinstance(item, dict) and isinstance(item.get("attributes"), dict):
        row: dict[str, Any] = {}
        if "id" in item:
            row["id"] = item["id"]
        if "type" in item:
            row["type"] = item["type"]
        row.update(item["attributes"])
        for key in ("relationships", "meta", "links"):
            if key in item and key not in row:
                row[key] = item[key]
        return row
    if isinstance(item, dict):
        return item
    return {"value": item}


def lookup(row: dict[str, Any], path: str) -> Any:
    """Fetch ``a.b.c`` from nested dicts; ``None`` when missing."""
    node: Any = row
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def render_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and set(value) == {"items"} and isinstance(value["items"], list):
        return ", ".join(render_value(v) for v in value["items"])
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def default_columns(rows: list[dict[str, Any]]) -> list[str]:
    ordered: list[str] = []
    for row in rows:
        for key in row:
            if key not in ordered:
                ordered.append(key)
    columns = [k for k in ordered if k in ("id",)]
    columns += [
        k
        for k in ordered
        if k not in ("id", "type", "relationships", "meta", "links") and not k.startswith("_")
    ][:DEFAULT_COLUMN_COUNT]
    if not columns:
        columns = ordered[: DEFAULT_COLUMN_COUNT + 1]
    return columns


def emit(state: AppState, payload: Any, *, fields: list[str] | None = None) -> None:
    """Print ``payload`` in the user's chosen format. The only output path for results."""
    if payload is None:
        return
    fmt = resolve_format(state)
    columns = fields or state.fields

    if fmt is OutputFormat.json:
        if isinstance(payload, str):
            print(payload, end="" if payload.endswith("\n") else "\n")
        else:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    items, single = items_of(payload)
    if fmt is OutputFormat.ndjson:
        for item in items:
            print(json.dumps(item, ensure_ascii=False))
        return

    rows = [flatten_item(item) for item in items]
    if fmt is OutputFormat.csv:
        _write_csv(rows, columns)
        return

    if single:
        _render_kv_table(rows[0], columns)
    else:
        _render_table(rows, columns or default_columns(rows))
        _footer(payload, len(rows))


def emit_message(message: str) -> None:
    """Print a status line to stderr so stdout stays machine-readable."""
    err_console.print(message)


def _write_csv(rows: list[dict[str, Any]], columns: list[str] | None) -> None:
    cols = columns or _all_columns(rows)
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(cols)
    for row in rows:
        writer.writerow([render_value(lookup(row, c)) for c in cols])


def _all_columns(rows: list[dict[str, Any]]) -> list[str]:
    cols: list[str] = []
    for row in rows:
        for key in row:
            if key not in cols:
                cols.append(key)
    return cols


def _render_table(rows: list[dict[str, Any]], columns: list[str]) -> None:
    table = Table(box=box.SIMPLE_HEAD, header_style="bold", show_edge=False, pad_edge=False)
    for col in columns:
        if col == "id":
            # Never squeeze IDs: they are what the user copies into the next command.
            width = min(max((len(str(r.get("id", ""))) for r in rows), default=2), ID_COLUMN_WIDTH)
            table.add_column(col, no_wrap=True, min_width=width, style="dim")
        else:
            table.add_column(col, overflow="ellipsis", max_width=MAX_COLUMN_WIDTH, no_wrap=True)
    for row in rows:
        table.add_row(*(render_value(lookup(row, c)) for c in columns))
    if not rows:
        err_console.print("[dim]No results.[/]")
        return
    console.print(table)


def _render_kv_table(row: dict[str, Any], columns: list[str] | None) -> None:
    table = Table(box=box.SIMPLE_HEAD, header_style="bold", show_edge=False, pad_edge=False)
    table.add_column("field", style="cyan", no_wrap=True)
    table.add_column("value", overflow="fold")
    keys = columns or list(row.keys())
    for key in keys:
        table.add_row(key, render_value(lookup(row, key)))
    console.print(table)


def _footer(payload: Any, shown: int) -> None:
    if not isinstance(payload, dict):
        return
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return
    total = meta.get("total_records")
    if isinstance(total, int) and total > shown:
        err_console.print(f"[dim]Showing {shown} of {total}. Use --all or --limit to see more.[/]")
