"""``clarify workflows``: automations and email sequences (Workflows tag).

Workflows are passed through as JSON:API documents. The CLI does not model the
trigger/block schema; write it in a file and pass ``--data @file``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

import typer

from ..cli_options import (
    AllOpt,
    DataOpt,
    FilterOpt,
    LimitOpt,
    OffsetOpt,
    PageSizeOpt,
    SetOpt,
    SortOpt,
)
from ..errors import UsageError
from ..inputs import body_from_options
from ..output import emit, emit_message
from ..params import collect_list
from ..state import get_state

app = typer.Typer(no_args_is_help=True)

# OpenAPI operationId -> command name.
OPERATIONS: dict[str, str] = {
    "getWorkflows": "list",
    "getWorkflow": "get",
    "createWorkflow": "create",
    "updateWorkflow": "update",
    "deleteWorkflow": "delete",
}

RESOURCE_TYPE = "workflow"
#: GET /workflows caps page[limit] at 500 (lower than the client's generic 1000).
MAX_PAGE_SIZE = 500


class WorkflowType(StrEnum):
    """Values accepted by the ``type`` filter (the ``attributes.type`` discriminator)."""

    workflow = "workflow"
    sequence = "sequence"
    system = "system"


WorkflowIdArg = Annotated[str, typer.Argument(help="The workflow's ID.", metavar="WORKFLOW_ID")]


@app.command("list")
def list_workflows(
    ctx: typer.Context,
    workflow_type: Annotated[
        WorkflowType | None,
        typer.Option(
            "--type",
            "-t",
            help="Only this workflow type (sugar for --filter type=VALUE).",
        ),
    ] = None,
    limit: LimitOpt = 50,
    offset: OffsetOpt = 0,
    all_pages: AllOpt = False,
    page_size: PageSizeOpt = None,
    sort: SortOpt = None,
    filters: FilterOpt = None,
) -> None:
    """List the workspace's workflows (GET /workflows).

    `workflow` is a general automation, `sequence` an email sequence (campaign), and
    `system` a hidden built-in. Example:

        clarify workflows list --type sequence --filter enabled=true --sort -_created_at
    """
    state = get_state(ctx)
    if page_size is None and not all_pages:
        page_size = min(limit, MAX_PAGE_SIZE)
    extra = [("filter[type]", workflow_type.value)] if workflow_type else None
    result = collect_list(
        state,
        "/workflows",
        filters=filters,
        sort=sort,
        limit=limit,
        offset=offset,
        all_pages=all_pages,
        page_size=page_size,
        extra=extra,
    )
    emit(state, result)


@app.command()
def get(ctx: typer.Context, workflow_id: WorkflowIdArg) -> None:
    """Show one workflow with its trigger and blocks (GET /workflows/{id})."""
    state = get_state(ctx)
    emit(state, state.client().get(f"/workflows/{workflow_id}"))


@app.command()
def create(ctx: typer.Context, data: DataOpt = None, set_values: SetOpt = None) -> None:
    """Create a workflow from a JSON document (POST /workflows).

    The body is sent as-is. Pass either a full `{"data": {"type": "workflow",
    "attributes": {...}}}` document or just the attributes object (`name`,
    `description`, `enabled`, `type`, `trigger`, `blocks`, ...); the CLI wraps it.
    Create it disabled and enable it once the graph is complete. Example:

        clarify workflows create --data @workflow.json --set enabled=false
    """
    state = get_state(ctx)
    document = body_from_options(RESOURCE_TYPE, data=data, set_values=set_values)
    emit(state, state.client().post("/workflows", json_body=document, silent=state.silent))


@app.command()
def update(
    ctx: typer.Context,
    workflow_id: WorkflowIdArg,
    data: DataOpt = None,
    set_values: SetOpt = None,
    enable: Annotated[
        bool, typer.Option("--enable", help="Turn the workflow on (sets enabled=true).")
    ] = False,
    disable: Annotated[
        bool, typer.Option("--disable", help="Turn the workflow off (sets enabled=false).")
    ] = False,
) -> None:
    """Partially update a workflow (PATCH /workflows/{id}).

    Only the attributes you send change. `--enable`/`--disable` are shorthand for
    `--set enabled=true|false` and can be combined with `--data`/`--set`. Examples:

        clarify workflows update WORKFLOW_ID --enable
        clarify workflows update WORKFLOW_ID --set name="Nightly sync" --data @blocks.json
    """
    state = get_state(ctx)
    if enable and disable:
        raise UsageError("--enable and --disable are mutually exclusive.")
    toggled = enable or disable
    document = body_from_options(
        RESOURCE_TYPE, data=data, set_values=set_values, id=workflow_id, require=not toggled
    )
    if toggled:
        attributes: Any = document["data"].setdefault("attributes", {})
        if not isinstance(attributes, dict):
            raise UsageError("`attributes` must be a JSON object.")
        attributes["enabled"] = bool(enable)
    emit(
        state,
        state.client().patch(f"/workflows/{workflow_id}", json_body=document, silent=state.silent),
    )


@app.command()
def delete(ctx: typer.Context, workflow_id: WorkflowIdArg) -> None:
    """Delete a workflow (DELETE /workflows/{id}).

    Asks for confirmation unless --yes is given. The API applies the deletion
    asynchronously and returns an empty 202 body, so the CLI prints a confirmation
    line to stderr. This cannot be undone.
    """
    state = get_state(ctx)
    state.confirm(f"Delete workflow {workflow_id}? This cannot be undone.")
    body = state.client().delete(f"/workflows/{workflow_id}", silent=state.silent)
    if body is None or body == {}:
        emit_message(f"Workflow {workflow_id} deletion accepted.")
        return
    emit(state, body)
