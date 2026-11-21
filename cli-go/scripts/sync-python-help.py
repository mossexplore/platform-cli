"""Copy the historical Typer help metadata used by the standalone Go CLI."""

import argparse
import inspect
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from typer import rich_utils
from typer.main import get_command

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "cli-go/internal/command/python_help.json"
sys.path.insert(0, str(ROOT / "cli-python/src"))
from wiserec_cli.cli import app


def metavar(param, ctx):
    kwargs = {"ctx": ctx} if "ctx" in inspect.signature(param.make_metavar).parameters else {}
    value = param.make_metavar(**kwargs)
    if isinstance(param, click.Argument) and value == param.name.upper():
        return param.type.name.upper()
    if isinstance(param, click.Option) and isinstance(param.type, click.types._NumberRangeBase):
        value += " [" + param.type._describe_range() + "]"
    return "" if value == "BOOLEAN" else value


def row(param, ctx):
    result = {"label": param.name}
    if isinstance(param, click.Option):
        result = {"label": ",".join(opt for opt in param.opts if opt.startswith("--"))}
        short = ",".join(opt for opt in param.opts if not opt.startswith("--"))
        if short:
            result["short"] = short
    value = metavar(param, ctx)
    if value:
        result["value"] = value
    parts = rich_utils._get_parameter_help(param=param, ctx=ctx, markup_mode="rich").renderables
    if parts:
        result["description"] = [part.plain for part in parts]
    if param.required:
        result["required"] = True
    return result


def walk(command, parent=None):
    ctx = click.Context(command, info_name=command.name, parent=parent)
    result = {
        "path": ctx.command_path.removeprefix("ml").strip(),
        "usage": " ".join(command.collect_usage_pieces(ctx)),
    }
    if command.help:
        help_text = rich_utils._get_help_text(obj=command, markup_mode="rich")
        console = Console(width=1000)
        result["intro"] = "\n".join(
            "".join(segment.text for segment in line).rstrip()
            for line in console.render_lines(help_text, pad=False)
        )
    for param in command.get_params(ctx):
        if getattr(param, "hidden", False):
            continue
        key = "arguments" if isinstance(param, click.Argument) else "options"
        result.setdefault(key, []).append(row(param, ctx))
    if isinstance(command, click.Group):
        children = [command.get_command(ctx, name) for name in command.list_commands(ctx)]
        children = [child for child in children if child and not child.hidden]
        result["children"] = [child.name for child in children]
    else:
        children = []
    yield result
    for child in children:
        yield from walk(child, ctx)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    pages = walk(get_command(app))
    rows = [json.dumps(page, ensure_ascii=False, separators=(",", ":")) for page in pages]
    content = "[\n  " + ",\n  ".join(rows) + "\n]\n"
    if args.check:
        if OUTPUT.read_text(encoding="utf-8") != content:
            parser.exit(1, "Python help metadata differs. Run cli-go/scripts/sync-python-help.py again.\n")
    else:
        OUTPUT.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
