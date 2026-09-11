# clarify command reference

Generated from the CLI's own help text by `scripts/gen_command_docs.py`; do not edit by hand. Regenerate with:

```bash
uv run python scripts/gen_command_docs.py > docs/COMMANDS.md
```

Command-line interface for the Clarify CRM API.

Global options go **before** the group name: `clarify --silent --yes records delete person ID`.

## Contents

| Group | Description |
| --- | --- |
| [Global options](#global-options) | Options accepted before any command. |
| [`api`](#api) | Call any API endpoint directly. |
| [`auth`](#auth) | Log in, check status, and log out. |
| [`config`](#config) | Read and write the CLI config file. |
| [`records`](#records) | Create, read, update, and delete records of any object. |
| [`lists`](#lists) | Manage lists and export their rows. |
| [`schemas`](#schemas) | Inspect and modify object schemas. |
| [`activities`](#activities) | Read a record's activity feed. |
| [`relationships`](#relationships) | Manage links between records. |
| [`attachments`](#attachments) | Manage files attached to records. |
| [`access`](#access) | Manage per-record access grants. |
| [`object-access`](#object-access) | Manage entity-wide access delegations. |
| [`comments`](#comments) | Create, read, update, and delete comments. |
| [`layouts`](#layouts) | Read, update, and reset layouts. |
| [`meetings`](#meetings) | Meeting recordings and transcripts. |
| [`campaigns`](#campaigns) | Campaign recipients and engagement. |
| [`workflows`](#workflows) | Manage workflows and sequences. |
| [`settings`](#settings) | Read and write workspace settings. |
| [`users`](#users) | List and inspect workspace users. |

## Global options

```
clarify [OPTIONS] COMMAND [ARGS]...
```

Authenticate with `clarify auth login` or set CLARIFY_API_KEY and CLARIFY_WORKSPACE. Output is JSON when piped and a table on a terminal; override with -o.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--workspace, -w` | TEXT |  | Workspace slug [env: CLARIFY_WORKSPACE]. |
| `--api-key` | TEXT |  | API key [env: CLARIFY_API_KEY]. Prefer env or config. |
| `--profile, -p` | TEXT |  | Config profile name [env: CLARIFY_PROFILE]. |
| `--base-url` | TEXT |  | API base URL [env: CLARIFY_BASE_URL]. |
| `--output, -o` | `json\|table\|ndjson\|csv` |  | Output format: json, table, ndjson, csv. |
| `--fields` | TEXT |  | Comma-separated columns for table/csv output. |
| `--silent` | flag |  | Suppress in-app and Slack notifications for mutations. |
| `--yes, -y` | flag |  | Skip confirmation prompts. |
| `--verbose, -v` | flag |  | Log each request to stderr. |
| `--debug` | flag |  | Log request and response bodies to stderr. |
| `--timeout` | FLOAT (min 0.1) | `30` | HTTP timeout in seconds. |
| `--version` | flag |  | Show version. |
| `--install-completion` | flag |  | Install completion for the current shell. |
| `--show-completion` | flag |  | Show completion for the current shell, to copy it or customize the installation. |

## api

Call any API endpoint directly.

```
clarify api [OPTIONS] METHOD PATH
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `METHOD` | TEXT | yes | HTTP method: GET, POST, PUT, PATCH, DELETE. |
| `PATH` | TEXT | yes | Workspace-relative path such as /objects/person/resources, a /workspaces/... path, or a full URL (for example a links.next value). |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--param, -P` | TEXT, repeatable |  | Query parameter KEY=VALUE, e.g. 'page[limit]=10'. |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |
| `--header, -H` | TEXT, repeatable |  | Extra header 'Name: value'. |
| `--all` | flag |  | GET only: follow links.next and merge every page. |
| `--out` | TEXT |  | Write the raw response body to this file. |

## auth

Log in, check status, and log out.

| Command | Description |
| --- | --- |
| [`auth login`](#auth-login) | Save an API key and workspace slug to the config file. |
| [`auth status`](#auth-status) | Show which workspace and key are active, where they came from, and whether they work. |
| [`auth logout`](#auth-logout) | Remove the stored API key from a profile (the workspace slug is kept). |

### auth login

Save an API key and workspace slug to the config file.

```
clarify auth login [OPTIONS]
```

Create a key under Settings → API Keys in Clarify. The slug is the segment
after `app.clarify.ai/` in your workspace URL.

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--workspace, -w` | TEXT |  | Workspace slug to store. |
| `--api-key` | TEXT |  | API key to store (prompted if omitted). |
| `--profile, -p` | TEXT |  | Profile to write (default: active). |
| `--no-verify` | flag |  | Skip the test request before saving. |
| `--default / --no-default` | flag | true | Make this profile the default. |

### auth status

Show which workspace and key are active, where they came from, and whether they work.

```
clarify auth status [OPTIONS]
```

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--no-verify` | flag |  | Only show the resolved settings. |

### auth logout

Remove the stored API key from a profile (the workspace slug is kept).

```
clarify auth logout [OPTIONS]
```

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--profile, -p` | TEXT |  | Profile to clear (default: active). |

## config

Read and write the CLI config file.

| Command | Description |
| --- | --- |
| [`config path`](#config-path) | Print the config file location. |
| [`config list`](#config-list) | Show every profile (API keys are masked). |
| [`config get`](#config-get) | Print one config value. |
| [`config set`](#config-set) | Store one config value in the active profile (or the top level). |
| [`config unset`](#config-unset) | Remove one config value. |

### config path

Print the config file location.

```
clarify config path
```

### config list

Show every profile (API keys are masked).

```
clarify config list
```

### config get

Print one config value.

```
clarify config get [OPTIONS] KEY
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `KEY` | TEXT | yes | workspace, api_key, base_url, or default_profile. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--profile, -p` | TEXT |  | Profile to act on (default: active). |
| `--reveal` | flag |  | Print the API key unmasked. |

### config set

Store one config value in the active profile (or the top level).

```
clarify config set [OPTIONS] KEY VALUE
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `KEY` | TEXT | yes | workspace, api_key, base_url, or default_profile. |
| `VALUE` | TEXT | yes | Value to store. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--profile, -p` | TEXT |  | Profile to act on (default: active). |

### config unset

Remove one config value.

```
clarify config unset [OPTIONS] KEY
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `KEY` | TEXT | yes | workspace, api_key, base_url, or default_profile. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--profile, -p` | TEXT |  | Profile to act on (default: active). |

## records

Create, read, update, and delete records of any object.

| Command | Description |
| --- | --- |
| [`records list`](#records-list) | List records with filters, sorting, and includes (GET /objects/{object}/resources). |
| [`records get`](#records-get) | Show one record (GET /objects/{object}/resources/{id}; --endpoint records → records/{id}). |
| [`records create`](#records-create) | Create or upsert a record (POST /objects/{object}/records, or --endpoint resources). |
| [`records update`](#records-update) | Partially update a record (PATCH /objects/{object}/records/{id}). |
| [`records delete`](#records-delete) | Permanently delete a record (DELETE /objects/{object}/records/{id}). |
| [`records bulk-create`](#records-bulk-create) | Create (or upsert) many records from a file (POST /objects/{object}/records/bulk). |
| [`records bulk-update`](#records-bulk-update) | Partially update many records from a file (PATCH /objects/{object}/records). |
| [`records bulk-delete`](#records-bulk-delete) | Permanently delete many records by ID (DELETE /objects/{object}/records). |
| [`records merge`](#records-merge) | Merge duplicates into a target record (POST /objects/{object}/records/{record}/merges). |
| [`records deleted`](#records-deleted) | List records deleted in the last 30 days (GET /objects/{object}/deleted-resources). |

### records list

List records with filters, sorting, and includes (GET /objects/{object}/resources).

```
clarify records list [OPTIONS] OBJECT
```

Filters are ANDed. A bare value is an exact match (also on collection fields
such as email_addresses); name an operator for anything else.

Examples:

```bash
clarify records list person -f email_addresses=jane@acme.com

clarify records list deal -f 'amount[Greater than]=50000' -s -amount -i company_id

clarify records list company -f 'name=*Acme*' --all -o ndjson > companies.ndjson
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--filter, -f` | TEXT, repeatable |  | Filter FIELD=VALUE or 'FIELD[Operator]=VALUE' (repeatable). Shorthand values like '>100', '\*Smith\*', 'a,b', 'null' are passed through. |
| `--sort, -s` | TEXT |  | Sort: FIELD, FIELD:asc, FIELD:desc, or -FIELD. |
| `--include, -i` | TEXT |  | Comma-separated relationships to embed. |
| `--limit, -n` | INTEGER (min 1) | `50` | Maximum number of items to return. |
| `--offset` | INTEGER (min 0) | `0` | Number of items to skip. |
| `--all` | flag |  | Fetch every page (ignores --limit). |
| `--page-size` | INTEGER (min 1) |  | Items per request (page[limit]); default derived. |

### records get

Show one record (GET /objects/{object}/resources/{id}; --endpoint records → records/{id}).

```
clarify records get [OPTIONS] OBJECT ID
```

Examples:

```bash
clarify records get person 5f8b7d2e-9c4a-4e1b-8f3d-2a6c9e0b4d71 -i company_id

clarify records get deal 1c2d... --endpoint records
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `ID` | TEXT | yes | The record's ID. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--include, -i` | TEXT |  | Comma-separated relationships to embed. |
| `--endpoint` | `resources\|records` | `resources` | Read from /resources/{id} (default, returns `included`) or /records/{id}. |

### records create

Create or upsert a record (POST /objects/{object}/records, or --endpoint resources).

```
clarify records create [OPTIONS] OBJECT
```

The body is `{"data": {"type": OBJECT, "attributes": {...}}}`; pass the
attributes object (or the full document) with --data and/or build it with
--set. Collection fields (email_addresses, domains, phone_numbers, labels)
take the shape `{"items": [...]}`.

Creating is a plain insert: a value that collides with an existing record's
unique field is rejected with a 400. Pass --match-on FIELD to upsert
instead: a record whose FIELD matches exactly one existing record updates
that record and returns its ID. --match-on is a records-endpoint feature
and is rejected with --endpoint resources.

Examples:

```bash
clarify records create person --set name.first_name=Jane --set name.last_name=Doe \
    --set 'email_addresses={"items": ["jane@acme.com"]}' --match-on email_addresses

clarify records create deal -d '{"name": "Acme Renewal", "amount": 12000}'

clarify records create company -d @company.json --endpoint resources
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |
| `--set` | TEXT, repeatable |  | Set an attribute KEY=VALUE (repeatable). Dotted keys nest; values parse as JSON when possible, so amount=100 is a number and name.first_name=Jane is a string. |
| `--match-on FIELD` | TEXT |  | Upsert: the unique field to match existing records on (person: email_addresses, company: domains, deal: name). A match is updated instead of creating a duplicate. |
| `--endpoint` | `resources\|records` | `records` | Write to /records (default, supports --match-on) or /resources. |

### records update

Partially update a record (PATCH /objects/{object}/records/{id}).

```
clarify records update [OPTIONS] OBJECT ID
```

Only the fields in `attributes` change; everything else keeps its value.
Collection fields (email_addresses, domains, phone_numbers, labels) take
the shape `{"items": [...]}` and are replaced by default. --append,
--remove, and --merge set the per-field write strategy in `meta`:
`{"collection": "append"|"remove"}` for `{"items": [...]}` values,
`{"array": "append"}` for JSON-array values, and `{"object": "merge"}` for
object values. The named field must be present in the body.

Examples:

```bash
clarify records update person 5f8b... --set job_title=CMO

clarify records update person 5f8b... \
    --set 'email_addresses={"items": ["jane@newco.com"]}' --append email_addresses

clarify records update deal 1c2d... -d @changes.json --merge custom_fields
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `ID` | TEXT | yes | The record's ID. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |
| `--set` | TEXT, repeatable |  | Set an attribute KEY=VALUE (repeatable). Dotted keys nest; values parse as JSON when possible, so amount=100 is a number and name.first_name=Jane is a string. |
| `--append FIELD` | TEXT, repeatable |  | Add FIELD's items to the collection (or array) instead of replacing it. |
| `--remove FIELD` | TEXT, repeatable |  | Remove FIELD's items from the collection instead of replacing it. |
| `--merge FIELD` | TEXT, repeatable |  | Merge FIELD's keys into the existing object instead of replacing it. |

### records delete

Permanently delete a record (DELETE /objects/{object}/records/{id}).

```
clarify records delete OBJECT ID
```

Asks for confirmation unless --yes is given. Deleted records stay visible
to `records deleted` for 30 days.

Example:

```bash
clarify --yes records delete person 5f8b7d2e-9c4a-4e1b-8f3d-2a6c9e0b4d71
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `ID` | TEXT | yes | The record's ID. |

### records bulk-create

Create (or upsert) many records from a file (POST /objects/{object}/records/bulk).

```
clarify records bulk-create [OPTIONS] OBJECT
```

The file may be a JSON array, `{"data": [...]}`, NDJSON, or CSV with a
header row (dotted headers nest: `name.first_name`). Each item is either a
JSON:API resource or a flat attributes object. Records are sent in
sequential batches of --batch-size; each batch is atomic, so one invalid
record fails its whole batch and the command stops there. Results of the
batches that succeeded are still printed, and the error names the failing
batch and record range.

Prints one envelope: `{"data": [...created...], "meta": {"batches": n,
"records": m}}`.

Examples:

```bash
clarify records bulk-create company -F companies.csv --match-on domains

clarify records bulk-create person -F people.ndjson --batch-size 25

cat people.json | clarify records bulk-create person -F - --match-on email_addresses
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--file, -F` | TEXT | required | Records file: JSON array, {"data": [...]}, NDJSON, or CSV. Use - for stdin. |
| `--format` | TEXT |  | Force the records file format: json, ndjson, or csv. |
| `--match-on FIELD` | TEXT |  | Upsert: the unique field to match existing records on (person: email_addresses, company: domains, deal: name). A match is updated instead of creating a duplicate. |
| `--batch-size` | INTEGER (min 1) | `100` | Records per request. Batches are atomic: one bad record fails its whole batch. |

### records bulk-update

Partially update many records from a file (PATCH /objects/{object}/records).

```
clarify records bulk-update [OPTIONS] OBJECT
```

Every record must carry an `id` (a top-level key on flat records, or the
resource's `id`); only the listed attributes change. Records are sent in
sequential, atomic batches of --batch-size, and the output is one envelope
`{"data": [...updated...], "meta": {"batches": n, "records": m}}`.

Collection, array, and object fields are replaced by default. --append,
--remove, and --merge set the per-field write strategy in the request's
`meta` (see `records update`); it applies to every batch, and the named
field must appear in at least one record. A JSON `{"data": [...],
"meta": {...}}` document's own `meta` is sent too.

Examples:

```bash
clarify records bulk-update deal -F stages.csv

clarify records bulk-update person -F new-emails.ndjson --append email_addresses

clarify records bulk-update person -F '{"data": [{"type": "person", "id": "5f8b...",
    "attributes": {"job_title": "CMO"}}]}' --format json
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--file, -F` | TEXT | required | Records file: JSON array, {"data": [...]}, NDJSON, or CSV. Use - for stdin. |
| `--format` | TEXT |  | Force the records file format: json, ndjson, or csv. |
| `--batch-size` | INTEGER (min 1) | `100` | Records per request. Batches are atomic: one bad record fails its whole batch. |
| `--append FIELD` | TEXT, repeatable |  | Add FIELD's items to the collection (or array) instead of replacing it. |
| `--remove FIELD` | TEXT, repeatable |  | Remove FIELD's items from the collection instead of replacing it. |
| `--merge FIELD` | TEXT, repeatable |  | Merge FIELD's keys into the existing object instead of replacing it. |

### records bulk-delete

Permanently delete many records by ID (DELETE /objects/{object}/records).

```
clarify records bulk-delete [OPTIONS] OBJECT [IDS]...
```

IDs come from the arguments, --file, or both (duplicates are dropped).
Asks for confirmation with the count unless --yes is given.

Examples:

```bash
clarify --yes records bulk-delete person 5f8b... 7a1c...

clarify records bulk-delete company -F stale-ids.txt

clarify records list deal -f stage=Lost -o ndjson \
    | clarify --yes records bulk-delete deal -F - --format ndjson
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `IDS` | TEXT, repeatable | no | Record IDs to delete. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--file, -F` | TEXT |  | IDs file: a .txt with one ID per line, or a records file (JSON array, {"data": [...]}, NDJSON, CSV) whose records carry an id. Use - for stdin. |
| `--format` | TEXT |  | Force the records file format: json, ndjson, or csv. |

### records merge

Merge duplicates into a target record (POST /objects/{object}/records/{record}/merges).

```
clarify records merge [OPTIONS] OBJECT TARGET
```

Field values and relationships of every --source record are combined onto
TARGET, then the sources are deleted. This cannot be undone, so the command
asks for confirmation unless --yes is given.

Example:

```bash
clarify records merge company c0a8... --source 9b1e... --source 4d2f...
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `TARGET` | TEXT | yes | ID of the record that survives. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--source ID` | TEXT, repeatable | required | ID of a duplicate to merge into TARGET; it is deleted afterwards (repeatable). |

### records deleted

List records deleted in the last 30 days (GET /objects/{object}/deleted-resources).

```
clarify records deleted [OPTIONS] OBJECT
```

Attributes are the values at deletion time plus `_deleted_at`. The only
filterable field is `_deleted_at` (epoch seconds); the endpoint supports
neither `include` nor sorting.

Examples:

```bash
clarify records deleted person

clarify records deleted deal -f '_deleted_at[Less than]=1787273241' --all
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--filter, -f` | TEXT, repeatable |  | Filter FIELD=VALUE or 'FIELD[Operator]=VALUE' (repeatable). Shorthand values like '>100', '\*Smith\*', 'a,b', 'null' are passed through. |
| `--limit, -n` | INTEGER (min 1) | `50` | Maximum number of items to return. |
| `--offset` | INTEGER (min 0) | `0` | Number of items to skip. |
| `--all` | flag |  | Fetch every page (ignores --limit). |
| `--page-size` | INTEGER (min 1) |  | Items per request (page[limit]); default derived. |

## lists

Manage lists and export their rows.

| Command | Description |
| --- | --- |
| [`lists list`](#lists-list) | List lists across the workspace (GET /lists) or on one object (GET /objects/{object}/lists). |
| [`lists get`](#lists-get) | Show one list, including its query and layout (GET /objects/{object}/lists/{list}). |
| [`lists create`](#lists-create) | Create a list on an object (POST /objects/{object}/lists). |
| [`lists update`](#lists-update) | Update some of a list's fields (PATCH /objects/{object}/lists/{list}). |
| [`lists delete`](#lists-delete) | Permanently delete a list (DELETE /objects/{object}/lists/{list}). |
| [`lists publish`](#lists-publish) | Publish a draft list to its audience (POST /objects/{object}/lists/{list}/publish). |
| [`lists unpublish`](#lists-unpublish) | Revert a published list to draft (POST /objects/{object}/lists/{list}/unpublish). |
| [`lists records`](#lists-records) | List the records in a list (GET /objects/{object}/lists/{list}/resources). |
| [`lists export-csv`](#lists-export-csv) | Export a list's rows as CSV (POST /objects/{object}/lists/{list}/rows/csv). |

### lists list

List lists across the workspace (GET /lists) or on one object (GET /objects/{object}/lists).

```
clarify lists list [OPTIONS] [OBJECT]
```

Dynamic lists are excluded unless a filter selects them, e.g. `-f type=dynamic`.
Filters: `type` (dynamic, static, default), `state` (draft, published),
`_created_by`, and, for the workspace-wide form, `entity` with one or more
object types (`-f entity=deal,company`). `--search` matches the list title.

Examples:

```bash
clarify lists list -f entity=deal -f state=published

clarify lists list deal -f type=dynamic --search enterprise -s -_created_at
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | no | Object type (person, company, deal, ... or c_\*) whose lists to show. Omit to list every object's lists in the workspace. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--limit, -n` | INTEGER (min 1) | `50` | Maximum number of items to return. |
| `--offset` | INTEGER (min 0) | `0` | Number of items to skip. |
| `--all` | flag |  | Fetch every page (ignores --limit). |
| `--page-size` | INTEGER (min 1) |  | Items per request (page[limit]); default derived. |
| `--sort, -s` | TEXT |  | Sort: FIELD, FIELD:asc, FIELD:desc, or -FIELD. |
| `--filter, -f` | TEXT, repeatable |  | Filter FIELD=VALUE or 'FIELD[Operator]=VALUE' (repeatable). Shorthand values like '>100', '\*Smith\*', 'a,b', 'null' are passed through. |
| `--search` | TEXT |  | Case-insensitive substring search. |

### lists get

Show one list, including its query and layout (GET /objects/{object}/lists/{list}).

```
clarify lists get OBJECT LIST
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `LIST` | TEXT | yes | The list ID. |

### lists create

Create a list on an object (POST /objects/{object}/lists).

```
clarify lists create [OPTIONS] OBJECT
```

The body is the plain list DTO, not a JSON:API document: `--data` supplies it
whole, the flags fill in single fields, and `--set` overrides any key (dotted
keys nest, e.g. `--set options.segmentedByInBoard=stage`). `title` and
`description` are required. `layout` defaults to `table`, the simplest layout
the API accepts, and `type` defaults to `dynamic` when a query is present,
otherwise `static`. Lists are created published; use `--set state=draft`
for a draft.

Examples:

```bash
clarify lists create deal --title "Big deals" --description "Over 50k" --query @big.sql

clarify lists create person --title Prospects --description "Hand-picked" --type static

clarify lists create deal -d @l.json --layout board --set options.segmentedByInBoard=stage
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |
| `--set` | TEXT, repeatable |  | Set an attribute KEY=VALUE (repeatable). Dotted keys nest; values parse as JSON when possible, so amount=100 is a number and name.first_name=Jane is a string. |
| `--title` | TEXT |  | Display name of the list. |
| `--description` | TEXT |  | Short description of the list. |
| `--type` | `dynamic\|static` |  | List type. Defaults to dynamic when a query is given, otherwise static. |
| `--query` | TEXT |  | SQL defining a dynamic list's membership: inline, @file, or - for stdin. Sent as query.sql with query.version=6. |
| `--emoji` | TEXT |  | Emoji shown next to the list in the app. |
| `--layout` | `table\|board` |  | How the list renders in the app. |

### lists update

Update some of a list's fields (PATCH /objects/{object}/lists/{list}).

```
clarify lists update [OPTIONS] OBJECT LIST
```

Partial: only the fields you pass change. The body is the plain list DTO
(`title`, `emoji`, `description`, `layout`, `options`, `query`, `rank`).
`--query` replaces the whole query object, so include every column you want
to keep. The object's default list cannot be updated.

Examples:

```bash
clarify lists update deal LIST --title "Enterprise deals (FY26)"

clarify lists update deal LIST --set emoji=null --set rank=0
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `LIST` | TEXT | yes | The list ID. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |
| `--set` | TEXT, repeatable |  | Set an attribute KEY=VALUE (repeatable). Dotted keys nest; values parse as JSON when possible, so amount=100 is a number and name.first_name=Jane is a string. |
| `--title` | TEXT |  | Display name of the list. |
| `--description` | TEXT |  | Short description of the list. |
| `--query` | TEXT |  | SQL defining a dynamic list's membership: inline, @file, or - for stdin. Sent as query.sql with query.version=6. |
| `--emoji` | TEXT |  | Emoji shown next to the list in the app. |
| `--layout` | `table\|board` |  | How the list renders in the app. |

### lists delete

Permanently delete a list (DELETE /objects/{object}/lists/{list}).

```
clarify lists delete OBJECT LIST
```

Asks for confirmation unless `--yes` is given. The object's default list and
the last remaining list on an object cannot be deleted. The API answers 202
with an empty body, so the confirmation line goes to stderr.

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `LIST` | TEXT | yes | The list ID. |

### lists publish

Publish a draft list to its audience (POST /objects/{object}/lists/{list}/publish).

```
clarify lists publish OBJECT LIST
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `LIST` | TEXT | yes | The list ID. |

### lists unpublish

Revert a published list to draft (POST /objects/{object}/lists/{list}/unpublish).

```
clarify lists unpublish OBJECT LIST
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `LIST` | TEXT | yes | The list ID. |

### lists records

List the records in a list (GET /objects/{object}/lists/{list}/resources).

```
clarify lists records [OPTIONS] OBJECT LIST
```

The list's membership applies on top of any `--filter`; `--include` embeds
related records under `included`.

Example:

```bash
clarify lists records deal LIST -f 'amount=>10000' -i company_id -s -_created_at
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `LIST` | TEXT | yes | The list ID. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--limit, -n` | INTEGER (min 1) | `50` | Maximum number of items to return. |
| `--offset` | INTEGER (min 0) | `0` | Number of items to skip. |
| `--all` | flag |  | Fetch every page (ignores --limit). |
| `--page-size` | INTEGER (min 1) |  | Items per request (page[limit]); default derived. |
| `--sort, -s` | TEXT |  | Sort: FIELD, FIELD:asc, FIELD:desc, or -FIELD. |
| `--filter, -f` | TEXT, repeatable |  | Filter FIELD=VALUE or 'FIELD[Operator]=VALUE' (repeatable). Shorthand values like '>100', '\*Smith\*', 'a,b', 'null' are passed through. |
| `--include, -i` | TEXT |  | Comma-separated relationships to embed. |

### lists export-csv

Export a list's rows as CSV (POST /objects/{object}/lists/{list}/rows/csv).

```
clarify lists export-csv [OPTIONS] OBJECT LIST
```

The response is text/csv with a header row of field names. It is written
verbatim to stdout (or to `--out`) regardless of `-o`. `--search` narrows the
rows with a case-insensitive substring match.

Examples:

```bash
clarify lists export-csv deal LIST > deals.csv

clarify lists export-csv deal LIST --sql @rows.sql --search acme --out rows.csv
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `LIST` | TEXT | yes | The list ID. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--sql` | TEXT |  | Custom SQL selecting the rows to export instead of the list's own query: inline, @file, or - for stdin. |
| `--search` | TEXT |  | Case-insensitive substring search. |
| `--out` | TEXT |  | Write the CSV to this file instead of stdout. |

## schemas

Inspect and modify object schemas.

| Command | Description |
| --- | --- |
| [`schemas list`](#schemas-list) | List every schema in the workspace (GET /schemas). |
| [`schemas objects`](#schemas-objects) | List the object types that have a schema: person, company, c_\* ... (GET /schemas). |
| [`schemas get`](#schemas-get) | Show one object's full JSON Schema (GET /schemas, selected client-side). |
| [`schemas fields`](#schemas-fields) | Tabulate an object's fields: type, required, unique, hidden, relationship (GET /schemas). |
| [`schemas create-object`](#schemas-create-object) | Create a custom object (POST /schemas/objects). |
| [`schemas replace`](#schemas-replace) | Replace an object's whole JSON Schema (PUT /schemas/objects/{object}). |
| [`schemas delete-object`](#schemas-delete-object) | Delete a custom object and all of its records (DELETE /schemas/objects/{object}). |
| [`schemas add-fields`](#schemas-add-fields) | Add non-relationship fields to an object (POST /schemas/{entity}/properties). |
| [`schemas add-relationships`](#schemas-add-relationships) | Add relationship fields between objects (POST /schemas/{entity}/relationships). |
| [`schemas delete-relationship`](#schemas-delete-relationship) | Delete a relationship field and its counterpart (DELETE .../relationships/{fieldName}). |
| [`schemas reorder`](#schemas-reorder) | Set the display order of an object's fields (PATCH /schemas/{entity}/fields-order). |
| [`schemas visibility`](#schemas-visibility) | Hide or show fields on the record detail view (PATCH /schemas/{entity}/fields-visibility). |
| [`schemas enum`](#schemas-enum) | Add or remove values of an enum field (PATCH /schemas). |
| [`schemas activities`](#schemas-activities) | List an object's schema change history (GET /schemas/{entity}/activities). |

### schemas list

List every schema in the workspace (GET /schemas).

```
clarify schemas list
```

JSON output is the API's schema list verbatim (pages merged, `links` dropped);
table/CSV output shows one row per schema with its id, object name, title and
field count. Example: `clarify schemas list -o table`

### schemas objects

List the object types that have a schema: person, company, c_* ... (GET /schemas).

```
clarify schemas objects
```

Derived from `GET /schemas`: only `entities/*` schemas are listed, never the
shared `core/*` definitions. Example: `clarify schemas objects -o json`

### schemas get

Show one object's full JSON Schema (GET /schemas, selected client-side).

```
clarify schemas get OBJECT
```

OBJECT is an object name (`person`, `c_project`) or a full schema id. Exits 4
when the workspace has no such schema. Example: `clarify schemas get c_project`

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |

### schemas fields

Tabulate an object's fields: type, required, unique, hidden, relationship (GET /schemas).

```
clarify schemas fields OBJECT
```

Each row is one entry of the schema's `properties`; the raw JSON Schema of the
field is kept as `definition` in JSON output. Example: `clarify schemas fields person`

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |

### schemas create-object

Create a custom object (POST /schemas/objects).

```
clarify schemas create-object [OPTIONS]
```

The body is the plain CreateCustomObjectDto (`name`, `plural`, `description`,
`icon`, `backgroundColor`, `properties`); flags override keys from --data.
Example: `clarify schemas create-object --name Project --plural Projects --icon Briefcase`

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--name` | TEXT |  | Object name; normalised to c_<name>. |
| `--plural` | TEXT |  | Plural display name for the UI. |
| `--description` | TEXT |  | Description stored as AI context. |
| `--icon` | TEXT |  | Avatar icon name (e.g. Briefcase, Box, Ticket, Rocket). |
| `--background-color` | TEXT |  | Avatar colour (e.g. blue, green, neutral). |
| `--properties` | TEXT |  | Initial fields as JSON {name: JSON Schema}: inline, @file, or - for stdin. |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |

### schemas replace

Replace an object's whole JSON Schema (PUT /schemas/objects/{object}).

```
clarify schemas replace [OPTIONS] OBJECT
```

--data is the complete schema document (or a `clarify schemas get` result,
whose `data.attributes` is unwrapped). Its `$id` must be
`https://getclarify.ai/schemas/entities/<OBJECT>`; mismatches are rejected before
any request. The API queues an async task, which is printed.
Example: `clarify schemas get c_project > s.json; clarify schemas replace c_project -d @s.json`

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` | TEXT | required | JSON body: inline, @file, or - for stdin. |

### schemas delete-object

Delete a custom object and all of its records (DELETE /schemas/objects/{object}).

```
clarify schemas delete-object OBJECT
```

Only `c_*` objects can be deleted; asks for confirmation unless --yes is given.
The API queues an async task, which is printed.
Example: `clarify -y schemas delete-object c_project`

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |

### schemas add-fields

Add non-relationship fields to an object (POST /schemas/{entity}/properties).

```
clarify schemas add-fields [OPTIONS] ENTITY
```

--data is either `{name: JSON Schema, ...}` or a full `{"data": {...}}` document;
--field entries are merged over it. Existing fields are never overwritten.
Example: `clarify schemas add-fields c_project --field budget=number --field active=boolean`

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `ENTITY` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--field` | TEXT, repeatable |  | NAME=TYPE (repeatable): adds NAME with JSON type [TYPE, "null"] (boolean stays bare), e.g. budget=number, notes=string, due=date. |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |

### schemas add-relationships

Add relationship fields between objects (POST /schemas/{entity}/relationships).

```
clarify schemas add-relationships [OPTIONS] ENTITY
```

--data is `{object: {field: JSON Schema}}` keyed by object type then field name
(both sides of each relationship together), or a full `{"data": {...}}` document.
one-to-many / many-to-many sides need
`"oneOf": [{"$ref": "https://getclarify.ai/schemas/core/collectionOfIds"}, {"type": "null"}]`.
Example: `clarify schemas add-relationships c_project -d @rel.json`

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `ENTITY` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` | TEXT | required | JSON body: inline, @file, or - for stdin. |

### schemas delete-relationship

Delete a relationship field and its counterpart (DELETE .../relationships/{fieldName}).

```
clarify schemas delete-relationship ENTITY FIELD
```

Asks for confirmation unless --yes is given; the API queues an async task,
which is printed. Example: `clarify -y schemas delete-relationship c_project company_id`

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `ENTITY` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `FIELD` | TEXT | yes | The field name. |

### schemas reorder

Set the display order of an object's fields (PATCH /schemas/{entity}/fields-order).

```
clarify schemas reorder [OPTIONS] ENTITY
```

--order lists every field name; --data accepts `["a","b"]`, `{"order": [...]}` or a
full `{"data": {...}}` document.
Example: `clarify schemas reorder c_project --order name,status,budget`

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `ENTITY` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--order` | TEXT |  | Comma-separated field names in display order. |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |

### schemas visibility

Hide or show fields on the record detail view (PATCH /schemas/{entity}/fields-visibility).

```
clarify schemas visibility [OPTIONS] ENTITY
```

Builds the `hiddenInDetails` map: --hide F sets F to true, --show F to false.
Example: `clarify schemas visibility c_project --hide budget --show status`

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `ENTITY` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--hide` | TEXT, repeatable |  | Field to hide on the detail view (repeatable). |
| `--show` | TEXT, repeatable |  | Field to show on the detail view (repeatable). |

### schemas enum

Add or remove values of an enum field (PATCH /schemas).

```
clarify schemas enum [OPTIONS] ENTITY FIELD
```

Sends one SchemaPropertiesPatchDto item for ENTITY with `meta.FIELD.enum` set to
`append` or `remove` (one operation per request). --append/--remove send just the
listed values. --data sends the field patch object as-is, i.e.
`{"enum": [...], "xClarifyEnumMetadata": {VALUE: {id, rank, color}}}` (nested
under `properties.items.items` with --multi), or a full `{"data": [...]}` document;
--op picks the operation and `type`/`id`/`meta` are filled in when absent.
Note that the spec's `append` example lists the COMPLETE enum (existing values
plus the new one) with per-option metadata; use --data to reproduce it.
Removing values is destructive (records set to a removed value are cleared), so
it asks for confirmation unless --yes is given.
Examples: `clarify schemas enum c_project status --append "On hold"`,
`clarify schemas enum c_project status -d @status-patch.json`

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `ENTITY` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `FIELD` | TEXT | yes | The field name. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--append` | TEXT, repeatable |  | Enum value to add (repeatable, case-sensitive). |
| `--remove` | TEXT, repeatable |  | Enum value to drop (repeatable). Records using it lose the value. |
| `--multi` | flag |  | FIELD is a multi-select (nests under properties.items.items). |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |
| `--op` | `append\|remove` |  | Operation for --data: append (default) or remove. |

### schemas activities

List an object's schema change history (GET /schemas/{entity}/activities).

```
clarify schemas activities [OPTIONS] ENTITY
```

Supports paging and `sortOrder` (page[limit] is capped at 500 by the API).
Example: `clarify schemas activities c_project --sort -_created_at -n 20`

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `ENTITY` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--limit, -n` | INTEGER (min 1) | `50` | Maximum number of items to return. |
| `--offset` | INTEGER (min 0) | `0` | Number of items to skip. |
| `--all` | flag |  | Fetch every page (ignores --limit). |
| `--page-size` | INTEGER (min 1) |  | Items per request (page[limit]); default derived. |
| `--sort, -s` | TEXT |  | Sort: FIELD, FIELD:asc, FIELD:desc, or -FIELD. |

## activities

Read a record's activity feed.

| Command | Description |
| --- | --- |
| [`activities list`](#activities-list) | List a record's activity feed (GET /objects/{object}/records/{record}/activities). |

### activities list

List a record's activity feed (GET /objects/{object}/records/{record}/activities).

```
clarify activities list [OPTIONS] OBJECT RECORD
```

Activities are change events (field updates, comments, relationship
changes) grouped by record and change type, newest first. Comments have
no list endpoint of their own; they appear here.

Example:

```bash
clarify activities list person 5f8b7d2e-9c4a-4e1b-8f3d-2a6c9e0b4d71 -n 20
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `RECORD` | TEXT | yes | The record's ID. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--limit, -n` | INTEGER (min 1) | `50` | Maximum number of items to return. |
| `--offset` | INTEGER (min 0) | `0` | Number of items to skip. |
| `--all` | flag |  | Fetch every page (ignores --limit). |
| `--page-size` | INTEGER (min 1) |  | Items per request (page[limit]); default derived. |
| `--sort, -s` | TEXT |  | Sort: FIELD, FIELD:asc, FIELD:desc, or -FIELD. |

## relationships

Manage links between records.

| Command | Description |
| --- | --- |
| [`relationships list`](#relationships-list) | List related records (GET /objects/{object}/records/{id}/relationships/{relationship}). |
| [`relationships set`](#relationships-set) | Link related records (PATCH /objects/{object}/records/{id}/relationships/{relationship}). |
| [`relationships unlink`](#relationships-unlink) | Unlink related records (DELETE /objects/{object}/records/{id}/relationships/{relationship}). |

### relationships list

List related records (GET /objects/{object}/records/{id}/relationships/{relationship}).

```
clarify relationships list [OPTIONS] OBJECT ID FIELD
```

Returns the records linked to the record through FIELD, e.g. the deals of
a person. `--include` takes nested relationship paths relative to the
parent record, such as `companies.deals`.

Example:

```bash
clarify relationships list person 5f8b7d2e-9c4a-4e1b-8f3d-2a6c9e0b4d71 deals -n 20
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `ID` | TEXT | yes | The record's ID. |
| `FIELD` | TEXT | yes | The relationship field name on OBJECT, e.g. deals, people, or company_id. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--limit, -n` | INTEGER (min 1) | `50` | Maximum number of items to return. |
| `--offset` | INTEGER (min 0) | `0` | Number of items to skip. |
| `--all` | flag |  | Fetch every page (ignores --limit). |
| `--page-size` | INTEGER (min 1) |  | Items per request (page[limit]); default derived. |
| `--sort, -s` | TEXT |  | Sort: FIELD, FIELD:asc, FIELD:desc, or -FIELD. |
| `--include, -i` | TEXT |  | Comma-separated relationships to embed. |

### relationships set

Link related records (PATCH /objects/{object}/records/{id}/relationships/{relationship}).

```
clarify relationships set [OPTIONS] OBJECT ID FIELD
```

For to-one and many-to-many relationships (a person's company, the people
on a deal) the request REPLACES the whole set: related records not listed
are unlinked. For one-to-many relationships (a company's people) it is
ADDITIVE: the listed records are linked and existing links stay, though a
record that already belongs to another parent is reassigned. `--clear`
sends the `{"id": null}` entry first to unlink every related record (or
clear a to-one link). Any body that unlinks everything (`--clear`, an
empty list, or an `id: null` entry in `--data`) asks for confirmation;
`--yes` skips the prompt. Use `relationships unlink` to remove specific
records.

Examples:

```bash
clarify relationships set person PERSON_ID deals --id DEAL_ID --id OTHER_DEAL_ID

clarify relationships set person PERSON_ID company_id --id COMPANY_ID

clarify relationships set company COMPANY_ID people --clear --id PERSON_ID --yes

clarify relationships set deal DEAL_ID people --data @people.json
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `ID` | TEXT | yes | The record's ID. |
| `FIELD` | TEXT | yes | The relationship field name on OBJECT, e.g. deals, people, or company_id. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--id` | TEXT, repeatable |  | ID of a related record (repeatable). |
| `--type` | TEXT |  | Object type of the records given with --id. Derived from FIELD when omitted (deals -> deal, companies -> company, people -> person, company_id -> company); pass it explicitly when FIELD is not named after its target object. |
| `--clear` | flag |  | Send {"id": null} first: clears a to-one relationship, or unlinks every related record before linking the --id records. |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |

### relationships unlink

Unlink related records (DELETE /objects/{object}/records/{id}/relationships/{relationship}).

```
clarify relationships unlink [OPTIONS] OBJECT ID FIELD
```

Removes the links to the listed records from FIELD; the records
themselves are not deleted. Asks for confirmation unless `--yes` is given.

Examples:

```bash
clarify relationships unlink person PERSON_ID deals --id DEAL_ID --yes

clarify relationships unlink deal DEAL_ID people --data '[{"type": "person", "id": "P1"}]'
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `ID` | TEXT | yes | The record's ID. |
| `FIELD` | TEXT | yes | The relationship field name on OBJECT, e.g. deals, people, or company_id. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--id` | TEXT, repeatable |  | ID of a related record (repeatable). |
| `--type` | TEXT |  | Object type of the records given with --id. Derived from FIELD when omitted (deals -> deal, companies -> company, people -> person, company_id -> company); pass it explicitly when FIELD is not named after its target object. |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |

## attachments

Manage files attached to records.

| Command | Description |
| --- | --- |
| [`attachments list`](#attachments-list) | List a record's attachments (GET /objects/{object}/records/{id}/attachments). |
| [`attachments get`](#attachments-get) | Get a short-lived signed download URL (GET .../attachments/{attachmentId}). |
| [`attachments request-upload`](#attachments-request-upload) | Request a signed upload URL for a new file (PUT .../records/{id}/attachments). |
| [`attachments add`](#attachments-add) | Link an already-uploaded file to a record (POST .../records/{id}/attachments). |
| [`attachments upload`](#attachments-upload) | Upload a local file and attach it to a record (request-upload → PUT → add). |
| [`attachments delete`](#attachments-delete) | Delete an attachment from a record (DELETE .../attachments/{attachmentId}). |

### attachments list

List a record's attachments (GET /objects/{object}/records/{id}/attachments).

```
clarify attachments list [OPTIONS] OBJECT ID
```

Covers both user uploads and files extracted from emails. Returns up to
--limit items (default 50); use --all to fetch every page.

Example:

```bash
clarify attachments list person 5f8b7d2e-9c4a-4e1b-8f3d-2a6c9e0b4d71 --all
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `ID` | TEXT | yes | The record's ID. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--limit, -n` | INTEGER (min 1) | `50` | Maximum number of items to return. |
| `--offset` | INTEGER (min 0) | `0` | Number of items to skip. |
| `--all` | flag |  | Fetch every page (ignores --limit). |
| `--page-size` | INTEGER (min 1) |  | Items per request (page[limit]); default derived. |

### attachments get

Get a short-lived signed download URL (GET .../attachments/{attachmentId}).

```
clarify attachments get [OPTIONS] OBJECT ID ATTACHMENT
```

Prints `{"data": {"url": ...}}`. With --download the URL is fetched right
away and the bytes are written to the given path; a one-line confirmation
goes to stderr and nothing is printed to stdout.

Example:

```bash
clarify attachments get person 5f8b…4d71 3b9f…9d24 --download proposal.pdf
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `ID` | TEXT | yes | The record's ID. |
| `ATTACHMENT` | TEXT | yes | The attachment's ID (the `_id` from `list`). |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--download` | FILE |  | Fetch the file from the signed URL and write it to this path. |

### attachments request-upload

Request a signed upload URL for a new file (PUT .../records/{id}/attachments).

```
clarify attachments request-upload [OPTIONS] OBJECT ID
```

Returns `signedUrl`, `key` and `attachmentId`. HTTP PUT the file contents to
`signedUrl`, then run `attachments add` with the `key` and `attachmentId`
to link the file to the record. `attachments upload` does all three steps.

Example:

```bash
clarify attachments request-upload deal 7c1d…e0a9 --name proposal.pdf
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `ID` | TEXT | yes | The record's ID. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--name` | TEXT | required | File name including its extension, e.g. proposal.pdf. |

### attachments add

Link an already-uploaded file to a record (POST .../records/{id}/attachments).

```
clarify attachments add [OPTIONS] OBJECT ID
```

Use after uploading the bytes to the signed URL from `request-upload`.
Prints the updated record.

Example:

```bash
clarify attachments add deal 7c1d…e0a9 --name proposal.pdf \
    --key attachments/acme/deal/3b9f…9d24/proposal.pdf --attachment-id 3b9f…9d24
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `ID` | TEXT | yes | The record's ID. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--name` | TEXT | required | File name including its extension, e.g. proposal.pdf. |
| `--key` | TEXT | required | Storage key returned by `request-upload`. |
| `--attachment-id` | TEXT | required | Attachment ID returned by `request-upload`. |

### attachments upload

Upload a local file and attach it to a record (request-upload → PUT → add).

```
clarify attachments upload [OPTIONS] OBJECT ID FILE
```

Runs `PUT .../attachments` to get a signed URL, sends the file bytes to
that URL with a plain HTTP PUT, then `POST .../attachments` to link it.
Prints the updated record. If the storage upload fails the record is left
untouched.

Example:

```bash
clarify attachments upload deal 7c1d…e0a9 ./proposal.pdf
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `ID` | TEXT | yes | The record's ID. |
| `FILE` | FILE | yes | Local file to upload. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--name` | TEXT |  | File name to store; defaults to FILE's basename. |
| `--content-type` | TEXT |  | Content-Type for the storage upload; guessed from the name by default. |

### attachments delete

Delete an attachment from a record (DELETE .../attachments/{attachmentId}).

```
clarify attachments delete OBJECT ID ATTACHMENT
```

Asks for confirmation unless --yes is given. This cannot be undone. Prints
the updated record.

Example:

```bash
clarify -y attachments delete person 5f8b…4d71 3b9f…9d24
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `ID` | TEXT | yes | The record's ID. |
| `ATTACHMENT` | TEXT | yes | The attachment's ID (the `_id` from `list`). |

## access

Manage per-record access grants.

These endpoints require a user-backed (Personal) API key; Workspace API keys are rejected with HTTP 403.

| Command | Description |
| --- | --- |
| [`access list`](#access-list) | List a record's access grants (GET /objects/{object}/records/{id}/access). |
| [`access grant`](#access-grant) | Share a record with a user or the workspace (POST /objects/{object}/records/{id}/access). |
| [`access grant-bulk`](#access-grant-bulk) | Share a record with many grantees at once (POST /objects/{object}/records/{id}/access/bulk). |
| [`access update`](#access-update) | Change a grant's access level (PATCH /objects/{object}/records/{id}/access/{grantId}). |
| [`access revoke`](#access-revoke) | Remove a grant from a record (DELETE /objects/{object}/records/{id}/access/{grantId}). |

### access list

List a record's access grants (GET /objects/{object}/records/{id}/access).

```
clarify access list OBJECT ID
```

Returns every grant on the record plus `meta.viewerAccess` for the calling
user. The endpoint is not paginated or filterable. Requires a Personal API key.

Example: clarify access list deal 9d2c4e6f-8a1b-4c3d-9e5f-7a9b1c3d5e7f

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Shareable object: person, company, deal, task, a custom c_\* object, or list, meeting, message. |
| `ID` | TEXT | yes | The shared record's ID. |

### access grant

Share a record with a user or the workspace (POST /objects/{object}/records/{id}/access).

```
clarify access grant [OPTIONS] OBJECT ID
```

Pick the grantee with --user USER_ID or --everyone and the level with
--level view|edit. --data may carry the attributes object (grantee_type,
grantee_id, access_level, notify) or a full JSON:API document instead;
flags override matching keys. Requires a Personal API key.

Examples: clarify access grant deal 9d2c… --user 7d4e… --level view;
clarify access grant list 1234… --everyone --level edit

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Shareable object: person, company, deal, task, a custom c_\* object, or list, meeting, message. |
| `ID` | TEXT | yes | The shared record's ID. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--user` | TEXT |  | Share with this workspace member (user ID). |
| `--everyone` | flag |  | Share with everyone in the workspace instead of a user. |
| `--level` | `view\|edit` |  | Access level: view (read-only) or edit (read-write). |
| `--notify / --no-notify` | flag |  | Whether to notify the grantee (API default: notify). Ignored for workspace grants. |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |

### access grant-bulk

Share a record with many grantees at once (POST /objects/{object}/records/{id}/access/bulk).

```
clarify access grant-bulk [OPTIONS] OBJECT ID
```

Up to 1000 grants per request, from exactly one source: repeatable --user
(plus --everyone) with one --level; --data with a JSON array of grants,
a single grant (attributes, a resource, or {"data": {...}}), or
{"data": [...]}; or --file (JSON, NDJSON, or CSV with grantee_type,
grantee_id, access_level columns). Flat objects are wrapped as
object-record-access resources; --level and --notify fill in missing
values. Requires a Personal API key.

Example: clarify access grant-bulk deal 9d2c… --user 7d4e… --user 2b6e… --everyone --level view

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Shareable object: person, company, deal, task, a custom c_\* object, or list, meeting, message. |
| `ID` | TEXT | yes | The shared record's ID. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--user` | TEXT, repeatable |  | Share with this workspace member (user ID); repeatable. |
| `--everyone` | flag |  | Share with everyone in the workspace instead of a user. |
| `--level` | `view\|edit` |  | Access level: view (read-only) or edit (read-write). |
| `--notify / --no-notify` | flag |  | Whether to notify the grantee (API default: notify). Ignored for workspace grants. |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |
| `--file, -F` | TEXT |  | Grants file: JSON array, {"data": [...]}, NDJSON, or CSV. Use - for stdin. |
| `--format` | TEXT |  | Force the records file format: json, ndjson, or csv. |

### access update

Change a grant's access level (PATCH /objects/{object}/records/{id}/access/{grantId}).

```
clarify access update [OPTIONS] OBJECT ID GRANT
```

Requires a Personal API key.

Example: clarify access update deal 9d2c… 2f4a… --level edit

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Shareable object: person, company, deal, task, a custom c_\* object, or list, meeting, message. |
| `ID` | TEXT | yes | The shared record's ID. |
| `GRANT` | TEXT | yes | The grant's ID (see `access list`). |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--level` | `view\|edit` |  | Access level: view (read-only) or edit (read-write). |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |

### access revoke

Remove a grant from a record (DELETE /objects/{object}/records/{id}/access/{grantId}).

```
clarify access revoke OBJECT ID GRANT
```

Asks for confirmation unless --yes is given. The API answers 202 with an
empty body, so a one-line confirmation goes to stderr. Requires a Personal
API key.

Example: clarify -y access revoke deal 9d2c… 2f4a…

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Shareable object: person, company, deal, task, a custom c_\* object, or list, meeting, message. |
| `ID` | TEXT | yes | The shared record's ID. |
| `GRANT` | TEXT | yes | The grant's ID (see `access list`). |

## object-access

Manage entity-wide access delegations.

These endpoints require a user-backed (Personal) API key; Workspace API keys are rejected with HTTP 403.

| Command | Description |
| --- | --- |
| [`object-access list`](#object-access-list) | List access delegations for an object type (GET /objects/{object}/access). |
| [`object-access grant`](#object-access-grant) | Delegate your access to every record of an object type (POST /objects/{object}/access). |
| [`object-access revoke`](#object-access-revoke) | Revoke an access delegation (DELETE /objects/{object}/access/{id}). |

### object-access list

List access delegations for an object type (GET /objects/{object}/access).

```
clarify object-access list OBJECT
```

Includes delegations you granted and those granted to you. The endpoint is
not paginated or filterable. Requires a Personal API key.

Example: clarify object-access list meeting

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type the delegation applies to: meeting or message. |

### object-access grant

Delegate your access to every record of an object type (POST /objects/{object}/access).

```
clarify object-access grant [OPTIONS] OBJECT
```

Name the delegate with --user USER_ID, or pass --data with the attributes
object ({"delegate_id": ...}) or a full JSON:API document; --user overrides
delegate_id. Requires a Personal API key and a plan with access delegation.

Example: clarify object-access grant meeting --user 2b6e4f8a-3d1c-4a9e-8b5f-7c2a9d0e4f63

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type the delegation applies to: meeting or message. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--user` | TEXT |  | Delegate to this workspace member (user ID → delegate_id). |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |

### object-access revoke

Revoke an access delegation (DELETE /objects/{object}/access/{id}).

```
clarify object-access revoke OBJECT ID
```

Asks for confirmation unless --yes is given. The API answers 202 with an
empty body, so a one-line confirmation goes to stderr. Requires a Personal
API key and a plan with access delegation.

Example: clarify -y object-access revoke meeting a1f4e6d2-8c9b-4f3a-9d5e-1b6c8a2f7d90

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type the delegation applies to: meeting or message. |
| `ID` | TEXT | yes | The delegation's ID (see `object-access list`). |

## comments

Create, read, update, and delete comments.

| Command | Description |
| --- | --- |
| [`comments create`](#comments-create) | Create a comment on a record (POST /comments). |
| [`comments get`](#comments-get) | Show one comment (GET /comments/{id}). |
| [`comments update`](#comments-update) | Replace a comment's body; author only (PATCH /comments/{id}). |
| [`comments delete`](#comments-delete) | Permanently delete a comment (DELETE /comments/{id}). |

### comments create

Create a comment on a record (POST /comments).

```
clarify comments create [OPTIONS] OBJECT RECORD_ID
```

The body is the CreateCommentDto: ``entity`` (OBJECT), ``owner_id``
(RECORD_ID) and ``message`` (BlockNote blocks). ``--message TEXT`` is
converted to one paragraph with a single text run. ``--data`` supplies the
rest of the DTO (or a bare block array for ``message``); the positional
OBJECT and RECORD_ID always win over ``entity``/``owner_id`` found in it.

Examples:

```bash
clarify comments create person 5f8b... -m "Called Jane."

clarify comments create person 5f8b... --data @comment.json

clarify comments create deal 9d3e... --data \
    '[{"type":"paragraph","content":[{"type":"text","text":"Hi","styles":{"bold":true}}]}]'
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `OBJECT` | TEXT | yes | Object type: person, company, deal, meeting, task, or a custom c_\* object. |
| `RECORD_ID` | TEXT | yes | ID of the record to comment on (sent as owner_id). |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--message, -m` | TEXT |  | Plain-text body; becomes one BlockNote paragraph. Use - to read stdin. |
| `--message-file` | TEXT |  | Read the plain-text body from this file. |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |

### comments get

Show one comment (GET /comments/{id}).

```
clarify comments get COMMENT_ID
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `COMMENT_ID` | TEXT | yes | The comment's ID. |

### comments update

Replace a comment's body; author only (PATCH /comments/{id}).

```
clarify comments update [OPTIONS] COMMENT_ID
```

Sends the UpdateCommentDto ``{"message": [...]}``. ``--message TEXT`` becomes
one paragraph; ``--data`` may be the DTO, a bare block array, or a comment
fetched with ``get`` (only its ``message`` is sent).

Example:

```bash
clarify comments update 9d3e... -m "Jane signed off on pricing."
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `COMMENT_ID` | TEXT | yes | The comment's ID. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--message, -m` | TEXT |  | Plain-text body; becomes one BlockNote paragraph. Use - to read stdin. |
| `--message-file` | TEXT |  | Read the plain-text body from this file. |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |

### comments delete

Permanently delete a comment (DELETE /comments/{id}).

```
clarify comments delete COMMENT_ID
```

Asks for confirmation unless --yes is given. The API returns the deleted
comment, which is printed.

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `COMMENT_ID` | TEXT | yes | The comment's ID. |

## layouts

Read, update, and reset layouts.

| Command | Description |
| --- | --- |
| [`layouts get`](#layouts-get) | Show one layout and its tree (GET /layouts/{id}). |
| [`layouts update`](#layouts-update) | Replace a layout's tree (PATCH /layouts/{id}). |
| [`layouts reset`](#layouts-reset) | Restore a layout to its default tree (POST /layouts/{id}/reset). |

### layouts get

Show one layout and its tree (GET /layouts/{id}).

```
clarify layouts get LAYOUT_ID
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `LAYOUT_ID` | TEXT | yes | The layout's ID, e.g. list__person. |

### layouts update

Replace a layout's tree (PATCH /layouts/{id}).

```
clarify layouts update [OPTIONS] LAYOUT_ID
```

Sends ``{"data": {"type": "layout", "id": LAYOUT_ID, "attributes": {"tree": ...}}}``.
``--data`` may be the bare tree, an object with a ``tree`` key (for example
the output of ``layouts get``, edited), a resource, or the full document.

Example (round trip):

```bash
clarify layouts get list__person > layout.json

# edit layout.json, then:
clarify layouts update list__person --data @layout.json
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `LAYOUT_ID` | TEXT | yes | The layout's ID, e.g. list__person. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |

### layouts reset

Restore a layout to its default tree (POST /layouts/{id}/reset).

```
clarify layouts reset LAYOUT_ID
```

Discards every customisation of the layout, so it asks for confirmation
unless --yes is given. Prints the restored layout.

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `LAYOUT_ID` | TEXT | yes | The layout's ID, e.g. list__person. |

## meetings

Meeting recordings and transcripts.

| Command | Description |
| --- | --- |
| [`meetings enable-recording`](#meetings-enable-recording) | Enable recording so the notetaker joins the call (POST /meetings/{meetingId}/recording). |
| [`meetings disable-recording`](#meetings-disable-recording) | Disable recording so no notetaker joins (DELETE /meetings/{meetingId}/recording). |
| [`meetings artifacts`](#meetings-artifacts) | Get signed video/transcript URLs (POST /meetings/{meetingId}/recordings/{id}/artifacts). |
| [`meetings upload-transcript`](#meetings-upload-transcript) | Create a recording from an external transcript (POST /meetings/{meetingId}/transcript). |
| [`meetings upload-recording-transcript`](#meetings-upload-recording-transcript) | Upload a transcript as a recording (POST /meetings/{meetingId}/recordings/transcript). |
| [`meetings init-media-upload`](#meetings-init-media-upload) | Start a media upload and get an S3 POST policy (POST /meetings/{meetingId}/recordings/media). |
| [`meetings confirm-media-upload`](#meetings-confirm-media-upload) | Finalize an uploaded media file (POST /meetings/{meetingId}/recordings/media/{recordingId}). |
| [`meetings upload-media`](#meetings-upload-media) | Upload a media file: init, S3 POST, confirm (POST .../recordings/media then .../media/{id}). |

### meetings enable-recording

Enable recording so the notetaker joins the call (POST /meetings/{meetingId}/recording).

```
clarify meetings enable-recording MEETING
```

Returns the updated meeting record.

Example:

```bash
clarify meetings enable-recording 6c8e0a2b-4d5f-4a7b-9c1d-3e5f7a9b1c2d
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `MEETING` | TEXT | yes | The meeting record's ID. |

### meetings disable-recording

Disable recording so no notetaker joins (DELETE /meetings/{meetingId}/recording).

```
clarify meetings disable-recording MEETING
```

Asks for confirmation unless --yes is given. Returns the updated meeting record.

Example:

```bash
clarify --yes meetings disable-recording 6c8e0a2b-4d5f-4a7b-9c1d-3e5f7a9b1c2d
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `MEETING` | TEXT | yes | The meeting record's ID. |

### meetings artifacts

Get signed video/transcript URLs (POST /meetings/{meetingId}/recordings/{id}/artifacts).

```
clarify meetings artifacts MEETING RECORDING
```

The URLs are short-lived; either is null when that artifact does not exist.

Example:

```bash
clarify meetings artifacts MEETING RECORDING | jq -r .data.transcriptionUrl
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `MEETING` | TEXT | yes | The meeting record's ID. |
| `RECORDING` | TEXT | yes | The meeting recording's ID. |

### meetings upload-transcript

Create a recording from an external transcript (POST /meetings/{meetingId}/transcript).

```
clarify meetings upload-transcript [OPTIONS] MEETING
```

The transcript is an ordered list of speaker segments with timed words (see
UploadTranscriptDto), given as JSON via --file PATH (or -) or --data
JSON|@file|-; it is sent through unchanged. A plain-text file (one utterance
per line, optionally prefixed 'Speaker Name: ') needs --plain-text: the CLI
then invents word timestamps at 0.4 s per word, sets each word's language to
null and the segment language to --language. Use that only when there is no
media for the timeline to line up with.

Examples:

```bash
clarify meetings upload-transcript MEETING --file call.json
clarify meetings upload-transcript MEETING --file notes.txt --plain-text --language fr
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `MEETING` | TEXT | yes | The meeting record's ID. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--file, -F` | TEXT |  | Transcript JSON file: an array of segments or {"transcript": [...]}. Use - for stdin. Add --plain-text to read a text file instead. |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |
| `--plain-text` | flag |  | Treat --file as plain text: one utterance per line, optionally 'Speaker: words'. Word timestamps are SYNTHETIC (0.4 s per word) and word language is null; the segment language comes from --language. |
| `--language` | TEXT | `en` | ISO language code for segments built with --plain-text. |

### meetings upload-recording-transcript

Upload a transcript as a recording (POST /meetings/{meetingId}/recordings/transcript).

```
clarify meetings upload-recording-transcript [OPTIONS] MEETING
```

Creates a second recording when the meeting already has one; pass
--recording-id to overwrite a completed manual-upload recording's transcript
instead. Accepts the same --file/--data/--plain-text inputs as
upload-transcript and triggers summary generation.

Example:

```bash
clarify meetings upload-recording-transcript MEETING -F call.json --recording-id REC
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `MEETING` | TEXT | yes | The meeting record's ID. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--file, -F` | TEXT |  | Transcript JSON file: an array of segments or {"transcript": [...]}. Use - for stdin. Add --plain-text to read a text file instead. |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |
| `--recording-id` | TEXT |  | Overwrite this completed manual-upload recording instead of creating a new one. |
| `--plain-text` | flag |  | Treat --file as plain text: one utterance per line, optionally 'Speaker: words'. Word timestamps are SYNTHETIC (0.4 s per word) and word language is null; the segment language comes from --language. |
| `--language` | TEXT | `en` | ISO language code for segments built with --plain-text. |

### meetings init-media-upload

Start a media upload and get an S3 POST policy (POST /meetings/{meetingId}/recordings/media).

```
clarify meetings init-media-upload [OPTIONS] MEETING
```

Creates a pending recording and returns data.recordingId plus
data.upload.{url,fields}: submit the file as a multipart POST with every
field as returned and the file last, then run confirm-media-upload. Media is
stored for playback, not transcribed; add --transcript-file with a JSON
transcript whose word timestamps match the media to attach one (plain text
is refused here because its timing would be invented). `upload-media` does
all three steps in one go.

Example:

```bash
clarify meetings init-media-upload MEETING --content-type video/mp4
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `MEETING` | TEXT | yes | The meeting record's ID. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--content-type` | TEXT | required | MIME type of the media file: audio/\* or video/\*. |
| `--recording-id` | TEXT |  | Overwrite this completed manual-upload recording instead of creating a new one. |
| `--transcript-file` | TEXT |  | Transcript JSON to attach to the same recording: an array of segments or {"transcript": [...]} whose word timestamps line up with the media. Use - for stdin. |

### meetings confirm-media-upload

Finalize an uploaded media file (POST /meetings/{meetingId}/recordings/media/{recordingId}).

```
clarify meetings confirm-media-upload MEETING RECORDING
```

Validates the stored object and marks the recording complete. Returns the recording.

Example:

```bash
clarify meetings confirm-media-upload MEETING RECORDING
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `MEETING` | TEXT | yes | The meeting record's ID. |
| `RECORDING` | TEXT | yes | The meeting recording's ID. |

### meetings upload-media

Upload a media file: init, S3 POST, confirm (POST .../recordings/media then .../media/{id}).

```
clarify meetings upload-media [OPTIONS] MEETING FILE
```

Convenience for init-media-upload -> multipart POST to the presigned policy
-> confirm-media-upload. The file goes straight to storage, never through the
Clarify API. Prints the finalized recording.

Example:

```bash
clarify meetings upload-media MEETING call.mp4
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `MEETING` | TEXT | yes | The meeting record's ID. |
| `FILE` | FILE | yes | Audio or video file. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--content-type` | TEXT |  | MIME type (audio/\* or video/\*); guessed from FILE by default. |
| `--recording-id` | TEXT |  | Overwrite this completed manual-upload recording instead of creating a new one. |

## campaigns

Campaign recipients and engagement.

| Command | Description |
| --- | --- |
| [`campaigns recipients`](#campaigns-recipients) | List a campaign's recipients with engagement (GET /campaigns/{campaignId}/recipients). |

### campaigns recipients

List a campaign's recipients with engagement (GET /campaigns/{campaignId}/recipients).

```
clarify campaigns recipients [OPTIONS] CAMPAIGN
```

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

```bash
clarify campaigns recipients 9a1f…c3e2 -f event=clicked,replied -s _created_at:desc
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `CAMPAIGN` | TEXT | yes | The campaign's ID. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--limit, -n` | INTEGER (min 1) | `50` | Maximum number of items to return. |
| `--offset` | INTEGER (min 0) | `0` | Number of items to skip. |
| `--all` | flag |  | Fetch every page (ignores --limit). |
| `--page-size` | INTEGER (min 1) |  | Items per request (page[limit]); default derived. |
| `--sort, -s` | TEXT |  | Sort: FIELD, FIELD:asc, FIELD:desc, or -FIELD. |
| `--filter, -f` | TEXT, repeatable |  | Filter FIELD=VALUE or 'FIELD[Operator]=VALUE' (repeatable). Shorthand values like '>100', '\*Smith\*', 'a,b', 'null' are passed through. |

## workflows

Manage workflows and sequences.

| Command | Description |
| --- | --- |
| [`workflows list`](#workflows-list) | List the workspace's workflows (GET /workflows). |
| [`workflows get`](#workflows-get) | Show one workflow with its trigger and blocks (GET /workflows/{id}). |
| [`workflows create`](#workflows-create) | Create a workflow from a JSON document (POST /workflows). |
| [`workflows update`](#workflows-update) | Partially update a workflow (PATCH /workflows/{id}). |
| [`workflows delete`](#workflows-delete) | Delete a workflow (DELETE /workflows/{id}). |

### workflows list

List the workspace's workflows (GET /workflows).

```
clarify workflows list [OPTIONS]
```

`workflow` is a general automation, `sequence` an email sequence (campaign), and
`system` a hidden built-in. Example:

```bash
clarify workflows list --type sequence --filter enabled=true --sort -_created_at
```

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--type, -t` | `workflow\|sequence\|system` |  | Only this workflow type (sugar for --filter type=VALUE). |
| `--limit, -n` | INTEGER (min 1) | `50` | Maximum number of items to return. |
| `--offset` | INTEGER (min 0) | `0` | Number of items to skip. |
| `--all` | flag |  | Fetch every page (ignores --limit). |
| `--page-size` | INTEGER (min 1) |  | Items per request (page[limit]); default derived. |
| `--sort, -s` | TEXT |  | Sort: FIELD, FIELD:asc, FIELD:desc, or -FIELD. |
| `--filter, -f` | TEXT, repeatable |  | Filter FIELD=VALUE or 'FIELD[Operator]=VALUE' (repeatable). Shorthand values like '>100', '\*Smith\*', 'a,b', 'null' are passed through. |

### workflows get

Show one workflow with its trigger and blocks (GET /workflows/{id}).

```
clarify workflows get WORKFLOW_ID
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `WORKFLOW_ID` | TEXT | yes | The workflow's ID. |

### workflows create

Create a workflow from a JSON document (POST /workflows).

```
clarify workflows create [OPTIONS]
```

The body is sent as-is. Pass either a full `{"data": {"type": "workflow",
"attributes": {...}}}` document or just the attributes object (`name`,
`description`, `enabled`, `type`, `trigger`, `blocks`, ...); the CLI wraps it.
Create it disabled and enable it once the graph is complete. Example:

```bash
clarify workflows create --data @workflow.json --set enabled=false
```

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |
| `--set` | TEXT, repeatable |  | Set an attribute KEY=VALUE (repeatable). Dotted keys nest; values parse as JSON when possible, so amount=100 is a number and name.first_name=Jane is a string. |

### workflows update

Partially update a workflow (PATCH /workflows/{id}).

```
clarify workflows update [OPTIONS] WORKFLOW_ID
```

Only the attributes you send change. `--enable`/`--disable` are shorthand for
`--set enabled=true|false` and can be combined with `--data`/`--set`. Examples:

```bash
clarify workflows update WORKFLOW_ID --enable
clarify workflows update WORKFLOW_ID --set name="Nightly sync" --data @blocks.json
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `WORKFLOW_ID` | TEXT | yes | The workflow's ID. |

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` | TEXT |  | JSON body: inline, @file, or - for stdin. |
| `--set` | TEXT, repeatable |  | Set an attribute KEY=VALUE (repeatable). Dotted keys nest; values parse as JSON when possible, so amount=100 is a number and name.first_name=Jane is a string. |
| `--enable` | flag |  | Turn the workflow on (sets enabled=true). |
| `--disable` | flag |  | Turn the workflow off (sets enabled=false). |

### workflows delete

Delete a workflow (DELETE /workflows/{id}).

```
clarify workflows delete WORKFLOW_ID
```

Asks for confirmation unless --yes is given. The API applies the deletion
asynchronously and returns an empty 202 body, so the CLI prints a confirmation
line to stderr. This cannot be undone.

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `WORKFLOW_ID` | TEXT | yes | The workflow's ID. |

## settings

Read and write workspace settings.

| Command | Description |
| --- | --- |
| [`settings list`](#settings-list) | List all workspace settings (GET /settings). |
| [`settings get`](#settings-get) | Show one setting's value, or its default (GET /settings/{key}). |
| [`settings set`](#settings-set) | Write a workspace setting (POST /settings). |
| [`settings reset`](#settings-reset) | Reset a setting to its default (DELETE /settings). |

### settings list

List all workspace settings (GET /settings).

```
clarify settings list
```

Defaults are applied for settings the workspace has not overridden. JSON output
is the API's `{key: value}` object verbatim; table, CSV, and NDJSON output show
one `key`/`value` row per setting. Example:

```bash
clarify settings list -o table
```

### settings get

Show one setting's value, or its default (GET /settings/{key}).

```
clarify settings get KEY
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `KEY` | TEXT | yes | Setting key, e.g. orgDescription (camelCase). |

### settings set

Write a workspace setting (POST /settings).

```
clarify settings set KEY VALUE
```

Read-only settings are rejected by the API and some require admin permissions.
Examples:

```bash
clarify settings set orgDescription "Acme builds industrial hardware."
clarify settings set dealDetectionEnabled true
clarify settings set ingestionRules @rules.json
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `KEY` | TEXT | yes | Setting key, e.g. orgDescription (camelCase). |
| `VALUE` | TEXT | yes | New value. Parsed as JSON when possible (true, 42, '["a"]', '{...}'); otherwise a string. Use @file or - to load JSON from a file or stdin. Quote as JSON ('"42"') to force a string. |

### settings reset

Reset a setting to its default (DELETE /settings).

```
clarify settings reset KEY
```

Asks for confirmation unless --yes is given. Sends `{"key": KEY}` as the
request body. Example:

```bash
clarify settings reset orgDescription --yes
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `KEY` | TEXT | yes | Setting key, e.g. orgDescription (camelCase). |

## users

List and inspect workspace users.

| Command | Description |
| --- | --- |
| [`users list`](#users-list) | List the workspace's users with their roles (GET /users). |
| [`users get`](#users-get) | Show one user, including roles and last-active time (GET /users/{userId}). |

### users list

List the workspace's users with their roles (GET /users).

```
clarify users list [OPTIONS]
```

**Options**

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--limit, -n` | INTEGER (min 1) | `50` | Maximum number of items to return. |
| `--offset` | INTEGER (min 0) | `0` | Number of items to skip. |
| `--all` | flag |  | Fetch every page (ignores --limit). |
| `--page-size` | INTEGER (min 1) |  | Items per request (page[limit]); default derived. |
| `--sort, -s` | TEXT |  | Sort: FIELD, FIELD:asc, FIELD:desc, or -FIELD. |

### users get

Show one user, including roles and last-active time (GET /users/{userId}).

```
clarify users get USER_ID
```

**Arguments**

| Argument | Type | Required | Description |
| --- | --- | --- | --- |
| `USER_ID` | TEXT | yes | The user's ID. |
