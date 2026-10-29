"""Configuration diagnostics that never echo values, inputs or exception text."""

import json
from pydantic import ValidationError
from .settings import Settings


def describe_config_error(exc):
    if isinstance(exc, FileNotFoundError):
        return "配置文件不存在，请确认 --config 指向现有文件（注意 .json.txt 扩展名）"
    if isinstance(exc, json.JSONDecodeError):
        return f"JSON 格式错误：第 {exc.lineno} 行，第 {exc.colno} 列；检查双引号、逗号和反斜杠，不支持注释"
    if isinstance(exc, UnicodeError):
        return "配置文件编码错误，请保存为 UTF-8"
    if isinstance(exc, OSError):
        return "无法读取配置文件，请检查路径、文件权限和目录是否可访问"
    if isinstance(exc, ValidationError):
        schema = Settings.model_json_schema()
        allowed = set(schema.get("properties", {}))
        for model in schema.get("$defs", {}).values():
            allowed.update(model.get("properties", {}))
        tips = {
            "missing": "缺少必填字段",
            "extra_forbidden": "存在模板未定义的字段，请核对字段名称",
            "literal_error": "值不在允许范围，请对照 config.example.json",
            "too_short": "长度不足（gateway_token 至少 32 字符）",
            "string_too_short": "字符串长度不足",
            "int_parsing": "应填写整数",
            "int_type": "应填写整数",
            "bool_parsing": "应填写 true 或 false",
            "bool_type": "应填写 true 或 false",
            "string_type": "应填写字符串",
            "model_type": "应填写 JSON 对象",
            "list_type": "应填写 JSON 数组",
            "greater_than_equal": "数值低于允许的最小值",
            "less_than_equal": "数值超过允许的最大值",
            "string_pattern_mismatch": "格式不符合要求，请核对环境标识或数据库名称",
            "value_error": "校验失败：检查环境 id 是否重复，以及服务地址是否为无账号密码、无查询参数的 http:// 或 https:// 地址",
        }
        lines = []
        for error in exc.errors(
            include_url=False, include_context=False, include_input=False
        ):
            path = (
                ".".join(
                    str(x) if isinstance(x, int) or x in allowed else "<未知字段>"
                    for x in error["loc"]
                )
                or "配置整体"
            )
            if error["loc"] == ("session",) and error["type"] == "value_error":
                lines.append("session：保活间隔必须小于空闲、会话及凭据超时")
                continue
            lines.append(
                f"{path}：{tips.get(error['type'], '字段类型或取值不正确，请对照配置模板')}"
            )
        return "\n".join(lines)
    return "配置结构或路径无效，请对照 config.example.json；未输出原始异常以保护秘密"
