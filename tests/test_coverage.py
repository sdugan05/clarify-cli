"""Prove the CLI covers every operation in Clarify's OpenAPI spec.

``tests/fixtures/operations.json`` is generated from https://api.clarify.ai/swagger-json
(one entry per operation). Each command module declares ``OPERATIONS`` mapping
operationId -> command name; the union must equal the spec.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from clarify_cli.commands import GROUPS
from clarify_cli.main import app

FIXTURE = Path(__file__).parent / "fixtures" / "operations.json"


def _manifests() -> dict[str, tuple[str, str]]:
    """operationId -> (cli group, command) across every module."""
    seen: dict[str, tuple[str, str]] = {}
    for cli_name, module_name, _help in GROUPS:
        module = importlib.import_module(f"clarify_cli.commands.{module_name}")
        for op_id, command in getattr(module, "OPERATIONS", {}).items():
            assert op_id not in seen, f"{op_id} declared by both {seen[op_id][0]} and {cli_name}"
            seen[op_id] = (cli_name, command)
    return seen


def test_every_spec_operation_has_a_command():
    spec_ops = {op["operationId"]: op for op in json.loads(FIXTURE.read_text())}
    assert len(spec_ops) == 76
    manifests = _manifests()
    missing = sorted(set(spec_ops) - set(manifests))
    assert not missing, "operations without a CLI command: " + ", ".join(
        f"{m} ({spec_ops[m]['method']} {spec_ops[m]['path']})" for m in missing
    )
    unknown = sorted(set(manifests) - set(spec_ops))
    assert not unknown, f"OPERATIONS entries not in the spec: {unknown}"


@pytest.mark.parametrize(
    "op_id", sorted(op["operationId"] for op in json.loads(FIXTURE.read_text()))
)
def test_manifest_command_exists(op_id):
    from typer.main import get_command

    group_name, command_name = _manifests()[op_id]
    root = get_command(app)
    group = root.commands[group_name]
    assert command_name in group.commands, f"{group_name} has no command {command_name!r}"
