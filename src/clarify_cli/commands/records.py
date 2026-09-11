"""``clarify records``: create, read, update, and delete records (Records + Resources tags).

Reads go to ``/objects/{object}/resources`` (filter, sort, include, paginate);
writes go to ``/objects/{object}/records``. The two paths address the same
underlying records.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer

from ..cli_options import (
    AllOpt,
    DataOpt,
    FileOpt,
    FilterOpt,
    FormatOpt,
    IncludeOpt,
    LimitOpt,
    ObjectArg,
    OffsetOpt,
    PageSizeOpt,
    SetOpt,
    SortOpt,
)
from ..errors import APIError, ClarifyError, UsageError
from ..inputs import body_from_options, load_json, load_records, to_resources
from ..output import emit, emit_message
from ..params import collect_list, parse_csv_list
from ..state import AppState, get_state

app = typer.Typer(no_args_is_help=True)

# OpenAPI operationId -> command name. `get` and `create` each cover two
# operations, selected with --endpoint.
OPERATIONS: dict[str, str] = {
    "getResources": "list",
    "getResource": "get",
    "getRecord": "get",
    "createRecord": "create",
    "createResource": "create",
    "updateRecord": "update",
    "deleteRecord": "delete",
    "createBulkRecords": "bulk-create",
    "updateRecords": "bulk-update",
    "deleteRecords": "bulk-delete",
    "mergeRecords": "merge",
    "getDeletedResources": "deleted",
}

#: Records per bulk request. The bulk guide recommends 100 for clean data and
#: smaller batches (25, or 1 when retrying) to limit the blast radius, because
#: every batch is atomic.
DEFAULT_BATCH_SIZE = 100
#: `GET .../deleted-resources` caps page[limit] at 500 (schema `maximum`).
DELETED_MAX_PAGE_SIZE = 500


class Endpoint(StrEnum):
    resources = "resources"
    records = "records"


IdArg = Annotated[str, typer.Argument(help="The record's ID.", metavar="ID")]
MatchOnOpt = Annotated[
    str | None,
    typer.Option(
        "--match-on",
        metavar="FIELD",
        help=(
            "Upsert: the unique field to match existing records on (person: email_addresses, "
            "company: domains, deal: name). A match is updated instead of creating a duplicate."
        ),
    ),
]
BatchSizeOpt = Annotated[
    int,
    typer.Option(
        "--batch-size",
        min=1,
        help="Records per request. Batches are atomic: one bad record fails its whole batch.",
    ),
]
# Per-field write strategies (`meta` of UpdateRecordDto / UpdateRecordsDto).
AppendOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--append",
        metavar="FIELD",
        help="Add FIELD's items to the collection (or array) instead of replacing it.",
    ),
]
RemoveOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--remove",
        metavar="FIELD",
        help="Remove FIELD's items from the collection instead of replacing it.",
    ),
]
MergeOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--merge",
        metavar="FIELD",
        help="Merge FIELD's keys into the existing object instead of replacing it.",
    ),
]


class BulkBatchError(APIError):
    """The API rejected one batch of a bulk request; says which records were (not) written."""

    def __init__(self, cause: APIError, note: str):
        self.batch_note = note
        super().__init__(
            cause.status, cause.errors, method=cause.method, url=cause.url, raw=cause.raw
        )

    def _summary(self) -> str:
        return f"{self.batch_note}\n{super()._summary()}"

    def _hint(self) -> str | None:
        base = super()._hint()
        tip = "Fix the records in that range and re-run; --batch-size 1 isolates the bad record."
        return f"{base} {tip}" if base else tip


# -- commands ----------------------------------------------------------------


@app.command("list")
def list_records(
    ctx: typer.Context,
    object_type: ObjectArg,
    filters: FilterOpt = None,
    sort: SortOpt = None,
    include: IncludeOpt = None,
    limit: LimitOpt = 50,
    offset: OffsetOpt = 0,
    all_pages: AllOpt = False,
    page_size: PageSizeOpt = None,
) -> None:
    """List records with filters, sorting, and includes (GET /objects/{object}/resources).

    Filters are ANDed. A bare value is an exact match (also on collection fields
    such as email_addresses); name an operator for anything else.

    Examples:

        clarify records list person -f email_addresses=jane@acme.com

        clarify records list deal -f 'amount[Greater than]=50000' -s -amount -i company_id

        clarify records list company -f 'name=*Acme*' --all -o ndjson > companies.ndjson
    """
    state = get_state(ctx)
    result = collect_list(
        state,
        f"/objects/{object_type}/resources",
        filters=filters,
        sort=sort,
        include=include,
        limit=limit,
        offset=offset,
        all_pages=all_pages,
        page_size=page_size,
    )
    emit(state, result)


@app.command()
def get(
    ctx: typer.Context,
    object_type: ObjectArg,
    record_id: IdArg,
    include: IncludeOpt = None,
    endpoint: Annotated[
        Endpoint,
        typer.Option(
            "--endpoint",
            help="Read from /resources/{id} (default, returns `included`) or /records/{id}.",
        ),
    ] = Endpoint.resources,
) -> None:
    """Show one record (GET /objects/{object}/resources/{id}; --endpoint records → records/{id}).

    Examples:

        clarify records get person 5f8b7d2e-9c4a-4e1b-8f3d-2a6c9e0b4d71 -i company_id

        clarify records get deal 1c2d... --endpoint records
    """
    state = get_state(ctx)
    params = [("include", ",".join(parse_csv_list(include)))] if include else None
    path = f"/objects/{object_type}/{endpoint.value}/{record_id}"
    emit(state, state.client().get(path, params=params))


@app.command()
def create(
    ctx: typer.Context,
    object_type: ObjectArg,
    data: DataOpt = None,
    set_values: SetOpt = None,
    match_on: MatchOnOpt = None,
    endpoint: Annotated[
        Endpoint,
        typer.Option(
            "--endpoint",
            help="Write to /records (default, supports --match-on) or /resources.",
        ),
    ] = Endpoint.records,
) -> None:
    """Create or upsert a record (POST /objects/{object}/records, or --endpoint resources).

    The body is `{"data": {"type": OBJECT, "attributes": {...}}}`; pass the
    attributes object (or the full document) with --data and/or build it with
    --set. Collection fields (email_addresses, domains, phone_numbers, labels)
    take the shape `{"items": [...]}`.

    Creating is a plain insert: a value that collides with an existing record's
    unique field is rejected with a 400. Pass --match-on FIELD to upsert
    instead: a record whose FIELD matches exactly one existing record updates
    that record and returns its ID. --match-on is a records-endpoint feature
    and is rejected with --endpoint resources.

    Examples:

        clarify records create person --set name.first_name=Jane --set name.last_name=Doe \\
            --set 'email_addresses={"items": ["jane@acme.com"]}' --match-on email_addresses

        clarify records create deal -d '{"name": "Acme Renewal", "amount": 12000}'

        clarify records create company -d @company.json --endpoint resources
    """
    state = get_state(ctx)
    document = body_from_options(object_type, data=data, set_values=set_values)
    if match_on:
        document["match_on"] = match_on
    if endpoint is Endpoint.resources and "match_on" in document:
        raise UsageError(
            "--match-on (upsert) is only supported by POST /objects/{object}/records.",
            hint="Drop --endpoint resources, or drop --match-on.",
        )
    path = f"/objects/{object_type}/{endpoint.value}"
    emit(state, state.client().post(path, document, silent=state.silent))


@app.command()
def update(
    ctx: typer.Context,
    object_type: ObjectArg,
    record_id: IdArg,
    data: DataOpt = None,
    set_values: SetOpt = None,
    append: AppendOpt = None,
    remove: RemoveOpt = None,
    merge_fields: MergeOpt = None,
) -> None:
    """Partially update a record (PATCH /objects/{object}/records/{id}).

    Only the fields in `attributes` change; everything else keeps its value.
    Collection fields (email_addresses, domains, phone_numbers, labels) take
    the shape `{"items": [...]}` and are replaced by default. --append,
    --remove, and --merge set the per-field write strategy in `meta`:
    `{"collection": "append"|"remove"}` for `{"items": [...]}` values,
    `{"array": "append"}` for JSON-array values, and `{"object": "merge"}` for
    object values. The named field must be present in the body.

    Examples:

        clarify records update person 5f8b... --set job_title=CMO

        clarify records update person 5f8b... \\
            --set 'email_addresses={"items": ["jane@newco.com"]}' --append email_addresses

        clarify records update deal 1c2d... -d @changes.json --merge custom_fields
    """
    state = get_state(ctx)
    document = body_from_options(object_type, data=data, set_values=set_values, id=record_id)
    if append or remove or merge_fields:
        attributes = document["data"].get("attributes")
        _write_strategies(
            _meta_of(document, "the body"),
            [attributes if isinstance(attributes, dict) else {}],
            append=append,
            remove=remove,
            merge=merge_fields,
            hint="Set it with --set FIELD=... or include it in --data.",
        )
    path = f"/objects/{object_type}/records/{record_id}"
    emit(state, state.client().patch(path, document, silent=state.silent))


@app.command()
def delete(ctx: typer.Context, object_type: ObjectArg, record_id: IdArg) -> None:
    """Permanently delete a record (DELETE /objects/{object}/records/{id}).

    Asks for confirmation unless --yes is given. Deleted records stay visible
    to `records deleted` for 30 days.

    Example:

        clarify --yes records delete person 5f8b7d2e-9c4a-4e1b-8f3d-2a6c9e0b4d71
    """
    state = get_state(ctx)
    state.confirm(f"Permanently delete {object_type} {record_id}?")
    result = state.client().delete(
        f"/objects/{object_type}/records/{record_id}", silent=state.silent
    )
    _emit_or_confirm(state, result, f"Deleted {object_type} {record_id}.")


@app.command("bulk-create")
def bulk_create(
    ctx: typer.Context,
    object_type: ObjectArg,
    file: FileOpt,
    fmt: FormatOpt = None,
    match_on: MatchOnOpt = None,
    batch_size: BatchSizeOpt = DEFAULT_BATCH_SIZE,
) -> None:
    """Create (or upsert) many records from a file (POST /objects/{object}/records/bulk).

    The file may be a JSON array, `{"data": [...]}`, NDJSON, or CSV with a
    header row (dotted headers nest: `name.first_name`). Each item is either a
    JSON:API resource or a flat attributes object. Records are sent in
    sequential batches of --batch-size; each batch is atomic, so one invalid
    record fails its whole batch and the command stops there. Results of the
    batches that succeeded are still printed, and the error names the failing
    batch and record range.

    Prints one envelope: `{"data": [...created...], "meta": {"batches": n,
    "records": m}}`.

    Examples:

        clarify records bulk-create company -F companies.csv --match-on domains

        clarify records bulk-create person -F people.ndjson --batch-size 25

        cat people.json | clarify records bulk-create person -F - --match-on email_addresses
    """
    state = get_state(ctx)
    resources, _meta = _load_resources(file, fmt, object_type)
    extra = {"match_on": match_on} if match_on else {}
    result = _send_batches(
        state,
        "POST",
        f"/objects/{object_type}/records/bulk",
        resources,
        batch_size=batch_size,
        extra=extra,
        verb="created",
    )
    emit(state, result)


@app.command("bulk-update")
def bulk_update(
    ctx: typer.Context,
    object_type: ObjectArg,
    file: FileOpt,
    fmt: FormatOpt = None,
    batch_size: BatchSizeOpt = DEFAULT_BATCH_SIZE,
    append: AppendOpt = None,
    remove: RemoveOpt = None,
    merge_fields: MergeOpt = None,
) -> None:
    """Partially update many records from a file (PATCH /objects/{object}/records).

    Every record must carry an `id` (a top-level key on flat records, or the
    resource's `id`); only the listed attributes change. Records are sent in
    sequential, atomic batches of --batch-size, and the output is one envelope
    `{"data": [...updated...], "meta": {"batches": n, "records": m}}`.

    Collection, array, and object fields are replaced by default. --append,
    --remove, and --merge set the per-field write strategy in the request's
    `meta` (see `records update`); it applies to every batch, and the named
    field must appear in at least one record. A JSON `{"data": [...],
    "meta": {...}}` document's own `meta` is sent too.

    Examples:

        clarify records bulk-update deal -F stages.csv

        clarify records bulk-update person -F new-emails.ndjson --append email_addresses

        clarify records bulk-update person -F '{"data": [{"type": "person", "id": "5f8b...",
            "attributes": {"job_title": "CMO"}}]}' --format json
    """
    state = get_state(ctx)
    resources, meta = _load_resources(file, fmt, object_type)
    missing = [str(index) for index, res in enumerate(resources, start=1) if not res.get("id")]
    if missing:
        raise UsageError(
            f"Every record needs an id for bulk-update; missing on record(s) {', '.join(missing)}.",
            hint='Add an "id" key (or CSV column) to each record.',
        )
    if append or remove or merge_fields:
        _write_strategies(
            meta,
            [res["attributes"] for res in resources if isinstance(res.get("attributes"), dict)],
            append=append,
            remove=remove,
            merge=merge_fields,
            hint="Add it to the attributes of the records it should apply to.",
        )
    result = _send_batches(
        state,
        "PATCH",
        f"/objects/{object_type}/records",
        resources,
        batch_size=batch_size,
        extra={"meta": meta} if meta else {},
        verb="updated",
    )
    emit(state, result)


@app.command("bulk-delete")
def bulk_delete(
    ctx: typer.Context,
    object_type: ObjectArg,
    ids: Annotated[
        list[str] | None, typer.Argument(help="Record IDs to delete.", metavar="IDS")
    ] = None,
    file: Annotated[
        str | None,
        typer.Option(
            "--file",
            "-F",
            help=(
                "IDs file: a .txt with one ID per line, or a records file (JSON array, "
                '{"data": [...]}, NDJSON, CSV) whose records carry an id. Use - for stdin.'
            ),
        ),
    ] = None,
    fmt: FormatOpt = None,
) -> None:
    """Permanently delete many records by ID (DELETE /objects/{object}/records).

    IDs come from the arguments, --file, or both (duplicates are dropped).
    Asks for confirmation with the count unless --yes is given.

    Examples:

        clarify --yes records bulk-delete person 5f8b... 7a1c...

        clarify records bulk-delete company -F stale-ids.txt

        clarify records list deal -f stage=Lost -o ndjson \\
            | clarify --yes records bulk-delete deal -F - --format ndjson
    """
    state = get_state(ctx)
    collected = list(ids or [])
    if file:
        collected.extend(_ids_from_file(file, fmt))
    unique = list(dict.fromkeys(value.strip() for value in collected if value.strip()))
    if not unique:
        raise UsageError("No record IDs given.", hint="Pass IDs as arguments and/or --file PATH.")
    state.confirm(f"Permanently delete {len(unique)} {object_type} record(s)?")
    result = state.client().delete(
        f"/objects/{object_type}/records", {"items": unique}, silent=state.silent
    )
    _emit_or_confirm(state, result, f"Deleted {len(unique)} {object_type} record(s).")


@app.command()
def merge(
    ctx: typer.Context,
    object_type: ObjectArg,
    target: Annotated[
        str, typer.Argument(help="ID of the record that survives.", metavar="TARGET")
    ],
    sources: Annotated[
        list[str],
        typer.Option(
            "--source",
            metavar="ID",
            help="ID of a duplicate to merge into TARGET; it is deleted afterwards (repeatable).",
        ),
    ],
) -> None:
    """Merge duplicates into a target record (POST /objects/{object}/records/{record}/merges).

    Field values and relationships of every --source record are combined onto
    TARGET, then the sources are deleted. This cannot be undone, so the command
    asks for confirmation unless --yes is given.

    Example:

        clarify records merge company c0a8... --source 9b1e... --source 4d2f...
    """
    state = get_state(ctx)
    unique = list(dict.fromkeys(sources))
    if target in unique:
        raise UsageError("TARGET cannot also be a --source.")
    state.confirm(f"Merge {len(unique)} {object_type} record(s) into {target} and delete them?")
    body = {"data": {"type": object_type, "attributes": {"sources": unique}}}
    result = state.client().post(
        f"/objects/{object_type}/records/{target}/merges", body, silent=state.silent
    )
    _emit_or_confirm(state, result, f"Merged {len(unique)} record(s) into {object_type} {target}.")


@app.command()
def deleted(
    ctx: typer.Context,
    object_type: ObjectArg,
    filters: FilterOpt = None,
    limit: LimitOpt = 50,
    offset: OffsetOpt = 0,
    all_pages: AllOpt = False,
    page_size: PageSizeOpt = None,
) -> None:
    """List records deleted in the last 30 days (GET /objects/{object}/deleted-resources).

    Attributes are the values at deletion time plus `_deleted_at`. The only
    filterable field is `_deleted_at` (epoch seconds); the endpoint supports
    neither `include` nor sorting.

    Examples:

        clarify records deleted person

        clarify records deleted deal -f '_deleted_at[Less than]=1787273241' --all
    """
    state = get_state(ctx)
    if page_size is None and not all_pages:
        page_size = min(limit, DELETED_MAX_PAGE_SIZE)
    result = collect_list(
        state,
        f"/objects/{object_type}/deleted-resources",
        filters=filters,
        limit=limit,
        offset=offset,
        all_pages=all_pages,
        page_size=page_size,
    )
    emit(state, result)


# -- helpers -----------------------------------------------------------------


def _emit_or_confirm(state: AppState, result: Any, message: str) -> None:
    """Print a response body if there is one, else a confirmation line on stderr."""
    if result is None:
        emit_message(message)
    else:
        emit(state, result)


def _meta_of(document: dict[str, Any], where: str) -> dict[str, Any]:
    """The document's ``meta`` object, created when absent."""
    meta = document.setdefault("meta", {})
    if not isinstance(meta, dict):
        raise UsageError(f"`meta` in {where} must be a JSON object.")
    return meta


def _write_strategies(
    meta: dict[str, Any],
    attributes: list[dict[str, Any]],
    *,
    append: list[str] | None,
    remove: list[str] | None,
    merge: list[str] | None,
    hint: str,
) -> None:
    """Fill ``meta`` with per-field write strategies (UpdateRecordDto / UpdateRecordsDto).

    ``attributes`` holds the attributes object of every record the strategies
    apply to (one for a single update, all of them for a bulk update); each
    named field must be set in at least one of them. For ``--append`` the value
    decides the kind: a bare JSON array is an array field, anything else (the
    ``{"items": [...]}`` shape) a collection.
    """
    plan: list[tuple[str, list[str] | None, str | None]] = [
        ("--append", append, None),
        ("--remove", remove, "collection"),
        ("--merge", merge, "object"),
    ]
    for flag, fields, kind in plan:
        for field in fields or []:
            values = [attrs[field] for attrs in attributes if field in attrs]
            if not values:
                raise UsageError(f"{flag} {field}: the field is not in the body.", hint=hint)
            entry = meta.setdefault(field, {})
            if not isinstance(entry, dict):
                raise UsageError(f"`meta.{field}` in the body must be a JSON object.")
            if kind is None:
                kinds = {"array" if isinstance(value, list) else "collection" for value in values}
                if len(kinds) > 1:
                    raise UsageError(
                        f"--append {field}: some records give a JSON array and others a "
                        '{"items": [...]} collection; use one shape.'
                    )
                entry[kinds.pop()] = "append"
            elif kind == "collection":
                entry["collection"] = "remove"
            else:
                entry["object"] = "merge"


def _load_resources(
    file: str, fmt: str | None, object_type: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Resources of a records file plus the top-level ``meta`` of a JSON document.

    ``inputs.load_records`` keeps only ``data``, so a JSON
    ``{"data": [...], "meta": {...}}`` document (the UpdateRecordsDto shape) is
    parsed here to keep its write strategies; NDJSON and CSV have no ``meta``.
    """
    meta: dict[str, Any] = {}
    if _is_json_source(file, fmt):
        parsed = load_json("-" if file == "-" else f"@{file}", what="records file")
        if isinstance(parsed, dict) and isinstance(parsed.get("data"), list):
            if parsed.get("meta") is not None:
                if not isinstance(parsed["meta"], dict):
                    raise UsageError(f"`meta` in {file} must be a JSON object.")
                meta = parsed["meta"]
            items = parsed["data"]
        elif isinstance(parsed, dict):
            items = [parsed]
        elif isinstance(parsed, list):
            items = parsed
        else:
            raise UsageError(
                'Records file must contain a JSON array, an object, or {"data": [...]}.'
            )
        bad = [str(i) for i, item in enumerate(items, start=1) if not isinstance(item, dict)]
        if bad:
            raise UsageError(f"Record(s) {', '.join(bad)} in {file} are not JSON objects.")
    else:
        items = load_records(file, fmt=fmt)
    resources = to_resources(items, object_type)
    if not resources:
        raise UsageError(f"No records found in {file}.")
    return resources, meta


def _is_json_source(file: str, fmt: str | None) -> bool:
    """Mirror ``inputs.load_records``: anything that is not NDJSON or CSV parses as JSON."""
    if fmt is not None:
        return fmt not in ("ndjson", "csv")
    return file == "-" or Path(file).suffix.lower() not in (".ndjson", ".jsonl", ".csv")


def _ids_from_file(source: str, fmt: str | None) -> list[str]:
    """IDs from a ``.txt`` (one per line, ``#`` comments allowed) or a records file."""
    if source != "-" and fmt is None and Path(source).suffix.lower() == ".txt":
        path = Path(source).expanduser()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise UsageError(f"Cannot read {path}: {exc}") from exc
        lines = (line.strip() for line in text.splitlines())
        return [line for line in lines if line and not line.startswith("#")]
    ids: list[str] = []
    missing: list[str] = []
    for index, item in enumerate(load_records(source, fmt=fmt), start=1):
        value = item.get("id")
        if value is None or value == "":
            missing.append(str(index))
        else:
            ids.append(str(value))
    if missing:
        raise UsageError(f"Record(s) {', '.join(missing)} in {source} have no id.")
    return ids


def _send_batches(
    state: AppState,
    method: str,
    path: str,
    resources: list[dict[str, Any]],
    *,
    batch_size: int,
    extra: dict[str, Any],
    verb: str,
) -> dict[str, Any]:
    """Send ``resources`` in sequential batches and merge the responses into one envelope.

    A failing batch stops the run: the results of completed batches are
    emitted first, then the error is re-raised naming the batch and record
    range. An API rejection becomes a :class:`BulkBatchError`; a timeout or
    connection error keeps its message, exit code, and hint.
    """
    client = state.client()
    batches = [resources[i : i + batch_size] for i in range(0, len(resources), batch_size)]
    data: list[Any] = []
    included: list[Any] = []
    sent = 0
    for index, batch in enumerate(batches, start=1):
        try:
            response = client.json(
                method, path, json_body={"data": batch, **extra}, silent=state.silent
            )
        except ClarifyError as exc:
            if sent:
                emit(state, _bulk_envelope(data, included, batches=index - 1, records=sent))
            first, last = sent + 1, sent + len(batch)
            where = f"Batch {index}/{len(batches)} (records {first}-{last} of the file)"
            earlier = f"{sent} records from earlier batches were {verb}."
            if isinstance(exc, APIError):
                note = (
                    f"{where} failed. Batches are atomic, so none of its records were {verb}; "
                    f"{earlier}"
                )
                raise BulkBatchError(exc, note) from exc
            # No response (timeout, connection dropped): the batch may or may not
            # have been applied, so say so and where to resume.
            note = f"{where} got no response, so its records may or may not be {verb}; {earlier}"
            resume = f"Check records {first}-{last}, then re-run from record {first}."
            raise ClarifyError(
                f"{note}\n{exc.message}",
                exit_code=exc.exit_code,
                hint=f"{exc.hint} {resume}" if exc.hint else resume,
            ) from exc
        sent += len(batch)
        if isinstance(response, dict):
            items = response.get("data") or []
            data.extend(items if isinstance(items, list) else [items])
            included.extend(response.get("included") or [])
    return _bulk_envelope(data, included, batches=len(batches), records=sent)


def _bulk_envelope(
    data: list[Any], included: list[Any], *, batches: int, records: int
) -> dict[str, Any]:
    out: dict[str, Any] = {"data": data}
    if included:
        out["included"] = included
    out["meta"] = {"batches": batches, "records": records}
    return out
