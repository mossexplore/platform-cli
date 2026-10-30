import tomllib
from pathlib import Path
import pytest

from app.build_info import application_version
from test_service import system, login


def test_local_version_uses_repository(monkeypatch):
    monkeypatch.delenv('WISEREC_APP_VERSION', raising=False)
    with (Path(__file__).resolve().parents[2] / 'pyproject.toml').open('rb') as source:
        assert application_version() == tomllib.load(source)['project']['version']


@pytest.fixture
def image_system(tmp_path, monkeypatch):
    monkeypatch.setenv('WISEREC_APP_VERSION', '9.8.7')
    yield from system.__wrapped__(tmp_path)


def test_built_version_is_displayed_before_logout(image_system):
    app, client, _ = image_system
    assert application_version() == '9.8.7'
    assert app.state.templates.env.globals['app_version'] == '9.8.7'
    login(client)
    response = client.get('/cli-permission/admin')
    assert response.status_code == 200
    header = response.text.split('<header class="topbar">', 1)[1].split('</header>', 1)[0]
    assert 'v9.8.7</span>' in header
    assert header.index('v9.8.7') < header.index('logout-icon')
