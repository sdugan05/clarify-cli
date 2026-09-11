"""``clarify relationships``: links between records (RecordRelationships tag).

The three operations share one path,
``/objects/{object}/records/{id}/relationships/{relationship}``, and the two
mutations share one body shape (``UpdateRelationshipDto``)::

    {"data": [{"type": "deal", "id": "<related record id>"}, ...]}

``id`` may be ``null`` to clear a to-one relationship or, for one-to-many
relationships, to unlink every related record before linking the rest.
"""

from __future__ import annotations

from typing import Annotated, Any

import typer

from ..cli_options import (
    AllOpt,
    DataOpt,
    IncludeOpt,
    LimitOpt,
    ObjectArg,
    OffsetOpt,
    PageSizeOpt,
    SortOpt,
)
from ..errors import UsageError
from ..inputs import load_json
from ..output import emit, emit_message
from ..params import collect_list
from ..state import get_state

app = typer.Typer(no_args_is_help=True)

# OpenAPI operationId -> command name.
OPERATIONS: dict[str, str] = {
    "getRecordRelationships": "list",
    "updateRecordRelationship": "set",
    "deleteRecordRelationship": "unlink",
}

#: The list endpoint accepts at most 500 items per page (``page[limit]`` maximum).
MAX_PAGE_SIZE = 500

RecordIdArg = Annotated[str, typer.Argument(help="The record's ID.", metavar="ID")]
FieldArg = Annotated[
    str,
    typer.Argument(
        help="The relationship field name on OBJECT, e.g. deals, people, or company_id.",
        metavar="FIELD",
    ),
]
IdOpt = Annotated[
    list[str] | None,
    typer.Option("--id", help="ID of a related record (repeatable)."),
]
TypeOpt = Annotated[
    str | None,
    typer.Option(
        "--type",
        help=(
            "Object type of the records given with --id. Derived from FIELD when omitted "
            "(deals -> deal, companies -> company, people -> person, company_id -> company); "
            "pass it explicitly when FIELD is not named after its target object."
        ),
    ),
]
ClearOpt = Annotated[
    bool,
    typer.Option(
        "--clear",
        help=(
            'Send {"id": null} first: clears a to-one relationship, or unlinks every related '
            "record before linking the --id records."
        ),
    ),
]

_DATA_SHAPE = (
    '--data must be {"data": [...]}, a JSON array of {"type", "id"} objects, or one such object.'
)


def _path(object_type: str, record_id: str, relationship: str) -> str:
    return f"/objects/{object_type}/records/{record_id}/relationships/{relationship}"


def default_type(relationship: str) -> str:
    """Guess the related object type from a relationship field name.

    ``company_id`` -> ``company``, ``deals`` -> ``deal``, ``companies`` -> ``company``,
    ``people`` -> ``person``, ``c_sales_orders`` -> ``c_sales_order``. Only a
    convenience for the common cases; ``--type`` overrides it.
    """
    name = relationship
    for suffix in ("_ids", "_id"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    if name == "people":
        return "person"
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name


def build_body(
    relationship: str,
    *,
    data: str | None,
    ids: list[str] | None,
    type_: str | None,
    clear: bool = False,
) -> dict[str, Any]:
    """Build the ``UpdateRelationshipDto`` document from the command's options.

    ``--data`` is sent as-is when it already has a top-level ``data`` key; a
    bare array (or a single ``{"type", "id"}`` object) is wrapped. Otherwise
    the document is assembled from ``--id``/``--type``, with the ``id: null``
    entry first when ``--clear`` is set.
    """
    if data is not None:
        if ids or type_ or clear:
            raise UsageError("--data cannot be combined with --id, --type, or --clear.")
        parsed = load_json(data)
        if isinstance(parsed, dict) and "data" in parsed:
            return parsed
        if isinstance(parsed, dict) and "id" in parsed:
            parsed = [parsed]
        if not isinstance(parsed, list):
            raise UsageError(_DATA_SHAPE)
        return {"data": parsed}
    if not ids and not clear:
        raise UsageError("Provide --id ID (repeatable), --clear, or --data JSON|@file|-.")
    related_type = type_ or default_type(relationship)
    items: list[dict[str, Any]] = []
    if clear:
        items.append({"type": related_type, "id": None})
    items.extend({"type": related_type, "id": rid} for rid in ids or [])
    return {"data": items}


def _count(body: dict[str, Any]) -> int:
    data = body.get("data")
    return len(data) if isinstance(data, list) else 1


def _unlinks_all(body: dict[str, Any]) -> bool:
    """Whether a PATCH body unlinks every related record.

    True for an empty ``data`` list (the replaced set is empty) and for any
    entry with ``id: null`` (clears a to-one link, or unlinks everything on a
    one-to-many relationship), however the body was supplied.
    """
    data = body.get("data")
    if not isinstance(data, list):
        return False
    return not data or any(isinstance(item, dict) and item.get("id") is None for item in data)


@app.command("list")
def list_related(
    ctx: typer.Context,
    object_type: ObjectArg,
    record_id: RecordIdArg,
    relationship: FieldArg,
    limit: LimitOpt = 50,
    offset: OffsetOpt = 0,
    all_pages: AllOpt = False,
    page_size: PageSizeOpt = None,
    sort: SortOpt = None,
    include: IncludeOpt = None,
) -> None:
    """List related records (GET /objects/{object}/records/{id}/relationships/{relationship}).

    Returns the records linked to the record through FIELD, e.g. the deals of
    a person. `--include` takes nested relationship paths relative to the
    parent record, such as `companies.deals`.

    Example:

        clarify relationships list person 5f8b7d2e-9c4a-4e1b-8f3d-2a6c9e0b4d71 deals -n 20
    """
    state = get_state(ctx)
    if page_size is None and not all_pages:
        page_size = min(limit, MAX_PAGE_SIZE)
    result = collect_list(
        state,
        _path(object_type, record_id, relationship),
        sort=sort,
        include=include,
        limit=limit,
        offset=offset,
        all_pages=all_pages,
        page_size=page_size,
    )
    emit(state, result)


@app.command("set")
def set_related(
    ctx: typer.Context,
    object_type: ObjectArg,
    record_id: RecordIdArg,
    relationship: FieldArg,
    ids: IdOpt = None,
    type_: TypeOpt = None,
    clear: ClearOpt = False,
    data: DataOpt = None,
) -> None:
    """Link related records (PATCH /objects/{object}/records/{id}/relationships/{relationship}).

    For to-one and many-to-many relationships (a person's company, the people
    on a deal) the request REPLACES the whole set: related records not listed
    are unlinked. For one-to-many relationships (a company's people) it is
    ADDITIVE: the listed records are linked and existing links stay, though a
    record that already belongs to another parent is reassigned. `--clear`
    sends the `{"id": null}` entry first to unlink every related record (or
    clear a to-one link). Any body that unlinks everything (`--clear`, an
    empty list, or an `id: null` entry in `--data`) asks for confirmation;
    `--yes` skips the prompt. Use `relationships unlink` to remove specific
    records.

    Examples:

        clarify relationships set person PERSON_ID deals --id DEAL_ID --id OTHER_DEAL_ID

        clarify relationships set person PERSON_ID company_id --id COMPANY_ID

        clarify relationships set company COMPANY_ID people --clear --id PERSON_ID --yes

        clarify relationships set deal DEAL_ID people --data @people.json
    """
    state = get_state(ctx)
    body = build_body(relationship, data=data, ids=ids, type_=type_, clear=clear)
    if _unlinks_all(body):
        state.confirm(
            f"Unlink every record related through {relationship} on {object_type} {record_id}?"
        )
    result = state.client().patch(
        _path(object_type, record_id, relationship), json_body=body, silent=state.silent
    )
    if result:
        emit(state, result)
        return
    emit_message(f"Updated {relationship} on {object_type} {record_id} ({_count(body)} item(s)).")


@app.command("unlink")
def unlink_related(
    ctx: typer.Context,
    object_type: ObjectArg,
    record_id: RecordIdArg,
    relationship: FieldArg,
    ids: IdOpt = None,
    type_: TypeOpt = None,
    data: DataOpt = None,
) -> None:
    """Unlink related records (DELETE /objects/{object}/records/{id}/relationships/{relationship}).

    Removes the links to the listed records from FIELD; the records
    themselves are not deleted. Asks for confirmation unless `--yes` is given.

    Examples:

        clarify relationships unlink person PERSON_ID deals --id DEAL_ID --yes

        clarify relationships unlink deal DEAL_ID people --data '[{"type": "person", "id": "P1"}]'
    """
    state = get_state(ctx)
    body = build_body(relationship, data=data, ids=ids, type_=type_)
    count = _count(body)
    state.confirm(f"Unlink {count} record(s) from {relationship} on {object_type} {record_id}?")
    result = state.client().delete(
        _path(object_type, record_id, relationship), json_body=body, silent=state.silent
    )
    if result:
        emit(state, result)
        return
    emit_message(f"Unlinked {count} record(s) from {relationship} on {object_type} {record_id}.")
