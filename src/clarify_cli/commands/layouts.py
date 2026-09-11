"""``clarify layouts``: workspace UI layouts (Layouts tag).

A layout's ``tree`` describes navigation and record-page regions. The CLI does
not model the tree; it passes JSON through.
"""

from __future__ import annotations

from typing import Annotated, Any

import typer

from ..cli_options import DataOpt
from ..errors import UsageError
from ..inputs import load_json
from ..output import emit, emit_message
from ..state import get_state

app = typer.Typer(no_args_is_help=True)

# OpenAPI operationId -> command name.
OPERATIONS: dict[str, str] = {
    "getLayoutById": "get",
    "updateLayout": "update",
    "resetLayout": "reset",
}

LAYOUT_TYPE = "layout"

LayoutIdArg = Annotated[
    str, typer.Argument(help="The layout's ID, e.g. list__person.", metavar="LAYOUT_ID")
]


def build_update_body(layout_id: str, data: str | None) -> dict[str, Any]:
    """Turn ``--data`` into the UpdateLayoutBodyDto document.

    Accepted inputs, detected by shape:

    - a full document ``{"data": {...}}`` — sent as is (``type``/``id`` filled in);
    - a resource ``{"type", "id", "attributes": {...}}`` — wrapped in ``data``;
    - an object with a ``tree`` key, such as the output of ``layouts get`` — only
      ``tree`` is taken, so ``_id``/``_created_at`` from a fetched layout are dropped;
    - the bare tree ``{"version": 1, "children": [...]}``.
    """
    parsed = load_json(data, what="layout") if data is not None else None
    if parsed is None:
        raise UsageError("Provide the layout tree with --data JSON|@file|-.")
    if not isinstance(parsed, dict):
        raise UsageError("--data must be a JSON object.")

    if isinstance(parsed.get("data"), dict):
        document = parsed
        res = parsed["data"]
    elif isinstance(parsed.get("attributes"), dict):
        res = parsed
        document = {"data": res}
    elif "tree" in parsed:
        res = {"attributes": {"tree": parsed["tree"]}}
        document = {"data": res}
    elif "version" in parsed and "children" in parsed:
        res = {"attributes": {"tree": parsed}}
        document = {"data": res}
    else:
        raise UsageError(
            "Unrecognised layout body.",
            hint='Pass the tree ({"version": 1, "children": [...]}), an object with a '
            '"tree" key, or a full {"data": {...}} document.',
        )
    res.setdefault("type", LAYOUT_TYPE)
    res.setdefault("id", layout_id)
    return document


@app.command()
def get(ctx: typer.Context, layout_id: LayoutIdArg) -> None:
    """Show one layout and its tree (GET /layouts/{id})."""
    state = get_state(ctx)
    emit(state, state.client().get(f"/layouts/{layout_id}"))


@app.command()
def update(ctx: typer.Context, layout_id: LayoutIdArg, data: DataOpt = None) -> None:
    """Replace a layout's tree (PATCH /layouts/{id}).

    Sends ``{"data": {"type": "layout", "id": LAYOUT_ID, "attributes": {"tree": ...}}}``.
    ``--data`` may be the bare tree, an object with a ``tree`` key (for example
    the output of ``layouts get``, edited), a resource, or the full document.

    Example (round trip):

        clarify layouts get list__person > layout.json

        # edit layout.json, then:
        clarify layouts update list__person --data @layout.json
    """
    state = get_state(ctx)
    body = build_update_body(layout_id, data)
    emit(state, state.client().patch(f"/layouts/{layout_id}", json_body=body, silent=state.silent))


@app.command()
def reset(ctx: typer.Context, layout_id: LayoutIdArg) -> None:
    """Restore a layout to its default tree (POST /layouts/{id}/reset).

    Discards every customisation of the layout, so it asks for confirmation
    unless --yes is given. Prints the restored layout.
    """
    state = get_state(ctx)
    state.confirm(f"Reset layout {layout_id} to its default tree? Customisations will be lost.")
    result = state.client().post(f"/layouts/{layout_id}/reset", silent=state.silent)
    if result is None:
        emit_message(f"Reset layout {layout_id}.")
        return
    emit(state, result)
