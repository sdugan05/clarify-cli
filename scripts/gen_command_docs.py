"""Generate ``docs/COMMANDS.md`` from the Typer application.

Walks the Click-style command tree that Typer builds for ``clarify_cli.main.app``
and prints a Markdown reference: one section per command group with a table of
its commands, then one subsection per command with its usage line, help text,
and argument/option tables. Output is deterministic so the file can be checked
in and regenerated:

    uv run python scripts/gen_command_docs.py > docs/COMMANDS.md
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from enum import Enum
from typing import Any

from typer.main import get_command

try:  # typer >= 0.20 vendors click under typer._click
    from typer._click.core import Command, Context, Parameter
except ImportError:  # pragma: no cover - older typer versions use the click package
    from click.core import Command, Context, Parameter

from clarify_cli.main import app

PROG = "clarify"
HIDDEN_PARAMS = frozenset({"help"})
TYPE_LABELS = {
    "str": "TEXT",
    "text": "TEXT",
    "int": "INTEGER",
    "integer": "INTEGER",
    "int range": "INTEGER",
    "float": "FLOAT",
    "float range": "FLOAT",
    "boolean": "BOOLEAN",
    "file": "FILE",
    "filename": "FILE",
    "path": "PATH",
}


# -- Markdown helpers ----------------------------------------------------------


def cell(text: str | None) -> str:
    """Make ``text`` safe inside a Markdown table cell.

    Pipes are escaped everywhere; ``*`` is escaped outside code spans so help
    such as ``'*Smith*'`` keeps its asterisks instead of turning italic.
    """
    if not text:
        return ""
    flat = " ".join(text.split())
    parts = flat.split("`")
    for index in range(0, len(parts), 2):  # even parts are outside code spans
        parts[index] = parts[index].replace("*", "\\*")
    return "`".join(parts).replace("|", "\\|")


def table(headers: list[str], rows: Iterable[list[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def anchor(title: str) -> str:
    """GitHub-style anchor for a plain heading like ``records bulk-create``."""
    return title.replace(" ", "-")


def help_body(text: str | None) -> list[str]:
    """Render a command's docstring after its first paragraph.

    Indented blocks (the ``Examples:`` in every docstring) become fenced shell
    code blocks so they render the same everywhere.
    """
    if not text:
        return []
    paragraphs = text.strip().split("\n\n", 1)
    if len(paragraphs) < 2:
        return []
    out: list[str] = []
    code: list[str] = []

    def flush() -> None:
        while code and not code[-1].strip():
            code.pop()
        if code:
            out.extend(["```bash", *code, "```", ""])
            code.clear()

    for line in paragraphs[1].splitlines():
        if line.startswith("    "):
            code.append(line[4:])
        elif not line.strip() and code:
            code.append("")
        else:
            flush()
            out.append(line)
    flush()
    return out


def first_line(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.strip().split("\n\n", 1)[0].split())


# -- parameter rendering -------------------------------------------------------


def is_argument(param: Parameter) -> bool:
    return param.param_type_name == "argument"


def is_flag(param: Parameter) -> bool:
    return bool(getattr(param, "is_flag", False))


def type_label(param: Parameter) -> str:
    """A compact type label: ``TEXT``, ``INTEGER (min 1)``, ``view|edit``, ``flag``."""
    if is_flag(param):
        return "flag"
    ptype: Any = param.type
    name = ptype.name
    if name == "choice":
        label = "`" + "|".join(str(c) for c in ptype.choices) + "`"
    else:
        label = TYPE_LABELS.get(name, name.upper())
        minimum = getattr(ptype, "min", None)
        maximum = getattr(ptype, "max", None)
        if minimum is not None and maximum is not None:
            label += f" ({minimum:g}..{maximum:g})"
        elif minimum is not None:
            label += f" (min {minimum:g})"
        elif maximum is not None:
            label += f" (max {maximum:g})"
    if param.multiple or param.nargs == -1:
        label += ", repeatable"
    return label


def default_label(param: Parameter) -> str:
    if param.required:
        return "required"
    value = param.default
    if value is None or callable(value):
        return ""
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, bool):
        return "" if (is_flag(param) and not value) else ("true" if value else "false")
    if isinstance(value, int | float):
        return f"`{value:g}`"
    if isinstance(value, str):
        return f"`{value}`" if value else ""
    if isinstance(value, list | tuple):
        return f"`{list(value)!r}`" if value else ""
    return f"`{value}`"


def option_name(param: Parameter) -> str:
    opts = list(getattr(param, "opts", []) or [])
    secondary = list(getattr(param, "secondary_opts", []) or [])
    if secondary:
        return "`" + " / ".join([*opts, *secondary]) + "`"
    metavar = param.metavar if not is_flag(param) and param.metavar else None
    text = ", ".join(opts)
    if metavar:
        text += f" {metavar}"
    return f"`{text}`"


def usage_line(path: list[str], params: list[Parameter]) -> str:
    parts = [PROG, *path]
    if any(not is_argument(p) and p.name not in HIDDEN_PARAMS for p in params):
        parts.append("[OPTIONS]")
    for param in params:
        if not is_argument(param):
            continue
        name = param.metavar or (param.name or "").upper()
        if param.nargs == -1:
            parts.append(f"[{name}]...")
        elif param.required:
            parts.append(name)
        else:
            parts.append(f"[{name}]")
    return " ".join(parts)


def argument_rows(params: list[Parameter]) -> list[list[str]]:
    rows: list[list[str]] = []
    for param in params:
        if not is_argument(param):
            continue
        name = param.metavar or (param.name or "").upper()
        required = "yes" if param.required else "no"
        rows.append(
            [f"`{name}`", cell(type_label(param)), required, cell(getattr(param, "help", None))]
        )
    return rows


def option_rows(params: list[Parameter]) -> list[list[str]]:
    rows: list[list[str]] = []
    for param in params:
        if is_argument(param) or param.name in HIDDEN_PARAMS:
            continue
        rows.append(
            [
                option_name(param),
                cell(type_label(param)),
                cell(default_label(param)),
                cell(getattr(param, "help", None)),
            ]
        )
    return rows


# -- tree walking --------------------------------------------------------------


def subcommands(group: Command, ctx: Context) -> list[tuple[str, Command, Context]]:
    """Child commands of a Click group in definition order."""
    out: list[tuple[str, Command, Context]] = []
    for name in group.list_commands(ctx):  # type: ignore[attr-defined]
        child = group.get_command(ctx, name)  # type: ignore[attr-defined]
        if child is None or child.hidden:
            continue
        out.append((name, child, Context(child, info_name=name, parent=ctx)))
    return out


def is_group(command: Command) -> bool:
    return hasattr(command, "commands") and hasattr(command, "list_commands")


def render_command(path: list[str], command: Command, ctx: Context, level: int) -> list[str]:
    title = " ".join(path)
    params = command.get_params(ctx)
    lines = [f"{'#' * level} {title}", "", first_line(command.help), ""]
    lines += ["```", usage_line(path, params), "```", ""]
    lines += help_body(command.help)
    if lines[-1] != "":
        lines.append("")
    args = argument_rows(params)
    if args:
        lines += ["**Arguments**", ""]
        lines += table(["Argument", "Type", "Required", "Description"], args)
        lines.append("")
    opts = option_rows(params)
    if opts:
        lines += ["**Options**", ""]
        lines += table(["Option", "Type", "Default", "Description"], opts)
        lines.append("")
    return lines


def render_group(name: str, group: Command, ctx: Context) -> list[str]:
    lines = [f"## {name}", "", first_line(group.help), ""]
    epilog = getattr(group, "epilog", None)
    if epilog:
        lines += [epilog.strip(), ""]
    children = subcommands(group, ctx)
    rows = [
        [f"[`{name} {child}`](#{anchor(f'{name} {child}')})", cell(first_line(cmd.help))]
        for child, cmd, _ in children
    ]
    lines += table(["Command", "Description"], rows)
    lines.append("")
    for child, cmd, child_ctx in children:
        lines += render_command([name, child], cmd, child_ctx, level=3)
    return lines


def render_root(root: Command, ctx: Context) -> list[str]:
    lines = [
        "# clarify command reference",
        "",
        "Generated from the CLI's own help text by `scripts/gen_command_docs.py`; "
        "do not edit by hand. Regenerate with:",
        "",
        "```bash",
        "uv run python scripts/gen_command_docs.py > docs/COMMANDS.md",
        "```",
        "",
        first_line(root.help),
        "",
        "Global options go **before** the group name: "
        "`clarify --silent --yes records delete person ID`.",
        "",
        "## Contents",
        "",
    ]
    children = subcommands(root, ctx)
    rows = [["[Global options](#global-options)", "Options accepted before any command."]]
    rows += [
        [f"[`{name}`](#{anchor(name)})", cell(first_line(cmd.help))] for name, cmd, _ in children
    ]
    lines += table(["Group", "Description"], rows)
    lines.append("")

    lines += ["## Global options", ""]
    lines += ["```", f"{PROG} [OPTIONS] COMMAND [ARGS]...", "```", ""]
    lines += help_body(root.help)
    if lines[-1] != "":
        lines.append("")
    lines += table(["Option", "Type", "Default", "Description"], option_rows(root.get_params(ctx)))
    lines.append("")

    for name, command, child_ctx in children:
        if is_group(command):
            lines += render_group(name, command, child_ctx)
        else:
            lines += render_command([name], command, child_ctx, level=2)
    return lines


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    root = get_command(app)
    ctx = Context(root, info_name=PROG)
    lines = render_root(root, ctx)
    while lines and lines[-1] == "":
        lines.pop()
    sys.stdout.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
