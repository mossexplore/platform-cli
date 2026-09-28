"""服务列表、主机视图和部署视图查询。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..client import PlatformClient
from ..errors import ApiError, BusinessError


class ServiceCatalog:
    def __init__(self, client: PlatformClient):
        self.client = client

    def _business_id(self) -> str:
        business_id = self.client.business_id
        if not business_id:
            raise BusinessError("尚未选择租户或团队，请运行 ml business use")
        return business_id

    @staticmethod
    def _result(payload: Any, action: str) -> Dict[str, Any]:
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ApiError(f"{action}失败：响应缺少 result")
        if type(result.get("code")) is not int or result["code"] != 0:
            raise ApiError(f"{action}失败：code={result.get('code')}，des={result.get('des')}")
        return result

    @staticmethod
    def _items(result: Dict[str, Any], key: str, action: str) -> list[dict[str, Any]]:
        items = result.get(key)
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ApiError(f"{action}失败：响应缺少有效的 result.{key}")
        return items

    @staticmethod
    def _count(result: Dict[str, Any], action: str, *, required: bool) -> Optional[int]:
        count = result.get("count")
        if count is None and not required:
            return None
        if type(count) is not int or count < 0:
            raise ApiError(f"{action}失败：响应缺少有效的 result.count")
        return count

    def list_services(
        self, page: int = 1, page_size: int = 10,
        name: Optional[str] = None, model_name: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        if page < 1 or page_size < 1:
            raise ValueError("page 和 page-size 必须为正整数")
        business_id = self._business_id()
        body = {
            "pageIndex": page, "pageSize": page_size, "inferenceType": None,
            "env": None, "tags": [], "serviceName": name, "selectService": None,
            "modelName": model_name, "selectModelName": None,
            "modelVersion": model_version, "businessId": business_id,
            "teamId": "", "infraType": None, "owner": None, "status": None,
            "isAccess": None, "noAccessDays": None, "isLowLoad": None,
            "lowLoadDays": None, "noticeTime": [], "clusterId": None,
            "clusterBusinessId": business_id, "isCluster": None,
            "dailTestTaskStatus": None, "scaleFlag": None,
        }
        payload = self.client.request(
            "POST", "/ai/backend/mep/services/queryList", json_body=body,
            headers={"businessid": business_id},
        )
        result = self._result(payload, "查询服务列表")
        return {
            "total": self._count(result, "查询服务列表", required=True),
            "pageIndex": page, "pageSize": page_size,
            "items": self._items(result, "services", "查询服务列表"),
        }

    def list_hosts(self, service_id: str) -> Dict[str, Any]:
        business_id = self._business_id()
        payload = self.client.request(
            "POST", "/ai/backend/mep/services/rtcContainer/queryServiceHostList",
            json_body={
                "businessId": business_id, "serviceId": service_id,
                "status": "", "hostIp": "", "clusterName": "",
                "preheatStatus": "ALL", "quotaType": None,
                "pageIndex": 1, "pageSize": 10,
            },
            headers={"businessid": business_id},
        )
        result = self._result(payload, "查询服务主机视图")
        return {
            "total": self._count(result, "查询服务主机视图", required=True),
            "pageIndex": 1, "pageSize": 10,
            "items": self._items(result, "data", "查询服务主机视图"),
        }

    def list_deployments(self, service_id: str) -> Dict[str, Any]:
        business_id = self._business_id()
        payload = self.client.request(
            "POST", "/ai/backend/mep/services/rtcContainer/queryDetail",
            json_body={
                "pageIndex": 1, "pageSize": 10,
                "serviceId": service_id, "businessId": business_id,
            },
            headers={"businessid": business_id},
        )
        result = self._result(payload, "查询服务部署视图")
        page = {
            "pageIndex": 1, "pageSize": 10,
            "items": self._items(result, "data", "查询服务部署视图"),
        }
        count = self._count(result, "查询服务部署视图", required=False)
        if count is not None:
            page["total"] = count
        return page
