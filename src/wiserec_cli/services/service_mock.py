"""使用服务文档样例发起一次服务测试。"""

from __future__ import annotations

import json
import ipaddress
import re
from copy import deepcopy
from typing import Any

from ..errors import ApiError
from .service import ServiceCatalog


def _reject_constant(value: str) -> None:
    raise ValueError(f"非标准 JSON 数值：{value}")


def parse_sample(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("报文必须是非空 JSON 字符串")
    parsed = json.loads(value, parse_constant=_reject_constant)
    # 同时拒绝指数溢出产生的 Infinity。
    json.dumps(parsed, allow_nan=False)
    return parsed


def _required(info: Any, key: str, label: str) -> str:
    value = info.get(key) if isinstance(info, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise ApiError(f"{label}缺少有效的 {key}")
    return value


def validate_host_address(value: str) -> str:
    """接受 IPv4:端口或 [IPv6]:端口，不猜测地址或默认端口。"""
    address = value.strip()
    match = re.fullmatch(r"(?:\[([^\[\]]+)\]|([^:]+)):([0-9]{1,5})", address)
    try:
        if match is None:
            raise ValueError
        bracketed, plain, port = match.groups()
        host = bracketed or plain
        if "%" in host:
            raise ValueError
        ip = ipaddress.ip_address(host)
        if ip.version != (6 if bracketed else 4) or not 1 <= int(port) <= 65535:
            raise ValueError
    except ValueError as exc:
        raise ValueError("host-address 必须为有效的 IPv4:端口或 [IPv6]:端口，端口范围为 1–65535") from exc
    return address


class ServiceMock(ServiceCatalog):
    def run(self, service_id: str, *, transmission_tag: int = 0,
            host_address: str | None = None) -> dict[str, Any]:
        if type(transmission_tag) is not int or transmission_tag not in (0, 1):
            raise ValueError("transmission-tag 仅支持 0 或 1")
        if host_address is not None:
            host_address = validate_host_address(host_address)
        headers = {"businessid": self._business_id()}
        base = self._result(self.client.request(
            "POST", "/ai/backend/mep/services/rtcContainer/queryServiceBaseInfoDetail",
            json_body={"serviceId": service_id}, headers=headers,
        ), "查询服务基本信息")
        name = _required(base.get("serviceInfo"), "serviceName", "服务基本信息")
        version = _required(base.get("serviceInfo"), "serviceVersion", "服务基本信息")
        business_id = _required(base.get("modelInfo"), "businessId", "服务租户信息")

        document = self._result(self.client.request(
            "POST", "/ai/backend/mep/services/queryServiceDoc",
            json_body={"serviceId": service_id}, headers=headers,
        ), "查询服务文档").get("serviceDocument")
        sample = _required(document, "requestContent", "服务文档")
        for key, expected in (("serviceId", service_id), ("businessId", business_id)):
            if key in document and document[key] != expected:
                raise ApiError(f"服务文档 {key} 与目标服务不一致，停止测试")
        try:
            parse_sample(sample)
        except (ValueError, RecursionError) as exc:
            raise ApiError("服务文档 requestContent 不是有效的标准 JSON") from exc

        data = {
            "requestSample": sample, "serviceName": name,
            "serviceVersion": version, "serviceId": service_id,
            "lmsServiceId": "", "algoType": "field-npy",
            "transmissionTag": transmission_tag, "businessId": business_id,
        }
        if host_address is not None:
            data["node"] = {"hostAddress": host_address}
        try:
            payload = self.client.request(
                "POST", "/ai/backend/mep/services/serviceMock",
                json_body={"data": data}, headers=headers,
            )
        except ApiError as exc:
            raise ApiError(f"服务测试未成功确认，执行结果可能未知，不自动重发：{exc}") from exc
        result = self._result(payload, "测试服务")
        self._items(result, "nodeList", "测试服务")
        return payload


def normalize_response(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """保留未知响应字段，解析节点报文，同时返回所有节点的诊断。"""
    normalized = deepcopy(payload)
    nodes = normalized["result"]["nodeList"]
    issues = []
    if not nodes:
        issues.append("未返回可测试节点")
    for index, node in enumerate(nodes, 1):
        label = node.get("hostName") or f"第 {index} 个节点"
        code = node.get("retCode")
        if type(code) is not int or code != 0:
            issues.append(f"{label}：节点测试未成功，retCode={code}")
        raw = node.get("mockResponse")
        node["mockResponseRaw"] = raw
        try:
            node["mockResponse"] = parse_sample(raw)
        except (ValueError, RecursionError):
            issues.append(f"{label}：结果报文无法解析为标准 JSON，保留原文")
    return normalized, issues
