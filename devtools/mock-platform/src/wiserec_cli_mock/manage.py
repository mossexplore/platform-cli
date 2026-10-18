"""Management remains outside the public ml command tree."""
import argparse
import json
import shutil
from pathlib import Path
from .workspace import initialize, checked
from .seeds import SCENARIOS
from .storage import Store


def advance(root, seconds):
    if seconds < 0:
        raise ValueError('时间推进必须为非负整数')
    with Store(root).transaction() as db:
        clock = int(db.execute("SELECT value FROM meta WHERE key='clock'").fetchone()[0]) + seconds
        db.execute("UPDATE meta SET value=? WHERE key='clock'", (str(clock),))
        for row in db.execute("SELECT scope,id,payload FROM entities WHERE kind='job'").fetchall():
            job = json.loads(row['payload'])
            if job['status'] == 'running' and clock - job.get('startedClock', clock) >= 60:
                job.update(status='success', jobStatus='success', duration=60)
                Store.put(db, row['scope'], 'job', row['id'], job)
                try:
                    task = Store.get(db, row['scope'], 'train', job['taskId'])
                    task['jobStatus'] = 'success'
                    Store.put(db, row['scope'], 'train', job['taskId'], task)
                except KeyError:
                    pass  # A soft-deleted task can retain execution history.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('action', choices=['init', 'status', 'reset', 'advance', 'fault', 'jupyter', 'jupyter-status', 'jupyter-stop', 'identity'])
    parser.add_argument('--scenario', choices=SCENARIOS, default='standard')
    parser.add_argument('--username')
    parser.add_argument('--permission-url')
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--yes', action='store_true')
    parser.add_argument('--path')
    parser.add_argument('--status', type=int, default=503)
    parser.add_argument('--count', type=int, default=1)
    parser.add_argument('--port', type=int, default=18888)
    args = parser.parse_args()
    try:
        if args.action == 'init':
            initialize(args.workspace, args.scenario, permission_url=args.permission_url, username=args.username)
            return
        root = checked(args.workspace)
        Store(root).validate()
        if args.action in {'reset', 'advance', 'fault', 'jupyter'}:
            from .bootstrap import activate
            activate(root)
            from wiserec_cli.runtime import Runtime
            runtime = Runtime()
            runtime.invocation_command = 'demo manage '+args.action
            runtime.authenticated_call(lambda client: None)
        if args.action == 'status':
            print((root / 'workspace.json').read_text())
        elif args.action == 'reset':
            if not args.yes:
                raise ValueError('重置需要 --yes')
            if (root / 'jupyter.json').exists():
                raise ValueError('请先关闭本地 Jupyter，再重置工作区')
            # Preserve external exports and unrelated files; rebuild managed entities only.
            (root / 'state.sqlite3').unlink()
            Store(root).create()
            from .seeds import populate
            populate(root, args.scenario)
            if args.scenario == 'partial-failure':
                with Store(root).transaction() as db:
                    db.execute('INSERT INTO faults VALUES(?,?,?)', ('/ai/backend/modelDev/modelTrain/list', 503, 1))
            metadata = json.loads((root/'workspace.json').read_text())
            metadata['scenario'] = args.scenario
            (root/'workspace.json').write_text(json.dumps(metadata))
            shutil.rmtree(root / 'client')
            (root / 'client').mkdir()
        elif args.action == 'identity':
            metadata = json.loads((root/'workspace.json').read_text())
            from .permissions import settings
            settings(metadata['permission_url'], args.username)
            metadata['username'] = args.username
            (root/'workspace.json').write_text(json.dumps(metadata))
            from wiserec_cli.credentials import CredentialStore
            CredentialStore(root/'client/credentials.json').delete()
        elif args.action == 'advance':
            advance(root, args.seconds)
        elif args.action == 'fault':
            if not args.path or not args.path.startswith('/ai/') or not 400 <= args.status <= 599 or args.count < 1:
                raise ValueError('故障需要 /ai/ 接口路径、400–599 状态码和正整数次数')
            with Store(root).transaction() as db:
                db.execute('INSERT OR REPLACE INTO faults VALUES(?,?,?)', (args.path, args.status, args.count))
        elif args.action in {'jupyter-status', 'jupyter-stop'}:
            from .local_jupyter import control
            control(root, stop=args.action == 'jupyter-stop')
        else:
            from .local_jupyter import run
            run(root, args.port)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
