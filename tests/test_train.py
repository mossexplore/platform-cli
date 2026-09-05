import io
import inspect
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from rich.console import Console
from typer.testing import CliRunner

from wisemlops_cli.cli import app
from wisemlops_cli.commands.train import display_value, render_page
from wisemlops_cli.errors import ApiError, BusinessError
from wisemlops_cli.services.train import TrainService


def tasks(items, count=None):
    return {"result": {"code": 0, "data": {
        "count": len(items) if count is None else count, "taskInfos": items,
    }}}


class FakeClient:
    def __init__(self, *responses, business_id="selected-business"):
        self.responses = list(responses)
        self.business_id = business_id
        self.calls = []

    def request(self, method, path, json_body):
        self.calls.append((method, path, json_body))
        return self.responses.pop(0)


class TrainServiceTest(unittest.TestCase):
    def test_complete_default_request_and_raw_records(self):
        record = {"taskId": "id", "fileSize": 0, "extra": {"a": None}}
        client = FakeClient(tasks([record]))
        result = TrainService(client).list_tasks()
        method, path, body = client.calls[0]
        self.assertEqual((method, path), ("POST", "/ai/backend/modelDev/modelTrain/list"))
        self.assertEqual(body, {"data": {
            "taskName": "", "taskType": None, "taskType1": "mtp-all",
            "businessId": "selected-business", "cronFlag": "", "depTask": "",
            "scene": "", "subScene": "", "noticeTime": [], "updateNoticeTime": [],
            "jobStatus": [], "teamId": "", "noRunDays": "", "createUser": "",
            "updateUser": "", "taskTags": [], "trainEngine": "", "trainMode": "",
            "distFramework": "", "tags": None, "reverseTaskTags": [], "reverseTags": [],
            "category": "mtp-all", "private": False, "baseInfo": False, "isDeleted": "",
            "region": "", "scope": "", "inputName": "", "algorithmName": "",
            "algoInputName": "", "algorithmVersion": "", "taskOwner": "",
            "imagePackageId": "", "bucketName": "", "taskStr": "", "external": False,
            "inputTaskId": "", "customLabels": "", "sharing": False, "beginTime": None,
            "endTime": None, "updateBeginTime": None, "updateEndTime": None,
            "pageIndex": 1, "pageSize": 10, "running": False, "excludeSpecFlag": False,
            "taskId": "",
        }})
        self.assertEqual(result, {"count": 1, "pageIndex": 1, "pageSize": 10, "items": [record]})

    def test_filters_and_pagination(self):
        client = FakeClient(tasks([]))
        result = TrainService(client).list_tasks(2, 20, "wiserec")
        data = client.calls[0][2]["data"]
        self.assertEqual((data["pageIndex"], data["pageSize"], data["taskName"]), (2, 20, "wiserec"))
        self.assertEqual(result["pageIndex"], 2)

    def test_find_later_page_and_use_task_context(self):
        task = {"taskId": "target", "businessId": "task-business", "taskType": "other"}
        job = {"jobId": "j", "runningTime": 0, "fileSize": 145755572, "unknown": None}
        client = FakeClient(
            tasks([{"taskId": str(i)} for i in range(10)], 11), tasks([task], 11),
            {"result": {"code": 0, "count": 1, "jobs": [job]}},
        )
        service = TrainService(client)
        result = service.list_instances(service.find_task("target"))
        self.assertEqual(client.calls[1][2]["data"]["pageIndex"], 2)
        self.assertEqual(client.calls[2], (
            "POST", "/ai/backend/mtp/traintask/queryJobInstanceByTaskId",
            {"taskId": "target", "businessId": "task-business", "jobType": "other",
             "pageIndex": 1, "pageSize": 10, "sortField": "createTime", "sortOrder": "ascend"},
        ))
        self.assertEqual(result["items"], [job])

    def test_missing_task_context_is_not_guessed(self):
        for field in ("businessId", "taskType"):
            task = {"taskId": "target", "businessId": "b", "taskType": "train"}
            del task[field]
            client = FakeClient(tasks([task]))
            with self.subTest(field=field), self.assertRaisesRegex(ApiError, field):
                TrainService(client).find_task("target")
            self.assertEqual(len(client.calls), 1)

    def test_not_found_empty_and_exhausted_pages(self):
        for response in (tasks([]), tasks([{"taskId": "other"}])):
            client = FakeClient(response)
            with self.assertRaisesRegex(ApiError, "未找到"):
                TrainService(client).find_task("target")
            self.assertEqual(len(client.calls), 1)

    def test_repeated_pages_stop_lookup(self):
        page = tasks([{"taskId": str(i)} for i in range(10)], 100)
        client = FakeClient(page, page)
        with self.assertRaisesRegex(ApiError, "分页未返回新任务"):
            TrainService(client).find_task("target")
        self.assertEqual(len(client.calls), 2)

    def test_invalid_requests_do_not_call_api(self):
        client = FakeClient(business_id="")
        with self.assertRaises(BusinessError):
            TrainService(client).list_tasks()
        with self.assertRaises(ValueError):
            TrainService(client).list_tasks(0)
        with self.assertRaises(ValueError):
            TrainService(client).find_task(" ")
        self.assertEqual(client.calls, [])

    def test_malformed_and_failed_responses(self):
        for response in ({}, {"result": {"code": 4, "des": "无权限"}},
                         {"result": {"code": 0}}, tasks([None]),
                         {"result": {"code": 0, "data": {"taskInfos": [], "count": "1"}}}):
            with self.subTest(response=response), self.assertRaises(ApiError):
                TrainService(FakeClient(response)).list_tasks()
        with self.assertRaisesRegex(ApiError, "jobs"):
            TrainService(FakeClient({"result": {"code": 0, "count": 0}})).list_instances(
                {"taskId": "t", "businessId": "b", "taskType": "train"})


class TrainOutputTest(unittest.TestCase):
    def test_size_zero_null_and_boundaries(self):
        for value, expected in ((None, "-"), ("", "-"), (0, "0B"), (1, "0.00M"),
                                (1024 ** 3 - 1, "1024.00M"), (1024 ** 3, "1.00G"),
                                (3858541639, "3.59G"), (145755572, "139.00M")):
            with self.subTest(value=value):
                self.assertEqual(display_value("fileSize", value), expected)
        for field in ("gpuSize", "runningTime", "cpuSize", "memorySize", "infraSize"):
            self.assertEqual(display_value(field, 0), "0")

    def test_time_is_milliseconds_in_shanghai(self):
        self.assertEqual(display_value("checkTime", 1785466890000), "2026-07-31 11:01:30")
        self.assertEqual(display_value("createTime", 0), "1970-01-01 08:00:00")
        self.assertEqual(display_value("statusTime", None), "-")

    def test_empty_and_fixed_page_messages(self):
        stream = io.StringIO()
        with patch("wisemlops_cli.commands.train.console", Console(file=stream, width=240)):
            render_page({"count": 0, "pageIndex": 1, "pageSize": 10, "items": []}, "table")
            render_page({"count": 11, "pageIndex": 1, "pageSize": 10, "items": []},
                        "table", {"taskId": "t", "taskName": "[bold]literal"})
        self.assertIn("暂无训练任务", stream.getvalue())
        self.assertIn("暂无执行实例", stream.getvalue())
        self.assertIn("当前仅展示第 1 页 10 条", stream.getvalue())
        self.assertIn("[bold]literal", stream.getvalue())

    def test_table_formats_records_without_mutating_them(self):
        task = {"taskId": "task-id", "taskName": "[bold]literal"}
        item = {"algorithmId": "algorithm-id", "algorithmName": "algorithm",
                "gpuSize": 0, "fileSize": 145755572, "checkTime": 1785466890000}
        stream = io.StringIO()
        with patch("wisemlops_cli.commands.train.console", Console(file=stream, width=240)):
            render_page({"count": 1, "pageIndex": 1, "pageSize": 10, "items": [item]},
                        "table", task)
        self.assertIn("139.00M", stream.getvalue())
        self.assertIn("2026-07-31 11:01:30", stream.getvalue())
        self.assertEqual(item["fileSize"], 145755572)

    def invoke(self, client, args, configured_output="table"):
        def authenticated(operation):
            print("正在刷新认证", flush=True)
            return operation(client)
        runtime = SimpleNamespace(
            authenticated_call=authenticated,
            config=SimpleNamespace(current_profile=lambda: SimpleNamespace(output_format=configured_output)),
        )
        with patch("wisemlops_cli.cli.Runtime", return_value=runtime), patch(
            "wisemlops_cli.commands.train.runtime_from_context", return_value=runtime,
        ):
            # Click 8.1 defaults to merging stderr; newer versions separate streams.
            options = {"mix_stderr": False} if "mix_stderr" in inspect.signature(CliRunner).parameters else {}
            return CliRunner(**options).invoke(app, args)

    def test_cli_json_remains_parseable_with_auth_messages(self):
        record = {"taskId": "t", "fileSize": 0, "updateTime": 1785466890000, "scene": None}
        result = self.invoke(FakeClient(tasks([record])), ["train", "list", "-o", "json"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.stdout)["items"], [record])
        self.assertIn("正在刷新认证", result.stderr)

    def test_cli_instance_json_uses_config_and_preserves_job_id(self):
        task = {"taskId": "t", "businessId": "b", "taskType": "train"}
        result = self.invoke(FakeClient(tasks([task]), {"result": {"code": 0, "count": 1,
                            "jobs": [{"jobId": "j", "runningTime": 0}]}}),
                             ["train", "instance", "list", "t"], "json")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.stdout)["items"], [{"jobId": "j", "runningTime": 0}])

    def test_cli_rejects_invalid_options_before_api_call(self):
        for args in (["train", "list", "--page", "0"],
                     ["train", "list", "--page-size", "0"],
                     ["train", "list", "-o", "csv"],
                     ["train", "instance", "list"],
                     ["train", "instance", "list", "t", "--page", "2"]):
            client = FakeClient()
            result = self.invoke(client, args)
            with self.subTest(args=args):
                self.assertNotEqual(result.exit_code, 0)
                self.assertEqual(client.calls, [])

    def test_api_error_exits_nonzero(self):
        result = self.invoke(FakeClient({"result": {"code": 1, "des": "无权限"}}),
                             ["train", "list", "-o", "json"])
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("无权限", result.stderr)
