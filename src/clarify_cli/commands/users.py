"""``clarify users``: workspace members (Users tag)."""

from __future__ import annotations

from typing import Annotated

import typer

from ..cli_options import AllOpt, LimitOpt, OffsetOpt, PageSizeOpt, SortOpt
from ..output import emit
from ..params import collect_list
from ..state import get_state

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_users(
    ctx: typer.Context,
    limit: LimitOpt = 50,
    offset: OffsetOpt = 0,
    all_pages: AllOpt = False,
    page_size: PageSizeOpt = None,
    sort: SortOpt = None,
) -> None:
    """List the workspace's users with their roles (GET /users)."""
    state = get_state(ctx)
    result = collect_list(
        state,
        "/users",
        sort=sort,
        limit=limit,
        offset=offset,
        all_pages=all_pages,
        page_size=page_size,
    )
    emit(state, result)


@app.command()
def get(
    ctx: typer.Context,
    user_id: Annotated[str, typer.Argument(help="The user's ID.", metavar="USER_ID")],
) -> None:
    """Show one user, including roles and last-active time (GET /users/{userId})."""
    state = get_state(ctx)
    emit(state, state.client().get(f"/users/{user_id}"))
