"""``clarify lists``: lists, their records, and CSV export.

Covers the Lists and ListRows tags plus ``getListResources`` from Resources.
List bodies are plain DTOs (``CreateListDto`` / ``UpdateListDto``), not JSON:API
documents, so ``--data`` and ``--set`` operate on the DTO's top-level keys.
"""

from __future__ import annotations

import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer

from ..cli_options import (
    AllOpt,
    DataOpt,
    FilterOpt,
    IncludeOpt,
    LimitOpt,
    ObjectArg,
    OffsetOpt,
    PageSizeOpt,
    SearchOpt,
    SetOpt,
    SortOpt,
)
from ..errors import UsageError
from ..inputs import load_json, parse_set, read_source
from ..output import emit, emit_message
from ..params import collect_list
from ..state import get_state

app = typer.Typer(no_args_is_help=True)

# OpenAPI operationId -> command name. Every module declares this so a test can
# prove the CLI covers the whole spec.
OPERATIONS: dict[str, str] = {
    "getWorkspaceLists": "list",
    "getLists": "list",
    "getList": "get",
    "createList": "create",
    "updateList": "update",
    "deleteList": "delete",
    "publishList": "publish",
    "unpublishList": "unpublish",
    "getListResources": "records",
    "getListRowsCsv": "export-csv",
}

#: The list endpoints cap ``page[limit]`` at 500, below the client's general 1000.
MAX_PAGE_LIMIT = 500
#: Current dynamic-list query format. An omitted version is treated as the oldest
#: and run through migrations on save, which can rewrite the SQL (dynamic-lists guide).
QUERY_VERSION = 6
#: The simplest layout the API accepts; used when ``create`` gets none.
DEFAULT_LAYOUT = "table"
#: The only media type ``getListRowsCsv`` produces; sent as ``Accept`` on export.
CSV_MEDIA_TYPE = "text/csv"


class ListType(StrEnum):
    dynamic = "dynamic"
    static = "static"


class ListLayout(StrEnum):
    table = "table"
    board = "board"


ListArg = Annotated[str, typer.Argument(help="The list ID.", metavar="LIST")]
OptionalObjectArg = Annotated[
    str | None,
    typer.Argument(
        help=(
            "Object type (person, company, deal, ... or c_*) whose lists to show. "
            "Omit to list every object's lists in the workspace."
        ),
        metavar="OBJECT",
    ),
]
TitleOpt = Annotated[str | None, typer.Option("--title", help="Display name of the list.")]
DescriptionOpt = Annotated[
    str | None, typer.Option("--description", help="Short description of the list.")
]
EmojiOpt = Annotated[
    str | None, typer.Option("--emoji", help="Emoji shown next to the list in the app.")
]
LayoutOpt = Annotated[
    ListLayout | None, typer.Option("--layout", help="How the list renders in the app.")
]
QueryOpt = Annotated[
    str | None,
    typer.Option(
        "--query",
        help=(
            "SQL defining a dynamic list's membership: inline, @file, or - for stdin. "
            f"Sent as query.sql with query.version={QUERY_VERSION}."
        ),
    ),
]
TypeOpt = Annotated[
    ListType | None,
    typer.Option(
        "--type",
        help="List type. Defaults to dynamic when a query is given, otherwise static.",
    ),
]
SqlOpt = Annotated[
    str | None,
    typer.Option(
        "--sql",
        help=(
            "Custom SQL selecting the rows to export instead of the list's own query: "
            "inline, @file, or - for stdin."
        ),
    ),
]
OutOpt = Annotated[
    str | None, typer.Option("--out", help="Write the CSV to this file instead of stdout.")
]


# -- helpers ---------------------------------------------------------------
def _page_size(limit: int, all_pages: bool, page_size: int | None) -> int | None:
    """Keep the derived ``page[limit]`` within the 500 these endpoints accept.

    An explicit ``--page-size`` is passed through; ``--all`` already defaults to
    500 in the client.
    """
    if page_size is not None or all_pages:
        return page_size
    return min(limit, MAX_PAGE_LIMIT)


def _merge(target: dict[str, Any], overrides: dict[str, Any]) -> None:
    for key, value in overrides.items():
        if isinstance(target.get(key), dict) and isinstance(value, dict):
            _merge(target[key], value)
        else:
            target[key] = value


def _list_body(
    data: str | None, set_values: list[str] | None, fields: dict[str, Any]
) -> dict[str, Any]:
    """Build the plain list DTO: ``--data``, then the convenience flags, then ``--set``."""
    body = load_json(data) if data is not None else {}
    if not isinstance(body, dict):
        raise UsageError("The list body must be a JSON object with the list's fields.")
    body.update({key: value for key, value in fields.items() if value is not None})
    _merge(body, parse_set(set_values))
    return body


def _query(sql: str | None) -> dict[str, Any] | None:
    if sql is None:
        return None
    return {"sql": read_source(sql), "version": QUERY_VERSION}


def _list_path(object_type: str, list_id: str, suffix: str = "") -> str:
    return f"/objects/{object_type}/lists/{list_id}{suffix}"


# -- commands --------------------------------------------------------------
@app.command("list")
def list_lists(
    ctx: typer.Context,
    object_type: OptionalObjectArg = None,
    limit: LimitOpt = 50,
    offset: OffsetOpt = 0,
    all_pages: AllOpt = False,
    page_size: PageSizeOpt = None,
    sort: SortOpt = None,
    filters: FilterOpt = None,
    search: SearchOpt = None,
) -> None:
    """List lists across the workspace (GET /lists) or on one object (GET /objects/{object}/lists).

    Dynamic lists are excluded unless a filter selects them, e.g. `-f type=dynamic`.
    Filters: `type` (dynamic, static, default), `state` (draft, published),
    `_created_by`, and, for the workspace-wide form, `entity` with one or more
    object types (`-f entity=deal,company`). `--search` matches the list title.

    Examples:

        clarify lists list -f entity=deal -f state=published

        clarify lists list deal -f type=dynamic --search enterprise -s -_created_at
    """
    state = get_state(ctx)
    path = f"/objects/{object_type}/lists" if object_type else "/lists"
    result = collect_list(
        state,
        path,
        filters=filters,
        sort=sort,
        search=search,
        limit=limit,
        offset=offset,
        all_pages=all_pages,
        page_size=_page_size(limit, all_pages, page_size),
    )
    emit(state, result)


@app.command()
def get(ctx: typer.Context, object_type: ObjectArg, list_id: ListArg) -> None:
    """Show one list, including its query and layout (GET /objects/{object}/lists/{list})."""
    state = get_state(ctx)
    emit(state, state.client().get(_list_path(object_type, list_id)))


@app.command()
def create(
    ctx: typer.Context,
    object_type: ObjectArg,
    data: DataOpt = None,
    set_values: SetOpt = None,
    title: TitleOpt = None,
    description: DescriptionOpt = None,
    list_type: TypeOpt = None,
    query: QueryOpt = None,
    emoji: EmojiOpt = None,
    layout: LayoutOpt = None,
) -> None:
    """Create a list on an object (POST /objects/{object}/lists).

    The body is the plain list DTO, not a JSON:API document: `--data` supplies it
    whole, the flags fill in single fields, and `--set` overrides any key (dotted
    keys nest, e.g. `--set options.segmentedByInBoard=stage`). `title` and
    `description` are required. `layout` defaults to `table`, the simplest layout
    the API accepts, and `type` defaults to `dynamic` when a query is present,
    otherwise `static`. Lists are created published; use `--set state=draft`
    for a draft.

    Examples:

        clarify lists create deal --title "Big deals" --description "Over 50k" --query @big.sql

        clarify lists create person --title Prospects --description "Hand-picked" --type static

        clarify lists create deal -d @l.json --layout board --set options.segmentedByInBoard=stage
    """
    state = get_state(ctx)
    body = _list_body(
        data,
        set_values,
        {
            "title": title,
            "description": description,
            "emoji": emoji,
            "layout": layout.value if layout else None,
            "type": list_type.value if list_type else None,
            "query": _query(query),
        },
    )
    body.setdefault("layout", DEFAULT_LAYOUT)
    body.setdefault("type", ListType.dynamic.value if body.get("query") else ListType.static.value)
    missing = [key for key in ("title", "description") if key not in body]
    if missing:
        raise UsageError(
            f"Missing required field(s): {', '.join(missing)}.",
            hint="Pass --title/--description, --set KEY=VALUE, or include them in --data.",
        )
    emit(state, state.client().post(f"/objects/{object_type}/lists", body, silent=state.silent))


@app.command()
def update(
    ctx: typer.Context,
    object_type: ObjectArg,
    list_id: ListArg,
    data: DataOpt = None,
    set_values: SetOpt = None,
    title: TitleOpt = None,
    description: DescriptionOpt = None,
    query: QueryOpt = None,
    emoji: EmojiOpt = None,
    layout: LayoutOpt = None,
) -> None:
    """Update some of a list's fields (PATCH /objects/{object}/lists/{list}).

    Partial: only the fields you pass change. The body is the plain list DTO
    (`title`, `emoji`, `description`, `layout`, `options`, `query`, `rank`).
    `--query` replaces the whole query object, so include every column you want
    to keep. The object's default list cannot be updated.

    Examples:

        clarify lists update deal LIST --title "Enterprise deals (FY26)"

        clarify lists update deal LIST --set emoji=null --set rank=0
    """
    state = get_state(ctx)
    body = _list_body(
        data,
        set_values,
        {
            "title": title,
            "description": description,
            "emoji": emoji,
            "layout": layout.value if layout else None,
            "query": _query(query),
        },
    )
    if not body:
        raise UsageError(
            "Nothing to update.",
            hint="Pass --title, --description, --emoji, --layout, --query, --set, or --data.",
        )
    emit(state, state.client().patch(_list_path(object_type, list_id), body, silent=state.silent))


@app.command()
def delete(ctx: typer.Context, object_type: ObjectArg, list_id: ListArg) -> None:
    """Permanently delete a list (DELETE /objects/{object}/lists/{list}).

    Asks for confirmation unless `--yes` is given. The object's default list and
    the last remaining list on an object cannot be deleted. The API answers 202
    with an empty body, so the confirmation line goes to stderr.
    """
    state = get_state(ctx)
    state.confirm(f"Delete list {list_id} on {object_type}? This cannot be undone.")
    result = state.client().delete(_list_path(object_type, list_id), silent=state.silent)
    if result is None:
        emit_message(f"Deleted list {list_id} on {object_type}.")
    else:
        emit(state, result)


@app.command()
def publish(ctx: typer.Context, object_type: ObjectArg, list_id: ListArg) -> None:
    """Publish a draft list to its audience (POST /objects/{object}/lists/{list}/publish)."""
    state = get_state(ctx)
    path = _list_path(object_type, list_id, "/publish")
    emit(state, state.client().post(path, silent=state.silent))


@app.command()
def unpublish(ctx: typer.Context, object_type: ObjectArg, list_id: ListArg) -> None:
    """Revert a published list to draft (POST /objects/{object}/lists/{list}/unpublish)."""
    state = get_state(ctx)
    path = _list_path(object_type, list_id, "/unpublish")
    emit(state, state.client().post(path, silent=state.silent))


@app.command()
def records(
    ctx: typer.Context,
    object_type: ObjectArg,
    list_id: ListArg,
    limit: LimitOpt = 50,
    offset: OffsetOpt = 0,
    all_pages: AllOpt = False,
    page_size: PageSizeOpt = None,
    sort: SortOpt = None,
    filters: FilterOpt = None,
    include: IncludeOpt = None,
) -> None:
    """List the records in a list (GET /objects/{object}/lists/{list}/resources).

    The list's membership applies on top of any `--filter`; `--include` embeds
    related records under `included`.

    Example:

        clarify lists records deal LIST -f 'amount=>10000' -i company_id -s -_created_at
    """
    state = get_state(ctx)
    result = collect_list(
        state,
        _list_path(object_type, list_id, "/resources"),
        filters=filters,
        sort=sort,
        include=include,
        limit=limit,
        offset=offset,
        all_pages=all_pages,
        page_size=_page_size(limit, all_pages, page_size),
    )
    emit(state, result)


@app.command("export-csv")
def export_csv(
    ctx: typer.Context,
    object_type: ObjectArg,
    list_id: ListArg,
    sql: SqlOpt = None,
    search: SearchOpt = None,
    out: OutOpt = None,
) -> None:
    """Export a list's rows as CSV (POST /objects/{object}/lists/{list}/rows/csv).

    The response is text/csv with a header row of field names. It is written
    verbatim to stdout (or to `--out`) regardless of `-o`. `--search` narrows the
    rows with a case-insensitive substring match.

    Examples:

        clarify lists export-csv deal LIST > deals.csv

        clarify lists export-csv deal LIST --sql @rows.sql --search acme --out rows.csv
    """
    state = get_state(ctx)
    body: dict[str, Any] = {}
    if sql is not None:
        body["sql"] = read_source(sql)
    if search is not None:
        body["search"] = {"query": search}
    # The endpoint's only response type is text/csv; override the client's JSON default.
    response = state.client().request(
        "POST",
        _list_path(object_type, list_id, "/rows/csv"),
        json_body=body,
        silent=state.silent,
        headers={"Accept": CSV_MEDIA_TYPE},
    )
    if out:
        target = Path(out).expanduser()
        target.write_bytes(response.content)
        # Plain echo, like ``clarify api --out``: paths must not wrap or be read as markup.
        typer.echo(f"Wrote {len(response.content)} bytes to {target}", err=True)
        return
    sys.stdout.flush()
    stream = getattr(sys.stdout, "buffer", None)
    if stream is not None:
        stream.write(response.content)
        stream.flush()
    else:  # pragma: no cover - text-only stdout replacement
        sys.stdout.write(response.text)
        sys.stdout.flush()
