"""数据集列表与详情接口。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..client import PlatformClient
from ..errors import ApiError, BusinessError


class DatasetService:
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

    def list_datasets(
        self, page: int = 1, page_size: int = 10, name: str = "",
        create_user: str = "", update_user: str = "",
        bucket_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if page < 1 or page_size < 1:
            raise ValueError("page 和 page-size 必须为正整数")
        business_id = self._business_id()
        body = {
            "pageIndex": page, "pageSize": page_size,
            "bucketName": bucket_name, "dataSetName": name,
            "dataSetId": "", "businessId": business_id, "teamId": "",
            "scene": "", "subScene": "", "dataSetType": "",
            "noticeTime": [], "updateNoticeTime": [], "origin": "",
            "notUsedDays": "", "subDatazoneId": "", "tags": "",
            "createUser": create_user, "updateUser": update_user,
            "expireStatus": None, "private": False, "isDeleted": "",
            "sharing": False, "inputName": "", "inputId": "",
            "region": "", "commonTabTitle": "", "algorithmVersion": "",
        }
        payload = self.client.request(
            "POST", "/ai/backend/mtp/dataSet/queryList", json_body=body,
            headers={"businessid": business_id},
        )
        result = self._result(payload, "查询数据集列表")
        total = result.get("totalSize")
        items = result.get("data")
        if type(total) is not int or total < 0:
            raise ApiError("数据集列表缺少有效的 result.totalSize")
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ApiError("数据集列表缺少有效的 result.data")
        return {"total": total, "pageIndex": page,
                "pageSize": page_size, "items": items}

    def dataset_detail(self, dataset_id: str) -> Dict[str, Any]:
        dataset_id = dataset_id.strip()
        if not dataset_id:
            raise ValueError("数据集 ID 不能为空")
        business_id = self._business_id()
        payload = self.client.request(
            "POST", "/ai/backend/mtp/dataSet/queryDetail",
            json_body={"dataSetId": dataset_id, "businessId": business_id, "teamId": ""},
            headers={"businessid": business_id},
        )
        data = self._result(payload, "查询数据集详情").get("data")
        if not isinstance(data, dict):
            raise ApiError("数据集详情缺少有效的 result.data")
        return data
