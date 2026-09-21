"""Turn a customer deal into a partner deal (``records convert-partner-deal``).

The work is split so the plan can be unit-tested from recorded JSON:

- :func:`fetch_context` reads the deal, its company, its people, and its tasks.
- :func:`build_plan` is pure: context + flags -> the partner deal to create, the
  contacts to link, the open tasks to re-point, what happens to the original,
  and the exact API requests that would do it.
- :func:`apply_plan` sends those requests in order, filling in the new record's
  ID once the create has returned.

Emails and meetings are never touched: they hang off people and companies, so
they stay visible from the partner deal through the shared contacts.
"""

from __future__ import annotations

import copy
import datetime as dt
from typing import Any

from .client import ClarifyClient
from .errors import ClarifyError, UsageError

PARTNER_OBJECT = "c_partner_deal"
CLOSED_STAGE = "Closed Disqualified"
#: Task statuses that count as finished; those tasks stay on the original deal.
CLOSED_TASK_STATUSES = frozenset({"Done", "Canceled"})
#: Stands in for the partner deal's ID in planned requests until the create returns.
NEW_ID = "{partner_deal_id}"

# Enum values of the c_partner_deal object (workspace schema, verified 2026-09-21).
# The API rejects anything else, so a stale list fails loudly rather than silently.
PARTNER_TYPES: tuple[str, ...] = (
    "Reseller / VAR",
    "MSSP / MSP",
    "Consultant / vCISO",
    "Technology Partner",
    "Distributor",
    "Strategic Alliance",
    "Referral Partner",
)
PARTNER_LEAD_SOURCES: frozenset[str] = frozenset(
    {"Inbound (Web)", "Event / Conference", "Referral", "Outbound", "Other"}
)
PARTNER_STAGES: frozenset[str] = frozenset(
    {"Prospecting", "Discovery", "Demo", "Partner Agreement", "Enablement", "Selling"}
)


# -- reading -------------------------------------------------------------------


def fetch_context(client: ClarifyClient, deal_id: str) -> dict[str, Any]:
    """Read everything the plan needs: the deal (+company), its people, and its tasks."""
    document = client.get(f"/objects/deal/resources/{deal_id}", params=[("include", "company_id")])
    if not isinstance(document, dict) or not isinstance(document.get("data"), dict):
        raise ClarifyError(f"Unexpected response reading deal {deal_id}.")
    included = document.get("included") or []
    company = next(
        (item for item in included if isinstance(item, dict) and item.get("type") == "company"),
        None,
    )
    people = client.collect(
        f"/objects/deal/records/{deal_id}/relationships/people", limit=None, all_pages=True
    )["data"]
    tasks = client.collect(
        "/objects/task/resources",
        [("filter[deal_id]", deal_id)],
        limit=None,
        all_pages=True,
    )["data"]
    return {"deal": document["data"], "company": company, "people": people, "tasks": tasks}


# -- planning ------------------------------------------------------------------


def build_plan(
    context: dict[str, Any],
    *,
    partner_type: str,
    close_reason: str | None = None,
    delete_original: bool = False,
    today: dt.date | None = None,
) -> dict[str, Any]:
    """Describe the conversion without performing it.

    Returns a JSON-serialisable plan with the field mapping (``partner_deal``),
    the contacts and open tasks that move, the fate of the original deal, human
    notes about anything that could not be carried over, and ``requests``: the
    ordered API calls, with :data:`NEW_ID` where the created record's ID goes.
    """
    if close_reason is not None and delete_original:
        raise UsageError("--close-original and --delete-original are mutually exclusive.")
    if partner_type not in PARTNER_TYPES:
        raise UsageError(
            f"Unknown partner type {partner_type!r}.",
            hint="One of: " + ", ".join(PARTNER_TYPES),
        )
    deal = context["deal"]
    if deal.get("type") != "deal":
        raise UsageError(f"{deal.get('id')} is a {deal.get('type')}, not a deal.")
    attrs = deal.get("attributes") or {}
    deal_id = deal["id"]
    if attrs.get("partner_id"):
        raise UsageError(
            f"Deal {deal_id} is a customer deal sold through partner {attrs['partner_id']}; "
            "that is not a partner relationship to move.",
            hint="Only convert deals whose company IS the partner.",
        )
    company = context.get("company")
    company_id = attrs.get("company_id")
    if not company_id:
        raise UsageError(
            f"Deal {deal_id} has no company; a partner deal needs partner_id.",
            hint="Set the deal's company first: clarify records update deal ID --set company_id=…",
        )
    company_name = (company or {}).get("attributes", {}).get("name") or attrs.get("name")
    notes: list[str] = []

    lead_source = attrs.get("lead_source")
    if lead_source is not None and lead_source not in PARTNER_LEAD_SOURCES:
        notes.append(f"lead_source {lead_source!r} does not exist on {PARTNER_OBJECT}; left empty.")
        lead_source = None

    stage = attrs.get("stage")
    if stage is not None and stage not in PARTNER_STAGES:
        notes.append(f"stage {stage!r} does not exist on {PARTNER_OBJECT}; left empty.")
        stage = None

    when = (today or dt.datetime.now(dt.UTC).date()).isoformat()
    provenance = f"Converted from deal {deal_id} on {when}."
    description = attrs.get("description")
    description = f"{description.rstrip()}\n\n{provenance}" if description else provenance

    partner_attributes: dict[str, Any] = {
        "name": company_name,
        "stage": stage,
        "owner_id": attrs.get("owner_id"),
        "partner_id": company_id,
        "partner_type": partner_type,
        "lead_source": lead_source,
        "description": description,
    }

    contacts = [
        {"id": person["id"], "name": _person_name(person)}
        for person in context.get("people") or []
        if isinstance(person, dict) and person.get("id")
    ]
    open_tasks: list[dict[str, Any]] = []
    closed_tasks: list[dict[str, Any]] = []
    for task in context.get("tasks") or []:
        if not isinstance(task, dict) or not task.get("id"):
            continue
        task_attrs = task.get("attributes") or {}
        entry = {
            "id": task["id"],
            "title": task_attrs.get("title"),
            "status": task_attrs.get("status"),
        }
        (closed_tasks if entry["status"] in CLOSED_TASK_STATUSES else open_tasks).append(entry)
    if closed_tasks:
        notes.append(
            f"{len(closed_tasks)} finished task(s) stay on the original deal: "
            + ", ".join(t["id"] for t in closed_tasks)
        )

    if delete_original:
        original: dict[str, Any] = {"action": "delete"}
    elif close_reason is not None:
        original = {"action": "close", "stage": CLOSED_STAGE, "disqualified_reason": close_reason}
    else:
        original = {"action": "keep"}
        notes.append("The original deal is left as is (use --close-original or --delete-original).")

    requests: list[dict[str, Any]] = [
        {
            "method": "POST",
            "path": f"/objects/{PARTNER_OBJECT}/records",
            "body": {"data": {"type": PARTNER_OBJECT, "attributes": partner_attributes}},
        }
    ]
    if contacts:
        requests.append(
            {
                "method": "PATCH",
                "path": f"/objects/{PARTNER_OBJECT}/records/{NEW_ID}/relationships/contacts",
                "body": {"data": [{"type": "person", "id": c["id"]} for c in contacts]},
            }
        )
    if open_tasks:
        requests.append(
            {
                "method": "PATCH",
                "path": "/objects/task/records",
                "body": {
                    "data": [
                        {
                            "type": "task",
                            "id": t["id"],
                            "attributes": {"c_partner_deal_id": NEW_ID, "deal_id": None},
                        }
                        for t in open_tasks
                    ]
                },
            }
        )
    if original["action"] == "close":
        requests.append(
            {
                "method": "PATCH",
                "path": f"/objects/deal/records/{deal_id}",
                "body": {
                    "data": {
                        "type": "deal",
                        "id": deal_id,
                        "attributes": {
                            "stage": CLOSED_STAGE,
                            "disqualified_reason": close_reason,
                        },
                    }
                },
            }
        )
    elif original["action"] == "delete":
        requests.append({"method": "DELETE", "path": f"/objects/deal/records/{deal_id}"})

    summary = attrs.get("summary")
    return {
        "deal": {
            "id": deal_id,
            "name": attrs.get("name"),
            "stage": attrs.get("stage"),
            "owner_id": attrs.get("owner_id"),
            "company_id": company_id,
            "company_name": company_name,
            "lead_source": attrs.get("lead_source"),
            "summary": summary if isinstance(summary, str) else None,
        },
        "partner_deal": {"type": PARTNER_OBJECT, "attributes": partner_attributes},
        "contacts": contacts,
        "tasks": open_tasks,
        "skipped_tasks": closed_tasks,
        "original": original,
        "notes": notes,
        "requests": requests,
    }


def render_plan(plan: dict[str, Any]) -> str:
    """A readable dry-run summary for terminals (JSON goes to pipes)."""
    deal = plan["deal"]
    lines = [
        f"Convert deal {deal['id']} ({deal['name']!s}, stage {deal['stage']!s}) "
        f"into a {PARTNER_OBJECT}:",
        "",
        "  partner deal",
    ]
    for key, value in plan["partner_deal"]["attributes"].items():
        text = value if isinstance(value, str) else ("" if value is None else str(value))
        if key == "description" and "\n" in text:
            text = text.replace("\n", "\n" + " " * 18)
        lines.append(f"    {key:<14} {text}")
    lines.append("")
    lines.append(f"  contacts ({len(plan['contacts'])})")
    lines.extend(f"    {c['id']}  {c['name']}" for c in plan["contacts"])
    lines.append("")
    lines.append(f"  open tasks re-pointed ({len(plan['tasks'])})")
    lines.extend(f"    {t['id']}  [{t['status']}] {t['title']}" for t in plan["tasks"])
    lines.append("")
    original = plan["original"]
    if original["action"] == "close":
        fate = f"set to {original['stage']} (reason: {original['disqualified_reason']})"
    elif original["action"] == "delete":
        fate = "DELETED"
    else:
        fate = "kept unchanged"
    lines.append(f"  original deal: {fate}")
    if plan["notes"]:
        lines.append("")
        lines.append("  notes")
        lines.extend(f"    - {note}" for note in plan["notes"])
    lines.append("")
    lines.append(f"  requests ({len(plan['requests'])})")
    lines.extend(f"    {r['method']:<6} {r['path']}" for r in plan["requests"])
    lines.append("")
    lines.append("Dry run: nothing was sent. Re-run with --apply to perform it.")
    return "\n".join(lines)


# -- applying ------------------------------------------------------------------


def apply_plan(client: ClarifyClient, plan: dict[str, Any], *, silent: bool) -> dict[str, Any]:
    """Send the plan's requests in order; the first one creates the partner deal.

    Returns ``{"partner_deal_id": ..., "partner_deal": <created resource>,
    "requests": [...]}``. If a later request fails the error names the partner
    deal that already exists and the steps that completed, so the rest can be
    finished by hand instead of creating a duplicate.
    """
    requests = plan["requests"]
    created = client.post(requests[0]["path"], requests[0]["body"], silent=silent)
    data = created.get("data") if isinstance(created, dict) else None
    new_id = data.get("id") if isinstance(data, dict) else None
    if not new_id:
        raise ClarifyError(
            f"Created the {PARTNER_OBJECT} but the response carried no id.",
            hint="Check the workspace for the new record before retrying.",
        )
    done: list[dict[str, Any]] = [{"method": "POST", "path": requests[0]["path"], "id": new_id}]
    for request in requests[1:]:
        path = request["path"].replace(NEW_ID, new_id)
        body = _fill(request.get("body"), new_id)
        try:
            client.json(request["method"], path, json_body=body, silent=silent)
        except ClarifyError as exc:
            steps = ", ".join(f"{d['method']} {d['path']}" for d in done)
            raise ClarifyError(
                f"{exc.message}\nPartner deal {new_id} was created and these steps completed: "
                f"{steps}. Failed at {request['method']} {path}.",
                exit_code=exc.exit_code,
                hint="Finish the remaining steps by hand; do not re-run --apply "
                "(it would create a second partner deal).",
            ) from exc
        done.append({"method": request["method"], "path": path})
    return {"partner_deal_id": new_id, "partner_deal": data, "requests": done}


# -- helpers -------------------------------------------------------------------


def _person_name(person: dict[str, Any]) -> str:
    attrs = person.get("attributes") or {}
    name = attrs.get("name")
    if isinstance(name, dict):
        full = name.get("full_name") or " ".join(
            part for part in (name.get("first_name"), name.get("last_name")) if part
        )
        if full:
            return str(full)
    elif isinstance(name, str) and name:
        return name
    emails = attrs.get("email_addresses")
    if isinstance(emails, dict) and emails.get("items"):
        return str(emails["items"][0])
    return str(person.get("id"))


def _fill(value: Any, new_id: str) -> Any:
    """Replace :data:`NEW_ID` anywhere inside a planned request body."""
    if isinstance(value, str):
        return value.replace(NEW_ID, new_id)
    if isinstance(value, list):
        return [_fill(v, new_id) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v, new_id) for k, v in value.items()}
    return copy.copy(value)
