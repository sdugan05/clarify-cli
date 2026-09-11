"""``clarify activities``: a record's activity feed (Activities tag)."""

from __future__ import annotations

from typing import Annotated

import typer

from ..cli_options import AllOpt, LimitOpt, ObjectArg, OffsetOpt, PageSizeOpt, SortOpt
from ..output import emit
from ..params import collect_list
from ..state import get_state

app = typer.Typer(no_args_is_help=True)

# OpenAPI operationId -> command name.
OPERATIONS: dict[str, str] = {"getActivities": "list"}

#: The endpoint accepts at most 500 items per page (``page[limit]`` maximum).
MAX_PAGE_SIZE = 500

RecordArg = Annotated[str, typer.Argument(help="The record's ID.", metavar="RECORD")]


@app.command("list")
def list_activities(
    ctx: typer.Context,
    object_type: ObjectArg,
    record: RecordArg,
    limit: LimitOpt = 50,
    offset: OffsetOpt = 0,
    all_pages: AllOpt = False,
    page_size: PageSizeOpt = None,
    sort: SortOpt = None,
) -> None:
    """List a record's activity feed (GET /objects/{object}/records/{record}/activities).

    Activities are change events (field updates, comments, relationship
    changes) grouped by record and change type, newest first. Comments have
    no list endpoint of their own; they appear here.

    Example:

        clarify activities list person 5f8b7d2e-9c4a-4e1b-8f3d-2a6c9e0b4d71 -n 20
    """
    state = get_state(ctx)
    if page_size is None and not all_pages:
        page_size = min(limit, MAX_PAGE_SIZE)
    result = collect_list(
        state,
        f"/objects/{object_type}/records/{record}/activities",
        sort=sort,
        limit=limit,
        offset=offset,
        all_pages=all_pages,
        page_size=page_size,
    )
    emit(state, result)
