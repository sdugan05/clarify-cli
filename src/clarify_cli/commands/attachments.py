"""``clarify attachments``: files attached to records (RecordAttachments tag).

Uploading is a three-step dance the API defines: ask for a signed URL
(``PUT .../attachments``), send the bytes to that URL with a plain HTTP PUT,
then link the stored file to the record (``POST .../attachments``). Each step
is its own command; ``upload`` runs all three.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer
from rich.markup import escape

from ..cli_options import AllOpt, LimitOpt, ObjectArg, OffsetOpt, PageSizeOpt
from ..console import err_console
from ..errors import ClarifyError, UsageError
from ..output import emit, emit_message
from ..params import collect_list
from ..state import AppState, get_state

app = typer.Typer(no_args_is_help=True)

# OpenAPI operationId -> command name. ``upload`` is a convenience over three
# operations and is therefore not listed.
OPERATIONS: dict[str, str] = {
    "listRecordAttachments": "list",
    "getRecordAttachment": "get",
    "getSignedUrlForRecordAttachmentUpload": "request-upload",
    "addRecordAttachment": "add",
    "deleteRecordAttachment": "delete",
}

#: Attachment items are plain objects keyed by ``_id`` (not JSON:API resources),
#: so the generic "id + first six attributes" table would hide the ID. These are
#: the default table/csv columns; ``--fields`` still overrides them.
ATTACHMENT_COLUMNS = ["_id", "name", "source", "mime_type", "size_bytes", "_created_at"]

DEFAULT_CONTENT_TYPE = "application/octet-stream"

RecordIdArg = Annotated[str, typer.Argument(help="The record's ID.", metavar="ID")]
AttachmentIdArg = Annotated[
    str, typer.Argument(help="The attachment's ID (the `_id` from `list`).", metavar="ATTACHMENT")
]
NameOpt = Annotated[
    str, typer.Option("--name", help="File name including its extension, e.g. proposal.pdf.")
]


def _attachments_path(object_type: str, record_id: str) -> str:
    return f"/objects/{object_type}/records/{record_id}/attachments"


def _emit_or_confirm(state: AppState, result: Any, message: str) -> None:
    """Emit a response body, or a stderr confirmation when the API sent none."""
    if result is None:
        emit_message(message)
    else:
        emit(state, result)


def _log_external(state: AppState, method: str, response: httpx.Response) -> None:
    """Mirror the client's ``-v`` request line for calls that bypass it (storage hosts)."""
    if state.verbose:
        err_console.print(f"[dim]{method} {escape(str(response.url))} → {response.status_code}[/]")


@app.command("list")
def list_attachments(
    ctx: typer.Context,
    object_type: ObjectArg,
    record_id: RecordIdArg,
    limit: LimitOpt = 50,
    offset: OffsetOpt = 0,
    all_pages: AllOpt = False,
    page_size: PageSizeOpt = None,
) -> None:
    """List a record's attachments (GET /objects/{object}/records/{id}/attachments).

    Covers both user uploads and files extracted from emails. Returns up to
    --limit items (default 50); use --all to fetch every page.

    Example:

        clarify attachments list person 5f8b7d2e-9c4a-4e1b-8f3d-2a6c9e0b4d71 --all
    """
    state = get_state(ctx)
    result = collect_list(
        state,
        _attachments_path(object_type, record_id),
        limit=limit,
        offset=offset,
        all_pages=all_pages,
        page_size=page_size,
    )
    emit(state, result, fields=state.fields or ATTACHMENT_COLUMNS)


@app.command()
def get(
    ctx: typer.Context,
    object_type: ObjectArg,
    record_id: RecordIdArg,
    attachment_id: AttachmentIdArg,
    download: Annotated[
        Path | None,
        typer.Option(
            "--download",
            help="Fetch the file from the signed URL and write it to this path.",
            dir_okay=False,
            writable=True,
        ),
    ] = None,
) -> None:
    """Get a short-lived signed download URL (GET .../attachments/{attachmentId}).

    Prints `{"data": {"url": ...}}`. With --download the URL is fetched right
    away and the bytes are written to the given path; a one-line confirmation
    goes to stderr and nothing is printed to stdout.

    Example:

        clarify attachments get person 5f8b…4d71 3b9f…9d24 --download proposal.pdf
    """
    state = get_state(ctx)
    path = f"{_attachments_path(object_type, record_id)}/{attachment_id}"
    result = state.client().get(path)
    if download is None:
        emit(state, result)
        return

    url = result.get("data", {}).get("url") if isinstance(result, dict) else None
    if not isinstance(url, str) or not url:
        raise ClarifyError("The API response did not include a download URL.")
    try:
        response = httpx.get(url, follow_redirects=True, timeout=state.timeout)
    except httpx.HTTPError as exc:
        raise ClarifyError(f"Download failed for GET {url}: {exc}") from exc
    _log_external(state, "GET", response)
    if response.status_code >= 400:
        raise ClarifyError(
            f"Download failed: HTTP {response.status_code} from GET {url}",
            hint="Signed URLs expire quickly; run the command again to get a fresh one.",
        )
    target = download.expanduser()
    try:
        target.write_bytes(response.content)
    except OSError as exc:
        raise UsageError(f"Cannot write {target}: {exc}") from exc
    emit_message(f"Wrote {len(response.content)} bytes to {escape(str(target))}")


@app.command("request-upload")
def request_upload(
    ctx: typer.Context,
    object_type: ObjectArg,
    record_id: RecordIdArg,
    name: NameOpt,
) -> None:
    """Request a signed upload URL for a new file (PUT .../records/{id}/attachments).

    Returns `signedUrl`, `key` and `attachmentId`. HTTP PUT the file contents to
    `signedUrl`, then run `attachments add` with the `key` and `attachmentId`
    to link the file to the record. `attachments upload` does all three steps.

    Example:

        clarify attachments request-upload deal 7c1d…e0a9 --name proposal.pdf
    """
    state = get_state(ctx)
    path = _attachments_path(object_type, record_id)
    result = state.client().put(path, {"name": name}, silent=state.silent)
    _emit_or_confirm(state, result, f"Requested an upload URL for {name}.")


@app.command()
def add(
    ctx: typer.Context,
    object_type: ObjectArg,
    record_id: RecordIdArg,
    name: NameOpt,
    key: Annotated[str, typer.Option("--key", help="Storage key returned by `request-upload`.")],
    attachment_id: Annotated[
        str,
        typer.Option("--attachment-id", help="Attachment ID returned by `request-upload`."),
    ],
) -> None:
    """Link an already-uploaded file to a record (POST .../records/{id}/attachments).

    Use after uploading the bytes to the signed URL from `request-upload`.
    Prints the updated record.

    Example:

        clarify attachments add deal 7c1d…e0a9 --name proposal.pdf \\
            --key attachments/acme/deal/3b9f…9d24/proposal.pdf --attachment-id 3b9f…9d24
    """
    state = get_state(ctx)
    result = _add(state, object_type, record_id, name=name, key=key, attachment_id=attachment_id)
    _emit_or_confirm(state, result, f"Attached {name} to {object_type} {record_id}.")


def _add(
    state: AppState, object_type: str, record_id: str, *, name: str, key: str, attachment_id: str
) -> Any:
    body = {"name": name, "key": key, "attachmentId": attachment_id}
    return state.client().post(_attachments_path(object_type, record_id), body, silent=state.silent)


@app.command()
def upload(
    ctx: typer.Context,
    object_type: ObjectArg,
    record_id: RecordIdArg,
    file: Annotated[
        Path,
        typer.Argument(
            help="Local file to upload.",
            metavar="FILE",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    name: Annotated[
        str | None,
        typer.Option("--name", help="File name to store; defaults to FILE's basename."),
    ] = None,
    content_type: Annotated[
        str | None,
        typer.Option(
            "--content-type",
            help="Content-Type for the storage upload; guessed from the name by default.",
        ),
    ] = None,
) -> None:
    """Upload a local file and attach it to a record (request-upload → PUT → add).

    Runs `PUT .../attachments` to get a signed URL, sends the file bytes to
    that URL with a plain HTTP PUT, then `POST .../attachments` to link it.
    Prints the updated record. If the storage upload fails the record is left
    untouched.

    Example:

        clarify attachments upload deal 7c1d…e0a9 ./proposal.pdf
    """
    state = get_state(ctx)
    file_name = name or file.name
    try:
        payload = file.read_bytes()
    except OSError as exc:
        raise UsageError(f"Cannot read {file}: {exc}") from exc

    path = _attachments_path(object_type, record_id)
    ticket = state.client().put(path, {"name": file_name}, silent=state.silent)
    data = ticket.get("data") if isinstance(ticket, dict) else None
    if not isinstance(data, dict) or not all(
        isinstance(data.get(k), str) and data[k] for k in ("signedUrl", "key", "attachmentId")
    ):
        raise ClarifyError("The upload-URL response did not include signedUrl, key, attachmentId.")

    mime = content_type or mimetypes.guess_type(file_name)[0] or DEFAULT_CONTENT_TYPE
    try:
        response = httpx.put(
            data["signedUrl"],
            content=payload,
            headers={"Content-Type": mime},
            timeout=state.timeout,
        )
    except httpx.HTTPError as exc:
        raise ClarifyError(f"Storage upload failed for PUT {data['signedUrl']}: {exc}") from exc
    _log_external(state, "PUT", response)
    if response.status_code >= 400:
        raise ClarifyError(
            f"Storage upload failed: HTTP {response.status_code} from PUT {data['signedUrl']}\n"
            f"  {response.text.strip()[:500] or 'no response body'}",
            hint="The record was not modified. Retry, or pass --content-type if storage "
            "rejected the guessed type.",
        )

    result = _add(
        state,
        object_type,
        record_id,
        name=file_name,
        key=data["key"],
        attachment_id=data["attachmentId"],
    )
    _emit_or_confirm(state, result, f"Attached {file_name} to {object_type} {record_id}.")


@app.command()
def delete(
    ctx: typer.Context,
    object_type: ObjectArg,
    record_id: RecordIdArg,
    attachment_id: AttachmentIdArg,
) -> None:
    """Delete an attachment from a record (DELETE .../attachments/{attachmentId}).

    Asks for confirmation unless --yes is given. This cannot be undone. Prints
    the updated record.

    Example:

        clarify -y attachments delete person 5f8b…4d71 3b9f…9d24
    """
    state = get_state(ctx)
    state.confirm(
        f"Delete attachment {attachment_id} from {object_type} {record_id}? This cannot be undone."
    )
    path = f"{_attachments_path(object_type, record_id)}/{attachment_id}"
    result = state.client().delete(path, silent=state.silent)
    _emit_or_confirm(state, result, f"Deleted attachment {attachment_id}.")
