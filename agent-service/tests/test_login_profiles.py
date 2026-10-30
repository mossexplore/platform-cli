import time
import httpx
import pytest
from sqlalchemy.exc import OperationalError
from app.errors import AppError
from app.login_support import (
    prepare_profile,
    profile_paths,
    clear_profile,
    login_failure,
)
from conftest import headers, ready


def test_profiles_are_reused_and_environment_isolated(settings):
    first = prepare_profile(settings, "dev")
    (first / "Cookies").write_text("private-state")
    assert prepare_profile(settings, "dev") == first
    assert (first / "Cookies").read_text() == "private-state"
    assert prepare_profile(settings, "mirror") != first
    with pytest.raises(AppError):
        prepare_profile(settings, "../dev")


def test_pending_clear_prevents_cache_reuse(settings):
    directory = prepare_profile(settings, "dev")
    (directory / "Cookies").write_text("private-state")
    _, pending = profile_paths(settings, "dev")
    pending.touch()
    assert prepare_profile(settings, "dev") == directory
    assert not (directory / "Cookies").exists()
    assert not pending.exists()


def test_logout_preserves_environment_profiles(client, app):
    ready(client)
    dev = prepare_profile(app.state.config, "dev")
    other = prepare_profile(app.state.config, "mirror")
    (dev / "Cookies").write_text("private-state")
    response = client.post("/api/logout", headers=headers(client))
    assert response.status_code == 200
    assert not response.json()["warning"]
    assert (dev / "Cookies").read_text() == "private-state"
    assert other.exists()
    assert not profile_paths(app.state.config, "dev")[1].exists()
    assert prepare_profile(app.state.config, "dev") == dev


def test_cleanup_retries_windows_file_lock(settings, monkeypatch):
    import app.login_support as support

    directory = prepare_profile(settings, "dev")
    real = support.shutil.rmtree
    calls = []

    def locked(path):
        calls.append(path)
        if len(calls) < 3:
            raise PermissionError("do-not-log-secret-path")
        real(path)

    monkeypatch.setattr(support.shutil, "rmtree", locked)
    monkeypatch.setattr(support.time, "sleep", lambda _: None)
    clear_profile(settings, "dev")
    assert len(calls) == 3 and not directory.exists()


def test_diagnostics_never_echo_exception_or_sql(caplog):
    underlying = Exception(1045, "secret-cookie-password")
    error = OperationalError(
        "secret-sql", {"cookie": "secret-cookie-password"}, underlying
    )
    result = login_failure("credential_save", error)
    assert "credential_save" in result.message and "1045" in result.message
    assert "secret" not in result.message + caplog.text


def test_identity_failure_is_distinguishable_from_edge_failure(client, app):
    def fail(*_):
        raise httpx.ConnectError("secret-cookie-password")

    app.state.platform.identity = fail
    attempt = client.post(
        "/api/login-attempts", json={"environment_id": "dev"}, headers=headers(client)
    ).json()["attempt_id"]
    for _ in range(100):
        result = client.get("/api/login-attempts/" + attempt).json()
        if result["status"] == "failed":
            break
        time.sleep(0.01)
    assert result["status"] == "failed"
    assert "identity_probe" in result["message"]
    assert "ConnectError" in result["message"]
    assert "secret" not in result["message"]


def test_local_edge_success_retains_profile_and_reuses_it(settings, monkeypatch):
    import threading
    from types import SimpleNamespace
    from contextlib import contextmanager
    from wiserec_cli.models import Credentials
    from app.login import LocalEdge
    import app.login as login_module
    import playwright.sync_api as playwright_api

    env = settings.env("dev")
    launched = []
    closed = []
    callback = None

    class Page:
        url = env.api_endpoint

        def goto(self, *args, **kwargs):
            callback(
                SimpleNamespace(
                    url=env.api_endpoint.rstrip("/") + "/user/info",
                    all_headers=lambda: {"csrftoken": "test-csrf"},
                )
            )

        def is_closed(self):
            return False

        reads = 0

        def evaluate(self, expression):
            self.reads += 1
            if self.reads == 1:
                return "[]"
            return '[{"value":"b1","cn":"Test business"}]'

        def wait_for_timeout(self, timeout):
            pass

    class Context:
        pages = [Page()]

        def on(self, name, handler):
            nonlocal callback
            callback = handler

        def close(self):
            closed.append(True)

    def launch(path, **kwargs):
        launched.append(path)
        from pathlib import Path

        (Path(path) / "Cookies").write_text("test-cookie")
        return Context()

    @contextmanager
    def playwright():
        yield SimpleNamespace(
            chromium=SimpleNamespace(launch_persistent_context=launch)
        )

    monkeypatch.setattr(playwright_api, "sync_playwright", playwright)
    monkeypatch.setattr(
        login_module.BrowserAuthenticator,
        "_credentials_from_headers",
        lambda *args: Credentials.create("dev", "cookie", "csrf", "u", 1800),
    )
    for attempt in ("first", "second"):
        credentials, catalog = LocalEdge()(
            settings, env, attempt, threading.Event(), lambda _: None
        )
        assert credentials.username == "u"
    assert launched[0] == launched[1]
    assert len(closed) == 2
    assert (prepare_profile(settings, "dev") / "Cookies").exists()


def test_logout_never_attempts_cache_deletion_and_revokes_credentials(client, app, monkeypatch):
    import app.login_support as support

    ready(client)
    directory = prepare_profile(app.state.config, "dev")
    (directory / "Cookies").write_text("test-private-cookie")

    def fail(*args):
        raise PermissionError("test-private-cookie")

    monkeypatch.setattr(support.shutil, "rmtree", fail)
    monkeypatch.setattr(support.time, "sleep", lambda _: None)
    response = client.post("/api/logout", headers=headers(client))
    assert response.status_code == 200
    assert not response.json()["warning"]
    assert not profile_paths(app.state.config, "dev")[1].exists()
    assert (prepare_profile(app.state.config, "dev") / "Cookies").read_text() == "test-private-cookie"
    assert client.get("/api/businesses").status_code == 401
    from sqlalchemy import select
    from app.models import Credential
    with app.state.db() as db:
        assert db.scalar(select(Credential)) is None
