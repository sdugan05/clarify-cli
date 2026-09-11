from __future__ import annotations

import json

import httpx

from helpers import json_body, page, query_pairs, resource

SCHEMAS = "/workspaces/acme/schemas"  # respx route (relative to the base URL)
PATH = "/v1" + SCHEMAS  # what request.url.path reports
PROJECT_ID = "https://getclarify.ai/schemas/entities/c_project"
PERSON_ID = "https://getclarify.ai/schemas/entities/person"
CORE_ID = "https://getclarify.ai/schemas/core/collectionOfIds"


def plain(text: str) -> str:
    """Collapse Typer's wrapped error panel into one line for substring checks."""
    return " ".join(text.replace("│", " ").split())


def project_schema() -> dict:
    return {
        "id": PROJECT_ID,
        "type": "schema",
        "attributes": {
            "$schema": "https://json-schema.org/draft/2020-12/clarify",
            "$id": PROJECT_ID,
            "title": "Project",
            "type": "object",
            "xClarifyLabel": {"singular": "Project", "plural": "Projects"},
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "title": "Name", "xClarifyPrimary": True},
                "status": {
                    "type": ["string", "null"],
                    "title": "Status",
                    "enum": ["Planning", "Complete"],
                },
                "company_id": {
                    "type": ["string", "null"],
                    "title": "Company",
                    "xClarifyRelationship": {
                        "kind": "many-to-one",
                        "entity": "company",
                        "field": "projects",
                    },
                    "xClarifyPresentation": {"rank": 3, "hiddenInDetails": True},
                },
                "members": {
                    "title": "Members",
                    "oneOf": [{"$ref": CORE_ID}, {"type": "null"}],
                    "xClarifyRelationship": {
                        "kind": "many-to-many",
                        "entity": "person",
                        "field": "projects",
                    },
                },
                "code": {"type": ["string", "null"], "title": "Code", "xClarifyUnique": True},
            },
        },
    }


def person_schema() -> dict:
    return {
        "id": PERSON_ID,
        "type": "schema",
        "attributes": {
            "$id": PERSON_ID,
            "title": "Person",
            "type": "object",
            "xClarifyLabel": {"singular": "Person", "plural": "People"},
            "properties": {"name": {"type": "object"}, "email_addresses": {"type": "object"}},
        },
    }


def core_schema() -> dict:
    return {"id": CORE_ID, "type": "schema", "attributes": {"$id": CORE_ID, "type": "array"}}


def schemas_body(*items: dict, next_url: str | None = None) -> dict:
    return {"links": {"next": next_url}, "data": list(items)}


def task_body() -> dict:
    return {
        "data": resource(
            "async-task", "task-1", type="schema_modification", metadata={"entity": "c_project"}
        )
    }


def mock_schemas(api, *items: dict):
    return api.get(SCHEMAS).mock(
        return_value=httpx.Response(200, json=schemas_body(*(items or (project_schema(),))))
    )


# -- list / objects / get / fields ----------------------------------------------
def test_list_json_is_verbatim_without_query(invoke, api):
    route = mock_schemas(api, project_schema(), core_schema())
    result = invoke("schemas", "list")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["data"] == [project_schema(), core_schema()]
    assert body["meta"] == {"returned": 2}
    assert "links" not in body
    request = route.calls.last.request
    assert request.method == "GET"
    assert request.url.path == PATH
    assert query_pairs(request) == []


def test_list_follows_next_links_verbatim(invoke, api):
    base = "https://api.clarify.ai/v1" + SCHEMAS
    route = api.get(SCHEMAS).mock(
        side_effect=[
            httpx.Response(200, json=schemas_body(person_schema(), next_url=f"{base}?cursor=abc")),
            httpx.Response(200, json=schemas_body(project_schema())),
        ]
    )
    result = invoke("-o", "ndjson", "schemas", "list")
    assert result.exit_code == 0, result.output
    assert [json.loads(line)["id"] for line in result.stdout.splitlines()] == [
        PERSON_ID,
        PROJECT_ID,
    ]
    assert route.call_count == 2
    assert query_pairs(route.calls[0].request) == []
    assert query_pairs(route.calls[1].request) == [("cursor", "abc")]


def test_list_table_is_one_row_per_schema_with_field_count(invoke, api):
    mock_schemas(api, project_schema(), person_schema())
    result = invoke("-o", "csv", "schemas", "list")
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[0] == "id,name,title,fields"
    assert lines[1] == f"{PROJECT_ID},c_project,Project,5"
    assert lines[2] == f"{PERSON_ID},person,Person,2"


def test_objects_lists_entities_only(invoke, api):
    mock_schemas(api, core_schema(), project_schema(), person_schema())
    result = invoke("schemas", "objects")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert [item["id"] for item in body["data"]] == ["c_project", "person"]
    assert body["data"][0]["attributes"] == {
        "title": "Project",
        "plural": "Projects",
        "custom": True,
        "fields": 5,
    }
    assert body["data"][1]["attributes"]["custom"] is False
    assert body["meta"] == {"returned": 2}


def test_get_selects_schema_client_side(invoke, api):
    route = mock_schemas(api, person_schema(), project_schema())
    result = invoke("schemas", "get", "c_project")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"data": project_schema()}
    assert route.calls.last.request.url.path == PATH


def test_get_accepts_full_schema_id(invoke, api):
    mock_schemas(api, person_schema(), project_schema())
    result = invoke("schemas", "get", PERSON_ID)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["id"] == PERSON_ID


def test_get_missing_object_exit_4(invoke, api):
    mock_schemas(api, person_schema())
    result = invoke("schemas", "get", "c_missing")
    assert result.exit_code == 4
    assert "No schema found for object 'c_missing'" in plain(result.stderr)
    assert "clarify schemas objects" in plain(result.stderr)


def test_fields_table(invoke, api):
    mock_schemas(api, project_schema())
    result = invoke("-o", "csv", "schemas", "fields", "c_project")
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[0] == "id,title,type,required,unique,hidden,relationship"
    assert lines[1] == "name,Name,string,true,false,false,"
    assert lines[2] == "status,Status,string enum,false,false,false,"
    assert (
        lines[3] == "company_id,Company,string,false,false,true,company (many-to-one via projects)"
    )
    assert (
        lines[4]
        == "members,Members,collectionOfIds,false,false,false,person (many-to-many via projects)"
    )
    assert lines[5] == "code,Code,string,false,true,false,"


def test_fields_json_keeps_definition(invoke, api):
    mock_schemas(api, project_schema())
    result = invoke("schemas", "fields", "c_project")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["meta"] == {"returned": 5}
    status = body["data"][1]
    assert status["id"] == "status" and status["type"] == "field"
    assert (
        status["attributes"]["definition"] == project_schema()["attributes"]["properties"]["status"]
    )
    assert body["data"][0]["attributes"]["primary"] is True


def test_fields_missing_object_exit_4(invoke, api):
    mock_schemas(api, person_schema())
    result = invoke("schemas", "fields", "deal")
    assert result.exit_code == 4


# -- create-object ----------------------------------------------------------------
def test_create_object_from_flags(invoke, api):
    route = api.post(f"{SCHEMAS}/objects").mock(
        return_value=httpx.Response(201, json={"data": project_schema()})
    )
    result = invoke(
        "schemas",
        "create-object",
        "--name",
        "Project",
        "--plural",
        "Projects",
        "--description",
        "A project.",
        "--icon",
        "Briefcase",
        "--background-color",
        "blue",
        "--properties",
        '{"budget": {"type": ["number", "null"], "title": "Budget"}}',
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["id"] == PROJECT_ID
    request = route.calls.last.request
    assert request.method == "POST" and request.url.path == f"{PATH}/objects"
    assert query_pairs(request) == []
    assert json_body(request) == {
        "name": "Project",
        "plural": "Projects",
        "description": "A project.",
        "icon": "Briefcase",
        "backgroundColor": "blue",
        "properties": {"budget": {"type": ["number", "null"], "title": "Budget"}},
    }


def test_create_object_data_with_flag_override_and_silent(invoke, api):
    route = api.post(f"{SCHEMAS}/objects").mock(
        return_value=httpx.Response(201, json={"data": project_schema()})
    )
    result = invoke(
        "--silent",
        "schemas",
        "create-object",
        "-d",
        '{"name": "Old", "plural": "Projects", "icon": "Box"}',
        "--name",
        "Project",
    )
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {"name": "Project", "plural": "Projects", "icon": "Box"}


def test_create_object_requires_name_and_plural(invoke, api):
    route = api.post(f"{SCHEMAS}/objects")
    result = invoke("schemas", "create-object", "--name", "Project")
    assert result.exit_code == 2
    assert "--plural" in plain(result.stderr)
    assert not route.called


def test_create_object_conflict_exit_1(invoke, api):
    api.post(f"{SCHEMAS}/objects").mock(
        return_value=httpx.Response(
            422, json={"errors": [{"status": "422", "detail": "Object already exists"}]}
        )
    )
    result = invoke("schemas", "create-object", "--name", "Project", "--plural", "Projects")
    assert result.exit_code == 1
    assert "HTTP 422" in plain(result.stderr) and "Object already exists" in plain(result.stderr)


# -- replace ------------------------------------------------------------------------
def test_replace_puts_full_schema(invoke, api):
    route = api.put(f"{SCHEMAS}/objects/c_project").mock(
        return_value=httpx.Response(200, json=task_body())
    )
    document = project_schema()["attributes"]
    result = invoke("--silent", "schemas", "replace", "c_project", "-d", json.dumps(document))
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["type"] == "async-task"
    request = route.calls.last.request
    assert request.method == "PUT" and request.url.path == f"{PATH}/objects/c_project"
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == document


def test_replace_unwraps_get_output(invoke, api):
    route = api.put(f"{SCHEMAS}/objects/c_project").mock(
        return_value=httpx.Response(200, json=task_body())
    )
    result = invoke("schemas", "replace", "c_project", "-d", json.dumps({"data": project_schema()}))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == project_schema()["attributes"]


def test_replace_rejects_mismatched_id_before_request(invoke, api):
    route = api.put(f"{SCHEMAS}/objects/c_other")
    result = invoke(
        "schemas", "replace", "c_other", "-d", json.dumps(project_schema()["attributes"])
    )
    assert result.exit_code == 2
    assert "does not match object 'c_other'" in plain(result.stderr)
    assert "https://getclarify.ai/schemas/entities/c_other" in plain(result.stderr)
    assert not route.called


def test_replace_rejects_missing_id(invoke, api):
    route = api.put(f"{SCHEMAS}/objects/c_project")
    result = invoke("schemas", "replace", "c_project", "-d", '{"title": "Project"}')
    assert result.exit_code == 2
    assert not route.called


# -- delete-object ------------------------------------------------------------------
def test_delete_object_with_yes_emits_task(invoke, api):
    route = api.delete(f"{SCHEMAS}/objects/c_project").mock(
        return_value=httpx.Response(200, json=task_body())
    )
    result = invoke("--yes", "--silent", "schemas", "delete-object", "c_project")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["id"] == "task-1"
    request = route.calls.last.request
    assert request.method == "DELETE" and request.url.path == f"{PATH}/objects/c_project"
    assert query_pairs(request) == [("silent", "true")]


def test_delete_object_refuses_without_yes(invoke, api):
    route = api.delete(f"{SCHEMAS}/objects/c_project")
    result = invoke("schemas", "delete-object", "c_project")
    assert result.exit_code == 2
    assert "Refusing to continue without confirmation" in plain(result.stderr)
    assert not route.called


def test_delete_object_rejects_builtin(invoke, api):
    route = api.delete(f"{SCHEMAS}/objects/person")
    result = invoke("--yes", "schemas", "delete-object", "person")
    assert result.exit_code == 2
    assert "only c_* objects can be deleted" in plain(result.stderr)
    assert not route.called


def test_delete_object_422_exit_1(invoke, api):
    api.delete(f"{SCHEMAS}/objects/c_project").mock(
        return_value=httpx.Response(
            422, json={"errors": [{"status": "422", "detail": "Cannot delete this object"}]}
        )
    )
    result = invoke("-y", "schemas", "delete-object", "c_project")
    assert result.exit_code == 1
    assert "Cannot delete this object" in plain(result.stderr)


# -- add-fields ---------------------------------------------------------------------
def test_add_fields_from_field_specs(invoke, api):
    route = api.post(f"{SCHEMAS}/c_project/properties").mock(return_value=httpx.Response(202))
    result = invoke(
        "--silent",
        "schemas",
        "add-fields",
        "c_project",
        "--field",
        "budget=number",
        "--field",
        "is_active=boolean",
        "--field",
        "due=date",
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "Accepted" in plain(result.stderr) and "budget, is_active, due" in plain(result.stderr)
    request = route.calls.last.request
    assert request.method == "POST" and request.url.path == f"{PATH}/c_project/properties"
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {
        "data": {
            "type": "schema-properties",
            "attributes": {
                "budget": {"type": ["number", "null"], "title": "Budget"},
                "is_active": {"type": "boolean", "title": "Is active"},
                "due": {"type": ["date", "null"], "title": "Due"},
            },
        }
    }


def test_add_fields_from_bare_attributes_data(invoke, api):
    route = api.post(f"{SCHEMAS}/person/properties").mock(return_value=httpx.Response(202))
    result = invoke(
        "schemas",
        "add-fields",
        "person",
        "-d",
        '{"nickname": {"type": ["string", "null"], "title": "Nickname"}}',
        "--field",
        "score=integer",
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "data": {
            "type": "schema-properties",
            "attributes": {
                "nickname": {"type": ["string", "null"], "title": "Nickname"},
                "score": {"type": ["integer", "null"], "title": "Score"},
            },
        }
    }


def test_add_fields_full_document_passes_through(invoke, api):
    route = api.post(f"{SCHEMAS}/person/properties").mock(return_value=httpx.Response(202))
    document = {
        "data": {"type": "schema-properties", "attributes": {"x": {"type": ["string", "null"]}}}
    }
    result = invoke("schemas", "add-fields", "person", "-d", json.dumps(document))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == document


def test_add_fields_emits_body_when_api_returns_one(invoke, api):
    api.post(f"{SCHEMAS}/person/properties").mock(
        return_value=httpx.Response(200, json={"data": {"ok": True}})
    )
    result = invoke("schemas", "add-fields", "person", "--field", "x=string")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"data": {"ok": True}}


def test_add_fields_requires_input(invoke, api):
    route = api.post(f"{SCHEMAS}/person/properties")
    result = invoke("schemas", "add-fields", "person")
    assert result.exit_code == 2
    assert not route.called
    bad = invoke("schemas", "add-fields", "person", "--field", "budget")
    assert bad.exit_code == 2 and "NAME=TYPE" in plain(bad.stderr)


# -- add-relationships --------------------------------------------------------------
def test_add_relationships_wraps_attributes(invoke, api):
    route = api.post(f"{SCHEMAS}/c_project/relationships").mock(return_value=httpx.Response(202))
    attrs = {
        "c_project": {
            "company_id": {
                "title": "Company",
                "type": ["string", "null"],
                "xClarifyRelationship": {
                    "kind": "many-to-one",
                    "entity": "company",
                    "field": "projects",
                },
            }
        },
        "company": {
            "projects": {
                "title": "Projects",
                "oneOf": [{"$ref": CORE_ID}, {"type": "null"}],
                "xClarifyRelationship": {
                    "kind": "one-to-many",
                    "entity": "c_project",
                    "field": "company_id",
                },
            }
        },
    }
    result = invoke(
        "--silent", "schemas", "add-relationships", "c_project", "-d", json.dumps(attrs)
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == "" and "Accepted" in plain(result.stderr)
    request = route.calls.last.request
    assert request.method == "POST"
    assert request.url.path == f"{PATH}/c_project/relationships"
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {"data": {"type": "relationship", "attributes": attrs}}


def test_add_relationships_full_document_and_invalid(invoke, api):
    route = api.post(f"{SCHEMAS}/c_project/relationships").mock(return_value=httpx.Response(202))
    document = {"data": {"type": "relationship", "attributes": {"company": {"p": {}}}}}
    result = invoke("schemas", "add-relationships", "c_project", "-d", json.dumps(document))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == document
    bad = invoke("schemas", "add-relationships", "c_project", "-d", "[]")
    assert bad.exit_code == 2
    assert route.call_count == 1


# -- delete-relationship ------------------------------------------------------------
def test_delete_relationship_with_yes(invoke, api):
    route = api.delete(f"{SCHEMAS}/c_project/relationships/company_id").mock(
        return_value=httpx.Response(200, json=task_body())
    )
    result = invoke("-y", "--silent", "schemas", "delete-relationship", "c_project", "company_id")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["type"] == "async-task"
    request = route.calls.last.request
    assert request.method == "DELETE"
    assert request.url.path == f"{PATH}/c_project/relationships/company_id"
    assert query_pairs(request) == [("silent", "true")]


def test_delete_relationship_refuses_without_yes(invoke, api):
    route = api.delete(f"{SCHEMAS}/c_project/relationships/company_id")
    result = invoke("schemas", "delete-relationship", "c_project", "company_id")
    assert result.exit_code == 2
    assert not route.called


# -- reorder ------------------------------------------------------------------------
def test_reorder_from_order_option(invoke, api):
    route = api.patch(f"{SCHEMAS}/c_project/fields-order").mock(return_value=httpx.Response(202))
    result = invoke(
        "--silent", "schemas", "reorder", "c_project", "--order", "name, status,company_id"
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == "" and "Accepted" in plain(result.stderr)
    request = route.calls.last.request
    assert request.method == "PATCH" and request.url.path == f"{PATH}/c_project/fields-order"
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {
        "data": {
            "type": "schema-property-order",
            "attributes": {"order": ["name", "status", "company_id"]},
        }
    }


def test_reorder_from_data_variants(invoke, api):
    route = api.patch(f"{SCHEMAS}/c_project/fields-order").mock(return_value=httpx.Response(202))
    expected = {"data": {"type": "schema-property-order", "attributes": {"order": ["a", "b"]}}}
    for data in ('["a", "b"]', '{"order": ["a", "b"]}', json.dumps(expected)):
        result = invoke("schemas", "reorder", "c_project", "-d", data)
        assert result.exit_code == 0, result.output
        assert json_body(route.calls.last.request) == expected


def test_reorder_requires_order(invoke, api):
    route = api.patch(f"{SCHEMAS}/c_project/fields-order")
    assert invoke("schemas", "reorder", "c_project").exit_code == 2
    assert invoke("schemas", "reorder", "c_project", "--order", " , ").exit_code == 2
    both = invoke("schemas", "reorder", "c_project", "--order", "a", "-d", '["a"]')
    assert both.exit_code == 2
    assert not route.called


# -- visibility ---------------------------------------------------------------------
def test_visibility_builds_hidden_map(invoke, api):
    route = api.patch(f"{SCHEMAS}/c_project/fields-visibility").mock(
        return_value=httpx.Response(202)
    )
    result = invoke(
        "--silent",
        "schemas",
        "visibility",
        "c_project",
        "--hide",
        "budget",
        "--hide",
        "code",
        "--show",
        "status",
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == "" and "Accepted" in plain(result.stderr)
    request = route.calls.last.request
    assert request.method == "PATCH"
    assert request.url.path == f"{PATH}/c_project/fields-visibility"
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {
        "data": {
            "type": "schema-property-visibility",
            "attributes": {"hiddenInDetails": {"budget": True, "code": True, "status": False}},
        }
    }


def test_visibility_requires_a_field(invoke, api):
    route = api.patch(f"{SCHEMAS}/c_project/fields-visibility")
    result = invoke("schemas", "visibility", "c_project")
    assert result.exit_code == 2
    assert not route.called


# -- enum ---------------------------------------------------------------------------
def test_enum_append(invoke, api):
    route = api.patch(SCHEMAS).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": PROJECT_ID,
                        "type": "schema-validation-result",
                        "attributes": {"isValid": True},
                    }
                ]
            },
        )
    )
    result = invoke(
        "--silent",
        "schemas",
        "enum",
        "c_project",
        "status",
        "--append",
        "On hold",
        "--append",
        "Cancelled",
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"][0]["attributes"]["isValid"] is True
    request = route.calls.last.request
    assert request.method == "PATCH" and request.url.path == PATH
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {
        "data": [
            {
                "type": "schema-properties",
                "id": PROJECT_ID,
                "attributes": {"status": {"enum": ["On hold", "Cancelled"]}},
                "meta": {"status": {"enum": "append"}},
            }
        ]
    }


def test_enum_remove_multi_select(invoke, api):
    route = api.patch(SCHEMAS).mock(return_value=httpx.Response(200, json={"data": []}))
    result = invoke("-y", "schemas", "enum", "person", "tags", "--remove", "old", "--multi")
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "data": [
            {
                "type": "schema-properties",
                "id": PERSON_ID,
                "attributes": {"tags": {"properties": {"items": {"items": {"enum": ["old"]}}}}},
                "meta": {"tags": {"enum": "remove"}},
            }
        ]
    }


def test_enum_remove_refuses_without_yes(invoke, api):
    route = api.patch(SCHEMAS)
    result = invoke("schemas", "enum", "c_project", "status", "--remove", "Complete")
    assert result.exit_code == 2
    assert "Refusing to continue without confirmation" in plain(result.stderr)
    assert "Complete" in plain(result.stderr) and "c_project.status" in plain(result.stderr)
    assert not route.called


def test_enum_append_never_asks_for_confirmation(invoke, api):
    route = api.patch(SCHEMAS).mock(return_value=httpx.Response(200, json={"data": []}))
    result = invoke("schemas", "enum", "c_project", "status", "--append", "On hold")
    assert result.exit_code == 0, result.output
    assert route.called


def spec_append_patch() -> dict:
    """The per-field patch from the spec's `append` example: the FULL enum plus metadata."""
    return {
        "enum": ["Planning", "In progress", "Complete", "On hold"],
        "xClarifyEnumMetadata": {
            "Planning": {"id": "planning", "rank": 0, "color": "blue"},
            "In progress": {"id": "in_progress", "rank": 1, "color": "amber"},
            "Complete": {"id": "complete", "rank": 2, "color": "green"},
            "On hold": {"id": "on_hold", "rank": 3, "color": "red"},
        },
    }


def test_enum_data_field_patch_sends_metadata_verbatim(invoke, api):
    route = api.patch(SCHEMAS).mock(return_value=httpx.Response(200, json={"data": []}))
    result = invoke(
        "--silent", "schemas", "enum", "c_project", "status", "-d", json.dumps(spec_append_patch())
    )
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert request.method == "PATCH" and request.url.path == PATH
    assert query_pairs(request) == [("silent", "true")]
    assert json_body(request) == {
        "data": [
            {
                "type": "schema-properties",
                "id": PROJECT_ID,
                "attributes": {"status": spec_append_patch()},
                "meta": {"status": {"enum": "append"}},
            }
        ]
    }


def test_enum_data_full_document_passes_through(invoke, api):
    route = api.patch(SCHEMAS).mock(return_value=httpx.Response(200, json={"data": []}))
    document = {
        "data": [
            {
                "type": "schema-properties",
                "id": PROJECT_ID,
                "attributes": {"status": spec_append_patch()},
                "meta": {"status": {"enum": "append"}},
            }
        ]
    }
    result = invoke("schemas", "enum", "c_project", "status", "-d", json.dumps(document))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == document


def test_enum_data_full_document_fills_type_id_and_meta(invoke, api):
    route = api.patch(SCHEMAS).mock(return_value=httpx.Response(200, json={"data": []}))
    document = {"data": [{"attributes": {"status": {"enum": ["Complete"]}}}]}
    result = invoke(
        "-y", "schemas", "enum", "c_project", "status", "-d", json.dumps(document), "--op", "remove"
    )
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request) == {
        "data": [
            {
                "attributes": {"status": {"enum": ["Complete"]}},
                "type": "schema-properties",
                "id": PROJECT_ID,
                "meta": {"status": {"enum": "remove"}},
            }
        ]
    }


def test_enum_data_multi_nests_field_patch(invoke, api):
    route = api.patch(SCHEMAS).mock(return_value=httpx.Response(200, json={"data": []}))
    patch = {
        "enum": ["vip"],
        "xClarifyEnumMetadata": {"vip": {"id": "vip", "rank": 0, "color": "gold"}},
    }
    result = invoke("schemas", "enum", "person", "tags", "--multi", "-d", json.dumps(patch))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request)["data"][0]["attributes"] == {
        "tags": {"properties": {"items": {"items": patch}}}
    }
    # An already-nested patch is not wrapped a second time.
    nested = {"properties": {"items": {"items": patch}}}
    result = invoke("schemas", "enum", "person", "tags", "--multi", "-d", json.dumps(nested))
    assert result.exit_code == 0, result.output
    assert json_body(route.calls.last.request)["data"][0]["attributes"] == {"tags": nested}


def test_enum_data_op_remove_confirms(invoke, api):
    route = api.patch(SCHEMAS)
    result = invoke(
        "schemas", "enum", "c_project", "status", "-d", '{"enum": ["Complete"]}', "--op", "remove"
    )
    assert result.exit_code == 2
    assert "Refusing to continue without confirmation" in plain(result.stderr)
    assert "Complete" in plain(result.stderr)
    assert not route.called


def test_enum_rejects_mixed_or_missing_operations(invoke, api):
    route = api.patch(SCHEMAS)
    both = invoke("schemas", "enum", "c_project", "status", "--append", "a", "--remove", "b")
    assert both.exit_code == 2 and "not both" in plain(both.stderr)
    none = invoke("schemas", "enum", "c_project", "status")
    assert none.exit_code == 2
    mixed = invoke("schemas", "enum", "c_project", "status", "--append", "a", "-d", "{}")
    assert mixed.exit_code == 2 and "not both" in plain(mixed.stderr)
    op_alone = invoke("schemas", "enum", "c_project", "status", "--append", "a", "--op", "append")
    assert op_alone.exit_code == 2 and "--op only applies to --data" in plain(op_alone.stderr)
    bad_op = invoke("schemas", "enum", "c_project", "status", "-d", "{}", "--op", "replace")
    assert bad_op.exit_code == 2
    not_object = invoke("schemas", "enum", "c_project", "status", "-d", "[]")
    assert not_object.exit_code == 2
    multi_doc = invoke("schemas", "enum", "c_project", "status", "--multi", "-d", '{"data": []}')
    assert multi_doc.exit_code == 2 and "--multi does not apply" in plain(multi_doc.stderr)
    assert not route.called


# -- activities ---------------------------------------------------------------------
def test_activities_defaults(invoke, api):
    route = api.get(f"{SCHEMAS}/c_project/activities").mock(
        return_value=httpx.Response(
            200, json=page([resource("activity", "a1", aggKey="x:clarify:update")], total=1)
        )
    )
    result = invoke("schemas", "activities", "c_project")
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["data"][0]["id"] == "a1"
    assert body["meta"] == {"total_records": 1, "returned": 1}
    request = route.calls.last.request
    assert request.method == "GET" and request.url.path == f"{PATH}/c_project/activities"
    assert query_pairs(request) == [("page[limit]", "50")]


def test_activities_options_and_page_cap(invoke, api):
    route = api.get(f"{SCHEMAS}/c_project/activities").mock(
        return_value=httpx.Response(200, json=page([]))
    )
    result = invoke(
        "schemas", "activities", "c_project", "-n", "800", "--offset", "10", "-s", "-_created_at"
    )
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [
        ("sortOrder[column]", "_created_at"),
        ("sortOrder[dir]", "DESC"),
        ("page[limit]", "500"),
        ("page[offset]", "10"),
    ]
    result = invoke("schemas", "activities", "c_project", "--page-size", "25")
    assert result.exit_code == 0, result.output
    assert query_pairs(route.calls.last.request) == [("page[limit]", "25")]


def test_activities_all_follows_pages(invoke, api):
    base = f"https://api.clarify.ai/v1{SCHEMAS}/c_project/activities"
    route = api.get(f"{SCHEMAS}/c_project/activities").mock(
        side_effect=[
            httpx.Response(
                200,
                json=page(
                    [resource("activity", "1")], total=2, next_url=f"{base}?page%5Boffset%5D=1"
                ),
            ),
            httpx.Response(200, json=page([resource("activity", "2")], total=2)),
        ]
    )
    result = invoke("-o", "ndjson", "schemas", "activities", "c_project", "--all")
    assert result.exit_code == 0, result.output
    assert [json.loads(line)["id"] for line in result.stdout.splitlines()] == ["1", "2"]
    assert query_pairs(route.calls[0].request) == [("page[limit]", "500")]
    assert route.call_count == 2


def test_activities_not_found_exit_4(invoke, api):
    api.get(f"{SCHEMAS}/c_nope/activities").mock(
        return_value=httpx.Response(
            404, json={"errors": [{"status": "404", "detail": "Entity not found"}]}
        )
    )
    result = invoke("schemas", "activities", "c_nope")
    assert result.exit_code == 4
    assert "Entity not found" in plain(result.stderr)


# -- manifest -----------------------------------------------------------------------
def test_operations_manifest_matches_spec_commands():
    from pathlib import Path

    from clarify_cli.commands import schemas

    fixture = Path(__file__).parent / "fixtures" / "operations.json"
    spec_ops = {
        op["operationId"]
        for op in json.loads(fixture.read_text(encoding="utf-8"))
        if op["tag"] == "Schemas"
    }
    assert set(schemas.OPERATIONS) == spec_ops
    registered = {
        cmd.name or cmd.callback.__name__.replace("_", "-")
        for cmd in schemas.app.registered_commands
    }
    assert set(schemas.OPERATIONS.values()) <= registered
    assert {"objects", "get", "fields"} <= registered
