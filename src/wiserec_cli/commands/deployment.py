"""部署模板列表和关联资源详情展示。"""
import json
import sys
from contextlib import redirect_stdout
from typing import Optional

import typer
from rich.text import Text

from ..errors import BusinessError
from ..output import console
from ..services.deployment import DeploymentTemplateService
from .common import fail, runtime_from_context
from .model import selected_output
from .resource import table_for, value

deployment_app = typer.Typer(no_args_is_help=True, help='部署管理')
template_app = typer.Typer(no_args_is_help=True, help='部署模板查询')
deployment_app.add_typer(template_app, name='template')
COLUMNS = (
    ('部署模板 ID', 'deployTemplateId'), ('模板名称', 'deployTemplateName'), ('环境', 'env'),
    ('业务编码', 'businessId'), ('组件包', 'comptPkgInfoList'), ('模板类型', 'deployTemplateType'),
    ('资源模板', 'dockerResourceTemplate'), ('推理类型', 'inferenceType'),
    ('是否默认模板', 'defaultFlag'), ('创建时间', 'createTime'),
    ('更新时间', 'updateTime'), ('是否系统模板', 'isSystem'),
)
RESOURCE_COLUMNS = (
    ('模板名称', 'dockerResourceTemplateName'), ('YAML 模板名', 'containerSpec'),
    ('镜像名称', 'appImageName'), ('镜像标签', 'imageTag'), ('集群名称', 'clusterName'),
    ('实例数', 'replicas'), ('创建时间', 'createTime'), ('更新时间', 'updateTime'), ('状态', 'status'),
)
BASIC_FIELDS = (
    ('租户', 'businessId'), ('是否默认模板', 'defaultFlag'), ('部署模板名称', 'deployTemplateName'),
    ('环境', 'env'), ('资源模板类型', 'deployTemplateType'), ('组件包', 'customComponents'),
    ('公共组件包（平台提供）', 'commonComponents'), ('工作进程数', 'workNum'),
    ('单个工作进程线程数', 'threadNum'), ('单服务实例最大能承受并发数（超过了会触发流控）', 'executeLimit'),
    ('服务调用方最大容忍超时时间（ms）', 'serviceTimeout'), ('是否系统模板', 'isSystem'),
    ('推理类型', 'inferenceType'), ('描述', 'description'),
)
HEALTH_FIELDS = (
    ('健康检查类型', 'healthType'), ('健康检查方法', 'healthPath'),
    ('服务拉起超时时间（s）', 'startTimeOut'), ('健康检查超时时间（s）', 'healthCheckTimeout'),
    ('运行多少时间后开始健康检查（s）', 'initialDelaySeconds'), ('健康检查间隔时间（s）', 'periodSeconds'),
    ('不健康阈值', 'failureThreshold'), ('优雅下线时间（s）', 'terminationGracePeriodSeconds'),
)


def components(data, common=None):
    items = data.get('comptPkgInfoList') or []
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ValueError('comptPkgInfoList 应为对象列表')
    return ','.join(f"{value('name', item)}@{value('version', item)}" for item in items
                    if common is None or (item.get('businessId') == 'common') == common) or '-'


def display(field, data):
    raw = data.get(field)
    if field == 'healthType' and raw == 'httpGet':
        return 'http'
    if field in {'defaultFlag', 'isSystem'}:
        return '-' if raw is None or raw == '' else '否' if str(raw) == '0' else '是'
    if field == 'comptPkgInfoList':
        return components(data)
    if field in {'customComponents', 'commonComponents'}:
        return components(data, common=field == 'commonComponents')
    if field == 'dockerResourceTemplate':
        if raw is None or raw == []:
            return '-'
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            raise ValueError('dockerResourceTemplate 应为名称列表')
        return ','.join(raw)
    return value(field, data)


def selected_service(runtime, client):
    selected = runtime.business.selected_business_id(runtime.config.current_profile().name, client.username)
    if selected != client.business_id:
        raise BusinessError('当前环境 selected.businessId 与业务目录不一致，请运行 ml business refresh')
    return DeploymentTemplateService(client)


def render_list(payload, page, page_size, output):
    if output == 'json':
        typer.echo(json.dumps(payload, ensure_ascii=False))
        return
    result = payload['result']
    items = result['deployTemplates']
    table = table_for([title for title, _ in COLUMNS],
                      [[display(field, item) for _, field in COLUMNS] for item in items])
    first = table.columns[0]
    first.width = first.min_width = first.max_width = 36
    first.no_wrap, first.overflow = True, 'ignore'
    console.print(table)
    if not items:
        console.print('暂无部署模板')
    console.print(f"第 {page} 页 · 每页 {page_size} 条 · 本页 {len(items)} 条 · 共 {result['count']} 条")


def render_detail(payload, output):
    if output == 'json':
        typer.echo(json.dumps(payload, ensure_ascii=False))
        return
    data = payload['deploymentTemplate']['result']['template']
    for index, (title, fields) in enumerate([('基本信息', BASIC_FIELDS), ('健康检查参数', HEALTH_FIELDS)], 1):
        console.print(f'{index}、{title}', style='bold cyan')
        console.print(table_for(['编号', '字段', '值'], [
            (f'{index}.{i}', label, display(field, data)) for i, (label, field) in enumerate(fields, 1)]))
    console.print('3、容器资源模板', style='bold cyan')
    resources = payload['resourceTemplates']
    rows = [item for entry in resources for item in entry['exactMatches']]
    if rows:
        console.print(table_for(['编号'] + [title for title, _ in RESOURCE_COLUMNS],
                               [[f'3.{i}'] + [value(field, item) for _, field in RESOURCE_COLUMNS]
                                for i, item in enumerate(rows, 1)]))
    elif not resources:
        console.print('暂无关联容器资源模板')
    else:
        console.print('暂无匹配的容器资源模板')
    for entry in resources:
        if entry['error']:
            console.print(Text(f"{entry['requestedName']}：{entry['error']}"))


@template_app.command('list')
def list_templates(context: typer.Context,
                   page: int = typer.Option(1, '--page', min=1, help='页码'),
                   page_size: int = typer.Option(10, '--page-size', min=1, help='每页条数'),
                   name: Optional[str] = typer.Option(None, '--name', help='部署模板名称条件'),
                   framework_name: str = typer.Option('', '--framework-name', help='推理框架包名称条件'),
                   env: Optional[str] = typer.Option(None, '--env', help='模板环境条件，不切换连接环境'),
                   framework_type: Optional[str] = typer.Option(None, '--framework-type', help='框架类型条件'),
                   output: Optional[str] = typer.Option(None, '--output', '-o', help='table 或 json')):
    """查询部署模板列表"""
    try:
        runtime = runtime_from_context(context)
        selected = selected_output(runtime, output)
        with redirect_stdout(sys.stderr):
            payload = runtime.authenticated_call(lambda client: selected_service(runtime, client).list_templates(
                page, page_size, framework_name, env, framework_type, name=name))
        render_list(payload, page, page_size, selected)
    except Exception as exc:
        fail(exc)


@template_app.command('detail')
def detail(context: typer.Context,
           template_id: str = typer.Argument(..., help='部署模板 ID'),
           output: Optional[str] = typer.Option(None, '--output', '-o', help='table 或 json')):
    """查询部署模板详情"""
    try:
        if not template_id.strip():
            raise ValueError('部署模板 ID 不能为空')
        runtime = runtime_from_context(context)
        selected = selected_output(runtime, output)
        with redirect_stdout(sys.stderr):
            payload = runtime.authenticated_call(lambda client: selected_service(runtime, client).detail(template_id))
        render_detail(payload, selected)
        if any(entry['error'] for entry in payload['resourceTemplates']):
            raise ValueError('关联资源模板查询存在失败、缺失或同名歧义，请核对详情输出')
    except Exception as exc:
        fail(exc)
