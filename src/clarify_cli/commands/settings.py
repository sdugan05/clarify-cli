"""``clarify settings``: workspace settings (WorkspaceSettings tag).

Settings are a flat key/value map rather than JSON:API resources. ``GET /settings``
returns them keyed by name; the CLI reshapes that into ``key``/``value`` rows for
table, CSV, and NDJSON output and leaves the JSON verbatim.
"""

from __future__ import annotations

import difflib
from typing import Annotated, Any

import typer

from ..errors import UsageError
from ..inputs import coerce_scalar, load_json
from ..output import OutputFormat, emit, emit_message, resolve_format
from ..state import get_state

app = typer.Typer(no_args_is_help=True)

# OpenAPI operationId -> command name.
OPERATIONS: dict[str, str] = {
    "readAllWorkspaceSettings": "list",
    "readWorkspaceSettings": "get",
    "writeWorkspaceSetting": "set",
    "deleteWorkspaceSetting": "reset",
}

#: Setting keys the API accepts (the ``key`` enum shared by GET /settings/{key},
#: POST /settings and DELETE /settings).
SETTING_KEYS: tuple[str, ...] = (
    "orgDescription",
    "dealDetectionEnabled",
    "dealDetectionPrompt",
    "dealSummaryEnabled",
    "dealSummaryPrompt",
    "dealFieldUpdatesEnabled",
    "meetingRecordingScope",
    "lockMeetingRecordingScope",
    "meetingPrepScope",
    "publishMeetingPrepToCalendar",
    "meetingSummaryEnabled",
    "meetingTemplates",
    "meetingTaskScope",
    "companyEmailDomains",
    "meetingRecorderName",
    "enableRecorderBackground",
    "meetingRecorderBackground",
    "meetingVideoStorageDisabled",
    "externalMeetingSummaryEnabled",
    "billingOveragesDisabled",
    "billingOverageSpendLimitDollars",
    "billingSeatSpendLimitsEnabled",
    "billingSeatSpendLimitCredits",
    "billingSeatSpendLimitCreditsUserOverrides",
    "billingUseLegacyPricing",
    "advancedEnrichmentsOverride",
    "maxActiveCampaignsOverride",
    "maxCustomObjectsOverride",
    "maxConnectedAccountsOverride",
    "reverseTrialEndOverride",
    "freeWorkspaceCreditLimitOverride",
    "enablePrivateMeetingIngestion",
    "enableZeroParticipantMeetingIngestion",
    "enableAttachmentIngestion",
    "emailLocalParts",
    "excludeInternalIngestion",
    "ingestionRules",
    "ingestionRecordCreation",
    "emailBrandingFooter",
    "historicalSyncPeriodDays",
    "closedWonDealStage",
    "closedLostDealStage",
    "fiscalYearOffset",
)

KeyArg = Annotated[
    str, typer.Argument(help="Setting key, e.g. orgDescription (camelCase).", metavar="KEY")
]


def normalize_key(key: str) -> str:
    """Return the canonical spelling of ``key`` or raise a usage error listing valid keys."""
    if key in SETTING_KEYS:
        return key
    folded = {k.lower(): k for k in SETTING_KEYS}
    if key.lower() in folded:
        return folded[key.lower()]
    close = difflib.get_close_matches(key, SETTING_KEYS, n=3, cutoff=0.6)
    hint = ""
    if close:
        hint = "Did you mean " + ", ".join(close) + "? "
    hint += "Allowed keys: " + ", ".join(SETTING_KEYS)
    raise UsageError(f"Unknown setting key {key!r}.", hint=hint)


def parse_value(text: str) -> Any:
    """Interpret a VALUE argument: ``@file``/``-`` load JSON, otherwise JSON-if-it-parses."""
    if text == "-" or text.startswith("@"):
        return load_json(text, what="value")
    return coerce_scalar(text)


def as_rows(settings: Any) -> Any:
    """Reshape ``{key: value, ...}`` into ``{"data": [{"key", "value"}, ...]}`` for tables."""
    if not isinstance(settings, dict):
        return settings
    return {"data": [{"key": key, "value": value} for key, value in settings.items()]}


@app.command("list")
def list_settings(ctx: typer.Context) -> None:
    """List all workspace settings (GET /settings).

    Defaults are applied for settings the workspace has not overridden. JSON output
    is the API's `{key: value}` object verbatim; table, CSV, and NDJSON output show
    one `key`/`value` row per setting. Example:

        clarify settings list -o table
    """
    state = get_state(ctx)
    body = state.client().get("/settings")
    if resolve_format(state) is OutputFormat.json:
        emit(state, body)
    else:
        emit(state, as_rows(body))


@app.command("get")
def get_setting(ctx: typer.Context, key: KeyArg) -> None:
    """Show one setting's value, or its default (GET /settings/{key})."""
    state = get_state(ctx)
    key = normalize_key(key)
    emit(state, state.client().get(f"/settings/{key}"))


@app.command("set")
def set_setting(
    ctx: typer.Context,
    key: KeyArg,
    value: Annotated[
        str,
        typer.Argument(
            help=(
                "New value. Parsed as JSON when possible (true, 42, '[\"a\"]', '{...}'); "
                "otherwise a string. Use @file or - to load JSON from a file or stdin. "
                "Quote as JSON ('\"42\"') to force a string."
            ),
            metavar="VALUE",
        ),
    ],
) -> None:
    """Write a workspace setting (POST /settings).

    Read-only settings are rejected by the API and some require admin permissions.
    Examples:

        clarify settings set orgDescription "Acme builds industrial hardware."
        clarify settings set dealDetectionEnabled true
        clarify settings set ingestionRules @rules.json
    """
    state = get_state(ctx)
    key = normalize_key(key)
    payload = {"key": key, "value": parse_value(value)}
    body = state.client().post("/settings", json_body=payload, silent=state.silent)
    if body is None or body == {}:
        emit_message(f"Setting {key} updated.")
        return
    emit(state, body)


@app.command("reset")
def reset_setting(ctx: typer.Context, key: KeyArg) -> None:
    """Reset a setting to its default (DELETE /settings).

    Asks for confirmation unless --yes is given. Sends `{"key": KEY}` as the
    request body. Example:

        clarify settings reset orgDescription --yes
    """
    state = get_state(ctx)
    key = normalize_key(key)
    state.confirm(f"Reset setting {key} to its default?")
    body = state.client().delete("/settings", json_body={"key": key}, silent=state.silent)
    if body is None or body == {}:
        emit_message(f"Setting {key} reset to its default.")
        return
    emit(state, body)
