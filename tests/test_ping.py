"""自动保活的请求、停止与状态验证。"""

import json
import os
import time
import unittest
from unittest.mock import patch

import httpx

from wiserec_cli.ping import (
    PingStore, _select_shell_pid, detach, run_worker, status, start, stop,
)
from wiserec_cli.ping_process import select_console_shell
from wiserec_cli.credentials import CredentialStore
from wiserec_cli import __version__
import test_runtime


class PingTest(unittest.TestCase):
    def test_shell_selection_skips_transient_cmd_under_powershell(self):
        processes = {
            10: (20, "ml.exe"),
            20: (30, "cmd.exe"),
            30: (40, "powershell.exe"),
            40: (0, "WindowsTerminal.exe"),
        }
        self.assertEqual(_select_shell_pid(processes, 10), 30)

    def test_console_shell_overrides_transient_cmd_parent(self):
        processes = {
            10: (20, "python.exe"),
            20: (40, "cmd.exe"),
            30: (0, "powershell.exe"),
            40: (0, "WindowsTerminal.exe"),
        }
        with patch("wiserec_cli.ping_process.process_identity",
                   side_effect=lambda pid: f"{pid}:0:{pid}"):
            self.assertEqual(select_console_shell(processes, 10, {10, 20, 30}), 30)

    def setUp(self):
        self.fixture = test_runtime.RuntimeBusinessContextTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.fixture.store.select("dev", "jack", tenant_id="mep")
        self.runtime = self.fixture.runtime
        self.state = PingStore(self.fixture.credential_path.with_name("ping.json"))

    def prepare_worker(self, *, owner_identity="123"):
        self.state.write({"profiles": {"dev": {
            "worker_pid": os.getpid(),
            "worker_identity": str(os.getpid()),
            "owners": [{"pid": 123, "identity": owner_identity}],
            "status": "running", "last_success": time.time() - 601,
            "success_count": 0, "failure_count": 0,
        }}})

    def test_worker_sends_authenticated_ping_and_stops_after_window_closes(self):
        self.prepare_worker()
        requests = []
        real_client = httpx.Client

        def handler(request):
            requests.append(request)
            return httpx.Response(200, headers={
                "set-cookie": "session=rotated; Path=/; HttpOnly",
                "csrftoken": "new-csrf",
            }, json={"result": {"code": 0, "des": "success", "data": [], "count": 0}})

        def client_factory(*args, **kwargs):
            self.assertIsInstance(kwargs["transport"], httpx.HTTPTransport)
            kwargs["transport"] = httpx.MockTransport(handler)
            return real_client(*args, **kwargs)

        def close_window(_seconds):
            with self.state.locked():
                data = self.state.read()
                data["profiles"]["dev"]["owners"] = []
                self.state.write(data)

        with patch("wiserec_cli.ping._process_identity", side_effect=lambda pid: str(pid)), \
             patch("wiserec_cli.ping.httpx.Client", side_effect=client_factory), \
             patch("wiserec_cli.ping.time.sleep", side_effect=close_window):
            run_worker(self.fixture.config_path, "dev", self.fixture.credential_path,
                       self.fixture.business_path, self.state.path)

        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(str(request.url),
                         "https://dev.example.com/ai/backend/mep/tenant/queryTeamList")
        self.assertEqual(json.loads(request.content), {"businessId": "mep"})
        self.assertEqual(request.headers["businessid"], "mep")
        self.assertEqual(request.headers["ai-businessid"], "mep")
        self.assertEqual(request.headers["cookie"], "session=abc")
        self.assertEqual(request.headers["csrftoken"], "csrf")
        self.assertTrue(request.headers["x-request-id"])
        self.assertEqual(request.headers["x-cli-name"], "wiserec-cli")
        self.assertEqual(request.headers["x-cli-version"], __version__)
        self.assertEqual(request.headers["x-cli-protocol-version"], "1")
        self.assertTrue(request.headers["x-cli-invocation-id"])
        self.assertEqual(CredentialStore(self.fixture.credential_path).load("dev").cookie,
                         "session=rotated")
        self.assertEqual(CredentialStore(self.fixture.credential_path).load("dev").csrftoken,
                         "new-csrf")
        entry = self.state.read()["profiles"]["dev"]
        self.assertEqual(entry["status"], "stopped")
        self.assertEqual(entry["success_count"], 1)
        self.assertEqual(entry["last_request_id"], request.headers["x-request-id"])

    def test_closed_window_prevents_request(self):
        self.prepare_worker(owner_identity="closed")
        with patch("wiserec_cli.ping._process_identity", side_effect=lambda pid: str(pid)), \
             patch("wiserec_cli.ping.httpx.Client") as client:
            run_worker(self.fixture.config_path, "dev", self.fixture.credential_path,
                       self.fixture.business_path, self.state.path)
        client.assert_not_called()
        self.assertEqual(self.state.read()["profiles"]["dev"]["status"], "stopped")

    def test_nonzero_result_does_not_confirm_ping(self):
        self.prepare_worker()
        real_client = httpx.Client

        def client_factory(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(
                lambda _request: httpx.Response(200, json={
                    "result": {"code": 1, "des": "failed"},
                })
            )
            return real_client(*args, **kwargs)

        def close_window(_seconds):
            with self.state.locked():
                data = self.state.read()
                data["profiles"]["dev"]["owners"] = []
                self.state.write(data)

        with patch("wiserec_cli.ping._process_identity", side_effect=lambda pid: str(pid)), \
             patch("wiserec_cli.ping.httpx.Client", side_effect=client_factory), \
             patch("wiserec_cli.ping.time.sleep", side_effect=close_window):
            run_worker(self.fixture.config_path, "dev", self.fixture.credential_path,
                       self.fixture.business_path, self.state.path)

        entry = self.state.read()["profiles"]["dev"]
        self.assertEqual(entry["success_count"], 0)
        self.assertEqual(entry["failure_count"], 1)
        self.assertIsNone(entry.get("last_confirmed"))

    def test_worker_accepts_launch_token_when_launcher_pid_differs(self):
        self.prepare_worker()
        with self.state.locked():
            data = self.state.read()
            entry = data["profiles"]["dev"]
            entry.update(worker_pid=999, worker_identity="999",
                         worker_token="launch-1", status="starting",
                         last_success=time.time())
            self.state.write(data)
        actual_pid = []

        def close_window(_seconds):
            with self.state.locked():
                data = self.state.read()
                entry = data["profiles"]["dev"]
                actual_pid.append(entry["worker_pid"])
                self.assertEqual(entry["status"], "running")
                entry["owners"] = []
                self.state.write(data)

        with patch("wiserec_cli.ping._process_identity", side_effect=lambda pid: str(pid)), \
             patch("wiserec_cli.ping.time.sleep", side_effect=close_window):
            run_worker(self.fixture.config_path, "dev", self.fixture.credential_path,
                       self.fixture.business_path, self.state.path, "launch-1")
        self.assertEqual(actual_pid, [os.getpid()])
        self.assertEqual(self.state.read()["profiles"]["dev"]["status"], "stopped")

    def test_disabling_config_stops_worker_without_request(self):
        self.prepare_worker()
        config = json.loads(self.fixture.config_path.read_text(encoding="utf-8"))
        config["auth"] = {"auto_ping": False}
        self.fixture.config_path.write_text(json.dumps(config), encoding="utf-8")
        with patch("wiserec_cli.ping._process_identity", side_effect=lambda pid: str(pid)), \
             patch("wiserec_cli.ping.httpx.Client") as client:
            run_worker(self.fixture.config_path, "dev", self.fixture.credential_path,
                       self.fixture.business_path, self.state.path)
        client.assert_not_called()
        self.assertIn("配置已关闭", self.state.read()["profiles"]["dev"]["last_error"])

    def test_status_is_read_only_and_noninteractive_start_does_not_spawn(self):
        self.prepare_worker()
        with patch("wiserec_cli.ping._process_identity", side_effect=lambda pid: str(pid)), \
             patch("wiserec_cli.ping.sys.stdin") as stdin, \
             patch("wiserec_cli.ping.subprocess.Popen") as process:
            stdin.isatty.return_value = False
            self.assertIn("不是交互式终端", start(self.runtime))
            shown = status(self.runtime)
        process.assert_not_called()
        self.assertEqual(shown["状态"], "running")
        self.assertEqual(shown["终端窗口数"], 1)
        self.assertEqual(shown["成功次数"], 0)

    def test_two_terminals_share_one_worker_and_last_owner_can_stop(self):
        def worker_ready(_seconds):
            with self.state.locked():
                data = self.state.read()
                data["profiles"]["dev"]["status"] = "running"
                self.state.write(data)
        with patch("wiserec_cli.ping._process_identity", side_effect=lambda pid: str(pid)), \
             patch("wiserec_cli.ping.sys.stdin") as stdin, \
             patch("wiserec_cli.ping.os.getppid", side_effect=[100, 101, 100, 100]), \
             patch("wiserec_cli.ping.subprocess.Popen") as process, \
             patch("wiserec_cli.ping.time.sleep", side_effect=worker_ready):
            stdin.isatty.return_value = True
            process.return_value.pid = 999
            process.return_value.poll.return_value = None
            self.assertIn("已启动", start(self.runtime))
            self.assertIn("已启动", start(self.runtime))
            process.assert_called_once()
            self.assertEqual(len(self.state.read()["profiles"]["dev"]["owners"]), 2)
            detach(self.runtime, "dev")
            self.assertEqual(len(self.state.read()["profiles"]["dev"]["owners"]), 1)
            stop(self.runtime)
            self.assertIn("已手动停止", start(self.runtime, automatic=True))
            process.assert_called_once()
        self.assertEqual(self.state.read()["profiles"]["dev"]["owners"], [])

    def test_dead_worker_reports_startup_error(self):
        def worker_failed(_seconds):
            with self.state.locked():
                data = self.state.read()
                data["profiles"]["dev"]["status"] = "failed"
                self.state.write(data)
        with patch("wiserec_cli.ping._process_identity", side_effect=lambda pid: str(pid)), \
             patch("wiserec_cli.ping.sys.stdin") as stdin, \
             patch("wiserec_cli.ping.os.getppid", return_value=100), \
             patch("wiserec_cli.ping.subprocess.Popen") as process, \
             patch("wiserec_cli.ping.time.sleep", side_effect=worker_failed):
            stdin.isatty.return_value = True
            process.return_value.pid = 999
            process.return_value.poll.return_value = 1
            def crashed(*_args, **kwargs):
                kwargs["stderr"].write("RuntimeError: Windows worker failed\n")
                kwargs["stderr"].flush()
                return process.return_value
            process.side_effect = crashed
            with self.assertRaisesRegex(RuntimeError, "启动失败"):
                start(self.runtime)
        self.assertIn("Windows worker failed", status(self.runtime)["最近错误"])
        self.assertEqual(status(self.runtime)["状态"], "未运行")

    def test_start_replaces_worker_from_previous_version(self):
        self.prepare_worker()
        with self.state.locked():
            data = self.state.read()
            data["profiles"]["dev"]["worker_version"] = "previous"
            self.state.write(data)

        def worker_ready(_seconds):
            with self.state.locked():
                data = self.state.read()
                data["profiles"]["dev"]["status"] = "running"
                self.state.write(data)

        with patch("wiserec_cli.ping._process_identity", side_effect=lambda pid: str(pid)), \
             patch("wiserec_cli.ping.sys.stdin") as stdin, \
             patch("wiserec_cli.ping.os.getppid", return_value=100), \
             patch("wiserec_cli.ping.subprocess.Popen") as process, \
             patch("wiserec_cli.ping.time.sleep", side_effect=worker_ready):
            stdin.isatty.return_value = True
            process.return_value.pid = 999
            self.assertIn("已启动", start(self.runtime))
            process.assert_called_once()
        self.assertEqual(self.state.read()["profiles"]["dev"]["worker_version"],
                         __version__)

    def test_same_console_replaces_transient_owner(self):
        def worker_ready(_seconds):
            with self.state.locked():
                data = self.state.read()
                data["profiles"]["dev"]["status"] = "running"
                self.state.write(data)
        with patch("wiserec_cli.ping._process_identity", side_effect=lambda pid: str(pid)), \
             patch("wiserec_cli.ping._terminal_session_id", return_value="console-1"), \
             patch("wiserec_cli.ping.sys.stdin") as stdin, \
             patch("wiserec_cli.ping.os.getppid", side_effect=[100, 101]), \
             patch("wiserec_cli.ping.subprocess.Popen") as process, \
             patch("wiserec_cli.ping.time.sleep", side_effect=worker_ready):
            stdin.isatty.return_value = True
            process.return_value.pid = 999
            process.return_value.poll.return_value = None
            start(self.runtime)
            start(self.runtime)
        owners = self.state.read()["profiles"]["dev"]["owners"]
        self.assertEqual([(owner["pid"], owner["session_id"]) for owner in owners],
                         [(101, "console-1")])


if __name__ == "__main__":
    unittest.main()
