"""Plan builder for ``records convert-partner-deal``, driven by recorded fixtures.

The fixtures under ``tests/fixtures/partner_conversion/`` are the three reads the
command makes, captured from a live workspace with identities replaced. No
request leaves this module: everything here is pure.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

import pytest

from clarify_cli import partner_conversion as pc
from clarify_cli.errors import UsageError

FIXTURES = Path(__file__).parent / "fixtures" / "partner_conversion"
DEAL_ID = "d1000000-0000-4000-8000-000000000001"
COMPANY_ID = "c1000000-0000-4000-8000-000000000001"
OPEN_TASK = "t1000000-0000-4000-8000-000000000001"
DONE_TASK = "t1000000-0000-4000-8000-000000000002"
TODAY = dt.date(2026, 9, 21)


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def context():
    deal_doc = load("deal.json")
    return {
        "deal": deal_doc["data"],
        "company": deal_doc["included"][0],
        "people": load("people.json")["data"],
        "tasks": load("tasks.json")["data"],
    }


def test_plan_maps_deal_fields_onto_partner_deal(context):
    plan = pc.build_plan(context, partner_type="Reseller / VAR", today=TODAY)
    assert plan["partner_deal"] == {
        "type": "c_partner_deal",
        "attributes": {
            "name": "Northwind Partners",
            "stage": "Prospecting",
            "owner_id": "user_01OWNER00000000000000000000",
            "partner_id": COMPANY_ID,
            "partner_type": "Reseller / VAR",
            "lead_source": None,
            "description": (
                "Inbound demo request from Pat Example (Principal Architect). "
                "Exploring a resale partnership.\n\n"
                f"Converted from deal {DEAL_ID} on 2026-09-21."
            ),
        },
    }
    assert plan["deal"] == {
        "id": DEAL_ID,
        "name": "Northwind Partners - Demo Request",
        "stage": "Prospecting",
        "owner_id": "user_01OWNER00000000000000000000",
        "company_id": COMPANY_ID,
        "company_name": "Northwind Partners",
        "lead_source": "Partner / Channel",
        "summary": None,
    }


def test_plan_drops_lead_source_missing_on_partner_object_and_says_so(context):
    plan = pc.build_plan(context, partner_type="Reseller / VAR", today=TODAY)
    assert plan["partner_deal"]["attributes"]["lead_source"] is None
    assert any("lead_source 'Partner / Channel'" in note for note in plan["notes"])

    context["deal"]["attributes"]["lead_source"] = "Inbound (Web)"
    plan = pc.build_plan(context, partner_type="Reseller / VAR", today=TODAY)
    assert plan["partner_deal"]["attributes"]["lead_source"] == "Inbound (Web)"
    assert not any("lead_source" in note for note in plan["notes"])


def test_plan_carries_stage_only_when_it_exists_on_partner_object(context):
    context["deal"]["attributes"]["stage"] = "Tech Evaluation"
    plan = pc.build_plan(context, partner_type="MSSP / MSP", today=TODAY)
    assert plan["partner_deal"]["attributes"]["stage"] is None
    assert any("stage 'Tech Evaluation'" in note for note in plan["notes"])


def test_plan_description_is_only_provenance_when_deal_has_none(context):
    context["deal"]["attributes"]["description"] = None
    plan = pc.build_plan(context, partner_type="Distributor", today=TODAY)
    assert (
        plan["partner_deal"]["attributes"]["description"]
        == f"Converted from deal {DEAL_ID} on 2026-09-21."
    )


def test_plan_links_every_person_and_names_them(context):
    plan = pc.build_plan(context, partner_type="Reseller / VAR", today=TODAY)
    assert plan["contacts"] == [
        {"id": "p1000000-0000-4000-8000-000000000001", "name": "Pat Example"},
        {"id": "p1000000-0000-4000-8000-000000000002", "name": "sam@northwind.example"},
    ]


def test_plan_repoints_open_tasks_and_leaves_finished_ones(context):
    plan = pc.build_plan(context, partner_type="Reseller / VAR", today=TODAY)
    assert plan["tasks"] == [
        {"id": OPEN_TASK, "title": "Follow up: Pat Example demo request", "status": "To Do"}
    ]
    assert plan["skipped_tasks"] == [
        {"id": DONE_TASK, "title": "Book capabilities demo", "status": "Done"}
    ]
    assert any(DONE_TASK in note for note in plan["notes"])


def test_plan_requests_default_keep_original(context):
    plan = pc.build_plan(context, partner_type="Reseller / VAR", today=TODAY)
    assert plan["original"] == {"action": "keep"}
    assert [(r["method"], r["path"]) for r in plan["requests"]] == [
        ("POST", "/objects/c_partner_deal/records"),
        ("PATCH", "/objects/c_partner_deal/records/{partner_deal_id}/relationships/contacts"),
        ("PATCH", "/objects/task/records"),
    ]
    create, contacts, tasks = plan["requests"]
    assert create["body"] == {"data": plan["partner_deal"]}
    assert contacts["body"] == {
        "data": [
            {"type": "person", "id": "p1000000-0000-4000-8000-000000000001"},
            {"type": "person", "id": "p1000000-0000-4000-8000-000000000002"},
        ]
    }
    assert tasks["body"] == {
        "data": [
            {
                "type": "task",
                "id": OPEN_TASK,
                "attributes": {"c_partner_deal_id": "{partner_deal_id}", "deal_id": None},
            }
        ]
    }


def test_plan_close_original(context):
    plan = pc.build_plan(
        context, partner_type="Reseller / VAR", close_reason="Partner, not a customer", today=TODAY
    )
    assert plan["original"] == {
        "action": "close",
        "stage": "Closed Disqualified",
        "disqualified_reason": "Partner, not a customer",
    }
    last = plan["requests"][-1]
    assert (last["method"], last["path"]) == ("PATCH", f"/objects/deal/records/{DEAL_ID}")
    assert last["body"] == {
        "data": {
            "type": "deal",
            "id": DEAL_ID,
            "attributes": {
                "stage": "Closed Disqualified",
                "disqualified_reason": "Partner, not a customer",
            },
        }
    }


def test_plan_delete_original(context):
    plan = pc.build_plan(context, partner_type="Reseller / VAR", delete_original=True, today=TODAY)
    assert plan["original"] == {"action": "delete"}
    assert plan["requests"][-1] == {
        "method": "DELETE",
        "path": f"/objects/deal/records/{DEAL_ID}",
    }


def test_plan_skips_empty_link_and_task_requests(context):
    context["people"] = []
    context["tasks"] = [t for t in context["tasks"] if t["id"] == DONE_TASK]
    plan = pc.build_plan(context, partner_type="Reseller / VAR", today=TODAY)
    assert [r["method"] for r in plan["requests"]] == ["POST"]
    assert plan["contacts"] == [] and plan["tasks"] == []


def test_plan_rejects_close_and_delete_together(context):
    with pytest.raises(UsageError, match="mutually exclusive"):
        pc.build_plan(
            context, partner_type="Reseller / VAR", close_reason="x", delete_original=True
        )


def test_plan_rejects_unknown_partner_type(context):
    with pytest.raises(UsageError, match="Unknown partner type"):
        pc.build_plan(context, partner_type="Friend")


def test_plan_refuses_deal_sold_through_a_partner(context):
    context["deal"]["attributes"]["partner_id"] = "c2000000-0000-4000-8000-000000000009"
    with pytest.raises(UsageError, match="sold through partner"):
        pc.build_plan(context, partner_type="Reseller / VAR")


def test_plan_refuses_deal_without_company(context):
    context["deal"]["attributes"]["company_id"] = None
    context["company"] = None
    with pytest.raises(UsageError, match="has no company"):
        pc.build_plan(context, partner_type="Reseller / VAR")


def test_plan_refuses_non_deal_resource(context):
    context["deal"]["type"] = "company"
    with pytest.raises(UsageError, match="not a deal"):
        pc.build_plan(context, partner_type="Reseller / VAR")


def test_plan_is_json_serialisable_and_does_not_mutate_context(context):
    before = copy.deepcopy(context)
    plan = pc.build_plan(context, partner_type="Reseller / VAR", close_reason="x", today=TODAY)
    json.dumps(plan)
    assert context == before


def test_render_plan_lists_mapping_contacts_tasks_and_requests(context):
    plan = pc.build_plan(
        context, partner_type="Reseller / VAR", close_reason="Partner, not a customer", today=TODAY
    )
    text = pc.render_plan(plan)
    assert text.startswith(f"Convert deal {DEAL_ID} (Northwind Partners - Demo Request, ")
    assert "partner_type   Reseller / VAR" in text
    assert "Pat Example" in text and "sam@northwind.example" in text
    assert f"{OPEN_TASK}  [To Do] Follow up: Pat Example demo request" in text
    assert DONE_TASK not in text.split("notes")[0]
    assert "original deal: set to Closed Disqualified (reason: Partner, not a customer)" in text
    assert "POST   /objects/c_partner_deal/records" in text
    assert text.endswith("Dry run: nothing was sent. Re-run with --apply to perform it.")


def test_render_plan_delete_and_keep_wording(context):
    keep = pc.render_plan(pc.build_plan(context, partner_type="Distributor", today=TODAY))
    assert "original deal: kept unchanged" in keep
    delete = pc.render_plan(
        pc.build_plan(context, partner_type="Distributor", delete_original=True, today=TODAY)
    )
    assert "original deal: DELETED" in delete
    assert f"DELETE /objects/deal/records/{DEAL_ID}" in delete


def test_fill_replaces_placeholder_everywhere():
    body = {"data": [{"attributes": {"c_partner_deal_id": pc.NEW_ID, "deal_id": None, "n": 1}}]}
    assert pc._fill(body, "new") == {
        "data": [{"attributes": {"c_partner_deal_id": "new", "deal_id": None, "n": 1}}]
    }
    assert body["data"][0]["attributes"]["c_partner_deal_id"] == pc.NEW_ID


@pytest.mark.parametrize(
    ("attributes", "expected"),
    [
        ({"name": {"full_name": "Pat Example"}}, "Pat Example"),
        ({"name": {"first_name": "Pat", "last_name": "Example"}}, "Pat Example"),
        ({"name": "Pat Example"}, "Pat Example"),
        ({"name": None, "email_addresses": {"items": ["pat@x.example"]}}, "pat@x.example"),
        ({}, "p9"),
    ],
)
def test_person_name_fallbacks(attributes, expected):
    assert pc._person_name({"id": "p9", "attributes": attributes}) == expected
