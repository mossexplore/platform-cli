from app.build_info import application_version
from app._version import __version__
from test_service import system, login


def test_own_packaged_version_ignores_runtime_override(monkeypatch):
    monkeypatch.setenv('WISEREC_APP_VERSION', '9.8.7')
    assert application_version() == __version__


def test_packaged_version_reaches_actual_header(system):
    app, client, _ = system
    assert app.state.templates.env.globals['app_version'] == __version__
    login(client)
    response = client.get('/cli-permission/admin')
    assert response.status_code == 200
    header = response.text.split('<header class="topbar">', 1)[1].split('</header>', 1)[0]
    assert f'v{__version__}</span>' in header
    assert header.index(f'v{__version__}') < header.index('logout-icon')
