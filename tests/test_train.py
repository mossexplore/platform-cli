import io
import inspect
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from rich.console import Console
from typer.testing import CliRunner

from wiserec_cli.cli import app
from wiserec_cli.commands.train import display_value, render_page
from wiserec_cli.errors import ApiError, BusinessError
from wiserec_cli.services.train import TrainService


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
    def test_history_request_is_direct_and_preserves_raw_jobs(self):
        job = {"jobId": "j", "fileSize": 97726898, "createTime": 1788598922000,
               "extra": None}
        client = FakeClient({"result": {"code": 0, "count": 1, "jobs": [job]}})
        result = TrainService(client).list_history(" task-id ")
        self.assertEqual(client.calls, [(
            "POST", "/ai/backend/mtp/traintask/queryScheduleTaskList",
            {"pageIndex": 1, "pageSize": 10, "sortField": "statusTime", "sortOrder": "ascend",
             "taskId": "task-id", "source": "history",
             "latestFlag": "true", "status": []},
        )])
        self.assertEqual(result, {"count": 1, "pageIndex": 1, "pageSize": 10, "items": [job]})

    def test_history_requires_task_and_business(self):
        client = FakeClient(business_id="")
        with self.assertRaises(ValueError):
            TrainService(client).list_history(" ")
        with self.assertRaises(BusinessError):
            TrainService(client).list_history("t")
        self.assertEqual(client.calls, [])

    def test_history_rejects_errors_and_invalid_response(self):
        for response in ({"result": {"code": 1, "des": "无权限"}},
                         {"result": {"code": 0, "count": 0}},
                         {"result": {"code": 0, "count": 1, "jobs": [None]}},
                         {"result": {"code": 0, "jobs": []}}):
            with self.subTest(response=response), self.assertRaises(ApiError):
                TrainService(FakeClient(response)).list_history("t")

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
             "pageIndex": 1, "pageSize": 10, "sortField": "periodDate", "sortOrder": "ascend"},
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
    def test_instance_duration_uses_current_time_and_start_not_running_time(self):
        from rich.table import Table

        now_ms = 1785466975500
        items = [
            {"createTime": now_ms - 116520000, "runningTime": 999, "queueTime": 157, "waitTime": 3631},
            {"createTime": None, "runningTime": 999, "waitTime": 0},
            {"createTime": ""}, {},
            {"createTime": now_ms + 1000},
            {"createTime": 0},
            {"createTime": now_ms - 59999},
            {"createTime": now_ms - 60000},
        ]
        with patch("wiserec_cli.commands.train.time.time", return_value=now_ms / 1000) as clock, patch(
            "wiserec_cli.commands.train.console"
        ) as output:
            render_page({"count": 8, "pageIndex": 1, "pageSize": 10, "items": items},
                        "table", {"taskId": "t"})
        table = next(call.args[0] for call in output.print.call_args_list
                     if isinstance(call.args[0], Table))
        duration = next(column for column in table.columns if column.header == "执行时长")
        self.assertEqual([cell.plain for cell in duration._cells],
                         ["1day8h22min", "-", "-", "-", "0min", display_value("runningTime", now_ms // 60000),
                          "0min", "1min"])
        clock.assert_called_once_with()
        self.assertEqual(items[0]["runningTime"], 999)
        self.assertEqual([column.header for column in table.columns[-3:]],
                         ["执行时长", "排队时长", "配额等待时间"])
        self.assertEqual(table.columns[-2]._cells[0].plain, "2h37min")
        wait_time = table.columns[-1]
        self.assertEqual(wait_time.header, "配额等待时间")
        self.assertEqual([cell.plain for cell in wait_time._cells],
                         ["1h0min31s", "0s", "-", "-", "-", "-", "-", "-"])

    def test_history_table_columns_values_and_pagination(self):
        from rich.table import Table

        item = {"jobId": "job-id", "algorithmId": "algo-id", "algorithmName": "algo-name",
                "cpuSize": 32, "gpuSize": 0, "memorySize": 256,
                "status": "CANCELED", "poolName": "pool", "infraSize": 1,
                "runningTime": 125, "queueTime": 157, "waitTime": 3631, "fileSize": 97726898,
                "checkTime": 1785466890000, "createTime": 1785466890000,
                "statusTime": 1785466890000, "actionType": "manual",
                "bucketName": "history-bucket"}
        with patch("wiserec_cli.commands.train.console") as output, \
             patch("wiserec_cli.commands.train.print_text") as messages:
            render_page({"count": 11, "pageIndex": 1, "pageSize": 10,
                         "items": [item, {"gpuSize": 0, "fileSize": 0,
                                          "algorithmId": None, "algorithmName": "",
                                          "waitTime": None},
                                   {"runningTime": 0, "queueTime": 0, "waitTime": 0},
                                   {"queueTime": 2.5, "waitTime": 125},
                                   {"status": "FAILED"}, {"status": "COMPLETED"},
                                   {"status": "TIMEOUT"}, {"status": "RUNNING"}]},
                        "table", history_task_id="task-id", translate_history_status=True)
        table = next(call.args[0] for call in output.print.call_args_list
                     if isinstance(call.args[0], Table))
        self.assertEqual([column.header for column in table.columns], [
            "作业ID", "算法名称", "CPU", "GPU", "内存", "状态", "集群",
            "节点数", "大小",
            "检查时间", "开始时间", "结束时间",
            "触发方式", "存储桶", "执行时长", "排队时长", "配额等待时间",
        ])
        self.assertEqual([column._cells[0].plain for column in table.columns], [
            "job-id",
            "algo-name", "32", "0", "256", "取消", "pool",
            "1", "93.20M", *(["2026-07-31 11:01:30"] * 3),
            "manual", "history-bucket", "2h5min", "2h37min", "1h0min31s",
        ])
        self.assertEqual([column._cells[1].plain for column in table.columns],
                         ["-", "-", "-", "0", "-", "-", "-", "-", "0B",
                          "-", "-", "-", "-", "-", "-", "-", "-"])
        self.assertEqual([column._cells[2].plain for column in table.columns[-3:]], ["0min", "0min", "0s"])
        self.assertEqual([column._cells[3].plain for column in table.columns[-2:]], ["2.5min", "2min5s"])
        self.assertEqual([(cell.plain, cell.style) for cell in table.columns[5]._cells], [
            ("取消", "yellow"), ("-", ""), ("-", ""), ("-", ""),
            ("执行失败", "red"), ("执行完成", "green"), ("超时", "yellow"), ("RUNNING", ""),
        ])
        output.print.assert_any_call("任务 ID：task-id", markup=False)
        messages.assert_called_once_with("第 1 页 · 每页 10 条 · 共 11 条")

    def test_history_cli_json_and_empty_results(self):
        job = {"jobId": "j", "fileSize": 97726898, "checkTime": None,
               "queueTime": 0, "waitTime": 2.5, "status": "COMPLETED"}
        client = FakeClient({"result": {"code": 0, "count": 1, "jobs": [job]}})
        result = self.invoke(client, ["train", "history", "list", "t", "-o", "json"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.stdout), {
            "count": 1, "pageIndex": 1, "pageSize": 10, "items": [job],
        })
        self.assertEqual(len(client.calls), 1)
        self.assertIn("正在刷新认证", result.stderr)
        for output_format in ("table", "json"):
            client = FakeClient({"result": {"code": 0, "count": 0, "jobs": []}})
            result = self.invoke(client, ["train", "history", "list", "t"], output_format)
            self.assertEqual(result.exit_code, 0, result.output)
            if output_format == "table":
                self.assertIn("暂无执行记录", result.stdout)
                self.assertNotIn("暂不支持翻页", result.stdout)
            else:
                self.assertEqual(json.loads(result.stdout)["items"], [])

    def test_history_cli_pagination_preserves_api_order(self):
        jobs = [{"jobId": "earlier", "createTime": 1000}, {"jobId": "later", "createTime": 2000}]
        client = FakeClient({"result": {"code": 0, "count": 202, "jobs": jobs}})
        args = ["train", "history", "list", "t", "--page", "2", "--page-size", "200"]
        result = self.invoke(client, args + ["-o", "json"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.stdout), {
            "count": 202, "pageIndex": 2, "pageSize": 200, "items": jobs,
        })
        self.assertEqual(client.calls[0][2], {
            "pageIndex": 2, "pageSize": 200, "sortField": "statusTime", "sortOrder": "ascend",
            "taskId": "t", "source": "history",
            "latestFlag": "true", "status": [],
        })
        client = FakeClient({"result": {"code": 0, "count": 202, "jobs": jobs}})
        result = self.invoke(client, args + ["-o", "table"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertLess(result.stdout.index("earlier"), result.stdout.index("later"))
        self.assertIn("第 2 页 · 每页 200 条 · 共 202 条", result.stdout)

    def test_history_cli_error_and_invalid_options(self):
        result = self.invoke(FakeClient({"result": {"code": 1, "des": "无权限"}}),
                             ["train", "history", "list", "t", "-o", "json"])
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("无权限", result.stderr)
        for args in (["train", "history", "list"],
                     ["train", "history", "list", " "],
                     ["train", "history", "list", "t", "--page", "0"],
                     ["train", "history", "list", "t", "--page-size", "0"],
                     ["train", "history", "list", "t", "--page-size", "201"],
                     ["train", "history", "list", "t", "--status", "CANCELED"]):
            client = FakeClient()
            self.assertNotEqual(self.invoke(client, args).exit_code, 0)
            self.assertEqual(client.calls, [])

    def test_size_zero_null_and_boundaries(self):
        for value, expected in ((None, "-"), ("", "-"), (0, "0B"), (1, "1B"),
                                (1024 ** 3 - 1, "1024.00M"), (1024 ** 3, "1.00G"),
                                (3858541639, "3.59G"), (145755572, "139.00M")):
            with self.subTest(value=value):
                self.assertEqual(display_value("fileSize", value), expected)
        for field in ("gpuSize", "cpuSize", "memorySize", "infraSize"):
            self.assertEqual(display_value(field, 0), "0")

    def test_duration_day_boundaries(self):
        for field in ("runningTime", "queueTime"):
            self.assertEqual(display_value(field, 1439), "23h59min")
            self.assertEqual(display_value(field, 1440), "1day0h0min")
            self.assertEqual(display_value(field, 1942), "1day8h22min")
        self.assertEqual(display_value("waitTime", 86399), "23h59min59s")
        self.assertEqual(display_value("waitTime", 86400), "1day0h0min0s")
        self.assertEqual(display_value("waitTime", 116551), "1day8h22min31s")

    def test_time_is_milliseconds_in_shanghai(self):
        self.assertEqual(display_value("checkTime", 1785466890000), "2026-07-31 11:01:30")
        self.assertEqual(display_value("createTime", 0), "1970-01-01 08:00:00")
        self.assertEqual(display_value("statusTime", None), "-")

    def test_empty_and_page_summary_messages(self):
        stream = io.StringIO()
        with patch("wiserec_cli.commands.train.console", Console(file=stream, width=240)), \
             patch("wiserec_cli.output.console", Console(file=stream, width=240)):
            render_page({"count": 0, "pageIndex": 1, "pageSize": 10, "items": []}, "table")
            render_page({"count": 11, "pageIndex": 1, "pageSize": 10, "items": []},
                        "table", {"taskId": "t", "taskName": "[bold]literal"})
        self.assertIn("暂无训练任务", stream.getvalue())
        self.assertIn("暂无执行实例", stream.getvalue())
        self.assertIn("第 1 页 · 每页 10 条 · 共 11 条", stream.getvalue())
        self.assertIn("[bold]literal", stream.getvalue())

    def test_table_formats_records_without_mutating_them(self):
        task = {"taskId": "task-id", "taskName": "[bold]literal"}
        item = {"jobId": "instance-job-id", "algorithmId": "algorithm-id", "algorithmName": "algorithm",
                "gpuSize": 0, "fileSize": 145755572, "createTime": 1785466890000,
                "hostIp": "10.0.0.1", "actionType": "manual", "bucketName": "train-bucket"}
        stream = io.StringIO()
        with patch("wiserec_cli.commands.train.console", Console(file=stream, width=240)), \
             patch("wiserec_cli.output.console", Console(file=stream, width=240)):
            render_page({"count": 1, "pageIndex": 1, "pageSize": 10, "items": [item]},
                        "table", task)
        self.assertNotIn("139.00M", stream.getvalue())
        for value in ("作业ID", "instance-job-id", "10.0.0.1", "manual", "train-bucket"):
            self.assertIn(value, stream.getvalue())
        for removed in ("算法id", "algorithm-id", "节点数", "检查时间", "结束时间", "大小"):
            self.assertNotIn(removed, stream.getvalue())
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
        with patch("wiserec_cli.cli.Runtime", return_value=runtime), patch(
            "wiserec_cli.commands.train.runtime_from_context", return_value=runtime,
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

    def test_cli_instance_pagination_preserves_api_order(self):
        task = {"taskId": "t", "businessId": "b", "taskType": "train"}
        jobs = [{"jobId": "middle", "createTime": 2000}, {"jobId": "earlier", "createTime": 1000},
                {"jobId": "later", "createTime": 3000}]
        args = ["train", "instance", "list", "t", "--page", "2", "--page-size", "200"]
        for output in ("json", "table"):
            client = FakeClient(tasks([task]), {"result": {"code": 0, "count": 203, "jobs": jobs}})
            result = self.invoke(client, args + ["-o", output])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(client.calls[-1][2], {
                "taskId": "t", "businessId": "b", "jobType": "train", "pageIndex": 2, "pageSize": 200,
                "sortField": "periodDate", "sortOrder": "ascend",
            })
            if output == "json":
                self.assertEqual(json.loads(result.stdout), {
                    "count": 203, "pageIndex": 2, "pageSize": 200, "items": jobs,
                })
            else:
                positions = [result.stdout.index(job["jobId"]) for job in jobs]
                self.assertEqual(positions, sorted(positions))
                self.assertIn("第 2 页 · 每页 200 条 · 共 203 条", result.stdout)

    def test_cli_rejects_invalid_options_before_api_call(self):
        for args in (["train", "list", "--page", "0"],
                     ["train", "list", "--page-size", "0"],
                     ["train", "list", "-o", "csv"],
                     ["train", "instance", "list"],
                     ["train", "instance", "list", "t", "--page", "0"],
                     ["train", "instance", "list", "t", "--page-size", "0"],
                     ["train", "instance", "list", "t", "--page-size", "201"]):
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
