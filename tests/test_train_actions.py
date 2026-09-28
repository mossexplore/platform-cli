"""训练任务导出、取消、删除及克隆的真实 CLI 请求路径。"""

import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from typer.testing import CliRunner

from wiserec_cli.cli import app
from wiserec_cli.client import PlatformClient
import test_runtime


def success(data=None, description="success"):
    return httpx.Response(200, json={"result": {
        "code": 0, "des": description, **({"data": data} if data is not None else {}),
    }})


class TrainActionsTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_runtime.RuntimeBusinessContextTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.fixture.store.select("dev", "jack", tenant_id="mep")

    def invoke(self, arguments, handler):
        def client_factory(**kwargs):
            return PlatformClient(**kwargs, transport=httpx.MockTransport(handler))
        options = {"mix_stderr": False} if "mix_stderr" in inspect.signature(CliRunner).parameters else {}
        with patch("wiserec_cli.cli.Runtime", return_value=self.fixture.runtime), patch(
            "wiserec_cli.runtime.PlatformClient", side_effect=client_factory,
        ):
            return CliRunner(**options).invoke(app, ["train"] + arguments)

    @staticmethod
    def task_response(task):
        return success({"count": 1, "taskInfos": [task]})

    def test_export_uses_selected_business_streams_and_keeps_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "task.yaml"
            target.write_text("original")
            calls = []

            def handler(request):
                calls.append(request)
                self.assertEqual(request.method, "GET")
                self.assertEqual(str(request.url),
                                 "https://dev.example.com/ai/backend/mtp/traintask/export?taskId=t&businessId=mep")
                self.assertEqual(request.headers["businessid"], "mep")
                return httpx.Response(200, headers={
                    "content-type": "application/octet-stream",
                    "content-disposition": 'attachment;filename="task.yaml"',
                }, stream=httpx.ByteStream(b"name: cloned\n"))

            result = self.invoke(["config", "export", "t", "--file", str(target)], handler)
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(target.read_text(), "original")
            self.assertEqual((Path(directory) / "task (1).yaml").read_bytes(), b"name: cloned\n")
            self.assertEqual(len(calls), 1)

    def test_export_incomplete_response_leaves_no_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "task.yaml"

            def handler(_request):
                return httpx.Response(200, headers={
                    "content-type": "application/octet-stream", "content-length": "20",
                }, content=b"short")

            result = self.invoke(["config", "export", "t", "--file", str(target)], handler)
            self.assertNotEqual(result.exit_code, 0)
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cancel_fetches_all_pages_and_reports_each_result(self):
        task = {"taskId": "t", "businessId": "mep", "taskType": "train",
                "teamId": "team", "taskName": "task"}
        cancelled = []
        pages = []

        def handler(request):
            self.assertEqual(request.headers["businessid"], "mep")
            body = json.loads(request.content)
            if request.url.path.endswith("/modelTrain/list"):
                return self.task_response(task)
            if request.url.path.endswith("/queryJobInstanceByTaskId"):
                page = body["pageIndex"]
                pages.append(page)
                jobs = [{"jobId": f"j{i}", "taskName": f"name{i}"}
                        for i in (range(10) if page == 1 else range(10, 11))]
                return httpx.Response(200, json={"result": {"code": 0, "count": 11, "jobs": jobs}})
            self.assertEqual(request.url.path, "/ai/backend/mtp/train/cancelMultiInstanceTask")
            self.assertEqual(body["version"], "1.0")
            self.assertTrue(body["meta"]["uuid"])
            self.assertEqual(body["eventTarget"], f"name{body['data']['jobId'][1:]}")
            cancelled.append(body["data"]["jobId"])
            return success(description="cancel job success")

        result = self.invoke(["cancel", "t", "--yes"], handler)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(pages, [1, 2])
        self.assertEqual(cancelled, [f"j{i}" for i in range(11)])
        self.assertEqual(result.output.count("响应描述是cancel job success"), 11)

    def test_cancel_empty_never_posts(self):
        task = {"taskId": "t", "businessId": "mep", "taskType": "train"}
        paths = []

        def handler(request):
            paths.append(request.url.path)
            if request.url.path.endswith("/modelTrain/list"):
                return self.task_response(task)
            return httpx.Response(200, json={"result": {"code": 0, "count": 0, "jobs": []}})

        result = self.invoke(["cancel", "t", "--yes"], handler)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("没有正在执行的任务，无法取消任务执行！", result.output)
        self.assertEqual(len(paths), 2)

    def test_cancel_reports_partial_failure_and_continues(self):
        task = {"taskId": "t", "businessId": "mep", "taskType": "train"}
        cancelled = []

        def handler(request):
            if request.url.path.endswith("/modelTrain/list"):
                return self.task_response(task)
            if request.url.path.endswith("/queryJobInstanceByTaskId"):
                return httpx.Response(200, json={"result": {"code": 0, "count": 2,
                    "jobs": [{"jobId": "j1", "taskName": "one"},
                             {"jobId": "j2", "taskName": "two"}]}})
            job_id = json.loads(request.content)["data"]["jobId"]
            cancelled.append(job_id)
            return success() if job_id == "j2" else httpx.Response(
                200, json={"result": {"code": 2, "des": "denied"}},
            )

        result = self.invoke(["cancel", "t", "--yes"], handler)
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(cancelled, ["j1", "j2"])
        self.assertIn("取消完成：成功 1 个，失败 1 个", result.output)
        self.assertIn("取消训练任务t的执行实例j2成功", result.output)

    def test_delete_uses_list_fields_and_soft_delete(self):
        task = {"taskId": "t", "teamId": "team", "taskName": "actual-name"}
        writes = []

        def handler(request):
            if request.url.path.endswith("/modelTrain/list"):
                return self.task_response(task)
            writes.append(json.loads(request.content))
            self.assertEqual(request.headers["businessid"], "mep")
            return success()

        result = self.invoke(["delete", "t", "--yes"], handler)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(writes, [{"taskId": "t", "teamId": "team",
                                   "target": "actual-name", "softDeleteFlag": True}])
        self.assertIn("删除训练任务t成功", result.output)

    def test_clone_preserves_detail_and_changes_only_requested_fields(self):
        task = {"taskId": "t", "teamId": "", "taskName": "old"}
        detail = {"id": "source-id", "name": "old", "other": {"keep": [1, None]},
                  "taskInfo": {"baseInfo": {"taskName": "old", "keep": 9},
                               "parameter": {"customizeConfig": "old", "keep": True}}}
        writes = []

        def handler(request):
            self.assertEqual(request.headers["businessid"], "mep")
            body = json.loads(request.content)
            if request.url.path.endswith("/modelTrain/list"):
                return self.task_response(task)
            if request.url.path.endswith("/detailNew"):
                self.assertEqual(body, {"data": {"id": "t", "businessId": "mep", "teamId": ""}})
                return success(detail)
            writes.append(body)
            return success({"id": "new-id"})

        result = self.invoke(["clone", "t", "--name", "new",
                              "--customize-config", "0099", "--yes"], handler)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(writes, [{"data": {
            **detail, "name": "new", "taskInfo": {
                "baseInfo": {"taskName": "new", "keep": 9},
                "parameter": {"customizeConfig": "0099", "keep": True},
            },
        }}])
        self.assertEqual(detail["name"], "old")
        self.assertIn("新任务 ID：new-id", result.output)


if __name__ == "__main__":
    unittest.main()
