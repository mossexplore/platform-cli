"""算法仓列表、下载地址和克隆接口。"""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import uuid4

from ..client import PlatformClient
from ..downloads import https_url
from ..errors import ApiError, AuthenticationError, BusinessError


class AlgorithmService:
    def __init__(self, client: PlatformClient):
        self.client = client

    def _business_id(self) -> str:
        if not self.client.business_id:
            raise BusinessError("尚未选择租户或团队，请运行 ml business use")
        return self.client.business_id

    @staticmethod
    def _result(payload: Any, action: str) -> Dict[str, Any]:
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ApiError(f"{action}失败：响应缺少 result")
        if type(result.get("code")) is not int or result["code"] != 0:
            raise ApiError(f"{action}失败：code={result.get('code')}，des={result.get('des')}")
        return result

    def list_algorithms(
        self, page: int = 1, page_size: int = 10,
        name: str = "", bucket_name: str = "",
    ) -> Dict[str, Any]:
        if page < 1 or page_size < 1:
            raise ValueError("page 和 page-size 必须大于等于 1")
        business_id = self._business_id()
        payload = self.client.request(
            "POST", "/ai/backend/modelDev/algorithmWarehouse/list",
            json_body={
                "data": {
                    "businessId": business_id, "pageIndex": page, "pageSize": page_size,
                    "algorithmName": name, "updater": "", "creator": "",
                    "visualTag": "", "algorithmVersion": "", "tagsList": [],
                    "bucketName": bucket_name, "region": "", "algorithmPurpose": "",
                    "enableFlag": "", "noticeTime": [], "beginTime": None,
                    "endTime": None, "teamId": "",
                },
                "meta": {"uuid": str(uuid4())}, "version": "1.0",
            },
            headers={"businessid": business_id},
        )
        data = self._result(payload, "查询算法仓列表").get("data")
        if not isinstance(data, dict) or type(data.get("total")) is not int or data["total"] < 0:
            raise ApiError("算法仓列表缺少有效的 result.data.total")
        if not isinstance(data.get("list"), list) or not all(
            isinstance(item, dict) for item in data["list"]
        ):
            raise ApiError("算法仓列表缺少有效的 result.data.list")
        return {"total": data["total"], "pageIndex": page,
                "pageSize": page_size, "items": data["list"]}

    def download_url(self, algorithm_id: str) -> str:
        algorithm_id = algorithm_id.strip()
        if not algorithm_id:
            raise ValueError("算法仓 ID 不能为空")
        business_id = self._business_id()
        payload = self.client.request(
            "GET", "/ai/backend/mtp/algorithm/downloadurl",
            params={"businessId": business_id, "algorithmId": algorithm_id},
            headers={"businessid": business_id},
        )
        url = self._result(payload, "获取算法仓下载地址").get("url")
        https_url(url)
        return url

    def clone(self, source_id: str, name: str, version: str) -> Optional[str]:
        source_id = source_id.strip()
        if not source_id or not name.strip() or not version.strip():
            raise ValueError("源算法仓 ID、新名称和版本均不能为空")
        business_id = self._business_id()
        operator = self.client.username
        if not isinstance(operator, str) or not operator.strip():
            raise BusinessError("当前登录账号无效，请运行 ml login")
        try:
            payload = self.client.request(
                "POST", "/ai/backend/modelDev/algorithmWarehouse/copy",
                json_body={"data": {
                    "srcId": source_id, "businessId": business_id,
                    "operator": operator, "tarName": name, "tarVersion": version,
                }},
                headers={"businessid": business_id},
            )
        except AuthenticationError as exc:
            raise ApiError(f"克隆算法仓结果未能确认：{exc}；请先查询算法仓列表") from exc
        result = self._result(payload, "克隆算法仓")
        created = result.get("data")
        return created.get("id") if isinstance(created, dict) and isinstance(created.get("id"), str) else None
