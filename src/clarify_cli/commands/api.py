"""``clarify api``: call any endpoint directly."""

from __future__ import annotations

from typing import Annotated

import typer

from ..errors import UsageError
from ..inputs import load_json
from ..output import emit
from ..params import parse_kv
from ..state import get_state

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def command(
    ctx: typer.Context,
    method: Annotated[str, typer.Argument(help="HTTP method: GET, POST, PUT, PATCH, DELETE.")],
    path: Annotated[
        str,
        typer.Argument(
            help=(
                "Workspace-relative path such as /objects/person/resources, a /workspaces/... "
                "path, or a full URL (for example a links.next value)."
            )
        ),
    ],
    param: Annotated[
        list[str] | None,
        typer.Option("--param", "-P", help="Query parameter KEY=VALUE, e.g. 'page[limit]=10'."),
    ] = None,
    data: Annotated[
        str | None, typer.Option("--data", "-d", help="JSON body: inline, @file, or - for stdin.")
    ] = None,
    header: Annotated[
        list[str] | None, typer.Option("--header", "-H", help="Extra header 'Name: value'.")
    ] = None,
    all_pages: Annotated[
        bool, typer.Option("--all", help="GET only: follow links.next and merge every page.")
    ] = False,
    out: Annotated[
        str | None, typer.Option("--out", help="Write the raw response body to this file.")
    ] = None,
) -> None:
    """Send an arbitrary request with the configured auth and workspace.

    Examples:

        clarify api GET /objects/person/resources -P 'page[limit]=5' -P 'filter[name]=*Smith*'

        clarify --silent api POST /comments -d @comment.json

        clarify -o ndjson api GET /users --all
    """
    state = get_state(ctx)
    verb = method.upper()
    if verb not in METHODS:
        raise UsageError(f"Unsupported method {method!r}; use one of {', '.join(METHODS)}.")
    params = parse_kv(param)
    body = load_json(data) if data is not None else None
    headers = _parse_headers(header)
    client = state.client()

    if all_pages:
        if verb != "GET":
            raise UsageError("--all only applies to GET requests.")
        emit(state, client.collect(path, params, all_pages=True))
        return

    response = client.request(
        verb,
        path,
        params=params,
        json_body=body,
        silent=state.silent and verb != "GET",
        headers=headers,
    )
    if out:
        with open(out, "wb") as fh:
            fh.write(response.content)
        typer.echo(f"Wrote {len(response.content)} bytes to {out}", err=True)
        return
    if response.status_code == 204 or not response.content:
        typer.echo(f"{response.status_code} {response.reason_phrase} (no body)", err=True)
        return
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        emit(state, response.json())
    else:
        text = response.text
        print(text, end="" if text.endswith("\n") else "\n")


def _parse_headers(values: list[str] | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw in values or []:
        name, sep, value = raw.partition(":")
        if not sep or not name.strip():
            raise UsageError(f"Invalid --header {raw!r}; expected 'Name: value'.")
        headers[name.strip()] = value.strip()
    return headers
