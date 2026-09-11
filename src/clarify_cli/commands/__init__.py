"""Command-group registry: (CLI name, module name, help)."""

from __future__ import annotations

GROUPS: list[tuple[str, str, str]] = [
    ("auth", "auth", "Log in, check status, and log out."),
    ("config", "config_cmd", "Read and write the CLI config file."),
    ("api", "api", "Call any API endpoint directly."),
    ("records", "records", "Create, read, update, and delete records of any object."),
    ("lists", "lists", "Manage lists and export their rows."),
    ("schemas", "schemas", "Inspect and modify object schemas."),
    ("activities", "activities", "Read a record's activity feed."),
    ("relationships", "relationships", "Manage links between records."),
    ("attachments", "attachments", "Manage files attached to records."),
    ("access", "access", "Manage per-record access grants."),
    ("object-access", "object_access", "Manage entity-wide access delegations."),
    ("comments", "comments", "Create, read, update, and delete comments."),
    ("layouts", "layouts", "Read, update, and reset layouts."),
    ("meetings", "meetings", "Meeting recordings and transcripts."),
    ("campaigns", "campaigns", "Campaign recipients and engagement."),
    ("workflows", "workflows", "Manage workflows and sequences."),
    ("settings", "settings", "Read and write workspace settings."),
    ("users", "users", "List and inspect workspace users."),
]
