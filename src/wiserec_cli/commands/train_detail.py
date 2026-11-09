"""Render the training task detail without modifying the API response."""

import json
import re
from datetime import datetime

from rich.table import Table
from rich.text import Text

from ..models import BEIJING_TIMEZONE
from ..output import console, print_result, print_text


def object_field(data, field):
    value = data.get(field)
    return value if isinstance(value, dict) else {}


def records(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def display(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return "-" if value is None or value == "" else str(value)


def yes_no(value):
    return {True: "是", False: "否"}[value] if isinstance(value, bool) else value


def display_time(value):
    try:
        if isinstance(value, str):
            # Python 3.9 only accepts three or six fractional digits in fromisoformat.
            value = re.sub(r"(?<=\d{2}:\d{2}:\d{2})[.,]\d+", "", value, count=1)
            timestamp = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
            if timestamp.tzinfo is not None:
                timestamp = timestamp.astimezone(BEIJING_TIMEZONE)
        elif type(value) in (int, float):
            timestamp = datetime.fromtimestamp(value / 1000, BEIJING_TIMEZONE)
        else:
            return display(value)
    except (ValueError, OverflowError, OSError):
        return display(value)
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def render_grid(title, rows, columns):
    print_text(title)
    table = Table(show_header=False)
    for _ in range(columns):
        table.add_column(ratio=1, overflow="fold")
    for row in rows:
        table.add_row(*(Text(f"{key}：{display(value)}") for key, value in row))
    if not table.row_count:
        print_text("-")
    else:
        console.print(table)


def grouped_fields(fields, columns):
    return [fields[index:index + columns] for index in range(0, len(fields), columns)]


def basic_fields(data, info, parameter, source):
    resource = object_field(info, "resource")
    environment = object_field(info, "environment")
    config = object_field(info, "taskConfig")
    base = object_field(info, "baseInfo")
    timeout = config.get("cronTimeOut")
    if timeout is None:
        timeout = object_field(config, "scheduling").get("cronTimeOut")
    mode = base.get("trainMode")
    region = environment.get("region")
    return [
        ("租户", data.get("businessId")), ("团队", info.get("teamId")), ("任务名称", data.get("name")),
        ("任务类型", info.get("category")), ("配额内等待", yes_no(resource.get("acceptQueue"))),
        ("训练模式", "单机单卡" if mode == "singleNodeSingleGpu" else mode),
        ("区域", "北京二" if region == "cn-north-2" else region), ("分布式框架", info.get("distFramework")),
        ("业务子场景", info.get("subScene")), ("领域", info.get("scope")),
        ("镜像", environment.get("imagePackageId")), ("资源规格", resource.get("imageSpecificInfo")),
        ("敏感", yes_no(config.get("isSensitive"))), ("节点数", resource.get("infraSize")),
        ("历史记录数目", config.get("maxHistoryNum")), ("排队时间(min)", config.get("maxQueueTime")),
        ("超时时间(s)", timeout), ("输出归档", yes_no(config.get("autoArchive"))),
        ("入口脚本", parameter.get("startScript")), ("算法", environment.get("algorithmName")),
        ("算法版本", environment.get("algorithmVersion")), ("执行引擎", info.get("trainEngine")),
        ("创建者", info.get("createUser")), ("创建时间", display_time(data.get("createTime"))),
        ("DMQ Topic名称", info.get("dmq")), ("基线/共享", "-"), ("来源", source),
        ("最大重试次数", config.get("maxRetryTimes")), ("过期时间（天）", info.get("expireDate")),
    ]


def render_detail(data, output):
    if output == "json":
        print_result(data, output)
        return
    info = object_field(data, "taskInfo")
    parameter = object_field(info, "parameter")
    samples = info.get("samples")
    sample = samples[0] if isinstance(samples, list) and samples and isinstance(samples[0], dict) else {}
    source = info.get("source")
    if source == "wisemlops":
        source = "WiseMLOps"
    render_grid("基本信息", grouped_fields(basic_fields(data, info, parameter, source), 3), 3)
    render_grid("数据集", [
        [("数据集目录", row.get("dataSetDirectory")), ("数据集名称", row.get("dataSetName")),
         ("区域", row.get("region")), ("来源", source)]
        for row in records(sample.get("dataSets"))
    ], 4)
    render_grid("输出引用", [
        [("输出目录", row.get("modelDirectory")), ("输出名称", row.get("modelName"))]
        for row in records(info.get("quoteModels"))
    ], 2)
    render_grid("组合配置引用", [
        [("文件名", row.get("mutiGroupRefName")), ("组合配置名称", row.get("mutiGroupName"))]
        for row in records(sample.get("mutiGroupRefInfos"))
    ], 2)
    render_grid("特征集引用", [
        [("文件名", row.get("setRefName")), ("特征集名称", row.get("setName"))]
        for row in records(sample.get("featureSetRefInfos"))
    ], 2)
    parameters = [
        (row["paramKey"], row.get("paramValue")) for row in records(parameter.get("algorithmConfig"))
        if isinstance(row.get("paramKey"), str) and row["paramKey"]
    ]
    render_grid("参数", grouped_fields(parameters, 3), 3)

    render_custom_config(parameter.get("customizeConfig"))


def render_custom_config(custom):
    print_text("自定义参数")
    if isinstance(custom, str) and custom.strip():
        try:
            custom = json.dumps(json.loads(custom), ensure_ascii=False, indent=2)
        except ValueError:
            custom = custom.replace("\\n", "\n")
        print_text(custom)
    else:
        print_text("-")
