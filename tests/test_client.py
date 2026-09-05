import unittest

import httpx

from wisemlops_cli.client import PlatformClient
from wisemlops_cli.business import BusinessSelection
from wisemlops_cli.errors import AuthenticationError
from wisemlops_cli.models import Credentials, Profile
from wisemlops_cli.services.mep import MepService
from wisemlops_cli.services.train import TrainService
from wisemlops_cli.services.user import UserService


class PlatformClientTest(unittest.TestCase):
    def create_client(self, handler):
        return PlatformClient(
            profile=Profile(
                name="dev",
                api_endpoint="https://dev.example.com/dashboard",
            ),
            credentials=Credentials.create(
                profile="dev",
                cookie="session=abc; token=xyz",
                csrftoken="csrf-value",
                username="jack",
                ttl_seconds=1800,
            ),
            timeout_ms=30000,
            retry_times=3,
            verify_ssl=True,
            transport=httpx.MockTransport(handler),
            business_selection=BusinessSelection(
                type="team",
                department_id="WiseCloudBigData",
                department_name="云平台部",
                tenant_id="mep",
                tenant_name="测试MEP平台",
                team_id="asdasd",
                team_name="asdasda",
                business_id="mep",
            ),
        )

    def test_sends_complete_authentication_headers(self):
        def handler(request):
            self.assertEqual(request.headers["cookie"], "session=abc; token=xyz")
            self.assertEqual(request.headers["csrftoken"], "csrf-value")
            self.assertEqual(request.headers["ai-businessId"], "mep")
            self.assertEqual(request.headers["businessid"], "mep")
            return httpx.Response(200, json={"username": "jack"})

        with self.create_client(handler) as client:
            self.assertEqual(client.username, "jack")
            result = client.request("GET", "/ai/user/info")
        self.assertEqual(result["username"], "jack")

    def test_services_inherit_business_headers_without_explicit_headers(self):
        paths = []

        def handler(request):
            paths.append(request.url.path)
            self.assertEqual(request.headers["businessid"], "mep")
            self.assertEqual(request.headers["ai-businessId"], "mep")
            return httpx.Response(200, json={"result": {
                "code": 0, "count": 0, "jobs": [],
                "data": {"count": 0, "taskInfos": []},
            }})

        with self.create_client(handler) as client:
            UserService(client).info()
            MepService(client).query_config("test-key")
            TrainService(client).list_tasks()
            TrainService(client).list_instances({
                "taskId": "task-id", "businessId": "mep", "taskType": "train",
            })
        self.assertEqual(paths, [
            "/ai/user/info", "/ai/backend/mep/config/queryConfig",
            "/ai/backend/modelDev/modelTrain/list",
            "/ai/backend/mtp/traintask/queryJobInstanceByTaskId",
        ])

    def test_custom_headers_preserve_default_business_headers(self):
        def handler(request):
            self.assertEqual(request.headers["businessid"], "mep")
            self.assertEqual(request.headers["ai-businessId"], "mep")
            self.assertEqual(request.headers["x-request-id"], "test-request")
            return httpx.Response(200, json={})

        with self.create_client(handler) as client:
            client.request("GET", "/ai/user/info", headers={"x-request-id": "test-request"})

    def test_sends_query_parameters_without_truncation(self):
        def handler(request):
            self.assertEqual(request.url.params["businessId"], "mep")
            self.assertEqual(request.url.params["projectName"], "测试 实验")
            self.assertEqual(request.url.params["pageIndex"], "2")
            self.assertEqual(request.headers["businessid"], "mep")
            self.assertEqual(request.headers.get_list("businessid"), ["mep"])
            return httpx.Response(200, json={"result": {"code": 0}})

        with self.create_client(handler) as client:
            client.request(
                "GET",
                "/ai/backend/experiment/project/list",
                params={
                    "businessId": client.business_id,
                    "projectName": "测试 实验",
                    "pageIndex": 2,
                },
                headers={"businessid": client.business_id},
            )

    def test_authentication_status_triggers_refresh_signal(self):
        def handler(_):
            return httpx.Response(401, json={"message": "expired"})

        with self.create_client(handler) as client:
            with self.assertRaises(AuthenticationError):
                client.request("GET", "/ai/user/info")

    def test_redirect_triggers_refresh_signal(self):
        def handler(_):
            return httpx.Response(302, headers={"location": "/login"})

        with self.create_client(handler) as client:
            with self.assertRaises(AuthenticationError):
                client.request("GET", "/ai/user/info")


if __name__ == "__main__":
    unittest.main()
