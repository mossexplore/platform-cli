"""特征任务详情的分区展示。"""

from ..output import print_result
from .train_detail import (
    display,
    display_time,
    grouped_fields,
    object_field,
    records,
    render_custom_config,
    render_grid,
    yes_no,
)


def basic_fields(info, algorithm):
    task_type = info.get("taskType")
    region = info.get("region")
    source = info.get("source")
    cron = object_field(info, "trainTaskCron")
    return [
        ("租户", info.get("businessId")), ("团队", info.get("teamId")), ("任务名称", info.get("taskName")),
        ("任务类型", "Train Fi" if task_type == "train_fi" else task_type),
        ("配额内等待", yes_no(info.get("acceptQueue"))), ("训练模式", info.get("trainMode")),
        ("区域", "北京二" if region == "cn-north-2" else region),
        ("分布式框架", info.get("distFramework")), ("业务子场景", info.get("subScene")),
        ("领域", info.get("scope")), ("资源规格", info.get("imageSpecificInfo")),
        ("敏感", yes_no(info.get("isSensitive"))),
        ("镜像", info.get("imagePackageId")), ("节点数", info.get("infraSize")),
        ("历史记录数目", info.get("maxHistoryNum")),
        ("排队时间(min)", info.get("maxQueueTime")), ("超时时间(s)", cron.get("cronTimeOut")),
        ("输出归档", yes_no(info.get("autoArchive"))),
        ("入口脚本", info.get("startScript")), ("算法", algorithm.get("algorithmName")),
        ("算法版本", algorithm.get("algorithmVersion")),
        ("执行引擎", info.get("trainEngine")), ("创建者", info.get("createUser")),
        ("创建时间", display_time(info.get("createTime"))),
        ("DMQ Topic名称", info.get("dmq")), ("基线/共享", "-"),
        ("来源", "WiseMLOps" if source == "wisemlops" else source),
    ]


def render_detail(result, output):
    if output == "json":
        print_result(result, output)
        return

    info = result["taskInfo"]
    algorithm = object_field(result, "algorithmInfo")
    render_grid("基本信息", grouped_fields(basic_fields(info, algorithm), 3), 3)
    render_grid("数据集", [
        [("数据集目录", group.get("dir")),
         ("数据集名称", ",".join(
             display(item.get("dataSetName")) for item in records(group.get("dataSetList"))
         ))]
        for group in records(info.get("dataSets"))
    ], 2)
    render_grid("特征集引用", [
        [("文件名", row.get("setRefName")), ("特征集名称", row.get("setName")), ("特征集版本", row.get("version"))]
        for row in records(info.get("featureSetRefInfos"))
    ], 3)
    parameters = dict.fromkeys(
        (row["paramKey"], display(row.get("paramValue")))
        for row in records(info.get("params"))
        if isinstance(row.get("paramKey"), str) and row["paramKey"]
    )
    render_grid("参数", grouped_fields(list(parameters), 3), 3)
    render_custom_config(info.get("customizeConfig"))
