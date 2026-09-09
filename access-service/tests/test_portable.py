from unittest.mock import Mock
import pytest
from app import portable
from app.models import Admin
from app.settings import Settings
from test_service import system


def test_prepare_initializes_and_detects_admin(system, monkeypatch):
    app, _, _ = system
    monkeypatch.setattr(portable, 'load_dotenv', lambda *_: None)
    monkeypatch.setattr(Settings, 'load', lambda: Settings('mysql+pymysql://configured'))
    monkeypatch.setattr(portable, 'database', lambda _: (app.state.engine, app.state.sessions))
    assert portable.prepare() is False
    with app.state.sessions() as db:
        db.get(Admin, 1).enabled = False
        db.commit()
    assert portable.prepare() is True


def test_placeholder_configuration_rejected(monkeypatch):
    monkeypatch.setattr(portable, 'load_dotenv', lambda *_: None)
    monkeypatch.setattr(Settings, 'load', lambda: Settings('mysql+pymysql://user:CHANGE_ME@localhost/db'))
    with pytest.raises(ValueError, match='DATABASE_URL'):
        portable.prepare()


def test_uninitialized_background_start_does_not_serve(monkeypatch, capsys):
    monkeypatch.setattr(portable, 'prepare', lambda: True)
    monkeypatch.setattr(portable.sys.stdin, 'isatty', lambda: False)
    server = Mock()
    monkeypatch.setattr(portable, 'serve', server)
    assert portable.main() == 1
    server.assert_not_called()
    assert 'manage.sh create-admin' in capsys.readouterr().err


def test_existing_admin_starts_without_interactive_prompt(monkeypatch):
    monkeypatch.setattr(portable, 'prepare', lambda: False)
    server = Mock()
    monkeypatch.setattr(portable, 'serve', server)
    assert portable.main() == 0
    server.assert_called_once()
