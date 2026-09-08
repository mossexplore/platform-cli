"""宽表与模型特征集的只读查询。"""

import json
from typing import Any, Dict, Optional

from ..client import PlatformClient
from ..errors import ApiError, BusinessError


class FeatureSetService:
    def __init__(self, client: PlatformClient):
        self.client = client

    def get_config(self, set_id: str) -> Dict[str, Any]:
        set_id = set_id.strip()
        if not set_id:
            raise ValueError("特征集 ID 不能为空")
        if not self.client.business_id.strip():
            raise BusinessError("尚未选择租户或团队，请运行 ml business use")
        payload = self.client.request(
            "POST", "/ai/backend/dpp/proxy/featureStore/featureset/config",
            json_body={"businessId": self.client.business_id, "setId": set_id},
        )
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ApiError("特征集配置查询响应缺少有效的 result")
        if (type(result.get("code")) is not int or result["code"] != 0
                or result.get("des") != "success"):
            raise ApiError(
                f"特征集配置查询失败: code={result.get('code')}，des={result.get('des')}"
            )
        raw_config = result.get("featureJson")
        if not isinstance(raw_config, str) or not raw_config.strip():
            raise ApiError("特征集配置查询响应缺少有效的 featureJson 字符串")
        try:
            config = json.loads(raw_config, parse_constant=self._invalid_json_constant)
        except ValueError as exc:
            raise ApiError(f"featureJson 不是有效的 JSON: {exc}") from exc
        if not isinstance(config, dict):
            raise ApiError("featureJson 必须是 JSON 对象")
        return config

    @staticmethod
    def _invalid_json_constant(value: str) -> None:
        # Python 默认接受 NaN/Infinity，这些不是合法 JSON 值。
        raise ValueError(f"不支持的 JSON 常量: {value}")

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
