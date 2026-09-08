"""宽表与模型特征集的只读查询。"""

from typing import Any, Dict, Optional

from ..client import PlatformClient
from ..errors import ApiError, BusinessError


class FeatureSetService:
    def __init__(self, client: PlatformClient):
        self.client = client

    def list_sets(
        self, set_type: str, page_index: int = 1, page_size: int = 10,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if set_type not in {"wide", "model"}:
            raise ValueError("特征集类型仅支持 wide 或 model")
        if any(type(value) is not int or value < 1 for value in (page_index, page_size)):
            raise ValueError("page 和 page-size 必须为正整数")
        if not self.client.business_id.strip():
            raise BusinessError("尚未选择租户或团队，请运行 ml business use")
        payload = self.client.request(
            "POST", "/ai/backend/dpp/proxy/featureStore/featureset/names",
            json_body={
                "pageIndex": page_index, "pageSize": page_size,
                "businessId": self.client.business_id, "teamId": "",
                "setName": name if name is not None else "",
                "scene": "", "subscene": "", "operator": "", "modifier": "",
                "setType": set_type, "tagIdList": "",
            },
        )
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ApiError("特征集查询响应缺少有效的 result")
        if type(result.get("code")) is not int or result["code"] != 0:
            raise ApiError(
                f"特征集查询失败: {result.get('des') or '未知错误'} "
                f"(code={result.get('code')})"
            )
        items = result.get("featureSetInfoList")
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ApiError("特征集查询响应缺少有效的 featureSetInfoList 数组")
        count = result.get("totalCount")
        if type(count) is not int or count < 0:
            raise ApiError("特征集查询响应缺少有效的 totalCount")
        return {"count": count, "pageIndex": page_index, "pageSize": page_size,
                "items": items}
