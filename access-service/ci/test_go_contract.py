"""Exercise the Go admission client against the access service over HTTP."""
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import tomllib

from sqlalchemy import select
import uvicorn

from app.models import CallLog
from test_service import system


def test_go_admission_contract(system):
    app, _, _ = system
    app.state.settings.kb_ticket_ak = 'contract'
    app.state.settings.kb_ticket_sk = 'contract-test-key' * 2
    root = Path(__file__).resolve().parents[2]
    version = tomllib.loads((root / 'versions.toml').read_text())['components']['cli_go']
    with socket.create_server(('127.0.0.1', 0)) as listener:
        server = uvicorn.Server(uvicorn.Config(app, lifespan='off', log_level='warning'))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        try:
            subprocess.run(
                ['go', 'test', '-tags=accesscontract', './internal/platform', '-count=1',
                 '-run', '^TestLiveAccessContract$'], cwd=root / 'cli-go', check=True, timeout=120,
                env={**os.environ, 'ACCESS_CONTRACT_URL': f'http://127.0.0.1:{listener.getsockname()[1]}',
                     'ACCESS_CONTRACT_CLI_VERSION': version},
            )
        finally:
            server.should_exit = True
            thread.join(timeout=10)
    with app.state.sessions() as db:
        allowed, denied = db.scalars(select(CallLog).order_by(CallLog.id)).all()
        for record in (allowed, denied):
            assert record.business_id == 'contract-business' and record.environment == 'prod'
            assert record.command == 'ml kb search' and record.cli_version == version
        assert allowed.allowed and json.loads(allowed.version_decision)['kb_ticket_id']
        assert not denied.allowed and 'kb_ticket_id' not in json.loads(denied.version_decision)
