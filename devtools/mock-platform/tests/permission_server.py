"""Test-only real permission application with disposable database and grants."""
import socket
import threading
import time
from pathlib import Path
import sys
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'access-service'))
from app.main import create_app
from app.manage import migrate
from app.models import Environment, Grant, User
from app.settings import Settings


class PermissionServer:
    def __init__(self, directory):
        self.app = create_app(Settings('sqlite:///'+str(directory/'permissions.db'), secure_cookie=False))
        migrate(self.app.state.engine, self.app.state.sessions)
        with self.app.state.sessions() as db:
            users = [User(username=name, display_name=name) for name in ('demo', 'analyst')]
            environments = [Environment(name=name, display_name=name, platform_origin=f'https://{name}.mock.invalid')
                            for name in ('demo-dev', 'demo-test')]
            db.add_all(users+environments)
            db.flush()
            db.add_all([Grant(user_id=u.id, environment_id=e.id) for u in users for e in environments])
            db.commit()
        self.socket = socket.socket()
        self.socket.bind(('127.0.0.1', 0))
        self.url = f'http://127.0.0.1:{self.socket.getsockname()[1]}'
        self.server = uvicorn.Server(uvicorn.Config(self.app, log_level='error'))
        self.thread = threading.Thread(target=self.server.run, kwargs={'sockets': [self.socket]}, daemon=True)
        self.thread.start()
        deadline = time.monotonic()+15
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError('Permission service failed to start')
            time.sleep(.02)

    def close(self):
        self.server.should_exit = True
        self.thread.join(timeout=10)
        self.socket.close()
        self.app.state.engine.dispose()
