"""``clarify schemas``: object schemas, fields, relationships and enums (Schemas tag).

``GET /schemas`` returns every JSON Schema in the workspace as one flat list;
``list``, ``objects``, ``get`` and ``fields`` are all client-side views of that
single call. The mutation commands are thin wrappers around the schema
endpoints, each building exactly the body shape the spec declares.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

import typer

from ..cli_options import AllOpt, DataOpt, LimitOpt, ObjectArg, OffsetOpt, PageSizeOpt, SortOpt
from ..errors import EXIT_NOT_FOUND, ClarifyError, UsageError
from ..inputs import load_json
from ..output import OutputFormat, emit, emit_message, resolve_format
from ..params import collect_list, parse_csv_list
from ..state import AppState, get_state

app = typer.Typer(no_args_is_help=True)

# OpenAPI operationId -> command name. Every module declares this so a test can
# prove the CLI covers the whole spec. ``objects``, ``get`` and ``fields`` are
# client-side views of getSchemas and therefore not listed separately.
OPERATIONS: dict[str, str] = {
    "getSchemas": "list",
    "createCustomObject": "create-object",
    "updateEntitySchema": "replace",
    "deleteCustomObject": "delete-object",
    "createSchemaProperties": "add-fields",
    "createSchemaRelationshipProperties": "add-relationships",
    "deleteSchemaRelationshipProperty": "delete-relationship",
    "updateSchemaPropertyOrder": "reorder",
    "updateSchemaPropertyVisibility": "visibility",
    "patchEnumFieldValues": "enum",
    "getSchemaActivities": "activities",
}

SCHEMA_ID_PREFIX = "https://getclarify.ai/schemas/entities/"
ACTIVITIES_MAX_PAGE = 500  # page[limit] maximum declared by getSchemaActivities

EntityArg = Annotated[
    str,
    typer.Argument(
        help="Object type: person, company, deal, meeting, task, or a custom c_* object.",
        metavar="ENTITY",
    ),
]
FieldArg = Annotated[str, typer.Argument(help="The field name.", metavar="FIELD")]


class EnumOp(StrEnum):
    """The ``meta.FIELD.enum`` operation of patchEnumFieldValues."""

    append = "append"
    remove = "remove"


# -- helpers -------------------------------------------------------------------
def schema_id(entity: str) -> str:
    """``c_project`` -> ``https://getclarify.ai/schemas/entities/c_project`` (URLs pass through)."""
    if entity.startswith(("http://", "https://")):
        return entity
    return SCHEMA_ID_PREFIX + entity


def entity_name(schema: dict[str, Any]) -> str | None:
    """The object name of a schema resource, or ``None`` for ``core/*`` definitions."""
    sid = schema.get("id")
    if not isinstance(sid, str):
        attrs = schema.get("attributes")
        sid = attrs.get("$id") if isinstance(attrs, dict) else None
    if isinstance(sid, str) and "/entities/" in sid:
        return sid.rsplit("/entities/", 1)[1].strip("/") or None
    return None


def fetch_schemas(state: AppState) -> dict[str, Any]:
    """``GET /schemas``, following ``links.next`` verbatim; returns a merged envelope."""
    data: list[Any] = []
    for page in state.client().pages("/schemas"):
        items = page.get("data") or []
        data.extend(items if isinstance(items, list) else [items])
    return {"data": data, "meta": {"returned": len(data)}}


def find_schema(state: AppState, obj: str) -> dict[str, Any]:
    """Select one object's schema from ``GET /schemas``; exit 4 when absent."""
    wanted = schema_id(obj)
    for schema in fetch_schemas(state)["data"]:
        if not isinstance(schema, dict):
            continue
        if schema.get("id") == wanted or entity_name(schema) == obj:
            return schema
    raise ClarifyError(
        f"No schema found for object {obj!r}.",
        exit_code=EXIT_NOT_FOUND,
        hint="Run `clarify schemas objects` to list the available object types.",
    )


def properties_of(schema: dict[str, Any]) -> dict[str, Any]:
    attrs = schema.get("attributes")
    props = attrs.get("properties") if isinstance(attrs, dict) else None
    return props if isinstance(props, dict) else {}


def field_type(prop: dict[str, Any]) -> str:
    """A compact type label for a JSON Schema property (``null`` dropped)."""
    if "$ref" in prop and isinstance(prop["$ref"], str):
        return prop["$ref"].rsplit("/", 1)[-1]
    if isinstance(prop.get("oneOf"), list):
        parts = [field_type(v) for v in prop["oneOf"] if isinstance(v, dict)]
        return "|".join(p for p in parts if p and p != "null") or "oneOf"
    raw = prop.get("type")
    types = raw if isinstance(raw, list) else [raw]
    label = "|".join(str(t) for t in types if t and t != "null")
    if "enum" in prop:
        label = f"{label or 'string'} enum"
    elif prop.get("format"):
        label = f"{label} ({prop['format']})"
    return label


def field_rows(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a schema's ``properties`` into one resource per field for ``fields``."""
    attrs = schema.get("attributes") if isinstance(schema.get("attributes"), dict) else {}
    required = attrs.get("required") if isinstance(attrs.get("required"), list) else []
    rows: list[dict[str, Any]] = []
    for name, prop in properties_of(schema).items():
        if not isinstance(prop, dict):
            continue
        presentation = prop.get("xClarifyPresentation")
        presentation = presentation if isinstance(presentation, dict) else {}
        rel = prop.get("xClarifyRelationship")
        rel = rel if isinstance(rel, dict) else None
        rows.append(
            {
                "type": "field",
                "id": name,
                "attributes": {
                    "title": prop.get("title"),
                    "type": field_type(prop),
                    "required": name in required,
                    "unique": bool(prop.get("xClarifyUnique") or prop.get("unique")),
                    "hidden": bool(
                        presentation.get("hiddenInDetails") or prop.get("hiddenInDetails")
                    ),
                    "relationship": (
                        f"{rel.get('entity')} ({rel.get('kind')} via {rel.get('field')})"
                        if rel
                        else None
                    ),
                    "primary": bool(prop.get("xClarifyPrimary")),
                    "definition": prop,
                },
            }
        )
    return rows


def summary_row(schema: dict[str, Any]) -> dict[str, Any]:
    attrs = schema.get("attributes") if isinstance(schema.get("attributes"), dict) else {}
    label = attrs.get("xClarifyLabel") if isinstance(attrs.get("xClarifyLabel"), dict) else {}
    return {
        "type": "schema",
        "id": schema.get("id"),
        "attributes": {
            "name": entity_name(schema),
            "title": attrs.get("title") or label.get("singular"),
            "fields": len(properties_of(schema)),
        },
    }


def wrap_resource(parsed: Any, resource_type: str) -> dict[str, Any]:
    """``{"data": {...}}`` passes through; anything else becomes the ``attributes``."""
    if isinstance(parsed, dict) and isinstance(parsed.get("data"), dict):
        parsed["data"].setdefault("type", resource_type)
        return parsed
    if not isinstance(parsed, dict):
        raise UsageError("The request body must be a JSON object.")
    return {"data": {"type": resource_type, "attributes": parsed}}


def field_title(name: str) -> str:
    text = name.replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else name


def parse_field_specs(values: list[str] | None) -> dict[str, Any]:
    """``NAME=TYPE`` -> ``{NAME: {"type": [TYPE, "null"], "title": ...}}`` (boolean stays bare)."""
    out: dict[str, Any] = {}
    for raw in values or []:
        name, sep, type_ = raw.partition("=")
        name, type_ = name.strip(), type_.strip()
        if not sep or not name or not type_:
            raise UsageError(f"Invalid --field {raw!r}; expected NAME=TYPE (e.g. budget=number).")
        json_type: Any = "boolean" if type_ == "boolean" else [type_, "null"]
        out[name] = {"type": json_type, "title": field_title(name)}
    return out


def enum_values_of(patch: dict[str, Any]) -> list[str]:
    """The ``enum`` list of a field patch (under ``properties.items.items`` for multi-selects)."""
    inner: Any = patch
    if isinstance(inner.get("properties"), dict):
        inner = inner["properties"].get("items")
        inner = inner.get("items") if isinstance(inner, dict) else None
    values = inner.get("enum") if isinstance(inner, dict) else None
    return [str(v) for v in values] if isinstance(values, list) else []


def emit_or_accepted(state: AppState, result: Any, message: str) -> None:
    """Print a body when the API returns one; otherwise confirm the 202 on stderr."""
    if result is None:
        emit_message(message)
    else:
        emit(state, result)


# -- read commands -------------------------------------------------------------
@app.command("list")
def list_schemas(ctx: typer.Context) -> None:
    """List every schema in the workspace (GET /schemas).

    JSON output is the API's schema list verbatim (pages merged, `links` dropped);
    table/CSV output shows one row per schema with its id, object name, title and
    field count. Example: `clarify schemas list -o table`
    """
    state = get_state(ctx)
    envelope = fetch_schemas(state)
    if resolve_format(state) in (OutputFormat.table, OutputFormat.csv):
        rows = [summary_row(s) for s in envelope["data"] if isinstance(s, dict)]
        emit(
            state,
            {"data": rows, "meta": envelope["meta"]},
            fields=state.fields or ["id", "name", "title", "fields"],
        )
        return
    emit(state, envelope)


@app.command()
def objects(ctx: typer.Context) -> None:
    """List the object types that have a schema: person, company, c_* ... (GET /schemas).

    Derived from `GET /schemas`: only `entities/*` schemas are listed, never the
    shared `core/*` definitions. Example: `clarify schemas objects -o json`
    """
    state = get_state(ctx)
    rows: list[dict[str, Any]] = []
    for schema in fetch_schemas(state)["data"]:
        if not isinstance(schema, dict):
            continue
        name = entity_name(schema)
        if not name:
            continue
        attrs = schema.get("attributes") if isinstance(schema.get("attributes"), dict) else {}
        label = attrs.get("xClarifyLabel") if isinstance(attrs.get("xClarifyLabel"), dict) else {}
        rows.append(
            {
                "type": "object",
                "id": name,
                "attributes": {
                    "title": attrs.get("title") or label.get("singular"),
                    "plural": label.get("plural"),
                    "custom": name.startswith("c_"),
                    "fields": len(properties_of(schema)),
                },
            }
        )
    emit(state, {"data": rows, "meta": {"returned": len(rows)}})


@app.command()
def get(ctx: typer.Context, obj: ObjectArg) -> None:
    """Show one object's full JSON Schema (GET /schemas, selected client-side).

    OBJECT is an object name (`person`, `c_project`) or a full schema id. Exits 4
    when the workspace has no such schema. Example: `clarify schemas get c_project`
    """
    state = get_state(ctx)
    emit(state, {"data": find_schema(state, obj)})


@app.command()
def fields(ctx: typer.Context, obj: ObjectArg) -> None:
    """Tabulate an object's fields: type, required, unique, hidden, relationship (GET /schemas).

    Each row is one entry of the schema's `properties`; the raw JSON Schema of the
    field is kept as `definition` in JSON output. Example: `clarify schemas fields person`
    """
    state = get_state(ctx)
    rows = field_rows(find_schema(state, obj))
    emit(
        state,
        {"data": rows, "meta": {"returned": len(rows)}},
        fields=state.fields
        or ["id", "title", "type", "required", "unique", "hidden", "relationship"],
    )


# -- object commands -----------------------------------------------------------
@app.command("create-object")
def create_object(
    ctx: typer.Context,
    name: Annotated[
        str | None, typer.Option("--name", help="Object name; normalised to c_<name>.")
    ] = None,
    plural: Annotated[
        str | None, typer.Option("--plural", help="Plural display name for the UI.")
    ] = None,
    description: Annotated[
        str | None, typer.Option("--description", help="Description stored as AI context.")
    ] = None,
    icon: Annotated[
        str | None,
        typer.Option("--icon", help="Avatar icon name (e.g. Briefcase, Box, Ticket, Rocket)."),
    ] = None,
    background_color: Annotated[
        str | None,
        typer.Option("--background-color", help="Avatar colour (e.g. blue, green, neutral)."),
    ] = None,
    properties: Annotated[
        str | None,
        typer.Option(
            "--properties",
            help="Initial fields as JSON {name: JSON Schema}: inline, @file, or - for stdin.",
        ),
    ] = None,
    data: DataOpt = None,
) -> None:
    """Create a custom object (POST /schemas/objects).

    The body is the plain CreateCustomObjectDto (`name`, `plural`, `description`,
    `icon`, `backgroundColor`, `properties`); flags override keys from --data.
    Example: `clarify schemas create-object --name Project --plural Projects --icon Briefcase`
    """
    state = get_state(ctx)
    body = load_json(data) if data is not None else {}
    if not isinstance(body, dict):
        raise UsageError("The request body must be a JSON object.")
    for key, value in (
        ("name", name),
        ("plural", plural),
        ("description", description),
        ("icon", icon),
        ("backgroundColor", background_color),
    ):
        if value is not None:
            body[key] = value
    if properties is not None:
        props = load_json(properties, what="--properties")
        if not isinstance(props, dict):
            raise UsageError("--properties must be a JSON object keyed by field name.")
        body["properties"] = props
    missing = [key for key in ("name", "plural") if not body.get(key)]
    if missing:
        raise UsageError(
            f"Missing required {', '.join('--' + m for m in missing)} (or provide them in --data)."
        )
    emit(state, state.client().post("/schemas/objects", json_body=body, silent=state.silent))


@app.command()
def replace(ctx: typer.Context, obj: ObjectArg, data: DataOpt) -> None:
    """Replace an object's whole JSON Schema (PUT /schemas/objects/{object}).

    --data is the complete schema document (or a `clarify schemas get` result,
    whose `data.attributes` is unwrapped). Its `$id` must be
    `https://getclarify.ai/schemas/entities/<OBJECT>`; mismatches are rejected before
    any request. The API queues an async task, which is printed.
    Example: `clarify schemas get c_project > s.json; clarify schemas replace c_project -d @s.json`
    """
    state = get_state(ctx)
    body = load_json(data, what="schema")
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        body = body["data"].get("attributes")
    if not isinstance(body, dict):
        raise UsageError("The schema must be a JSON object (the full JSON Schema document).")
    expected = schema_id(obj)
    actual = body.get("$id")
    if actual != expected:
        raise UsageError(
            f"Schema $id {actual!r} does not match object {obj!r}.",
            hint=f'Set "$id": "{expected}" in the document.',
        )
    result = state.client().put(f"/schemas/objects/{obj}", json_body=body, silent=state.silent)
    emit(state, result)


@app.command("delete-object")
def delete_object(ctx: typer.Context, obj: ObjectArg) -> None:
    """Delete a custom object and all of its records (DELETE /schemas/objects/{object}).

    Only `c_*` objects can be deleted; asks for confirmation unless --yes is given.
    The API queues an async task, which is printed.
    Example: `clarify -y schemas delete-object c_project`
    """
    state = get_state(ctx)
    if not obj.startswith("c_"):
        raise UsageError(
            f"{obj!r} is not a custom object; only c_* objects can be deleted.",
            hint="Run `clarify schemas objects` to see which objects are custom.",
        )
    state.confirm(f"Delete custom object {obj} and ALL of its records? This cannot be undone.")
    result = state.client().delete(f"/schemas/objects/{obj}", silent=state.silent)
    emit(state, result)


# -- field commands ------------------------------------------------------------
@app.command("add-fields")
def add_fields(
    ctx: typer.Context,
    entity: EntityArg,
    field: Annotated[
        list[str] | None,
        typer.Option(
            "--field",
            help=(
                'NAME=TYPE (repeatable): adds NAME with JSON type [TYPE, "null"] '
                "(boolean stays bare), e.g. budget=number, notes=string, due=date."
            ),
        ),
    ] = None,
    data: DataOpt = None,
) -> None:
    """Add non-relationship fields to an object (POST /schemas/{entity}/properties).

    --data is either `{name: JSON Schema, ...}` or a full `{"data": {...}}` document;
    --field entries are merged over it. Existing fields are never overwritten.
    Example: `clarify schemas add-fields c_project --field budget=number --field active=boolean`
    """
    state = get_state(ctx)
    body = wrap_resource(load_json(data) if data is not None else {}, "schema-properties")
    attrs = body["data"].setdefault("attributes", {})
    if not isinstance(attrs, dict):
        raise UsageError("`attributes` must be a JSON object keyed by field name.")
    attrs.update(parse_field_specs(field))
    if not attrs:
        raise UsageError("Provide at least one field with --field NAME=TYPE or --data.")
    result = state.client().post(
        f"/schemas/{entity}/properties", json_body=body, silent=state.silent
    )
    emit_or_accepted(
        state, result, f"Accepted: {len(attrs)} field(s) queued for {entity}: {', '.join(attrs)}."
    )


@app.command("add-relationships")
def add_relationships(ctx: typer.Context, entity: EntityArg, data: DataOpt) -> None:
    """Add relationship fields between objects (POST /schemas/{entity}/relationships).

    --data is `{object: {field: JSON Schema}}` keyed by object type then field name
    (both sides of each relationship together), or a full `{"data": {...}}` document.
    one-to-many / many-to-many sides need
    `"oneOf": [{"$ref": "https://getclarify.ai/schemas/core/collectionOfIds"}, {"type": "null"}]`.
    Example: `clarify schemas add-relationships c_project -d @rel.json`
    """
    state = get_state(ctx)
    body = wrap_resource(load_json(data), "relationship")
    attrs = body["data"].get("attributes")
    if not isinstance(attrs, dict) or not attrs:
        raise UsageError("`attributes` must map object types to their new relationship fields.")
    result = state.client().post(
        f"/schemas/{entity}/relationships", json_body=body, silent=state.silent
    )
    emit_or_accepted(
        state, result, f"Accepted: relationships queued for {', '.join(attrs)} via {entity}."
    )


@app.command("delete-relationship")
def delete_relationship(ctx: typer.Context, entity: EntityArg, field: FieldArg) -> None:
    """Delete a relationship field and its counterpart (DELETE .../relationships/{fieldName}).

    Asks for confirmation unless --yes is given; the API queues an async task,
    which is printed. Example: `clarify -y schemas delete-relationship c_project company_id`
    """
    state = get_state(ctx)
    state.confirm(
        f"Delete relationship {field} from {entity} (and its counterpart on the related object)?"
    )
    result = state.client().delete(f"/schemas/{entity}/relationships/{field}", silent=state.silent)
    emit(state, result)


@app.command()
def reorder(
    ctx: typer.Context,
    entity: EntityArg,
    order: Annotated[
        str | None,
        typer.Option("--order", help="Comma-separated field names in display order."),
    ] = None,
    data: DataOpt = None,
) -> None:
    """Set the display order of an object's fields (PATCH /schemas/{entity}/fields-order).

    --order lists every field name; --data accepts `["a","b"]`, `{"order": [...]}` or a
    full `{"data": {...}}` document.
    Example: `clarify schemas reorder c_project --order name,status,budget`
    """
    state = get_state(ctx)
    if order is not None and data is not None:
        raise UsageError("Use either --order or --data, not both.")
    if order is not None:
        parsed: Any = {"order": parse_csv_list(order)}
    elif data is not None:
        parsed = load_json(data)
        if isinstance(parsed, list):
            parsed = {"order": parsed}
    else:
        raise UsageError("Provide the field order with --order a,b,c or --data.")
    body = wrap_resource(parsed, "schema-property-order")
    names = body["data"].get("attributes", {}).get("order")
    if not isinstance(names, list) or not names:
        raise UsageError("The order must be a non-empty list of field names.")
    result = state.client().patch(
        f"/schemas/{entity}/fields-order", json_body=body, silent=state.silent
    )
    emit_or_accepted(state, result, f"Accepted: field order for {entity} queued.")


@app.command()
def visibility(
    ctx: typer.Context,
    entity: EntityArg,
    hide: Annotated[
        list[str] | None,
        typer.Option("--hide", help="Field to hide on the detail view (repeatable)."),
    ] = None,
    show: Annotated[
        list[str] | None,
        typer.Option("--show", help="Field to show on the detail view (repeatable)."),
    ] = None,
) -> None:
    """Hide or show fields on the record detail view (PATCH /schemas/{entity}/fields-visibility).

    Builds the `hiddenInDetails` map: --hide F sets F to true, --show F to false.
    Example: `clarify schemas visibility c_project --hide budget --show status`
    """
    state = get_state(ctx)
    hidden: dict[str, bool] = {}
    for name in hide or []:
        hidden[name] = True
    for name in show or []:
        hidden[name] = False
    if not hidden:
        raise UsageError("Provide at least one --hide FIELD or --show FIELD.")
    body = {
        "data": {"type": "schema-property-visibility", "attributes": {"hiddenInDetails": hidden}}
    }
    result = state.client().patch(
        f"/schemas/{entity}/fields-visibility", json_body=body, silent=state.silent
    )
    emit_or_accepted(
        state, result, f"Accepted: visibility of {', '.join(hidden)} on {entity} queued."
    )


@app.command()
def enum(
    ctx: typer.Context,
    entity: EntityArg,
    field: FieldArg,
    append: Annotated[
        list[str] | None,
        typer.Option("--append", help="Enum value to add (repeatable, case-sensitive)."),
    ] = None,
    remove: Annotated[
        list[str] | None,
        typer.Option(
            "--remove",
            help="Enum value to drop (repeatable). Records using it lose the value.",
        ),
    ] = None,
    multi: Annotated[
        bool,
        typer.Option(
            "--multi", help="FIELD is a multi-select (nests under properties.items.items)."
        ),
    ] = False,
    data: DataOpt = None,
    op: Annotated[
        EnumOp | None,
        typer.Option("--op", help="Operation for --data: append (default) or remove."),
    ] = None,
) -> None:
    """Add or remove values of an enum field (PATCH /schemas).

    Sends one SchemaPropertiesPatchDto item for ENTITY with `meta.FIELD.enum` set to
    `append` or `remove` (one operation per request). --append/--remove send just the
    listed values. --data sends the field patch object as-is, i.e.
    `{"enum": [...], "xClarifyEnumMetadata": {VALUE: {id, rank, color}}}` (nested
    under `properties.items.items` with --multi), or a full `{"data": [...]}` document;
    --op picks the operation and `type`/`id`/`meta` are filled in when absent.
    Note that the spec's `append` example lists the COMPLETE enum (existing values
    plus the new one) with per-option metadata; use --data to reproduce it.
    Removing values is destructive (records set to a removed value are cleared), so
    it asks for confirmation unless --yes is given.
    Examples: `clarify schemas enum c_project status --append "On hold"`,
    `clarify schemas enum c_project status -d @status-patch.json`
    """
    state = get_state(ctx)
    if append and remove:
        raise UsageError(
            "Use --append or --remove, not both: the API takes one operation per field."
        )
    if data is not None and (append or remove):
        raise UsageError("Use --data or --append/--remove, not both.")
    if op is not None and data is None:
        raise UsageError("--op only applies to --data; --append/--remove imply the operation.")
    if data is None and not append and not remove:
        raise UsageError("Provide at least one --append VALUE or --remove VALUE, or --data.")
    operation = op or (EnumOp.remove if remove else EnumOp.append)
    meta = {field: {"enum": operation.value}}

    parsed = load_json(data) if data is not None else {"enum": list(append or remove or [])}
    if not isinstance(parsed, dict):
        raise UsageError('--data must be the field patch object or a {"data": [...]} document.')
    if "data" in parsed:
        if multi:
            raise UsageError("--multi does not apply to a full document; nest the patch in it.")
        body = parsed
        items = body["data"] if isinstance(body["data"], list) else [body["data"]]
        for item in items:
            if isinstance(item, dict):
                item.setdefault("type", "schema-properties")
                item.setdefault("id", schema_id(entity))
                item.setdefault("meta", meta)
        body["data"] = items
        values: list[str] = []
    else:
        patch = parsed
        if multi and "properties" not in patch:
            patch = {"properties": {"items": {"items": patch}}}
        body = {
            "data": [
                {
                    "type": "schema-properties",
                    "id": schema_id(entity),
                    "attributes": {field: patch},
                    "meta": meta,
                }
            ]
        }
        values = enum_values_of(patch)
    if operation is EnumOp.remove:
        listed = f" {', '.join(values)}" if values else ""
        state.confirm(
            f"Remove enum value(s){listed} from {entity}.{field}? "
            "Records using them will be cleared."
        )
    emit(state, state.client().patch("/schemas", json_body=body, silent=state.silent))


@app.command()
def activities(
    ctx: typer.Context,
    entity: EntityArg,
    limit: LimitOpt = 50,
    offset: OffsetOpt = 0,
    all_pages: AllOpt = False,
    page_size: PageSizeOpt = None,
    sort: SortOpt = None,
) -> None:
    """List an object's schema change history (GET /schemas/{entity}/activities).

    Supports paging and `sortOrder` (page[limit] is capped at 500 by the API).
    Example: `clarify schemas activities c_project --sort -_created_at -n 20`
    """
    state = get_state(ctx)
    if page_size is None and not all_pages:
        page_size = min(limit, ACTIVITIES_MAX_PAGE)
    result = collect_list(
        state,
        f"/schemas/{entity}/activities",
        sort=sort,
        limit=limit,
        offset=offset,
        all_pages=all_pages,
        page_size=page_size,
    )
    emit(state, result)
