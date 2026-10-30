"""当前业务下的质量监控报告分页查询。"""

from ..errors import ApiError, BusinessError

PREFIX = "/ai/backend/dpp/proxy/featurestore/quality-visualization/features"
TYPES = {
    "CONTINUOUS": "连续", "DISCRETE": "离散", "ORDINAL": "有序",
    "CATEGORICAL": "分类", "SEQUENCE": "序列", "LONG_SEQUENCE": "长序列",
    "VECTOR": "向量",
}


def normalize_type(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("类型必须为中文名称或英文枚举字符串")
    candidate = value.strip().upper()
    if candidate in TYPES:
        return candidate
    for key, label in TYPES.items():
        if candidate == label:
            return key
    raise ValueError("类型仅支持：" + "、".join(f"{label}/{key}" for key, label in TYPES.items()))


class QualityService:
    def __init__(self, client):
        self.client = client

    def _list(self, suffix, list_key, body):
        page, size = body["pageIndex"], body["pageSize"]
        if type(page) is not int or page < 1:
            raise ValueError("page 必须为正整数")
        if type(size) is not int or not 1 <= size <= 100:
            raise ValueError("page-size 必须为 1～100 的整数")
        if not self.client.business_id.strip():
            raise BusinessError("尚未选择业务，请运行 ml business use")
        payload = self.client.request(
            "POST", PREFIX + suffix, json_body=body,
            headers={"businessid": self.client.business_id},
        )
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ApiError("质量监控查询响应缺少有效的 result")
        if type(result.get("code")) is not int or result["code"] != 0:
            raise ApiError(f"质量监控查询失败：code={result.get('code')}，des={result.get('des', '')}")
        items = result.get(list_key)
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ApiError(f"质量监控查询响应缺少有效的 {list_key} 数组")
        count = result.get("totalCount")
        if type(count) is not int or count < 0:
            raise ApiError("质量监控查询响应缺少有效的 totalCount")
        # 示例可能省略分页字段；存在时必须采用并验证服务端实际值。
        page, size = result.get("pageIndex", page), result.get("pageSize", size)
        if any(type(v) is not int or v < 1 for v in (page, size)):
            raise ApiError("质量监控查询响应的分页信息无效")
        return {"items": items, "count": count, "pageIndex": page, "pageSize": size}

    def list_features(self, page=1, page_size=10, name="", table_name="",
                      feature_value_type=None, indicator_type=None):
        body = {"featureName": name, "tableName": table_name,
                "pageIndex": page, "pageSize": page_size}
        for field, value in (("featureValueType", feature_value_type),
                             ("indicatorType", indicator_type)):
            normalized = normalize_type(value)
            if normalized is not None:
                body[field] = normalized
        return self._list("", "featureList", body)

    def list_wide_featuresets(self, page=1, page_size=10, name=""):
        return self._list("/wide-feature-sets", "featureSetList", {
            "setName": name, "pageIndex": page, "pageSize": page_size,
        })
