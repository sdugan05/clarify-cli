from __future__ import annotations

import json

import httpx
import pytest
import respx

from helpers import json_body, query_pairs, resource

MEETING = "6c8e0a2b-4d5f-4a7b-9c1d-3e5f7a9b1c2d"
RECORDING = "2f7a9c1e-4b6d-4e8a-9c0f-1d3b5e7a9c62"
WS = "/workspaces/acme"
#: Captured requests carry the base URL's /v1 prefix in their path.
API = f"/v1{WS}"
STORAGE = "https://storage.clarify.ai"
UPLOAD_URL = f"{STORAGE}/meeting-recordings"
KEY = f"acme/manual/2026-02-01/{RECORDING}/recording-7e71a013.mp4"

SEGMENTS = [
    {
        "speaker": "Jane Doe",
        "speaker_id": 1,
        "language": "en",
        "words": [
            {
                "text": "Thanks",
                "start_timestamp": 0,
                "end_timestamp": 0.4,
                "language": "en",
                "confidence": 0.98,
            }
        ],
    }
]

PLAIN_TEXT = """Jane Doe: Thanks everyone
Bob: Hi

Jane Doe: Let's begin
Unattributed line
"""


#: A word built from plain text: synthetic timing, no detected language, no confidence.
def _word(text: str, start: float, end: float, language: str | None = None) -> dict:
    return {
        "text": text,
        "start_timestamp": start,
        "end_timestamp": end,
        "language": language,
        "confidence": None,
    }


PLAIN_TEXT_SEGMENTS = [
    {
        "speaker": "Jane Doe",
        "speaker_id": 1,
        "language": "en",
        "words": [_word("Thanks", 0.0, 0.4), _word("everyone", 0.4, 0.8)],
    },
    {"speaker": "Bob", "speaker_id": 2, "language": "en", "words": [_word("Hi", 0.8, 1.2)]},
    {
        "speaker": "Jane Doe",
        "speaker_id": 1,
        "language": "en",
        "words": [_word("Let's", 1.2, 1.6), _word("begin", 1.6, 2.0)],
    },
    {
        "speaker": None,
        "speaker_id": None,
        "language": "en",
        "words": [_word("Unattributed", 2.0, 2.4), _word("line", 2.4, 2.8)],
    },
]


def meeting_doc(recording_enabled: bool) -> dict:
    return {
        "data": resource(
            "meeting", MEETING, title="Acme Renewal QBR", recording_enabled=recording_enabled
        )
    }


def recording_doc() -> dict:
    return {
        "data": resource(
            "meeting_recording",
            RECORDING,
            meeting_id=MEETING,
            recording_source="manual_upload",
            status="Done",
        )
    }


def init_doc() -> dict:
    return {
        "data": {
            "recordingId": RECORDING,
            "meetingId": MEETING,
            "key": KEY,
            "upload": {
                "url": UPLOAD_URL,
                "fields": {
                    "key": KEY,
                    "Content-Type": "video/mp4",
                    "policy": "POLICY-BLOB",
                    "x-amz-signature": "SIG",
                },
            },
        }
    }


@pytest.fixture
def s3():
    """A second respx router for the storage host the presigned policy points at."""
    with respx.mock(base_url=STORAGE, assert_all_called=False, assert_all_mocked=True) as router:
        yield router


# -- enable / disable recording ---------------------------------------------


def test_enable_recording(invoke, api):
    route = api.post(f"{WS}/meetings/{MEETING}/recording").mock(
        return_value=httpx.Response(201, json=meeting_doc(True))
    )
    result = invoke("meetings", "enable-recording", MEETING)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["attributes"]["recording_enabled"] is True
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"{API}/meetings/{MEETING}/recording"
    assert query_pairs(request) == []
    assert request.content == b""


def test_enable_recording_silent(invoke, api):
    route = api.post(f"{WS}/meetings/{MEETING}/recording").mock(
        return_value=httpx.Response(201, json=meeting_doc(True))
    )
    result = invoke("--silent", "meetings", "enable-recording", MEETING)
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [("silent", "true")]


def test_disable_recording_refuses_without_confirmation(invoke, api):
    route = api.delete(f"{WS}/meetings/{MEETING}/recording").mock(
        return_value=httpx.Response(200, json=meeting_doc(False))
    )
    result = invoke("meetings", "disable-recording", MEETING)
    assert result.exit_code == 2
    assert "Refusing to continue without confirmation" in result.stderr
    assert not route.called


def test_disable_recording_with_yes(invoke, api):
    route = api.delete(f"{WS}/meetings/{MEETING}/recording").mock(
        return_value=httpx.Response(200, json=meeting_doc(False))
    )
    result = invoke("--yes", "--silent", "meetings", "disable-recording", MEETING)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["attributes"]["recording_enabled"] is False
    request = route.calls.last.request
    assert request.method == "DELETE"
    assert request.url.path == f"{API}/meetings/{MEETING}/recording"
    assert query_pairs(request) == [("silent", "true")]


def test_disable_recording_empty_body_confirms_on_stderr(invoke, api):
    api.delete(f"{WS}/meetings/{MEETING}/recording").mock(return_value=httpx.Response(204))
    result = invoke("-y", "meetings", "disable-recording", MEETING)
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert f"Recording disabled for meeting {MEETING}" in result.stderr


def test_disable_recording_not_found_exit_4(invoke, api):
    api.delete(f"{WS}/meetings/{MEETING}/recording").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Meeting not found"}]}
        )
    )
    result = invoke("-y", "meetings", "disable-recording", MEETING)
    assert result.exit_code == 4
    assert "Meeting not found" in result.stderr


# -- artifacts ----------------------------------------------------------------


def test_artifacts(invoke, api):
    payload = {"data": {"videoUrl": "https://s/video.mp4?sig=1", "transcriptionUrl": None}}
    route = api.post(f"{WS}/meetings/{MEETING}/recordings/{RECORDING}/artifacts").mock(
        return_value=httpx.Response(201, json=payload)
    )
    result = invoke("meetings", "artifacts", MEETING, RECORDING)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == payload
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"{API}/meetings/{MEETING}/recordings/{RECORDING}/artifacts"
    assert query_pairs(request) == []
    assert request.content == b""


def test_artifacts_not_found_exit_4(invoke, api):
    api.post(f"{WS}/meetings/{MEETING}/recordings/nope/artifacts").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Recording not found"}]}
        )
    )
    result = invoke("meetings", "artifacts", MEETING, "nope")
    assert result.exit_code == 4


# -- upload-transcript ----------------------------------------------------------


def test_upload_transcript_json_array_file(invoke, api, tmp_path):
    path = tmp_path / "call.json"
    path.write_text(json.dumps(SEGMENTS))
    route = api.post(f"{WS}/meetings/{MEETING}/transcript").mock(
        return_value=httpx.Response(201, json=recording_doc())
    )
    result = invoke("meetings", "upload-transcript", MEETING, "--file", str(path))
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["id"] == RECORDING
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"{API}/meetings/{MEETING}/transcript"
    assert query_pairs(request) == []
    assert json_body(request) == {"transcript": SEGMENTS}


def test_upload_transcript_json_object_file(invoke, api, tmp_path):
    path = tmp_path / "call.JSON"
    path.write_text(json.dumps({"transcript": SEGMENTS}))
    route = api.post(f"{WS}/meetings/{MEETING}/transcript").mock(
        return_value=httpx.Response(201, json=recording_doc())
    )
    result = invoke("--silent", "meetings", "upload-transcript", MEETING, "-F", str(path))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {"transcript": SEGMENTS}
    assert query_pairs(route.calls.last.request) == [("silent", "true")]


def test_upload_transcript_plain_text_file(invoke, api, tmp_path):
    path = tmp_path / "call.txt"
    path.write_text(PLAIN_TEXT)
    route = api.post(f"{WS}/meetings/{MEETING}/transcript").mock(
        return_value=httpx.Response(201, json=recording_doc())
    )
    result = invoke("meetings", "upload-transcript", MEETING, "--file", str(path), "--plain-text")
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"{API}/meetings/{MEETING}/transcript"
    assert json_body(request) == {"transcript": PLAIN_TEXT_SEGMENTS}


def test_upload_transcript_plain_text_stdin_with_language(invoke, api):
    route = api.post(f"{WS}/meetings/{MEETING}/transcript").mock(
        return_value=httpx.Response(201, json=recording_doc())
    )
    result = invoke(
        "meetings",
        "upload-transcript",
        MEETING,
        "--file",
        "-",
        "--plain-text",
        "--language",
        "fr",
        input="Bonjour\n",
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "transcript": [
            {
                "speaker": None,
                "speaker_id": None,
                "language": "fr",
                "words": [_word("Bonjour", 0.0, 0.4)],
            }
        ]
    }


def test_upload_transcript_json_on_stdin_is_sent_unchanged(invoke, api):
    route = api.post(f"{WS}/meetings/{MEETING}/transcript").mock(
        return_value=httpx.Response(201, json=recording_doc())
    )
    result = invoke(
        "meetings",
        "upload-transcript",
        MEETING,
        "--file",
        "-",
        input=json.dumps({"transcript": SEGMENTS}),
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {"transcript": SEGMENTS}


def test_upload_transcript_json_in_txt_file_is_sent_unchanged(invoke, api, tmp_path):
    path = tmp_path / "call.txt"
    path.write_text(json.dumps(SEGMENTS))
    route = api.post(f"{WS}/meetings/{MEETING}/transcript").mock(
        return_value=httpx.Response(201, json=recording_doc())
    )
    result = invoke("meetings", "upload-transcript", MEETING, "--file", str(path))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {"transcript": SEGMENTS}


def test_upload_transcript_text_without_plain_text_flag_is_usage_error(invoke, api, tmp_path):
    path = tmp_path / "call.txt"
    path.write_text(PLAIN_TEXT)
    route = api.post(f"{WS}/meetings/{MEETING}/transcript").mock(
        return_value=httpx.Response(201, json=recording_doc())
    )
    result = invoke("meetings", "upload-transcript", MEETING, "--file", str(path))
    assert result.exit_code == 2
    assert "Invalid JSON" in result.stderr and "--plain-text" in result.stderr
    assert not route.called


def test_upload_transcript_plain_text_refuses_json_document(invoke, api, tmp_path):
    path = tmp_path / "call.json"
    path.write_text(json.dumps({"transcript": SEGMENTS}))
    route = api.post(f"{WS}/meetings/{MEETING}/transcript").mock(
        return_value=httpx.Response(201, json=recording_doc())
    )
    result = invoke("meetings", "upload-transcript", MEETING, "--file", str(path), "--plain-text")
    assert result.exit_code == 2
    assert "JSON document" in result.stderr and "Drop --plain-text" in result.stderr
    assert not route.called


def test_upload_transcript_data_inline_and_stdin(invoke, api):
    route = api.post(f"{WS}/meetings/{MEETING}/transcript").mock(
        return_value=httpx.Response(201, json=recording_doc())
    )
    result = invoke("meetings", "upload-transcript", MEETING, "--data", json.dumps(SEGMENTS))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {"transcript": SEGMENTS}

    result = invoke(
        "meetings",
        "upload-transcript",
        MEETING,
        "-d",
        "-",
        input=json.dumps({"transcript": SEGMENTS}),
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {"transcript": SEGMENTS}
    assert route.call_count == 2


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ([], "Provide a transcript"),
        (["--data", "[]", "--file", "x.txt"], "not both"),
        (["--data", "{not json"], "Invalid JSON"),
        (["--data", '{"nope": 1}'], "array of segments"),
        (["--file", "missing.txt"], "Cannot read"),
        (["--plain-text"], "--plain-text requires --file"),
        (["--data", "[]", "--plain-text"], "--plain-text requires --file"),
    ],
)
def test_upload_transcript_usage_errors(invoke, api, args, message):
    route = api.post(f"{WS}/meetings/{MEETING}/transcript").mock(
        return_value=httpx.Response(201, json=recording_doc())
    )
    result = invoke("meetings", "upload-transcript", MEETING, *args)
    assert result.exit_code == 2, result.output
    assert message in result.stderr
    assert not route.called


def test_upload_transcript_empty_text_is_usage_error(invoke, api, tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("\n\n")
    result = invoke("meetings", "upload-transcript", MEETING, "--file", str(path), "--plain-text")
    assert result.exit_code == 2
    assert "empty" in result.stderr


def test_upload_transcript_invalid_json_file(invoke, api, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{oops")
    result = invoke("meetings", "upload-transcript", MEETING, "--file", str(path))
    assert result.exit_code == 2
    assert "Invalid JSON" in result.stderr and "--plain-text" in result.stderr


def test_upload_transcript_api_error_exit_1(invoke, api):
    api.post(f"{WS}/meetings/{MEETING}/transcript").mock(
        return_value=httpx.Response(
            422,
            json={
                "errors": [
                    {
                        "status": "422",
                        "detail": "transcript must be an array",
                        "source": {"pointer": "/transcript"},
                    }
                ]
            },
        )
    )
    result = invoke("meetings", "upload-transcript", MEETING, "--data", "[]")
    assert result.exit_code == 1
    assert "HTTP 422" in result.stderr and "/transcript" in result.stderr


# -- upload-recording-transcript ---------------------------------------------


def test_upload_recording_transcript(invoke, api, tmp_path):
    path = tmp_path / "call.json"
    path.write_text(json.dumps(SEGMENTS))
    route = api.post(f"{WS}/meetings/{MEETING}/recordings/transcript").mock(
        return_value=httpx.Response(201, json=recording_doc())
    )
    result = invoke("meetings", "upload-recording-transcript", MEETING, "--file", str(path))
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"{API}/meetings/{MEETING}/recordings/transcript"
    assert query_pairs(request) == []
    assert json_body(request) == {"transcript": SEGMENTS}


def test_upload_recording_transcript_with_recording_id(invoke, api):
    route = api.post(f"{WS}/meetings/{MEETING}/recordings/transcript").mock(
        return_value=httpx.Response(201, json=recording_doc())
    )
    result = invoke(
        "--silent",
        "meetings",
        "upload-recording-transcript",
        MEETING,
        "--data",
        json.dumps(SEGMENTS),
        "--recording-id",
        RECORDING,
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {"transcript": SEGMENTS, "recordingId": RECORDING}
    assert query_pairs(route.calls.last.request) == [("silent", "true")]


def test_upload_recording_transcript_plain_text(invoke, api, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text(PLAIN_TEXT)
    route = api.post(f"{WS}/meetings/{MEETING}/recordings/transcript").mock(
        return_value=httpx.Response(201, json=recording_doc())
    )
    result = invoke(
        "meetings",
        "upload-recording-transcript",
        MEETING,
        "--file",
        str(path),
        "--plain-text",
        "--recording-id",
        RECORDING,
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "transcript": PLAIN_TEXT_SEGMENTS,
        "recordingId": RECORDING,
    }


def test_upload_recording_transcript_requires_source(invoke, api):
    result = invoke("meetings", "upload-recording-transcript", MEETING)
    assert result.exit_code == 2
    assert "Provide a transcript" in result.stderr


# -- init-media-upload ----------------------------------------------------------


def test_init_media_upload(invoke, api):
    route = api.post(f"{WS}/meetings/{MEETING}/recordings/media").mock(
        return_value=httpx.Response(201, json=init_doc())
    )
    result = invoke("meetings", "init-media-upload", MEETING, "--content-type", "video/mp4")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["upload"]["url"] == UPLOAD_URL
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"{API}/meetings/{MEETING}/recordings/media"
    assert query_pairs(request) == []
    assert json_body(request) == {"contentType": "video/mp4"}


def test_init_media_upload_with_recording_and_transcript(invoke, api, tmp_path):
    path = tmp_path / "call.json"
    path.write_text(json.dumps({"transcript": SEGMENTS}))
    route = api.post(f"{WS}/meetings/{MEETING}/recordings/media").mock(
        return_value=httpx.Response(201, json=init_doc())
    )
    result = invoke(
        "--silent",
        "meetings",
        "init-media-upload",
        MEETING,
        "--content-type",
        "audio/mpeg",
        "--recording-id",
        RECORDING,
        "--transcript-file",
        str(path),
    )
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [("silent", "true")]
    assert json_body(route.calls.last.request) == {
        "contentType": "audio/mpeg",
        "recordingId": RECORDING,
        "transcript": SEGMENTS,
    }


def test_init_media_upload_transcript_from_stdin(invoke, api):
    route = api.post(f"{WS}/meetings/{MEETING}/recordings/media").mock(
        return_value=httpx.Response(201, json=init_doc())
    )
    result = invoke(
        "meetings",
        "init-media-upload",
        MEETING,
        "--content-type",
        "video/mp4",
        "--transcript-file",
        "-",
        input=json.dumps(SEGMENTS),
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "contentType": "video/mp4",
        "transcript": SEGMENTS,
    }


def test_init_media_upload_refuses_plain_text_transcript(invoke, api, tmp_path):
    """Synthetic timestamps would be out of sync with real media, so text is rejected."""
    path = tmp_path / "call.txt"
    path.write_text("Bob: Hi\n")
    route = api.post(f"{WS}/meetings/{MEETING}/recordings/media").mock(
        return_value=httpx.Response(201, json=init_doc())
    )
    result = invoke(
        "meetings",
        "init-media-upload",
        MEETING,
        "--content-type",
        "audio/mpeg",
        "--transcript-file",
        str(path),
    )
    assert result.exit_code == 2
    assert "Invalid JSON" in result.stderr and "real word timestamps" in result.stderr
    assert not route.called


def test_init_media_upload_has_no_plain_text_options(invoke, api):
    route = api.post(f"{WS}/meetings/{MEETING}/recordings/media").mock(
        return_value=httpx.Response(201, json=init_doc())
    )
    for extra in (["--plain-text"], ["--language", "en"]):
        result = invoke(
            "meetings", "init-media-upload", MEETING, "--content-type", "video/mp4", *extra
        )
        assert result.exit_code == 2, extra
    assert not route.called


def test_init_media_upload_rejects_non_media_type(invoke, api):
    route = api.post(f"{WS}/meetings/{MEETING}/recordings/media").mock(
        return_value=httpx.Response(201, json=init_doc())
    )
    result = invoke("meetings", "init-media-upload", MEETING, "--content-type", "text/plain")
    assert result.exit_code == 2
    assert "audio/* or video/*" in result.stderr
    assert not route.called


def test_init_media_upload_requires_content_type(invoke):
    result = invoke("meetings", "init-media-upload", MEETING)
    assert result.exit_code == 2


# -- confirm-media-upload -------------------------------------------------------


def test_confirm_media_upload(invoke, api):
    route = api.post(f"{WS}/meetings/{MEETING}/recordings/media/{RECORDING}").mock(
        return_value=httpx.Response(200, json=recording_doc())
    )
    result = invoke("--silent", "meetings", "confirm-media-upload", MEETING, RECORDING)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["attributes"]["status"] == "Done"
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"{API}/meetings/{MEETING}/recordings/media/{RECORDING}"
    assert query_pairs(request) == [("silent", "true")]
    assert request.content == b""


def test_confirm_media_upload_error_exit_1(invoke, api):
    api.post(f"{WS}/meetings/{MEETING}/recordings/media/{RECORDING}").mock(
        return_value=httpx.Response(
            400, json={"errors": [{"status": "400", "detail": "Object not found in storage"}]}
        )
    )
    result = invoke("meetings", "confirm-media-upload", MEETING, RECORDING)
    assert result.exit_code == 1
    assert "Object not found in storage" in result.stderr


# -- upload-media (convenience) ---------------------------------------------------


def test_upload_media_flow(invoke, api, s3, tmp_path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"FAKE MP4 BYTES")
    order: list[str] = []

    def record(label: str, response: httpx.Response):
        def side_effect(request: httpx.Request) -> httpx.Response:
            order.append(label)
            return response

        return side_effect

    init_route = api.post(f"{WS}/meetings/{MEETING}/recordings/media").mock(
        side_effect=record("init", httpx.Response(201, json=init_doc()))
    )
    s3_route = s3.post("/meeting-recordings").mock(side_effect=record("s3", httpx.Response(204)))
    confirm_route = api.post(f"{WS}/meetings/{MEETING}/recordings/media/{RECORDING}").mock(
        side_effect=record("confirm", httpx.Response(200, json=recording_doc()))
    )

    result = invoke("--silent", "meetings", "upload-media", MEETING, str(media))
    assert result.exit_code == 0, result.output
    assert order == ["init", "s3", "confirm"]
    assert json.loads(result.stdout) == recording_doc()
    assert "Uploaded clip.mp4 (14 bytes)" in result.stderr

    init_request = init_route.calls.last.request
    assert json_body(init_request) == {"contentType": "video/mp4"}
    assert query_pairs(init_request) == [("silent", "true")]

    upload = s3_route.calls.last.request
    assert upload.method == "POST"
    assert str(upload.url) == UPLOAD_URL
    assert "authorization" not in upload.headers
    assert upload.headers["content-type"].startswith("multipart/form-data; boundary=")
    body = upload.content
    assert f'name="key"\r\n\r\n{KEY}'.encode() in body
    assert b'name="Content-Type"\r\n\r\nvideo/mp4' in body
    assert b'name="policy"\r\n\r\nPOLICY-BLOB' in body
    assert b'name="x-amz-signature"\r\n\r\nSIG' in body
    file_part = b'name="file"; filename="clip.mp4"\r\nContent-Type: video/mp4\r\n\r\nFAKE MP4 BYTES'
    assert file_part in body
    # S3 POST policies ignore everything after the file part, so it must come last.
    assert body.index(b'name="file"') > body.index(b'name="x-amz-signature"')

    confirm_request = confirm_route.calls.last.request
    assert confirm_request.content == b""
    assert query_pairs(confirm_request) == [("silent", "true")]


def test_upload_media_content_type_override_and_recording_id(invoke, api, s3, tmp_path):
    media = tmp_path / "clip.bin"
    media.write_bytes(b"x")
    init_route = api.post(f"{WS}/meetings/{MEETING}/recordings/media").mock(
        return_value=httpx.Response(201, json=init_doc())
    )
    s3_route = s3.post("/meeting-recordings").mock(return_value=httpx.Response(204))
    api.post(f"{WS}/meetings/{MEETING}/recordings/media/{RECORDING}").mock(
        return_value=httpx.Response(200, json=recording_doc())
    )
    result = invoke(
        "meetings",
        "upload-media",
        MEETING,
        str(media),
        "--content-type",
        "audio/wav",
        "--recording-id",
        RECORDING,
    )
    assert result.exit_code == 0, result.output
    assert json_body(init_route.calls.last.request) == {
        "contentType": "audio/wav",
        "recordingId": RECORDING,
    }
    assert b'filename="clip.bin"\r\nContent-Type: audio/wav' in s3_route.calls.last.request.content


def test_upload_media_unguessable_type_is_usage_error(invoke, api, tmp_path):
    media = tmp_path / "clip.unknownext"
    media.write_bytes(b"x")
    route = api.post(f"{WS}/meetings/{MEETING}/recordings/media").mock(
        return_value=httpx.Response(201, json=init_doc())
    )
    result = invoke("meetings", "upload-media", MEETING, str(media))
    assert result.exit_code == 2
    assert "--content-type" in result.stderr
    assert not route.called


def test_upload_media_non_media_file_is_usage_error(invoke, api, tmp_path):
    media = tmp_path / "notes.txt"
    media.write_text("hello")
    route = api.post(f"{WS}/meetings/{MEETING}/recordings/media").mock(
        return_value=httpx.Response(201, json=init_doc())
    )
    result = invoke("meetings", "upload-media", MEETING, str(media))
    assert result.exit_code == 2
    assert "audio/* or video/*" in result.stderr
    assert not route.called


def test_upload_media_missing_file_is_usage_error(invoke, api):
    result = invoke("meetings", "upload-media", MEETING, "/nonexistent/clip.mp4")
    assert result.exit_code == 2


def test_upload_media_storage_failure_exit_1_and_no_confirm(invoke, api, s3, tmp_path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"x")
    api.post(f"{WS}/meetings/{MEETING}/recordings/media").mock(
        return_value=httpx.Response(201, json=init_doc())
    )
    s3.post("/meeting-recordings").mock(
        return_value=httpx.Response(
            403, text="<Error><Code>AccessDenied</Code><Message>Policy expired</Message></Error>"
        )
    )
    confirm_route = api.post(f"{WS}/meetings/{MEETING}/recordings/media/{RECORDING}").mock(
        return_value=httpx.Response(200, json=recording_doc())
    )
    result = invoke("meetings", "upload-media", MEETING, str(media))
    assert result.exit_code == 1
    assert "HTTP 403" in result.stderr and "Policy expired" in result.stderr
    assert not confirm_route.called


def test_upload_media_init_failure_skips_storage(invoke, api, s3, tmp_path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"x")
    api.post(f"{WS}/meetings/{MEETING}/recordings/media").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Meeting not found"}]}
        )
    )
    s3_route = s3.post("/meeting-recordings").mock(return_value=httpx.Response(204))
    result = invoke("meetings", "upload-media", MEETING, str(media))
    assert result.exit_code == 4
    assert not s3_route.called


def test_upload_media_malformed_init_response(invoke, api, s3, tmp_path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"x")
    api.post(f"{WS}/meetings/{MEETING}/recordings/media").mock(
        return_value=httpx.Response(201, json={"data": {"recordingId": RECORDING}})
    )
    s3_route = s3.post("/meeting-recordings").mock(return_value=httpx.Response(204))
    result = invoke("meetings", "upload-media", MEETING, str(media))
    assert result.exit_code == 1
    assert "data.upload" in result.stderr
    assert not s3_route.called
