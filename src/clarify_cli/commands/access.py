"""``clarify access``: per-record access grants (RecordAccess tag).

A grant shares one record (a record entity such as ``deal``/``person``/``c_*``,
or a ``list``, ``meeting``, or ``message``) with a single workspace member or
with the whole workspace at a given access level.

Every endpoint in this group requires a user-backed (Personal) API key; a
Workspace API key is rejected with HTTP 403.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

import typer

from ..cli_options import DataOpt, FormatOpt
from ..errors import UsageError
from ..inputs import body_from_options, load_json, load_records, to_resources
from ..output import emit, emit_message
from ..state import get_state

RESOURCE_TYPE = "object-record-access"
MAX_BULK_GRANTS = 1000
KEY_NOTE = (
    "These endpoints require a user-backed (Personal) API key; "
    "Workspace API keys are rejected with HTTP 403."
)

app = typer.Typer(
    no_args_is_help=True,
    help=f"Manage per-record access grants. {KEY_NOTE}",
    epilog=KEY_NOTE,
)

# OpenAPI operationId -> command name.
OPERATIONS: dict[str, str] = {
    "getGrants": "list",
    "createGrant": "grant",
    "createGrantsBulk": "grant-bulk",
    "updateGrant": "update",
    "revokeGrant": "revoke",
}


class AccessLevel(StrEnum):
    """Access levels a grant can be created or updated with (per the spec)."""

    view = "view"
    edit = "edit"


ObjectArg = Annotated[
    str,
    typer.Argument(
        help=(
            "Shareable object: person, company, deal, task, a custom c_* object, "
            "or list, meeting, message."
        ),
        metavar="OBJECT",
    ),
]
RecordIdArg = Annotated[str, typer.Argument(help="The shared record's ID.", metavar="ID")]
GrantIdArg = Annotated[
    str, typer.Argument(help="The grant's ID (see `access list`).", metavar="GRANT")
]
UserOpt = Annotated[
    str | None, typer.Option("--user", help="Share with this workspace member (user ID).")
]
UsersOpt = Annotated[
    list[str] | None,
    typer.Option("--user", help="Share with this workspace member (user ID); repeatable."),
]
WorkspaceFlag = Annotated[
    bool,
    typer.Option("--everyone", help="Share with everyone in the workspace instead of a user."),
]
LevelOpt = Annotated[
    AccessLevel | None,
    typer.Option("--level", help="Access level: view (read-only) or edit (read-write)."),
]
NotifyOpt = Annotated[
    bool | None,
    typer.Option(
        "--notify/--no-notify",
        help="Whether to notify the grantee (API default: notify). Ignored for workspace grants.",
    ),
]
BulkFileOpt = Annotated[
    str | None,
    typer.Option(
        "--file",
        "-F",
        help='Grants file: JSON array, {"data": [...]}, NDJSON, or CSV. Use - for stdin.',
    ),
]


def _access_path(object_type: str, record_id: str) -> str:
    return f"/objects/{object_type}/records/{record_id}/access"


def _grantee(user: str | None, workspace: bool) -> dict[str, Any]:
    """Attributes naming the grantee, or ``{}`` when neither option was given."""
    if user and workspace:
        raise UsageError("--user and --everyone are mutually exclusive; pick one grantee.")
    if user:
        return {"grantee_type": "user", "grantee_id": user}
    if workspace:
        return {"grantee_type": "workspace", "grantee_id": None}
    return {}


def _document(data: str | None, overrides: dict[str, Any]) -> dict[str, Any]:
    """Build ``{"data": {"type": ..., "attributes": ...}}`` from ``--data`` plus flag values."""
    document = body_from_options(RESOURCE_TYPE, data=data, set_values=None, require=False)
    attributes = document["data"].setdefault("attributes", {})
    if not isinstance(attributes, dict):
        raise UsageError("`attributes` must be a JSON object.")
    attributes.update(overrides)
    return document


def _unwrap_documents(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace single-resource documents (``{"data": {...}}``) with the resource they wrap.

    ``access grant --data`` accepts that shape, so a user copying it into
    ``grant-bulk`` gets the resource instead of a nested ``attributes.data``.
    """
    return [
        item["data"] if set(item) == {"data"} and isinstance(item["data"], dict) else item
        for item in items
    ]


def _bulk_grants(
    users: list[str],
    workspace: bool,
    level: AccessLevel | None,
    notify: bool | None,
    data: str | None,
    file: str | None,
    fmt: str | None,
) -> list[dict[str, Any]]:
    """Collect the grants for ``grant-bulk`` from exactly one input source."""
    sources = [
        name
        for name, given in (
            ("--data", data is not None),
            ("--file", bool(file)),
            ("--user/--everyone", bool(users) or workspace),
        )
        if given
    ]
    if len(sources) != 1:
        given = f" (got {', '.join(sources)})" if sources else ""
        raise UsageError(
            f"Provide the grants with exactly one of --data, --file, or --user/--everyone{given}."
        )

    items: list[Any]
    if data is not None:
        parsed = load_json(data, what="grants")
        if isinstance(parsed, dict) and isinstance(parsed.get("data"), list):
            items = parsed["data"]
        elif isinstance(parsed, dict):
            items = [parsed]
        elif isinstance(parsed, list):
            items = parsed
        else:
            raise UsageError(
                '--data must be a JSON array of grants, a single grant, or {"data": [...]}.'
            )
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise UsageError(f"Grant #{index + 1} is not a JSON object.")
        items = _unwrap_documents(items)
    elif file:
        items = _unwrap_documents(load_records(file, fmt=fmt))
    else:
        if level is None:
            raise UsageError("--level is required with --user/--everyone: view or edit.")
        items = [{"grantee_type": "user", "grantee_id": user} for user in users]
        if workspace:
            items.append({"grantee_type": "workspace", "grantee_id": None})

    resources = to_resources(items, RESOURCE_TYPE)
    for res in resources:
        attrs = res.get("attributes")
        if not isinstance(attrs, dict):
            continue
        if attrs.get("grantee_type") == "workspace":
            attrs.setdefault("grantee_id", None)
        if level is not None:
            attrs.setdefault("access_level", level.value)
        if notify is not None:
            attrs.setdefault("notify", notify)
    if not resources:
        raise UsageError("No grants to create.")
    if len(resources) > MAX_BULK_GRANTS:
        raise UsageError(
            f"Too many grants ({len(resources)}); the API accepts at most "
            f"{MAX_BULK_GRANTS} per request."
        )
    return resources


@app.command("list")
def list_grants(ctx: typer.Context, object_type: ObjectArg, record_id: RecordIdArg) -> None:
    """List a record's access grants (GET /objects/{object}/records/{id}/access).

    Returns every grant on the record plus `meta.viewerAccess` for the calling
    user. The endpoint is not paginated or filterable. Requires a Personal API key.

    Example: clarify access list deal 9d2c4e6f-8a1b-4c3d-9e5f-7a9b1c3d5e7f
    """
    state = get_state(ctx)
    emit(state, state.client().get(_access_path(object_type, record_id)))


@app.command()
def grant(
    ctx: typer.Context,
    object_type: ObjectArg,
    record_id: RecordIdArg,
    user: UserOpt = None,
    workspace: WorkspaceFlag = False,
    level: LevelOpt = None,
    notify: NotifyOpt = None,
    data: DataOpt = None,
) -> None:
    """Share a record with a user or the workspace (POST /objects/{object}/records/{id}/access).

    Pick the grantee with --user USER_ID or --everyone and the level with
    --level view|edit. --data may carry the attributes object (grantee_type,
    grantee_id, access_level, notify) or a full JSON:API document instead;
    flags override matching keys. Requires a Personal API key.

    Examples: clarify access grant deal 9d2c… --user 7d4e… --level view;
    clarify access grant list 1234… --everyone --level edit
    """
    state = get_state(ctx)
    overrides = _grantee(user, workspace)
    if level is not None:
        overrides["access_level"] = level.value
    if notify is not None:
        overrides["notify"] = notify
    if data is None:
        if "grantee_type" not in overrides:
            raise UsageError("Choose a grantee with --user USER_ID or --everyone (or pass --data).")
        if level is None:
            raise UsageError("--level is required: view or edit.")
    document = _document(data, overrides)
    result = state.client().post(
        _access_path(object_type, record_id), document, silent=state.silent
    )
    emit(state, result)


@app.command("grant-bulk")
def grant_bulk(
    ctx: typer.Context,
    object_type: ObjectArg,
    record_id: RecordIdArg,
    user: UsersOpt = None,
    workspace: WorkspaceFlag = False,
    level: LevelOpt = None,
    notify: NotifyOpt = None,
    data: DataOpt = None,
    file: BulkFileOpt = None,
    fmt: FormatOpt = None,
) -> None:
    """Share a record with many grantees at once (POST /objects/{object}/records/{id}/access/bulk).

    Up to 1000 grants per request, from exactly one source: repeatable --user
    (plus --everyone) with one --level; --data with a JSON array of grants,
    a single grant (attributes, a resource, or {"data": {...}}), or
    {"data": [...]}; or --file (JSON, NDJSON, or CSV with grantee_type,
    grantee_id, access_level columns). Flat objects are wrapped as
    object-record-access resources; --level and --notify fill in missing
    values. Requires a Personal API key.

    Example: clarify access grant-bulk deal 9d2c… --user 7d4e… --user 2b6e… --everyone --level view
    """
    state = get_state(ctx)
    grants = _bulk_grants(user or [], workspace, level, notify, data, file, fmt)
    result = state.client().post(
        _access_path(object_type, record_id) + "/bulk", {"data": grants}, silent=state.silent
    )
    emit(state, result)


@app.command()
def update(
    ctx: typer.Context,
    object_type: ObjectArg,
    record_id: RecordIdArg,
    grant_id: GrantIdArg,
    level: LevelOpt = None,
    data: DataOpt = None,
) -> None:
    """Change a grant's access level (PATCH /objects/{object}/records/{id}/access/{grantId}).

    Requires a Personal API key.

    Example: clarify access update deal 9d2c… 2f4a… --level edit
    """
    state = get_state(ctx)
    if level is None and data is None:
        raise UsageError("Pass the new level with --level view|edit (or --data).")
    overrides = {"access_level": level.value} if level is not None else {}
    document = _document(data, overrides)
    result = state.client().patch(
        f"{_access_path(object_type, record_id)}/{grant_id}", document, silent=state.silent
    )
    emit(state, result)


@app.command()
def revoke(
    ctx: typer.Context,
    object_type: ObjectArg,
    record_id: RecordIdArg,
    grant_id: GrantIdArg,
) -> None:
    """Remove a grant from a record (DELETE /objects/{object}/records/{id}/access/{grantId}).

    Asks for confirmation unless --yes is given. The API answers 202 with an
    empty body, so a one-line confirmation goes to stderr. Requires a Personal
    API key.

    Example: clarify -y access revoke deal 9d2c… 2f4a…
    """
    state = get_state(ctx)
    state.confirm(f"Revoke grant {grant_id} on {object_type} {record_id}?")
    result = state.client().delete(
        f"{_access_path(object_type, record_id)}/{grant_id}", silent=state.silent
    )
    if result:
        emit(state, result)
    else:
        emit_message(f"Revoked grant {grant_id} on {object_type} {record_id}.")
