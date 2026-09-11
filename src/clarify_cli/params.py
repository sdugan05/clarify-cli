"""Parsing of list-style options (``--filter``, ``--sort``, paging) and a shared
``collect_list`` helper so every list command behaves identically."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .client import ParamPairs
from .errors import UsageError

if TYPE_CHECKING:
    from .state import AppState

_FILTER_KEY = re.compile(r"^(?P<field>[^\[\]]+)(?P<op>\[[^\]]+\])?$")


def parse_filters(values: list[str] | None) -> ParamPairs:
    """Turn ``FIELD=VALUE`` / ``FIELD[Operator]=VALUE`` into ``filter[...]`` pairs.

    Values are passed through untouched so the API's shorthand (``>100``,
    ``*Smith*``, ``null``, ``a,b``) keeps working. Keys that already start with
    ``filter[`` are sent as-is.
    """
    pairs: ParamPairs = []
    for raw in values or []:
        key, sep, value = raw.partition("=")
        key = key.strip()
        if not sep or not key:
            raise UsageError(
                f"Invalid --filter {raw!r}; expected FIELD=VALUE or 'FIELD[Operator]=VALUE'."
            )
        if key.startswith("filter["):
            pairs.append((key, value))
            continue
        match = _FILTER_KEY.match(key)
        if not match:
            raise UsageError(f"Invalid --filter key {key!r}; expected FIELD or FIELD[Operator].")
        pairs.append((f"filter[{match.group('field')}]{match.group('op') or ''}", value))
    return pairs


def parse_sort(value: str | None) -> ParamPairs:
    """``FIELD``, ``FIELD:asc``, ``FIELD:desc`` or ``-FIELD`` → ``sortOrder[...]`` pairs."""
    if not value:
        return []
    column, _, direction = value.partition(":")
    column = column.strip()
    if column.startswith("-") and not direction:
        column, direction = column[1:], "desc"
    direction = (direction or "asc").strip().upper()
    if not column:
        raise UsageError(f"Invalid --sort {value!r}; expected FIELD[:asc|:desc].")
    if direction not in ("ASC", "DESC"):
        raise UsageError(f"Invalid sort direction {direction!r}; use asc or desc.")
    return [("sortOrder[column]", column), ("sortOrder[dir]", direction)]


def parse_kv(values: list[str] | None, *, flag: str = "--param") -> ParamPairs:
    """Parse repeatable ``KEY=VALUE`` options into pairs."""
    pairs: ParamPairs = []
    for raw in values or []:
        key, sep, value = raw.partition("=")
        if not sep or not key.strip():
            raise UsageError(f"Invalid {flag} {raw!r}; expected KEY=VALUE.")
        pairs.append((key.strip(), value))
    return pairs


def parse_csv_list(value: str | None) -> list[str]:
    """Split a comma-separated option value, dropping blanks."""
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def collect_list(
    state: AppState,
    path: str,
    *,
    filters: list[str] | None = None,
    sort: str | None = None,
    include: str | None = None,
    search: str | None = None,
    limit: int | None = 50,
    offset: int = 0,
    all_pages: bool = False,
    page_size: int | None = None,
    extra: ParamPairs | None = None,
) -> dict[str, Any]:
    """Build query parameters from the standard list options and fetch the items."""
    params: ParamPairs = []
    params.extend(parse_filters(filters))
    params.extend(parse_sort(sort))
    if include:
        params.append(("include", ",".join(parse_csv_list(include))))
    if search:
        params.append(("search", search))
    if extra:
        params.extend(extra)
    return state.client().collect(
        path,
        params,
        limit=None if all_pages else limit,
        all_pages=all_pages,
        page_size=page_size,
        offset=offset or None,
    )
