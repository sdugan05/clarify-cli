"""Assertion helpers shared by command tests."""

from __future__ import annotations

import json
from typing import Any

import httpx


def query_pairs(request: httpx.Request) -> list[tuple[str, str]]:
    """Decoded query parameters of a captured request, in order."""
    return list(request.url.params.multi_items())


def json_body(request: httpx.Request) -> Any:
    return json.loads(request.content.decode("utf-8"))


def page(
    items: list[dict[str, Any]],
    *,
    total: int | None = None,
    next_url: str | None = None,
    included: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a JSON:API list envelope like the API returns."""
    body: dict[str, Any] = {
        "data": items,
        "meta": {
            "total_records": total if total is not None else len(items),
            "offset": 0,
            "limit": len(items),
        },
        "links": {"next": next_url, "prev": None},
    }
    if included is not None:
        body["included"] = included
    return body


def resource(type_: str, id_: str, **attributes: Any) -> dict[str, Any]:
    return {"type": type_, "id": id_, "attributes": attributes}
