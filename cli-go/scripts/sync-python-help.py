"""Embed the Python CLI's real Typer help pages in the standalone Go CLI."""

import argparse
from contextlib import redirect_stdout
from functools import partial
import io
import json
import os
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import click
from typer import rich_utils
from typer.main import get_command

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli-python/src"))
from wiserec_cli.cli import app

OUTPUT = ROOT / "cli-go/internal/command/python-help.zip"
WIDTHS = range(48, 161)


def contexts(command, name, parent=None):
    context = click.Context(command, parent=parent, info_name=name)
    yield context
    for child, spec in getattr(command, "commands", {}).items():
        if not spec.hidden:
            yield from contexts(spec, child, context)


def help_files():
    os.environ.pop("NO_COLOR", None)
    os.environ["TERM"] = "xterm-256color"
    rich_utils.Console = partial(rich_utils.Console, legacy_windows=False)
    rich_utils.FORCE_TERMINAL = True
    rich_utils.COLOR_SYSTEM = "standard"
    commands = list(contexts(get_command(app), "ml"))
    options = {
        context.command_path: [
            spelling
            for param in context.command.get_params(context)
            if isinstance(param, click.Option) and not param.hidden
            for spelling in [*param.opts, *param.secondary_opts]
        ]
        for context in commands
    }
    yield "options.json", json.dumps(options, separators=(",", ":")).encode()
    for context in commands:
        pages = []
        for width in WIDTHS:
            os.environ["COLUMNS"] = str(width)
            rich_utils.MAX_WIDTH = width
            with redirect_stdout(io.StringIO()) as stream:
                plain_help = context.command.get_help(context)
                # Click echoes the returned help even when Typer has printed it.
                pages.append(stream.getvalue() + plain_help + "\n")
        yield f"help/{context.command_path}.json", json.dumps(
            {"first_width": WIDTHS.start, "pages": pages}, ensure_ascii=False, separators=(",", ":")
        ).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with ZipFile(OUTPUT) as archive:
            remaining = set(archive.namelist())
            for name, contents in help_files():
                if name not in remaining or archive.read(name) != contents:
                    parser.exit(1, f"Python CLI help changed ({name}). Run cli-go/scripts/sync-python-help.py again.\n")
                remaining.remove(name)
            if remaining:
                parser.exit(1, "Obsolete help pages remain. Run cli-go/scripts/sync-python-help.py again.\n")
    else:
        buffer = io.BytesIO()
        with ZipFile(buffer, "w") as archive:
            for name, contents in help_files():
                archive.writestr(ZipInfo(name), contents, compress_type=ZIP_DEFLATED, compresslevel=9)
        OUTPUT.write_bytes(buffer.getvalue())
    with ZipFile(OUTPUT) as archive:
        count = len(archive.namelist()) - 1  # options.json records the command contract.
    print(f"Python help synchronized for {count} command paths.")


if __name__ == "__main__":
    main()
