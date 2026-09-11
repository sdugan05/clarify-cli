"""Shared option/argument types so every command spells things the same way."""

from __future__ import annotations

from typing import Annotated

import typer

ObjectArg = Annotated[
    str,
    typer.Argument(
        help="Object type: person, company, deal, meeting, task, or a custom c_* object.",
        metavar="OBJECT",
    ),
]

LimitOpt = Annotated[
    int, typer.Option("--limit", "-n", min=1, help="Maximum number of items to return.")
]
OffsetOpt = Annotated[int, typer.Option("--offset", min=0, help="Number of items to skip.")]
AllOpt = Annotated[bool, typer.Option("--all", help="Fetch every page (ignores --limit).")]
PageSizeOpt = Annotated[
    int | None,
    typer.Option("--page-size", min=1, help="Items per request (page[limit]); default derived."),
]
SortOpt = Annotated[
    str | None,
    typer.Option("--sort", "-s", help="Sort: FIELD, FIELD:asc, FIELD:desc, or -FIELD."),
]
FilterOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--filter",
        "-f",
        help=(
            "Filter FIELD=VALUE or 'FIELD[Operator]=VALUE' (repeatable). "
            "Shorthand values like '>100', '*Smith*', 'a,b', 'null' are passed through."
        ),
    ),
]
IncludeOpt = Annotated[
    str | None,
    typer.Option("--include", "-i", help="Comma-separated relationships to embed."),
]
SearchOpt = Annotated[
    str | None, typer.Option("--search", help="Case-insensitive substring search.")
]
DataOpt = Annotated[
    str | None,
    typer.Option("--data", "-d", help="JSON body: inline, @file, or - for stdin."),
]
SetOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--set",
        help=(
            "Set an attribute KEY=VALUE (repeatable). Dotted keys nest; values parse as JSON "
            "when possible, so amount=100 is a number and name.first_name=Jane is a string."
        ),
    ),
]
FileOpt = Annotated[
    str,
    typer.Option(
        "--file",
        "-F",
        help='Records file: JSON array, {"data": [...]}, NDJSON, or CSV. Use - for stdin.',
    ),
]
FormatOpt = Annotated[
    str | None,
    typer.Option("--format", help="Force the records file format: json, ndjson, or csv."),
]
