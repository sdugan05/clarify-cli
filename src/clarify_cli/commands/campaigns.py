"""``clarify campaigns``: campaign recipients and their engagement (Campaigns tag)."""

from __future__ import annotations

from typing import Annotated

import typer

from ..cli_options import AllOpt, FilterOpt, LimitOpt, OffsetOpt, PageSizeOpt, SortOpt
from ..output import emit
from ..params import collect_list
from ..state import get_state

app = typer.Typer(no_args_is_help=True)

# OpenAPI operationId -> command name.
OPERATIONS: dict[str, str] = {"getRecipients": "recipients"}

#: The recipients endpoint caps ``page[limit]`` at 500 (the generic client default is 1000).
RECIPIENTS_MAX_PAGE_SIZE = 500

CampaignArg = Annotated[str, typer.Argument(help="The campaign's ID.", metavar="CAMPAIGN")]


@app.command()
def recipients(
    ctx: typer.Context,
    campaign_id: CampaignArg,
    limit: LimitOpt = 50,
    offset: OffsetOpt = 0,
    all_pages: AllOpt = False,
    page_size: PageSizeOpt = None,
    sort: SortOpt = None,
    filters: FilterOpt = None,
) -> None:
    """List a campaign's recipients with engagement (GET /campaigns/{campaignId}/recipients).

    One row per person (their active run is preferred) with `has_opened`,
    `has_clicked`, `has_replied`, `has_unsubscribed` and the matching
    `last_*_at` times. Filters this endpoint understands:

    - `-f event=clicked` — recipients who did at least one of `opened`,
      `clicked`, `replied`; comma-separate to OR them (`event=clicked,replied`).
    - `-f status=completed` — delivery state: `scheduled`, `completed`,
      `paused`, `failed` or `unsubscribed`.
    - `-f q=jane` — case-insensitive substring match on name or email (max 50 chars).

    Sort with `-s _created_at:desc`. Pages are capped at 500 recipients.

    Example:

        clarify campaigns recipients 9a1f…c3e2 -f event=clicked,replied -s _created_at:desc
    """
    state = get_state(ctx)
    if page_size is None and not all_pages:
        page_size = min(limit, RECIPIENTS_MAX_PAGE_SIZE)
    result = collect_list(
        state,
        f"/campaigns/{campaign_id}/recipients",
        filters=filters,
        sort=sort,
        limit=limit,
        offset=offset,
        all_pages=all_pages,
        page_size=page_size,
    )
    emit(state, result)
