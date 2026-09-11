"""``clarify comments``: comments on records (Comments tag).

Comment bodies are rich text: the API expects ``message`` to be a non-empty
array of BlockNote blocks, never a plain string. ``--message TEXT`` is turned
into the minimal valid structure (one paragraph holding one text run); pass
``--data`` when you need headings, styles, or several blocks.
"""

from __future__ import annotations

import sys
from typing import Annotated, Any

import typer

from ..cli_options import DataOpt, ObjectArg
from ..errors import UsageError
from ..inputs import load_json, read_source
from ..output import emit, emit_message
from ..state import get_state

app = typer.Typer(no_args_is_help=True)

# OpenAPI operationId -> command name.
OPERATIONS: dict[str, str] = {
    "createComment": "create",
    "getComment": "get",
    "updateComment": "update",
    "deleteComment": "delete",
}

CommentIdArg = Annotated[str, typer.Argument(help="The comment's ID.", metavar="COMMENT_ID")]
RecordIdArg = Annotated[
    str,
    typer.Argument(help="ID of the record to comment on (sent as owner_id).", metavar="RECORD_ID"),
]
MessageOpt = Annotated[
    str | None,
    typer.Option(
        "--message",
        "-m",
        help="Plain-text body; becomes one BlockNote paragraph. Use - to read stdin.",
    ),
]
MessageFileOpt = Annotated[
    str | None,
    typer.Option("--message-file", help="Read the plain-text body from this file."),
]


def plain_message(text: str) -> list[dict[str, Any]]:
    """Wrap plain text in the smallest BlockNote structure the API accepts.

    One ``paragraph`` block with a single unstyled ``text`` run, exactly as in
    the rich-text guide. Newlines are kept inside the run; use ``--data`` for
    multiple blocks.
    """
    if not text.strip():
        raise UsageError("The comment message must not be empty.")
    return [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": text, "styles": {}}],
        }
    ]


def _message_blocks(
    data: str | None, message: str | None, message_file: str | None = None
) -> tuple[dict[str, Any], bool]:
    """Resolve ``--data``/``--message``/``--message-file`` into ``(base_object, has_message)``.

    ``--data`` may be the DTO object or, as a shortcut, a bare block array which
    is taken as ``message``. ``--message`` wins over a ``message`` in ``--data``.
    """
    if message is not None and message_file is not None:
        raise UsageError("--message and --message-file are mutually exclusive.")
    if message_file is not None:
        message = read_source("@" + message_file)
    parsed = load_json(data) if data is not None else None
    base: dict[str, Any]
    if parsed is None:
        base = {}
    elif isinstance(parsed, list):
        base = {"message": parsed}
    elif isinstance(parsed, dict):
        base = dict(parsed)
    else:
        raise UsageError("--data must be a JSON object (the comment) or an array of blocks.")
    if message is not None:
        text = sys.stdin.read() if message == "-" else message
        base["message"] = plain_message(text or "")
    blocks = base.get("message")
    if blocks is not None and (not isinstance(blocks, list) or not blocks):
        raise UsageError("`message` must be a non-empty array of BlockNote blocks.")
    return base, blocks is not None


@app.command()
def create(
    ctx: typer.Context,
    object_type: ObjectArg,
    record_id: RecordIdArg,
    message: MessageOpt = None,
    message_file: MessageFileOpt = None,
    data: DataOpt = None,
) -> None:
    """Create a comment on a record (POST /comments).

    The body is the CreateCommentDto: ``entity`` (OBJECT), ``owner_id``
    (RECORD_ID) and ``message`` (BlockNote blocks). ``--message TEXT`` is
    converted to one paragraph with a single text run. ``--data`` supplies the
    rest of the DTO (or a bare block array for ``message``); the positional
    OBJECT and RECORD_ID always win over ``entity``/``owner_id`` found in it.

    Examples:

        clarify comments create person 5f8b... -m "Called Jane."

        clarify comments create person 5f8b... --data @comment.json

        clarify comments create deal 9d3e... --data \\
            '[{"type":"paragraph","content":[{"type":"text","text":"Hi","styles":{"bold":true}}]}]'
    """
    state = get_state(ctx)
    body, has_message = _message_blocks(data, message, message_file)
    body["entity"] = object_type
    body["owner_id"] = record_id
    if not has_message:
        raise UsageError(
            "Missing --message.",
            hint="Pass --message TEXT or include `message` (BlockNote blocks) in --data.",
        )
    emit(state, state.client().post("/comments", json_body=body, silent=state.silent))


@app.command()
def get(ctx: typer.Context, comment_id: CommentIdArg) -> None:
    """Show one comment (GET /comments/{id})."""
    state = get_state(ctx)
    emit(state, state.client().get(f"/comments/{comment_id}"))


@app.command()
def update(
    ctx: typer.Context,
    comment_id: CommentIdArg,
    message: MessageOpt = None,
    message_file: MessageFileOpt = None,
    data: DataOpt = None,
) -> None:
    """Replace a comment's body; author only (PATCH /comments/{id}).

    Sends the UpdateCommentDto ``{"message": [...]}``. ``--message TEXT`` becomes
    one paragraph; ``--data`` may be the DTO, a bare block array, or a comment
    fetched with ``get`` (only its ``message`` is sent).

    Example:

        clarify comments update 9d3e... -m "Jane signed off on pricing."
    """
    state = get_state(ctx)
    base, has_message = _message_blocks(data, message, message_file)
    if not has_message:
        raise UsageError("Provide the new body with --message TEXT or --data JSON|@file|-.")
    body = {"message": base["message"]}
    emit(
        state, state.client().patch(f"/comments/{comment_id}", json_body=body, silent=state.silent)
    )


@app.command()
def delete(ctx: typer.Context, comment_id: CommentIdArg) -> None:
    """Permanently delete a comment (DELETE /comments/{id}).

    Asks for confirmation unless --yes is given. The API returns the deleted
    comment, which is printed.
    """
    state = get_state(ctx)
    state.confirm(f"Permanently delete comment {comment_id}? This cannot be undone.")
    result = state.client().delete(f"/comments/{comment_id}", silent=state.silent)
    if result is None:
        emit_message(f"Deleted comment {comment_id}.")
        return
    emit(state, result)
