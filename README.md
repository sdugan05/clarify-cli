# clarify-cli

[![CI](https://github.com/sdugan05/clarify-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/sdugan05/clarify-cli/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

`clarify` is a command-line interface for the [Clarify CRM API](https://developer.clarify.ai/docs).
Every operation in Clarify's OpenAPI spec is an explicit subcommand (`records list`,
`lists export-csv`, `schemas add-fields`, ...), with a raw `clarify api` escape hatch for
anything else. It prints JSON when piped and tables on a terminal, follows pagination for
you, turns `--filter`/`--sort`/`--set` flags into the right JSON:API query parameters and
request bodies, loads bulk records from JSON, NDJSON, or CSV files, and exits with
meaningful status codes so it is easy to script.

## Install

Requires Python 3.11 or newer.

```bash
# once published on PyPI
uv tool install clarify-cli
# or
pipx install clarify-cli
```

From source:

```bash
git clone https://github.com/sdugan05/clarify-cli && cd clarify-cli
uv sync
uv run clarify --help
```

## Authentication

Create an API key in Clarify under **Settings → API Keys**. There are two kinds:

- **Personal** keys act on your behalf and can access everything you can. The
  access-delegation commands (`access`, `object-access`) require one; the API rejects
  Workspace keys there with `403`.
- **Workspace** keys are shared keys scoped to public data in the workspace. Only
  workspace admins can create them.

The key is sent as `Authorization: api-key <key>` (not `Bearer`). The CLI never prints it;
`auth status` and `config list` show a masked form.

The quickest setup is interactive: it prompts for the workspace slug (the segment after
`app.clarify.ai/` in your workspace URL) and the key, verifies them with a test request,
and writes a config profile with `0600` permissions.

```bash
clarify auth login
clarify auth status     # resolved workspace/key, where each came from, and whether they work
clarify auth logout     # removes the stored key; keeps the slug
```

Or use environment variables, which is what CI jobs and scripts usually want:

| Variable            | Meaning                                              |
| ------------------- | ---------------------------------------------------- |
| `CLARIFY_API_KEY`   | API key                                              |
| `CLARIFY_WORKSPACE` | Workspace slug                                       |
| `CLARIFY_PROFILE`   | Config profile to use (default `default`)            |
| `CLARIFY_BASE_URL`  | API base URL (default `https://api.clarify.ai/v1`)   |
| `CLARIFY_CONFIG`    | Path of the config file (overrides the default path) |

Precedence is flag > environment > config profile > default. The same settings exist as
global flags (`-w/--workspace`, `--api-key`, `-p/--profile`, `--base-url`), which go
**before** the group name.

The config file lives at `$XDG_CONFIG_HOME/clarify/config.toml` (default
`~/.config/clarify/config.toml`; `%APPDATA%\clarify\config.toml` on Windows). `clarify
config path` prints the location; `clarify config list|get|set|unset` edit it. Profiles let
you keep several workspaces around:

```toml
default_profile = "default"

[profiles.default]
workspace = "acme"
api_key = "..."

[profiles.staging]
workspace = "acme-staging"
api_key = "..."
base_url = "https://api.clarify.ai/v1"
```

```bash
clarify auth login -p staging       # write a second profile
clarify -p staging users list       # use it for one command
```

## Quick start

Global options (`-o`, `--fields`, `--yes`, `--silent`, `-w`, ...) always go before the
group name: `clarify -o csv records list company`, not `clarify records list company -o csv`.

```bash
# People with an acme.com address, newest first
clarify records list person -f 'email_addresses[Contains]=@acme.com' -s -_created_at -n 20

# Deals over 50k in Negotiation, largest first, with the company embedded under "included"
clarify records list deal -f 'amount=>50000' -f stage=Negotiation -s -amount -i company_id

# One record (by ID), with its company
clarify records get person 5f8b7d2e-9c4a-4e1b-8f3d-2a6c9e0b4d71 -i company_id
```

Create and update records with `--set KEY=VALUE` (dotted keys nest, values parse as JSON
when they can) or `-d/--data` (inline JSON, `@file`, or `-` for stdin). Collection fields
such as `email_addresses`, `domains`, `phone_numbers`, and `labels` take the
`{"items": [...]}` shape. `--match-on FIELD` turns a create into an upsert on the
object's unique field (`email_addresses` for people, `domains` for companies, `name` for
deals):

```bash
clarify records create person \
  --set name.first_name=Jane --set name.last_name=Doe \
  --set 'email_addresses={"items": ["jane@acme.com"]}' \
  --set job_title=CMO \
  --match-on email_addresses

clarify records create deal -d '{"name": "Acme Renewal", "amount": 12000}'

# Partial update: only the given attributes change
clarify records update person 5f8b7d2e-9c4a-4e1b-8f3d-2a6c9e0b4d71 --set job_title=CEO

# Add an email without replacing the existing ones
clarify records update person 5f8b7d2e-9c4a-4e1b-8f3d-2a6c9e0b4d71 \
  --set 'email_addresses={"items": ["jane@newco.com"]}' --append email_addresses
```

Bulk-create from a file. Records go in sequential batches (`--batch-size`, default 100);
each batch is atomic, and the error names the failing batch and record range. CSV cells
are always strings and dotted headers nest, so use JSON or NDJSON when a field needs a
number, boolean, or a collection:

```bash
# people.csv
#   name.first_name,name.last_name,job_title
#   Jane,Doe,CMO
clarify records bulk-create person -F people.csv

# companies.ndjson
#   {"name": "Acme Corp", "domains": {"items": ["acme.com"]}, "employee_count": 1200}
clarify records bulk-create company -F companies.ndjson --match-on domains
```

Lists and their rows:

```bash
clarify lists list deal                                    # find the list ID
clarify lists records deal LIST_ID -n 100                  # its records, as JSON:API resources
clarify lists export-csv deal LIST_ID --out deals.csv      # the rows as CSV, straight from the API
```

Schemas (which objects exist and what fields they have):

```bash
clarify schemas objects
clarify schemas fields deal
clarify schemas get person
clarify schemas add-fields c_project --field due=date
```

Anything else, with the same auth, workspace prefix, and output handling:

```bash
clarify api GET /objects/person/resources -P 'page[limit]=5' -P 'filter[name]=*Smith*'
clarify api POST /objects/deal/records -d @deal.json
clarify api GET /users --all                               # follows links.next and merges pages
```

## Output formats and scripting

Output is a table when stdout is a terminal and JSON when it is piped; `-o` overrides
(`json`, `table`, `ndjson`, `csv`).

```
$ clarify records list company -n 2 -s -employee_count
id                                     name        domains             industry        employee_count
─────────────────────────────────────────────────────────────────────────────────────────────────────
c0a8f1e2-7b3d-4c5e-9f10-2a4b6c8d0e12   Acme Corp   acme.com, acme.io   Manufacturing   1200
9b1e4d7a-2c3f-4e5a-8b6c-7d8e9f0a1b2c   Globex      globex.com          Software        340
Showing 2 of 812. Use --all or --limit to see more.
```

List commands always emit one envelope: `{"data": [...], "included": [...]?, "meta": {...}}`,
where `meta` carries `total_records`/`total_pages` from the first page plus `returned`
(the number of items in `data`); `links` is dropped because paging is already done.

```bash
clarify records list company -n 2 | jq '.meta'
# {"total_records": 812, "total_pages": 407, "returned": 2}

# One resource per line; pairs well with jq and xargs
clarify -o ndjson records list company --all | jq -r '.attributes.name'

# CSV with chosen columns (dotted paths allowed; collections are comma-joined)
clarify -o csv --fields id,name,domains records list company -n 500 > companies.csv
clarify --fields id,name.first_name,email_addresses records list person
```

- Table and CSV rows are flattened resources: `id`, `type`, then the attributes. The
  default table shows `id` plus the first six non-underscore attributes; `--fields`
  picks columns, and with a single record the table is a `field | value` view.
- Paging: `-n/--limit N` (default 50) caps the total returned; `--all` fetches every page;
  `--offset N` skips; `--page-size N` sets `page[limit]` per request.
- Results go to stdout only. Errors, confirmations for empty `202`/`204` responses
  (`Deleted person 5f8b...`), the "Showing N of M" footer, and `-v` request logs all go
  to stderr, so `$(...)` and pipes stay clean.
- `--silent` before the group name adds `silent=true` to every mutation, which
  suppresses in-app and Slack notifications for that change.

Exit codes:

| Code | Meaning                                                              |
| ---- | -------------------------------------------------------------------- |
| 0    | success                                                              |
| 1    | API error (4xx/5xx not listed below) or other failure                |
| 2    | usage error: bad flags, invalid JSON, refused or missing confirmation |
| 3    | authentication/configuration problem (401, 403, missing key or slug) |
| 4    | not found (404)                                                      |
| 5    | rate limited after retries (429)                                     |

Errors are printed as `HTTP 422 from POST <url>` followed by one line per JSON:API error
(its `detail`, with the `source.pointer` when present) and a `Hint:` line when the CLI has
one.

## Filtering cheat-sheet

`-f/--filter` is repeatable; conditions are ANDed (the API has no OR). A bare value is an
exact match (`Is`), including on collection fields such as `email_addresses`. Name an
operator with `FIELD[Operator]=VALUE` (operator names are case-sensitive, so quote the
argument), or use the API's shorthand inside the value:

| `-f` argument                       | Sent as                                   | Meaning                   |
| ----------------------------------- | ----------------------------------------- | ------------------------- |
| `email_addresses=jane@acme.com`     | `filter[email_addresses]=jane@acme.com`   | exact match (`Is`)        |
| `'amount[Greater than]=50000'`      | `filter[amount][Greater than]=50000`      | named operator            |
| `'amount=>50000'` / `'amount=>=50000'` | shorthand                              | `Greater than` / `... or equal` |
| `'amount=<50000'` / `'amount=<=50000'` | shorthand                              | `Less than` / `... or equal`    |
| `'stage=!=Lost'`                    | shorthand                                 | `Is not`                  |
| `'name=*Smith*'`                    | shorthand                                 | `Contains`                |
| `'name=Smith*'` / `'name=*Smith'`   | shorthand                                 | `Starts with` / `Ends with` |
| `stage=Won,Negotiation`             | shorthand                                 | `One of`                  |
| `stage=null` / `'stage=!null'`      | shorthand                                 | `Is empty` / `Is not empty` |
| `person.company_id.name=Acme`       | `filter[person.company_id.name]=Acme`     | field on a related record (up to three levels) |

Operators by field type (from the [filtering guide](https://developer.clarify.ai/docs/api-basics/filtering)):

| Field type      | Operators                                                                                                       |
| --------------- | --------------------------------------------------------------------------------------------------------------- |
| Text            | `Is`, `Is not`, `Contains`, `Does not contain`, `Starts with`, `Ends with`, `Is empty`, `Is not empty`          |
| Number/currency | `Is`, `Is not`, `Greater than`, `Greater than or equal`, `Less than`, `Less than or equal`, `Is empty`, `Is not empty` |
| Date/datetime   | `Is`, `Is not`, `Is before`, `Is on or before`, `Is after`, `Is on or after`, `Is empty`, `Is not empty`        |
| Single select   | `Is`, `Is not`, `One of`, `Not one of`, `Is empty`, `Is not empty`                                              |
| Multi select    | `Contains`, `Does not contain`, `Is empty`, `Is not empty` (no bare-value match)                                |
| Boolean         | `Is`, `Is not`, `Is set`, `Is not set`                                                                          |
| Collections     | `Is`, `Is not`, `Contains`, `Does not contain`, `Is empty`, `Is not empty`                                      |
| Record IDs      | `Is`, `Is not`, `Is empty`, `Is not empty`                                                                      |

Two filters on the same field make a range:
`-f 'amount[Greater than]=10000' -f 'amount[Less than or equal]=50000'`.

Sorting is `-s FIELD`, `-s FIELD:asc`, `-s FIELD:desc`, or `-s -FIELD` (sent as
`sortOrder[column]`/`sortOrder[dir]`). `-i/--include a,b` embeds related records under
`included`; `--search TEXT` is available on the endpoints that declare it (lists).
Each list command only exposes the options its endpoint supports; `--help` shows them.

## Commands

The full reference, generated from the CLI's own help, is in
[docs/COMMANDS.md](docs/COMMANDS.md). `clarify --help` and `clarify <group> <command> --help`
show the same text.

| Group                                            | Commands                                                                                                                                                       |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`auth`](docs/COMMANDS.md#auth)                   | `login`, `status`, `logout`                                                                                                                                    |
| [`config`](docs/COMMANDS.md#config)               | `path`, `list`, `get`, `set`, `unset`                                                                                                                          |
| [`api`](docs/COMMANDS.md#api)                     | `api METHOD PATH` — any endpoint, with `-P` query params, `-d` body, `--all` paging, `--out` raw download                                                       |
| [`records`](docs/COMMANDS.md#records)             | `list`, `get`, `create`, `update`, `delete`, `bulk-create`, `bulk-update`, `bulk-delete`, `merge`, `deleted`                                                   |
| [`lists`](docs/COMMANDS.md#lists)                 | `list`, `get`, `create`, `update`, `delete`, `publish`, `unpublish`, `records`, `export-csv`                                                                   |
| [`schemas`](docs/COMMANDS.md#schemas)             | `list`, `objects`, `get`, `fields`, `create-object`, `replace`, `delete-object`, `add-fields`, `add-relationships`, `delete-relationship`, `reorder`, `visibility`, `enum`, `activities` |
| [`activities`](docs/COMMANDS.md#activities)       | `list`                                                                                                                                                         |
| [`relationships`](docs/COMMANDS.md#relationships) | `list`, `set`, `unlink`                                                                                                                                        |
| [`attachments`](docs/COMMANDS.md#attachments)     | `list`, `get`, `request-upload`, `add`, `upload`, `delete`                                                                                                     |
| [`access`](docs/COMMANDS.md#access)               | `list`, `grant`, `grant-bulk`, `update`, `revoke` (Personal key required)                                                                                      |
| [`object-access`](docs/COMMANDS.md#object-access) | `list`, `grant`, `revoke` (Personal key required)                                                                                                              |
| [`comments`](docs/COMMANDS.md#comments)           | `create`, `get`, `update`, `delete`                                                                                                                            |
| [`layouts`](docs/COMMANDS.md#layouts)             | `get`, `update`, `reset`                                                                                                                                       |
| [`meetings`](docs/COMMANDS.md#meetings)           | `enable-recording`, `disable-recording`, `artifacts`, `upload-transcript`, `upload-recording-transcript`, `init-media-upload`, `confirm-media-upload`, `upload-media` |
| [`campaigns`](docs/COMMANDS.md#campaigns)         | `recipients`                                                                                                                                                   |
| [`workflows`](docs/COMMANDS.md#workflows)         | `list`, `get`, `create`, `update`, `delete`                                                                                                                    |
| [`settings`](docs/COMMANDS.md#settings)           | `list`, `get`, `set`, `reset`                                                                                                                                  |
| [`users`](docs/COMMANDS.md#users)                 | `list`, `get`                                                                                                                                                  |

## Notes

**Destructive commands ask first.** `delete`, `bulk-delete`, `merge`, `revoke`, `reset`,
`delete-object`, `delete-relationship`, `unlink`, `disable-recording`, `layouts reset`,
`relationships set --clear`, and `schemas enum --remove` prompt for confirmation. `-y/--yes` (before the group name)
skips the prompt. When stdin is not a terminal and `--yes` is absent, the command refuses
with exit code 2 instead of hanging, so scripts must pass `--yes` explicitly:

```bash
clarify --yes records delete person 5f8b7d2e-9c4a-4e1b-8f3d-2a6c9e0b4d71

# Delete every Lost deal: list as NDJSON, feed the IDs back in
clarify -o ndjson records list deal -f stage=Lost --all \
  | clarify --yes records bulk-delete deal -F - --format ndjson
```

**`--silent`** adds `silent=true` to every write (POST/PATCH/PUT/DELETE) so the change
does not trigger in-app or Slack notifications. Useful for imports and clean-ups.

**Retries and rate limits.** Clarify allows 3,000 requests per minute per workspace per
endpoint. The client retries `429` up to three times, honouring `Retry-After` and
otherwise backing off exponentially, and retries `502`/`503`/`504` for GET requests only.
Nothing else is retried; a request still throttled after the retries exits with code 5.
Bulk commands send one request per batch rather than one per record, which keeps large
imports well under the limit.

**Diagnostics.** `-v` logs each request line (`GET <url> → 200 (123 ms)`) to stderr,
`--debug` also logs request and response bodies, and `--timeout SECONDS` (default 30)
bounds each request. `clarify --version` prints the installed version.

## Development

```bash
uv sync                                   # install with the dev group (pytest, respx, ruff)
uv run ruff check . && uv run ruff format --check .
uv run pytest                             # no network: the API is mocked with respx
uv run python scripts/gen_command_docs.py > docs/COMMANDS.md   # regenerate the reference
```

Tests never touch the live API: `tests/conftest.py` sets fake credentials and mounts a
[respx](https://github.com/lundberg/respx) router at the API base URL, and every command
has a test that pins the exact method, path, query parameters, and body it sends.

## Contributing

Read [docs/DESIGN.md](docs/DESIGN.md) first: it is the contract every command module
follows (naming, global options, list and mutation conventions, output shapes, exit codes)
and maps each OpenAPI `operationId` to its CLI command. Each command group is one module
under `src/clarify_cli/commands/` with one test file under `tests/`, and declares an
`OPERATIONS` manifest so a test can prove the CLI covers the whole spec. Keep `ruff` clean
and add a request-pinning test for every new command.

## License

[MIT](LICENSE)
