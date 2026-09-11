# clarify-cli design and conventions

This document is the contract every command module follows. Read it before
adding or changing a command. The API contract itself is Clarify's OpenAPI 3.1
spec at <https://api.clarify.ai/swagger-json>; the docs live at
<https://developer.clarify.ai/docs>.

## Goals

- Cover every operation in the OpenAPI spec with an explicit, discoverable
  subcommand, plus a raw `clarify api` escape hatch.
- Be script-friendly: JSON by default when piped, stable output shapes,
  meaningful exit codes, no interactive prompts unless stdout is a TTY.
- Be human-friendly: tables when interactive, helpful `--help`, sensible
  defaults, confirmation before destructive actions.
- Stay thin. The CLI does not re-model Clarify's schemas; it passes JSON:API
  documents through and adds ergonomics (filters, paging, `--set`, files).

## Layout

```
src/clarify_cli/
  __init__.py        version
  main.py            root Typer app, global options, group registration
  state.py           AppState on ctx.obj; get_state(); lazy client; confirm()
  config.py          config file (TOML), env vars, precedence, Settings
  client.py          ClarifyClient: auth header, retries, errors, pagination
  errors.py          ClarifyError hierarchy + exit codes
  output.py          emit(): json | table | ndjson | csv
  params.py          --filter/--sort/--page parsing; collect_list() helper
  inputs.py          --data/@file/stdin, --set KEY=VALUE, record files
  cli_options.py     shared Annotated option types (LimitOpt, FilterOpt, ...)
  console.py         rich consoles (stdout, stderr)
  commands/
    __init__.py      GROUPS: (cli name, module, help) registration list
    <group>.py       one module per command group; exposes `app = typer.Typer()`
tests/
  conftest.py        isolated env, respx router, CliRunner helpers
  test_<group>.py    one test module per command module
```

Each command module owns exactly one file under `commands/` and one test file
under `tests/`. Modules never import from each other; shared behaviour lives in
the core modules listed above.

Every command module declares `OPERATIONS: dict[str, str]` mapping each OpenAPI
`operationId` it implements to the CLI command name (for example
`{"getUsers": "list", "getUser": "get"}`). Convenience commands that are not a
single operation (such as `attachments upload`) are not listed. A test checks
that the union of all manifests covers every operation in the spec.

## Naming

- Package `clarify_cli`, distribution `clarify-cli`, executable `clarify`.
- Groups are nouns (`records`, `lists`, `schemas`); commands are verbs
  (`list`, `get`, `create`, `update`, `delete`) or short verb phrases
  (`bulk-create`, `export-csv`, `enable-recording`). Use kebab-case.
- Positional arguments in this order: OBJECT, then IDs, then the rest.
  `OBJECT` is the object type (`person`, `company`, `deal`, `c_*`).
- Option names are shared across groups (see `cli_options.py`). Never invent a
  new spelling for an existing concept.

## Global options (root callback, available before the group name)

| Option | Env | Meaning |
| --- | --- | --- |
| `-w, --workspace SLUG` | `CLARIFY_WORKSPACE` | workspace slug |
| `--api-key KEY` | `CLARIFY_API_KEY` | API key (prefer env or config) |
| `-p, --profile NAME` | `CLARIFY_PROFILE` | config profile |
| `--base-url URL` | `CLARIFY_BASE_URL` | default `https://api.clarify.ai/v1` |
| `-o, --output FMT` | | `json` (default when piped), `table` (default on a TTY), `ndjson`, `csv` |
| `--fields a,b,c` | | columns for `table`/`csv`; dotted paths allowed |
| `--silent` | | add `silent=true` to mutations (suppresses in-app/Slack notifications) |
| `-y, --yes` | | skip confirmation prompts |
| `-v, --verbose` | | log each request line to stderr |
| `--debug` | | also log request/response bodies |
| `--timeout SECONDS` | | HTTP timeout (default 30) |

Precedence for settings: flag > environment > config profile > default.

## Config file

`$XDG_CONFIG_HOME/clarify/config.toml` (default `~/.config/clarify/config.toml`;
`%APPDATA%\clarify\config.toml` on Windows; override with `CLARIFY_CONFIG`).
Written with mode 0600.

```toml
default_profile = "default"

[profiles.default]
workspace = "acme"
api_key = "..."
base_url = "https://api.clarify.ai/v1"
```

## HTTP client (`client.py`)

- `Authorization: api-key <key>` (not Bearer). `User-Agent: clarify-cli/<v>`.
- Paths passed to the client are workspace-relative (`/objects/person/resources`).
  Paths starting with `/workspaces/` or a full URL pass through unchanged, so
  `links.next` URLs can be fetched verbatim as the docs require.
- Query params are `list[tuple[str, str]]`. Bracketed keys
  (`filter[amount][Greater than]`, `page[limit]`, `sortOrder[column]`) are
  passed as-is; httpx percent-encodes them and the API decodes them.
- Retries: `429` always (honour `Retry-After`, else exponential backoff);
  `502/503/504` only for GET. Max 3 retries. Nothing else is retried.
- Any 4xx/5xx raises `APIError` carrying the JSON:API `errors` array.
- `client.get/post/patch/put/delete(path, params=, json_body=, silent=)`
  return the parsed JSON body, `None` for empty bodies, or text for non-JSON.
- `client.collect(path, params, limit=, all_pages=, page_size=, offset=)`
  follows `links.next` and returns a merged envelope (see Output).

## Output (`output.py`)

- `emit(state, payload)` is the only way commands print results.
- `json`: the payload verbatim, indented, on stdout.
- `ndjson`: each item of `payload["data"]` (or the single resource) per line.
- `table` / `csv`: rows are flattened JSON:API resources:
  `id`, `type`, then `attributes` keys. Collection fields (`{"items": [...]}`)
  render as comma-joined values; other objects/arrays render as compact JSON.
  Default columns: `id` plus the first six non-underscore attributes; `--fields`
  overrides.
- List commands always emit `{"data": [...], "included": [...]?, "meta": {...}}`
  where `meta` has `total_records`/`total_pages` from the first page and
  `returned` (count of items emitted). `links` is dropped.
- Mutations emit the response body. If the API returns no body (202/204),
  print a one-line confirmation to **stderr** so stdout stays clean.
- Never print secrets. `auth status` masks keys (`bbb9…0086`).

## List command conventions

Every list-style command accepts:

- `-n, --limit N` (default 50) total items to return; `--all` fetches every page.
- `--offset N` starting offset; `--page-size N` sets `page[limit]` per request
  (default `min(limit, 500)`; the client never sends more than 500, the maximum
  several endpoints declare).
- `-s, --sort FIELD | FIELD:asc | FIELD:desc | -FIELD` → `sortOrder[...]`.
- `-f, --filter FIELD=VALUE` (repeatable). `FIELD[Operator]=VALUE` names an
  operator; the value may use the API's shorthand (`>100`, `*Smith*`, `null`,
  `a,b`). Sent as `filter[FIELD][Operator]=VALUE`.
- `-i, --include a,b` where the endpoint supports `include`.
- `--search TEXT` where the endpoint has a `search` query parameter.

Use `params.collect_list(state, path, ...)` so all list commands behave the
same; only add options the endpoint actually declares.

## Mutation conventions

- Body input, in priority order: `-d/--data JSON|@file|-` (full JSON:API body
  or the `attributes` object, per command help), `--set KEY=VALUE` (repeatable,
  dotted keys nest, values parse as JSON when possible so `amount=100` is a
  number and `name.first_name=Jane` is a string; quote for literal strings),
  and `--file PATH` for bulk records (JSON array, JSON `{"data": [...]}`,
  NDJSON, or CSV with a header row).
- Commands wrap plain attribute objects in `{"data": {"type": OBJECT,
  "attributes": ...}}`. If the user passes a document that already has a
  top-level `data` key, send it unchanged.
- Destructive commands (`delete`, `bulk-delete`, `merge`, `revoke`, `reset`,
  `delete-object`, ...) call `state.confirm("...")` first. `--yes` skips it.
  When stdin is not a TTY and `--yes` is absent, the command errors (exit 2)
  rather than hanging.
- Every mutation passes `silent=state.silent` to the client.

## Errors and exit codes

| Code | Meaning |
| --- | --- |
| 0 | success |
| 1 | API error (4xx/5xx not covered below) or generic failure |
| 2 | usage error (bad flags, invalid JSON, refused confirmation) |
| 3 | authentication / configuration problem (401, 403, missing key or workspace) |
| 4 | not found (404) |
| 5 | rate limited after retries (429) |

Error text goes to stderr as `Error: HTTP 422 from POST <url>` followed by one
line per JSON:API error (`detail`, with `source.pointer` when present) and an
optional `Hint:` line.

## Testing conventions

- `pytest` + `respx`. The `api` fixture mounts a respx router at
  `https://api.clarify.ai/v1` and the autouse fixture sets
  `CLARIFY_API_KEY=test-key`, `CLARIFY_WORKSPACE=acme`, and an isolated config
  path. Sleep is patched out so retry tests run instantly.
- `invoke(*args)` runs the root app through `CliRunner`. Assert on
  `result.exit_code`, `json.loads(result.stdout)`, and the captured request
  (`route.calls.last.request`): method, URL path, decoded query params, and
  JSON body. Every command gets at least one test that pins the exact
  method + path + query + body it sends, because that is what the spec defines.
- No network. No live keys in tests.

## Style

- Python 3.11+, `from __future__ import annotations`, type hints everywhere.
- Typer with `Annotated[...]` options, `no_args_is_help=True` on groups,
  one-line help on every command and option; longer help in the docstring.
- `ruff check` and `ruff format` clean (config in `pyproject.toml`).
- Keep modules small and boring. Prefer plain dicts over dataclasses for API
  payloads.

## Command map (OpenAPI operationId → CLI)

Groups marked (core) are written first and serve as the reference pattern.

| Group | Command | Method + path | operationId |
| --- | --- | --- | --- |
| auth (core) | login / status / logout | `GET /users?page[limit]=1` to verify | – |
| config (core) | path / list / get / set / unset | – | – |
| api (core) | `api METHOD PATH` | any | – |
| users (core) | list | `GET /users` | getUsers |
| | get USER_ID | `GET /users/{userId}` | getUser |
| records | list OBJECT | `GET /objects/{object}/resources` | getResources |
| | get OBJECT ID | `GET /objects/{object}/resources/{id}` (`--endpoint records` → `GET /objects/{object}/records/{id}`) | getResource / getRecord |
| | create OBJECT | `POST /objects/{object}/records` (`--match-on`; `--endpoint resources` → `POST .../resources`) | createRecord / createResource |
| | update OBJECT ID | `PATCH /objects/{object}/records/{id}` | updateRecord |
| | delete OBJECT ID | `DELETE /objects/{object}/records/{id}` | deleteRecord |
| | bulk-create OBJECT --file | `POST /objects/{object}/records/bulk` | createBulkRecords |
| | bulk-update OBJECT --file | `PATCH /objects/{object}/records` | updateRecords |
| | bulk-delete OBJECT IDS... | `DELETE /objects/{object}/records` | deleteRecords |
| | merge OBJECT TARGET --source ID... | `POST /objects/{object}/records/{record}/merges` | mergeRecords |
| | deleted OBJECT | `GET /objects/{object}/deleted-resources` | getDeletedResources |
| lists | list [OBJECT] | `GET /lists` or `GET /objects/{object}/lists` | getWorkspaceLists / getLists |
| | get OBJECT LIST | `GET /objects/{object}/lists/{list}` | getList |
| | create OBJECT | `POST /objects/{object}/lists` | createList |
| | update OBJECT LIST | `PATCH /objects/{object}/lists/{list}` | updateList |
| | delete OBJECT LIST | `DELETE /objects/{object}/lists/{list}` | deleteList |
| | publish / unpublish OBJECT LIST | `POST .../lists/{list}/publish|unpublish` | publishList / unpublishList |
| | records OBJECT LIST | `GET /objects/{object}/lists/{list}/resources` | getListResources |
| | export-csv OBJECT LIST | `POST /objects/{object}/lists/{list}/rows/csv` | getListRowsCsv |
| schemas | list / get OBJECT / fields OBJECT / objects | `GET /schemas` (client-side selection) | getSchemas |
| | create-object | `POST /schemas/objects` | createCustomObject |
| | replace OBJECT | `PUT /schemas/objects/{object}` | updateEntitySchema |
| | delete-object OBJECT | `DELETE /schemas/objects/{object}` | deleteCustomObject |
| | add-fields ENTITY | `POST /schemas/{entity}/properties` | createSchemaProperties |
| | add-relationships ENTITY | `POST /schemas/{entity}/relationships` | createSchemaRelationshipProperties |
| | delete-relationship ENTITY FIELD | `DELETE /schemas/{entity}/relationships/{fieldName}` | deleteSchemaRelationshipProperty |
| | reorder ENTITY | `PATCH /schemas/{entity}/fields-order` | updateSchemaPropertyOrder |
| | visibility ENTITY | `PATCH /schemas/{entity}/fields-visibility` | updateSchemaPropertyVisibility |
| | enum ENTITY FIELD | `PATCH /schemas` | patchEnumFieldValues |
| | activities ENTITY | `GET /schemas/{entity}/activities` | getSchemaActivities |
| activities | list OBJECT RECORD | `GET /objects/{object}/records/{record}/activities` | getActivities |
| relationships | list OBJECT ID FIELD | `GET .../records/{id}/relationships/{relationship}` | getRecordRelationships |
| | set OBJECT ID FIELD | `PATCH .../relationships/{relationship}` | updateRecordRelationship |
| | unlink OBJECT ID FIELD | `DELETE .../relationships/{relationship}` | deleteRecordRelationship |
| attachments | list OBJECT ID | `GET .../records/{id}/attachments` | listRecordAttachments |
| | get OBJECT ID ATTACHMENT | `GET .../attachments/{attachmentId}` | getRecordAttachment |
| | request-upload OBJECT ID | `PUT .../records/{id}/attachments` | getSignedUrlForRecordAttachmentUpload |
| | add OBJECT ID | `POST .../records/{id}/attachments` | addRecordAttachment |
| | upload OBJECT ID FILE | request-upload → HTTP PUT to signed URL → add | (convenience) |
| | delete OBJECT ID ATTACHMENT | `DELETE .../attachments/{attachmentId}` | deleteRecordAttachment |
| access | list OBJECT ID | `GET .../records/{id}/access` | getGrants |
| | grant OBJECT ID | `POST .../records/{id}/access` | createGrant |
| | grant-bulk OBJECT ID | `POST .../records/{id}/access/bulk` | createGrantsBulk |
| | update OBJECT ID GRANT | `PATCH .../access/{grantId}` | updateGrant |
| | revoke OBJECT ID GRANT | `DELETE .../access/{grantId}` | revokeGrant |
| object-access | list OBJECT | `GET /objects/{object}/access` | getObjectAccess |
| | grant OBJECT | `POST /objects/{object}/access` | giveObjectAccess |
| | revoke OBJECT ID | `DELETE /objects/{object}/access/{id}` | revokeObjectAccess |
| comments | create / get / update / delete | `/comments[/{id}]` | createComment / getComment / updateComment / deleteComment |
| layouts | get / update / reset ID | `/layouts/{id}[/reset]` | getLayoutById / updateLayout / resetLayout |
| meetings | enable-recording / disable-recording MEETING | `POST|DELETE /meetings/{meetingId}/recording` | enableRecording / disableRecording |
| | artifacts MEETING RECORDING | `POST /meetings/{meetingId}/recordings/{id}/artifacts` | getRecordingArtifacts |
| | upload-transcript MEETING | `POST /meetings/{meetingId}/transcript` | uploadTranscript |
| | upload-recording-transcript MEETING | `POST /meetings/{meetingId}/recordings/transcript` | uploadRecordingTranscript |
| | init-media-upload MEETING | `POST /meetings/{meetingId}/recordings/media` | initMediaUpload |
| | confirm-media-upload MEETING RECORDING | `POST /meetings/{meetingId}/recordings/media/{recordingId}` | confirmMediaUpload |
| | upload-media MEETING FILE | init → S3 POST policy → confirm | (convenience) |
| campaigns | recipients CAMPAIGN | `GET /campaigns/{campaignId}/recipients` | getRecipients |
| workflows | list / get / create / update / delete | `/workflows[/{id}]` | getWorkflows / getWorkflow / createWorkflow / updateWorkflow / deleteWorkflow |
| settings | list / get KEY / set KEY VALUE / reset KEY | `/settings[/{key}]` | readAllWorkspaceSettings / readWorkspaceSettings / writeWorkspaceSetting / deleteWorkspaceSetting |
