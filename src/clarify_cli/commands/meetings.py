"""``clarify meetings``: recordings, transcripts, and media uploads (MeetingRecordings tag)."""

from __future__ import annotations

import json
import mimetypes
import re
import sys
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer

from ..cli_options import DataOpt
from ..console import err_console
from ..errors import ClarifyError, UsageError
from ..inputs import load_json
from ..output import emit, emit_message
from ..state import AppState, get_state

app = typer.Typer(no_args_is_help=True)

# OpenAPI operationId -> command name. ``upload-media`` is a convenience that
# chains initMediaUpload -> S3 POST -> confirmMediaUpload and is not listed.
OPERATIONS: dict[str, str] = {
    "enableRecording": "enable-recording",
    "disableRecording": "disable-recording",
    "getRecordingArtifacts": "artifacts",
    "uploadTranscript": "upload-transcript",
    "uploadRecordingTranscript": "upload-recording-transcript",
    "initMediaUpload": "init-media-upload",
    "confirmMediaUpload": "confirm-media-upload",
}

#: Plain-text transcripts carry no timing, but the API requires word timestamps.
#: With ``--plain-text`` words are laid out on a synthetic timeline at this pace
#: so their order is preserved; the values are invented, not measured.
SECONDS_PER_WORD = 0.4

PLAIN_TEXT_HINT = "Pass --plain-text to upload a text transcript with synthetic word timestamps."
MEDIA_TRANSCRIPT_HINT = (
    "--transcript-file must be JSON with real word timestamps that line up with the media; "
    "plain text is not accepted here."
)

_SPEAKER_LINE = re.compile(r"^(?P<speaker>[^:]{1,80}?):\s+(?P<text>\S.*)$")
_MEDIA_TYPE = re.compile(r"^(audio|video)/")

MeetingArg = Annotated[str, typer.Argument(help="The meeting record's ID.", metavar="MEETING")]
RecordingArg = Annotated[
    str, typer.Argument(help="The meeting recording's ID.", metavar="RECORDING")
]
TranscriptFileOpt = Annotated[
    str | None,
    typer.Option(
        "--file",
        "-F",
        help=(
            'Transcript JSON file: an array of segments or {"transcript": [...]}. '
            "Use - for stdin. Add --plain-text to read a text file instead."
        ),
    ),
]
PlainTextOpt = Annotated[
    bool,
    typer.Option(
        "--plain-text",
        help=(
            "Treat --file as plain text: one utterance per line, optionally 'Speaker: words'. "
            f"Word timestamps are SYNTHETIC ({SECONDS_PER_WORD} s per word) and word language "
            "is null; the segment language comes from --language."
        ),
    ),
]
MediaTranscriptFileOpt = Annotated[
    str | None,
    typer.Option(
        "--transcript-file",
        help=(
            "Transcript JSON to attach to the same recording: an array of segments or "
            '{"transcript": [...]} whose word timestamps line up with the media. Use - for stdin.'
        ),
    ),
]
LanguageOpt = Annotated[
    str,
    typer.Option("--language", help="ISO language code for segments built with --plain-text."),
]
RecordingIdOpt = Annotated[
    str | None,
    typer.Option(
        "--recording-id",
        help="Overwrite this completed manual-upload recording instead of creating a new one.",
    ),
]


# -- helpers -----------------------------------------------------------------


def _emit_result(state: AppState, result: Any, message: str) -> None:
    if result is None:
        emit_message(message)
    else:
        emit(state, result)


def _check_media_type(content_type: str) -> str:
    if not _MEDIA_TYPE.match(content_type):
        raise UsageError(
            f"Invalid --content-type {content_type!r}; must be an audio/* or video/* MIME type."
        )
    return content_type


def segments_from_text(text: str, *, language: str) -> list[dict[str, Any]]:
    """Turn a plain-text transcript into the API's speaker-segment shape.

    Each non-blank line is one segment. ``Speaker Name: words`` attributes the
    line to that speaker (speaker IDs are numbered in order of first
    appearance); other lines are unattributed. The text carries no timing, so
    words get consecutive synthetic timestamps (``SECONDS_PER_WORD`` each),
    ``language: null`` (nothing was detected) and ``confidence: null``;
    ``language`` is applied to the segment only.
    """
    segments: list[dict[str, Any]] = []
    speaker_ids: dict[str, int] = {}
    position = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = _SPEAKER_LINE.match(line)
        if match:
            speaker: str | None = match.group("speaker").strip()
            speaker_id: int | None = speaker_ids.setdefault(speaker, len(speaker_ids) + 1)
            spoken = match.group("text")
        else:
            speaker, speaker_id, spoken = None, None, line
        words: list[dict[str, Any]] = []
        for token in spoken.split():
            words.append(
                {
                    "text": token,
                    "start_timestamp": round(position * SECONDS_PER_WORD, 3),
                    "end_timestamp": round((position + 1) * SECONDS_PER_WORD, 3),
                    "language": None,
                    "confidence": None,
                }
            )
            position += 1
        segments.append(
            {"speaker": speaker, "speaker_id": speaker_id, "language": language, "words": words}
        )
    if not segments:
        raise UsageError("The transcript is empty.")
    return segments


def _document_from_json(parsed: Any) -> dict[str, Any]:
    """Accept a bare segment array or a ``{"transcript": [...]}`` object."""
    if isinstance(parsed, list):
        return {"transcript": parsed}
    if isinstance(parsed, dict) and isinstance(parsed.get("transcript"), list):
        return parsed
    raise UsageError(
        'Transcript JSON must be an array of segments or an object with a "transcript" array.'
    )


def _read_text(source: str) -> str:
    """Read a ``--file`` style input: ``-`` is stdin, anything else a path."""
    if source == "-":
        return sys.stdin.read()
    path = Path(source).expanduser()
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"Cannot read {path}: {exc}") from exc


def _is_json_document(text: str) -> bool:
    try:
        return isinstance(json.loads(text), list | dict)
    except ValueError:
        return False


def transcript_from_json_text(text: str, *, label: str, hint: str | None = None) -> dict[str, Any]:
    """Parse a JSON transcript (segment array or ``{"transcript": [...]}``) verbatim."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UsageError(
            f"Invalid JSON in {label}: {exc.msg} (line {exc.lineno}).", hint=hint
        ) from exc
    return _document_from_json(parsed)


def transcript_from_file(
    source: str, *, plain_text: bool = False, language: str = "en"
) -> dict[str, Any]:
    """Load ``--file`` (``-`` = stdin) as JSON, or as plain text when ``plain_text`` is set.

    The format is chosen by the flag, never by the file suffix, so a JSON
    document is passed through unchanged wherever it comes from and text is
    only converted (with synthetic timestamps) on explicit request.
    """
    text = _read_text(source)
    label = "stdin" if source == "-" else source
    if not plain_text:
        return transcript_from_json_text(text, label=label, hint=PLAIN_TEXT_HINT)
    if _is_json_document(text):
        raise UsageError(
            f"{label} holds a JSON document, not plain text.",
            hint="Drop --plain-text to send it as a structured transcript.",
        )
    return {"transcript": segments_from_text(text, language=language)}


def transcript_body(
    *, file: str | None, data: str | None, plain_text: bool = False, language: str = "en"
) -> dict[str, Any]:
    """Build the transcript request body from ``--file`` or ``--data`` (exactly one)."""
    if file is not None and data is not None:
        raise UsageError("Use either --file or --data, not both.")
    if plain_text and file is None:
        raise UsageError("--plain-text requires --file PATH (or --file - for stdin).")
    if file is not None:
        return transcript_from_file(file, plain_text=plain_text, language=language)
    if data is not None:
        return _document_from_json(load_json(data, what="transcript"))
    raise UsageError("Provide a transcript with --file PATH or --data JSON|@file|-.")


def media_init_body(
    content_type: str,
    *,
    recording_id: str | None = None,
    transcript_file: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"contentType": _check_media_type(content_type)}
    if recording_id:
        body["recordingId"] = recording_id
    if transcript_file is not None:
        # This transcript is synced to real playback media, so only measured
        # timestamps make sense: there is no plain-text conversion on this path.
        label = "stdin" if transcript_file == "-" else transcript_file
        document = transcript_from_json_text(
            _read_text(transcript_file), label=label, hint=MEDIA_TRANSCRIPT_HINT
        )
        body["transcript"] = document["transcript"]
    return body


def _upload_policy(init_response: Any) -> tuple[str, str, dict[str, str]]:
    """Extract ``(recordingId, url, fields)`` from an InitRecordingMediaResponse."""
    data = init_response.get("data") if isinstance(init_response, dict) else None
    upload = data.get("upload") if isinstance(data, dict) else None
    if (
        not isinstance(upload, dict)
        or not isinstance(upload.get("url"), str)
        or not isinstance(upload.get("fields"), dict)
        or not isinstance(data.get("recordingId"), str)
    ):
        raise ClarifyError(
            "Unexpected response from the media upload init: missing data.recordingId or "
            "data.upload.{url,fields}."
        )
    return data["recordingId"], upload["url"], {k: str(v) for k, v in upload["fields"].items()}


def post_to_storage(
    state: AppState, url: str, fields: dict[str, str], path: Path, content_type: str
) -> None:
    """Submit the presigned S3 POST policy: every returned field, then the file last.

    This goes to the storage host with a plain httpx client, so the API key is
    never sent along.
    """
    try:
        with path.open("rb") as handle, httpx.Client(timeout=state.timeout) as http:
            response = http.post(
                url, data=fields, files={"file": (path.name, handle, content_type)}
            )
    except OSError as exc:
        raise UsageError(f"Cannot read {path}: {exc}") from exc
    except httpx.HTTPError as exc:
        raise ClarifyError(f"Media upload to {url} failed: {exc}") from exc
    if state.verbose:
        err_console.print(f"[dim]POST {response.url} → {response.status_code}[/]")
    if response.is_error:
        snippet = response.text.strip()[:500]
        message = f"HTTP {response.status_code} from POST {url} (storage upload)"
        if snippet:
            message += f"\n  {snippet}"
        raise ClarifyError(
            message,
            hint="The presigned policy may have expired or the file may not match "
            "--content-type. Re-run to start a fresh upload.",
        )


# -- commands ----------------------------------------------------------------


@app.command("enable-recording")
def enable_recording(ctx: typer.Context, meeting_id: MeetingArg) -> None:
    """Enable recording so the notetaker joins the call (POST /meetings/{meetingId}/recording).

    Returns the updated meeting record.

    Example:

        clarify meetings enable-recording 6c8e0a2b-4d5f-4a7b-9c1d-3e5f7a9b1c2d
    """
    state = get_state(ctx)
    result = state.client().post(f"/meetings/{meeting_id}/recording", silent=state.silent)
    _emit_result(state, result, f"Recording enabled for meeting {meeting_id}.")


@app.command("disable-recording")
def disable_recording(ctx: typer.Context, meeting_id: MeetingArg) -> None:
    """Disable recording so no notetaker joins (DELETE /meetings/{meetingId}/recording).

    Asks for confirmation unless --yes is given. Returns the updated meeting record.

    Example:

        clarify --yes meetings disable-recording 6c8e0a2b-4d5f-4a7b-9c1d-3e5f7a9b1c2d
    """
    state = get_state(ctx)
    state.confirm(f"Disable recording for meeting {meeting_id}?")
    result = state.client().delete(f"/meetings/{meeting_id}/recording", silent=state.silent)
    _emit_result(state, result, f"Recording disabled for meeting {meeting_id}.")


@app.command()
def artifacts(ctx: typer.Context, meeting_id: MeetingArg, recording_id: RecordingArg) -> None:
    """Get signed video/transcript URLs (POST /meetings/{meetingId}/recordings/{id}/artifacts).

    The URLs are short-lived; either is null when that artifact does not exist.

    Example:

        clarify meetings artifacts MEETING RECORDING | jq -r .data.transcriptionUrl
    """
    state = get_state(ctx)
    result = state.client().post(
        f"/meetings/{meeting_id}/recordings/{recording_id}/artifacts", silent=state.silent
    )
    _emit_result(state, result, f"No artifacts returned for recording {recording_id}.")


@app.command("upload-transcript")
def upload_transcript(
    ctx: typer.Context,
    meeting_id: MeetingArg,
    file: TranscriptFileOpt = None,
    data: DataOpt = None,
    plain_text: PlainTextOpt = False,
    language: LanguageOpt = "en",
) -> None:
    """Create a recording from an external transcript (POST /meetings/{meetingId}/transcript).

    The transcript is an ordered list of speaker segments with timed words (see
    UploadTranscriptDto), given as JSON via --file PATH (or -) or --data
    JSON|@file|-; it is sent through unchanged. A plain-text file (one utterance
    per line, optionally prefixed 'Speaker Name: ') needs --plain-text: the CLI
    then invents word timestamps at 0.4 s per word, sets each word's language to
    null and the segment language to --language. Use that only when there is no
    media for the timeline to line up with.

    Examples:

        clarify meetings upload-transcript MEETING --file call.json
        clarify meetings upload-transcript MEETING --file notes.txt --plain-text --language fr
    """
    state = get_state(ctx)
    body = transcript_body(file=file, data=data, plain_text=plain_text, language=language)
    result = state.client().post(
        f"/meetings/{meeting_id}/transcript", json_body=body, silent=state.silent
    )
    _emit_result(state, result, f"Transcript uploaded for meeting {meeting_id}.")


@app.command("upload-recording-transcript")
def upload_recording_transcript(
    ctx: typer.Context,
    meeting_id: MeetingArg,
    file: TranscriptFileOpt = None,
    data: DataOpt = None,
    recording_id: RecordingIdOpt = None,
    plain_text: PlainTextOpt = False,
    language: LanguageOpt = "en",
) -> None:
    """Upload a transcript as a recording (POST /meetings/{meetingId}/recordings/transcript).

    Creates a second recording when the meeting already has one; pass
    --recording-id to overwrite a completed manual-upload recording's transcript
    instead. Accepts the same --file/--data/--plain-text inputs as
    upload-transcript and triggers summary generation.

    Example:

        clarify meetings upload-recording-transcript MEETING -F call.json --recording-id REC
    """
    state = get_state(ctx)
    body = transcript_body(file=file, data=data, plain_text=plain_text, language=language)
    if recording_id:
        body["recordingId"] = recording_id
    result = state.client().post(
        f"/meetings/{meeting_id}/recordings/transcript", json_body=body, silent=state.silent
    )
    _emit_result(state, result, f"Recording transcript uploaded for meeting {meeting_id}.")


@app.command("init-media-upload")
def init_media_upload(
    ctx: typer.Context,
    meeting_id: MeetingArg,
    content_type: Annotated[
        str,
        typer.Option("--content-type", help="MIME type of the media file: audio/* or video/*."),
    ],
    recording_id: RecordingIdOpt = None,
    transcript_file: MediaTranscriptFileOpt = None,
) -> None:
    """Start a media upload and get an S3 POST policy (POST /meetings/{meetingId}/recordings/media).

    Creates a pending recording and returns data.recordingId plus
    data.upload.{url,fields}: submit the file as a multipart POST with every
    field as returned and the file last, then run confirm-media-upload. Media is
    stored for playback, not transcribed; add --transcript-file with a JSON
    transcript whose word timestamps match the media to attach one (plain text
    is refused here because its timing would be invented). `upload-media` does
    all three steps in one go.

    Example:

        clarify meetings init-media-upload MEETING --content-type video/mp4
    """
    state = get_state(ctx)
    body = media_init_body(content_type, recording_id=recording_id, transcript_file=transcript_file)
    result = state.client().post(
        f"/meetings/{meeting_id}/recordings/media", json_body=body, silent=state.silent
    )
    _emit_result(state, result, f"Media upload started for meeting {meeting_id}.")


@app.command("confirm-media-upload")
def confirm_media_upload(
    ctx: typer.Context, meeting_id: MeetingArg, recording_id: RecordingArg
) -> None:
    """Finalize an uploaded media file (POST /meetings/{meetingId}/recordings/media/{recordingId}).

    Validates the stored object and marks the recording complete. Returns the recording.

    Example:

        clarify meetings confirm-media-upload MEETING RECORDING
    """
    state = get_state(ctx)
    result = state.client().post(
        f"/meetings/{meeting_id}/recordings/media/{recording_id}", silent=state.silent
    )
    _emit_result(state, result, f"Media upload confirmed for recording {recording_id}.")


@app.command("upload-media")
def upload_media(
    ctx: typer.Context,
    meeting_id: MeetingArg,
    file: Annotated[
        Path,
        typer.Argument(
            exists=True, dir_okay=False, readable=True, help="Audio or video file.", metavar="FILE"
        ),
    ],
    content_type: Annotated[
        str | None,
        typer.Option(
            "--content-type", help="MIME type (audio/* or video/*); guessed from FILE by default."
        ),
    ] = None,
    recording_id: RecordingIdOpt = None,
) -> None:
    """Upload a media file: init, S3 POST, confirm (POST .../recordings/media then .../media/{id}).

    Convenience for init-media-upload -> multipart POST to the presigned policy
    -> confirm-media-upload. The file goes straight to storage, never through the
    Clarify API. Prints the finalized recording.

    Example:

        clarify meetings upload-media MEETING call.mp4
    """
    state = get_state(ctx)
    media_type = content_type or mimetypes.guess_type(file.name)[0]
    if not media_type:
        raise UsageError(
            f"Cannot infer the media type of {file.name}; pass --content-type audio/* or video/*."
        )
    body = media_init_body(media_type, recording_id=recording_id)
    client = state.client()
    init = client.post(
        f"/meetings/{meeting_id}/recordings/media", json_body=body, silent=state.silent
    )
    new_recording_id, url, fields = _upload_policy(init)
    post_to_storage(state, url, fields, file, media_type)
    emit_message(
        f"Uploaded {file.name} ({file.stat().st_size} bytes) for recording {new_recording_id}; "
        "confirming."
    )
    result = client.post(
        f"/meetings/{meeting_id}/recordings/media/{new_recording_id}", silent=state.silent
    )
    _emit_result(state, result, f"Media upload confirmed for recording {new_recording_id}.")
