"""Read-only coverage, signature, evidence and link audit; no CLI callbacks run."""
from pathlib import Path
import hashlib
import json
import re
import shlex
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
import click
import typer
from wiserec_cli.cli import app

BASE = ROOT / 'skill-lab/wiserec-platform-detailed'


def parameters(command):
    result = []
    for p in command.params:
        default = str(p.default) if isinstance(p.default, Path) else p.default
        result.append(dict(name=p.name, opts=p.opts, secondary_opts=p.secondary_opts,
            required=p.required, default=default, type=p.type.name.upper(), parser={k:getattr(p.type,k) for k in ('min','max','min_open','max_open','exists','file_okay','dir_okay','readable','writable','resolve_path','case_sensitive','choices') if hasattr(p.type,k)}, multiple=p.multiple,
            nargs=p.nargs, envvar=p.envvar, help=getattr(p, 'help', '') or ''))
    return json.loads(json.dumps(result))


def audit():
    coverage = json.loads((Path(__file__).with_name('coverage.json')).read_text())
    leaves, groups = {}, {}

    def walk(command, path=''):
        if isinstance(command, click.Group):
            groups[path] = command
            for name, child in command.commands.items():
                walk(child, (path + ' ' + name).strip())
        else:
            leaves[path] = command

    walk(typer.main.get_command(app))
    errors = []
    for label, actual in [('commands', leaves), ('groups', groups)]:
        recorded = coverage[label]
        if set(actual) != set(recorded):
            errors.append(f'{label} drift: added={set(actual)-set(recorded)}, removed={set(recorded)-set(actual)}')
        for name in set(actual) & set(recorded):
            expected = [{k: v for k, v in p.items() if k != 'constraints'}
                        for p in recorded[name]['parameters']]
            if parameters(actual[name]) != expected:
                errors.append(f'parameter drift: ml {name}')
            if label == 'groups':
                for flag in ('invoke_without_command', 'no_args_is_help'):
                    if getattr(actual[name], flag) != recorded[name][flag]:
                        errors.append(f'group behavior drift: ml {name} {flag}')
            else:
                document = BASE / recorded[name]['document']
                if not document.is_file():
                    errors.append(f'missing document: {document}')
                elif not document.read_text().startswith(f'# `ml {name}`\n'):
                    errors.append(f'wrong command document: {document}')
                else:
                    body = document.read_text()
                    for parameter in actual[name].params:
                        for option in parameter.opts + parameter.secondary_opts:
                            if f'`{option}`' not in body:
                                errors.append(f'undocumented parameter: ml {name} {option}')
                    option_map = {option: p for p in actual[name].params
                                  for option in p.opts + p.secondary_opts if option.startswith('-')}
                    for block in re.findall(r'```text\n(.*?)\n```', body, re.S):
                        if '[OPTIONS]' in block or '[ARG' in block:
                            continue
                        tokens = shlex.split(block)
                        prefix = ['ml'] + name.split()
                        if tokens[:len(prefix)] != prefix:
                            errors.append(f'example does not match command: {document}')
                            continue
                        args = tokens[len(prefix):]
                        i = 0
                        while i < len(args):
                            value = args[i]
                            if value == '--':
                                break
                            if value.startswith('-'):
                                parameter = option_map.get(value)
                                if parameter is None:
                                    errors.append(f'unknown example option: {document}: {value}')
                                elif not parameter.is_flag:
                                    if i + parameter.nargs >= len(args):
                                        errors.append(f'missing example option value: {document}: {value}')
                                    i += parameter.nargs
                            i += 1
    for source, digest in coverage['sources'].items():
        path = ROOT / source
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            errors.append(f'evidence drift; review semantics before updating: {source}')
    declared = {BASE / entry['document'] for entry in coverage['commands'].values()}
    actual_docs = set((BASE / 'references/commands').rglob('*.md'))
    if declared != actual_docs:
        errors.append('command document inventory differs from coverage')
    links = re.compile(r'\]\(([^)#\s]+)(?:#[^)]*)?\)')
    visited = set()

    def visit(path):
        path = path.resolve()
        if path in visited:
            return
        visited.add(path)
        if not path.is_file():
            errors.append(f'broken link: {path}')
            return
        if path.suffix != '.md':
            return
        for target in links.findall(path.read_text()):
            if '://' in target:
                continue
            resolved = (path.parent / target).resolve()
            if BASE.resolve() not in resolved.parents:
                errors.append(f'nonportable reference: {path} -> {target}')
            else:
                visit(resolved)
    visit(BASE / 'SKILL.md')
    unreachable = set(p.resolve() for p in BASE.rglob('*.md')) - visited
    if unreachable:
        errors.append(f'unreachable documents: {unreachable}')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'PASS: {len(leaves)} commands, {len(groups)} groups; parameters, example options, evidence, links and reachability')


if __name__ == '__main__':
    audit()
