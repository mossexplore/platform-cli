"""Render the skill index and check its command examples against the CLI contract, without calls."""
import argparse
from pathlib import Path
import re

import click

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "cli-go/internal/command/testdata/python-cli.tsv"
TEMPLATE = ROOT / "scripts/skill_index/commands.md.in"
OUTPUT = ROOT / "skill/wiserec-platform/references/commands.md"


def go_cli_tree(contract_path=CONTRACT):
    root = click.Group(params=[click.Option(["--version"], is_flag=True)])
    for raw_line in contract_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            continue
        parts = line.split("\t")
        path = parts[0].split()
        options = parts[2].split() if len(parts) > 2 else []
        group = root
        for segment in path[:-1]:
            child = group.commands.get(segment)
            if not isinstance(child, click.Group):
                child = click.Group(segment)
                group.add_command(child)
            group = child
        params = [click.Option([opt], is_flag=True) for opt in options if opt.startswith("-")]
        group.add_command(click.Command(path[-1], params=params))
    ping = root.commands["auth"].commands["ping"]
    ping.add_command(click.Command("tick", params=[
        click.Option(["--capabilities"], is_flag=True),
        click.Option(["--json"], is_flag=True),
    ]))
    # Go also accepts a tenant ID directly on the business command group.
    business = root.commands.get("business")
    if isinstance(business, click.Group):
        business.params.append(click.Argument(["tenant_id"]))
    kb = click.Group('kb')
    pages = click.Group('page')
    files = click.Group('file')
    root.add_command(kb)
    kb.add_command(pages)
    kb.add_command(files)
    for group, name, flags in ((kb, 'list', []), (kb, 'search', ['--kb', '--limit']),
                               (pages, 'list', ['--kb', '--page', '--page-size']),
                               (pages, 'show', ['--kb']),
                               (files, 'list', ['--kb', '--page', '--page-size', '--all'])):
        group.add_command(click.Command(name, params=[click.Option([flag]) for flag in flags]
                                        + [click.Option(['--output', '-o'])]))
    files.add_command(click.Command('download', params=[click.Option(['--kb']), click.Option(['--file'])]))
    return root


def leaves(command, prefix=()):
    if isinstance(command, click.Group):
        paths = {path: leaf for name, child in command.commands.items()
                 for path, leaf in leaves(child, prefix + (name,)).items()}
        if any(isinstance(param, click.Argument) for param in command.params):
            paths[prefix] = command
        return paths
    return {prefix: command}


def resolve_example(root, example, parent):
    tokens = example.split()
    if tokens[0] == "ml":
        tokens = tokens[1:]
    else:
        tokens = list(parent) + tokens
    command, path = root, []
    while tokens and isinstance(command, click.Group) and tokens[0] in command.commands:
        name = tokens.pop(0)
        path.append(name)
        command = command.commands[name]
    if isinstance(command, click.Group):
        argument_count = sum(isinstance(param, click.Argument) for param in command.params)
        version_option = not path and tokens == ["--version"]
        has_arguments = argument_count > 0 and len(tokens) == argument_count
        if not version_option and not has_arguments:
            raise ValueError(f"Unknown or incomplete command: {example}")
    declared = {option for parameter in command.params
                for option in parameter.opts + parameter.secondary_opts
                if option.startswith("-")}
    used = set(re.findall(r"(?<![\w-])--?[a-zA-Z][\w-]*", " ".join(tokens)))
    if used - declared:
        raise ValueError(f"Unknown options in {example}: {sorted(used - declared)}")
    return tuple(path), command, declared


def render(root, template):
    seen, rendered = set(), []
    for line in template.splitlines():
        if not line.startswith("| `"):
            rendered.append(line)
            continue
        cells = re.split(r"(?<!\\)\|", line)
        if len(cells) != 6 or cells[3].strip() != "{{confirm}}":
            raise ValueError(f"Index row needs four columns and a confirm placeholder: {line}")
        examples = re.findall(r"`([^`]+)`", cells[1])
        parent, confirmations = (), set()
        for example in examples:
            path, command, options = resolve_example(root, example, parent)
            if path:
                seen.add(path)
                parent = path[:-1]
            confirmations.add("--yes" in options)
        if len(confirmations) != 1:
            raise ValueError(f"Split rows with different confirmation options: {line}")
        cells[3] = " 是 " if True in confirmations else " "
        rendered.append("|".join(cells))
    missing = set(leaves(root)) - seen
    if missing:
        raise ValueError(f"Missing commands: {sorted(' '.join(path) for path in missing)}")
    notice = "<!-- Generated by scripts/sync_skill_index.py; edit scripts/skill_index/commands.md.in -->"
    return notice + "\n\n" + "\n".join(rendered) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Reject drift without writing")
    args = parser.parse_args()
    result = render(go_cli_tree(), TEMPLATE.read_text(encoding="utf-8"))
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != result:
            raise SystemExit("Skill command index is stale; run python scripts/sync_skill_index.py")
    else:
        OUTPUT.write_text(result, encoding="utf-8")


if __name__ == "__main__":
    main()
