"""``clarify object-access``: entity-wide access delegations (ObjectAccess tag).

A delegation gives another user the same access you have to every record of
an object type (``meeting`` or ``message``). Listing shows both delegations you
granted and delegations granted to you.

Every endpoint in this group requires a user-backed (Personal) API key; a
Workspace API key is rejected with HTTP 403. Granting and revoking also need a
paid plan with access delegation enabled.
"""

from __future__ import annotations

from typing import Annotated, Any

import typer

from ..cli_options import DataOpt
from ..errors import UsageError
from ..inputs import body_from_options
from ..output import emit, emit_message
from ..state import get_state

RESOURCE_TYPE = "object-access"
KEY_NOTE = (
    "These endpoints require a user-backed (Personal) API key; "
    "Workspace API keys are rejected with HTTP 403."
)

app = typer.Typer(
    no_args_is_help=True,
    help=f"Manage entity-wide access delegations. {KEY_NOTE}",
    epilog=KEY_NOTE,
)

# OpenAPI operationId -> command name.
OPERATIONS: dict[str, str] = {
    "getObjectAccess": "list",
    "giveObjectAccess": "grant",
    "revokeObjectAccess": "revoke",
}

ObjectArg = Annotated[
    str,
    typer.Argument(
        help="Object type the delegation applies to: meeting or message.", metavar="OBJECT"
    ),
]
DelegationIdArg = Annotated[
    str, typer.Argument(help="The delegation's ID (see `object-access list`).", metavar="ID")
]
UserOpt = Annotated[
    str | None,
    typer.Option("--user", help="Delegate to this workspace member (user ID → delegate_id)."),
]


def _access_path(object_type: str) -> str:
    return f"/objects/{object_type}/access"


@app.command("list")
def list_delegations(ctx: typer.Context, object_type: ObjectArg) -> None:
    """List access delegations for an object type (GET /objects/{object}/access).

    Includes delegations you granted and those granted to you. The endpoint is
    not paginated or filterable. Requires a Personal API key.

    Example: clarify object-access list meeting
    """
    state = get_state(ctx)
    emit(state, state.client().get(_access_path(object_type)))


@app.command()
def grant(
    ctx: typer.Context,
    object_type: ObjectArg,
    user: UserOpt = None,
    data: DataOpt = None,
) -> None:
    """Delegate your access to every record of an object type (POST /objects/{object}/access).

    Name the delegate with --user USER_ID, or pass --data with the attributes
    object ({"delegate_id": ...}) or a full JSON:API document; --user overrides
    delegate_id. Requires a Personal API key and a plan with access delegation.

    Example: clarify object-access grant meeting --user 2b6e4f8a-3d1c-4a9e-8b5f-7c2a9d0e4f63
    """
    state = get_state(ctx)
    if user is None and data is None:
        raise UsageError("Name the delegate with --user USER_ID (or pass --data).")
    document = body_from_options(RESOURCE_TYPE, data=data, set_values=None, require=False)
    attributes: Any = document["data"].setdefault("attributes", {})
    if not isinstance(attributes, dict):
        raise UsageError("`attributes` must be a JSON object.")
    if user is not None:
        attributes["delegate_id"] = user
    emit(state, state.client().post(_access_path(object_type), document, silent=state.silent))


@app.command()
def revoke(ctx: typer.Context, object_type: ObjectArg, delegation_id: DelegationIdArg) -> None:
    """Revoke an access delegation (DELETE /objects/{object}/access/{id}).

    Asks for confirmation unless --yes is given. The API answers 202 with an
    empty body, so a one-line confirmation goes to stderr. Requires a Personal
    API key and a plan with access delegation.

    Example: clarify -y object-access revoke meeting a1f4e6d2-8c9b-4f3a-9d5e-1b6c8a2f7d90
    """
    state = get_state(ctx)
    state.confirm(f"Revoke {object_type} access delegation {delegation_id}?")
    result = state.client().delete(
        f"{_access_path(object_type)}/{delegation_id}", silent=state.silent
    )
    if result:
        emit(state, result)
    else:
        emit_message(f"Revoked {object_type} access delegation {delegation_id}.")
