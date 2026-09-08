import copy
import inspect
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from rich.console import Console
from typer.testing import CliRunner

from wisemlops_cli.business import BusinessSelection
from wisemlops_cli.cli import app
from wisemlops_cli.client import PlatformClient
from wisemlops_cli.commands.featureset import COLUMNS, display_value, render_page
from wisemlops_cli.errors import ApiError, BusinessError
from wisemlops_cli.models import Credentials, Profile
from wisemlops_cli.services.featureset import FeatureSetService


def response(items=None, count=0):
    return {"result": {"code": 0, "featureSetInfoList": items or [], "totalCount": count}}


def config_response(config):
    return {"result": {"code": 0, "des": "success", "featureJson": json.dumps(config)}}


class FakeClient:
    def __init__(self, payload=None, business_id="selected-business"):
        self.business_id = business_id
        self.payload = response() if payload is None else payload
        self.calls = []

    def request(self, method, path, json_body):
        self.calls.append((method, path, json_body))
        return self.payload


class FeatureSetServiceTest(unittest.TestCase):
    def test_config_request_and_business_header(self):
        config = {"features": [], "table_configs": {}, "feature_set_name": "test_hash", "version": "latest"}

        def handler(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(str(request.url),
                             "https://dev.example.com/ai/backend/dpp/proxy/featureStore/featureset/config")
            self.assertEqual(request.headers.get_list("businessid"), ["chosen"])
            self.assertEqual(json.loads(request.content), {"businessId": "chosen", "setId": "set-id"})
            return httpx.Response(200, json=config_response(config))

        selection = BusinessSelection(
            type="team", department_id="d", department_name="D", tenant_id="t",
            tenant_name="T", team_id="team", team_name="Team", business_id="chosen",
        )
        with PlatformClient(
            Profile("dev", "https://dev.example.com/dashboard"),
            Credentials.create("dev", "session=a", "csrf", "jack", 1800),
            30000, 0, True, transport=httpx.MockTransport(handler), business_selection=selection,
        ) as client:
            self.assertEqual(FeatureSetService(client).get_config(" set-id "), config)

    def test_config_requires_id_and_business_before_request(self):
        for set_id, business_id, error in ((" ", "chosen", ValueError),
                                          ("id", "", BusinessError), ("id", " ", BusinessError)):
            client = FakeClient(business_id=business_id)
            with self.subTest(set_id=set_id, business_id=business_id), self.assertRaises(error):
                FeatureSetService(client).get_config(set_id)
            self.assertEqual(client.calls, [])

    def test_config_rejects_bad_status_and_invalid_json(self):
        invalid = [[], {}, {"result": []}]
        for field, values in {
            "code": [None, False, "0", 0.0, 1],
            "des": [None, "Success", " success", "failed"],
            "featureJson": [None, {}, "", " ", "broken", r'{"name":"bad\_escape"}',
                            "[]", "null", '"string"', "1", "true", '{"value":NaN}',
                            '{"value":Infinity}'],
        }.items():
            missing = config_response({})
            del missing["result"][field]
            invalid.append(missing)
            for value in values:
                payload = config_response({})
                payload["result"][field] = value
                invalid.append(payload)
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ApiError):
                FeatureSetService(FakeClient(payload)).get_config("id")

    def test_request_uses_environment_host_and_same_business_in_header_and_body(self):
        for kind in ("wide", "model"):
            with self.subTest(kind=kind):
                def handler(request):
                    self.assertEqual(request.method, "POST")
                    self.assertEqual(str(request.url),
                                     "https://dev.example.com/ai/backend/dpp/proxy/featureStore/featureset/names")
                    self.assertEqual(request.headers.get_list("businessid"), ["chosen"])
                    self.assertEqual(json.loads(request.content), {
                        "pageIndex": 1, "pageSize": 10, "businessId": "chosen",
                        "teamId": "", "setName": "", "scene": "", "subscene": "",
                        "operator": "", "modifier": "", "setType": kind, "tagIdList": "",
                    })
                    return httpx.Response(200, json=response())

                selection = BusinessSelection(
                    type="team", department_id="d", department_name="D",
                    tenant_id="t", tenant_name="T", team_id="team", team_name="Team",
                    business_id="chosen",
                )
                with PlatformClient(
                    Profile("dev", "https://dev.example.com/dashboard"),
                    Credentials.create("dev", "session=a", "csrf", "jack", 1800),
                    30000, 0, True, transport=httpx.MockTransport(handler),
                    business_selection=selection,
                ) as client:
                    self.assertEqual(FeatureSetService(client).list_sets(kind),
                                     {"count": 0, "pageIndex": 1, "pageSize": 10, "items": []})

    def test_custom_query_preserves_order_types_and_extra_fields(self):
        items = [{"setId": "b", "setType": "model", "extra": None}, {"setId": "a"}]
        client = FakeClient(response(items, 21))
        result = FeatureSetService(client).list_sets("wide", 2, 20, "test")
        self.assertEqual(result, {"count": 21, "pageIndex": 2, "pageSize": 20, "items": items})
        body = client.calls[0][2]
        self.assertEqual((body["pageIndex"], body["pageSize"], body["setName"]), (2, 20, "test"))

    def test_invalid_inputs_do_not_send_request(self):
        client = FakeClient()
        for args in (("other",), ("wide", 0), ("model", 1, -1), ("wide", True), ("wide", 1.5)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                FeatureSetService(client).list_sets(*args)
        self.assertEqual(client.calls, [])
        for business in ("", "   "):
            client = FakeClient(business_id=business)
            with self.assertRaises(BusinessError):
                FeatureSetService(client).list_sets("wide")
            self.assertEqual(client.calls, [])

    def test_malformed_responses_are_errors_not_empty_pages(self):
        invalid = [[], {}, {"result": []}]
        for field, values in {
            "code": [None, "0", False, 1],
            "featureSetInfoList": [None, {}, [None]],
            "totalCount": [None, "1", True, -1],
        }.items():
            missing = response()
            del missing["result"][field]
            invalid.append(missing)
            for value in values:
                payload = response()
                payload["result"][field] = value
                invalid.append(payload)
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ApiError):
                FeatureSetService(FakeClient(payload)).list_sets("wide")


class FeatureSetCommandTest(unittest.TestCase):
    def test_config_both_entries_print_decoded_json_with_original_values(self):
        config = {"features": [{"name": "中文特征", "enabled": True, "default": None}],
                  "table_configs": {}, "feature_set_name": "test_hash_239features",
                  "path": "C:\\data\\file", "regex": r"\d+", "quoted": 'say "hello"',
                  "multiline": "first\nsecond", "version": "latest"}
        for kind in ("wide", "model"):
            for output in ("table", "json"):
                client = FakeClient(config_response(config))
                result = self.invoke(client, [kind, "config", " set-id "], output)
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual(json.loads(result.stdout), config)
                self.assertIn("中文特征", result.stdout)
                self.assertIn('"feature_set_name": "test_hash_239features"', result.stdout)
                self.assertIn("正在刷新认证", result.stderr)
                self.assertEqual(client.calls, [(
                    "POST", "/ai/backend/dpp/proxy/featureStore/featureset/config",
                    {"businessId": "selected-business", "setId": "set-id"},
                )])

    def test_config_empty_object_and_no_extra_escaping(self):
        for config in ({}, {"features": [], "table_configs": {}, "feature_set_name": "test_hash"}):
            result = self.invoke(FakeClient(config_response(config)), ["wide", "config", "id"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(json.loads(result.stdout), config)
            self.assertNotIn("\\", result.stdout)

    def test_config_bad_ids_and_missing_business(self):
        for args in (["model", "config"], ["wide", "config", " "],
                     ["wide", "config", "id", "--output", "table"]):
            client = FakeClient()
            result = self.invoke(client, args)
            self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(client.calls, [])
        client = FakeClient(business_id="")
        result = self.invoke(client, ["model", "config", "id"])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("ml business use", result.stderr)
        self.assertEqual(client.calls, [])

    def test_config_failure_does_not_print_configuration(self):
        payload = config_response({"secret": "not-for-output"})
        payload["result"]["des"] = "denied"
        result = self.invoke(FakeClient(payload), ["model", "config", "id"])
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("code=0", result.stderr)
        self.assertIn("des=denied", result.stderr)
        self.assertNotIn("not-for-output", result.stderr)

    def invoke(self, client, args, configured_output="table"):
        def authenticated(operation):
            print("正在刷新认证", flush=True)
            return operation(client)
        runtime = SimpleNamespace(
            authenticated_call=authenticated,
            config=SimpleNamespace(current_profile=lambda: SimpleNamespace(output_format=configured_output)),
        )
        with patch("wisemlops_cli.cli.Runtime", return_value=runtime), patch(
            "wisemlops_cli.commands.featureset.runtime_from_context", return_value=runtime,
        ):
            options = {"mix_stderr": False} if "mix_stderr" in inspect.signature(CliRunner).parameters else {}
            return CliRunner(**options).invoke(app, ["featureset"] + args)

    def test_both_entries_and_json_output(self):
        record = {"setId": "id", "setType": "model", "scene": None,
                  "createTime": "2026-09-08T03:30:58.000+00:00", "extra": {"v": 1}}
        for kind in ("wide", "model"):
            client = FakeClient(response([record], 20))
            result = self.invoke(client, [kind, "list", "--name", "test", "--page", "2",
                                         "--page-size", "5", "-o", "json"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(json.loads(result.stdout),
                             {"count": 20, "pageIndex": 2, "pageSize": 5, "items": [record]})
            self.assertIn("正在刷新认证", result.stderr)
            body = client.calls[0][2]
            self.assertEqual((body["setType"], body["pageIndex"], body["pageSize"], body["setName"]),
                             (kind, 2, 5, "test"))

    def test_configured_json_and_default_table(self):
        result = self.invoke(FakeClient(), ["model", "list"], "json")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.stdout)["items"], [])
        result = self.invoke(FakeClient(), ["wide", "list"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("暂无特征集", result.stdout)
        self.assertIn("第 1 页 · 每页 10 条 · 共 0 条", result.stdout)

    def test_invalid_options_do_not_call_api(self):
        for option in (["--page", "0"], ["--page-size", "-1"], ["--page", "1.5"],
                       ["-o", "csv"], ["--team-id", "t"], ["--set-type", "model"]):
            client = FakeClient()
            result = self.invoke(client, ["wide", "list"] + option)
            self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(client.calls, [])

    def test_business_error_is_reported(self):
        result = self.invoke(FakeClient({"result": {"code": 17, "des": "无权限"}}), ["wide", "list"])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("无权限", result.stderr)
        self.assertIn("17", result.stderr)

    def test_time_and_empty_values(self):
        for value in (None, ""):
            self.assertEqual(display_value("createTime", value), "-")
        self.assertEqual(display_value("scene", 0), "0")
        for value in ("2026-09-08T03:30:58.000+00:00", "2026-09-08T03:30:58Z",
                      "2026-09-07T23:30:58-04:00"):
            self.assertEqual(display_value("createTime", value), "2026-09-08 11:30:58")
        with patch("wisemlops_cli.commands.featureset.error_console") as errors:
            for value in ("bad", "2026-09-08T03:30:58"):
                self.assertEqual(display_value("updateTime", value), value)
            self.assertEqual(errors.print.call_count, 2)

    def test_table_columns_and_raw_record_preservation(self):
        record = {"setId": "id", "setName": "[bold]literal", "setType": "model",
                  "createTime": "2026-09-08T03:30:58Z"}
        original = copy.deepcopy(record)
        stream = io.StringIO()
        with patch("wisemlops_cli.commands.featureset.console", Console(file=stream, width=240)):
            render_page({"count": 1, "pageIndex": 1, "pageSize": 10, "items": [record]}, "table")
        text = stream.getvalue()
        positions = [text.index(title) for title, _ in COLUMNS]
        self.assertEqual(positions, sorted(positions))
        for expected in ("[bold]literal", "model", "2026-09-08 11:30:58", "Asia/Shanghai"):
            self.assertIn(expected, text)
        self.assertEqual(record, original)
