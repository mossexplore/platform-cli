"""资源模板命令和人工可读展示。"""
import json
import sys
from contextlib import redirect_stdout
from decimal import Decimal, InvalidOperation
from typing import Optional

import typer
from rich.table import Table
from rich.text import Text

from ..errors import AuthenticationError, BusinessError
from ..output import console
from ..services.resource import ResourceTemplateService
from .common import fail, runtime_from_context
from .model import display_value, selected_output

resource_app = typer.Typer(no_args_is_help=True, help='资源管理')
template_app = typer.Typer(no_args_is_help=True, help='资源模板查询')
resource_app.add_typer(template_app, name='template')
COLUMNS = (
    ('资源模板 ID', 'dockerId'), ('模板名称', 'dockerResourceTemplateName'),
    ('环境', 'env'), ('YAML 模板名', 'containerSpec'), ('镜像名称', 'appImageName'),
    ('镜像标签', 'imageTag'), ('业务编码', 'businessId'), ('集群名称', 'clusterName'),
    ('创建时间', 'createTime'), ('更新时间', 'updateTime'), ('状态', 'status'),
)


def selected_service(runtime, client):
    selected = runtime.business.selected_business_id(runtime.config.current_profile().name, client.username)
    if selected != client.business_id:
        raise BusinessError('当前环境 selected.businessId 与业务目录不一致，请运行 ml business refresh')
    return ResourceTemplateService(client)


def value(field, item):
    data = item.get(field)
    if data is None or data == '':
        return '-'
    if field == 'status':
        return '在用' if str(data) == '0' else '停用'
    return display_value(field, data)


def table_for(headers, rows):
    table = Table(header_style='bold cyan')
    for header in headers:
        table.add_column(header, overflow='fold', min_width=1)
    for row in rows:
        table.add_row(*(Text(str(cell)) for cell in row))
    return table


def render_list(payload, page, page_size, output):
    if output == 'json':
        typer.echo(json.dumps(payload, ensure_ascii=False))
        return
    result = payload['result']
    items = result['resourceTemplateInfoList']
    table = table_for([title for title, _ in COLUMNS],
                      [[value(field, item) for _, field in COLUMNS] for item in items])
    first = table.columns[0]
    first.width = first.min_width = first.max_width = 36
    first.no_wrap, first.overflow = True, 'ignore'
    console.print(table)
    if not items:
        console.print('暂无容器资源模板')
    console.print(f"第 {page} 页 · 每页 {page_size} 条 · 本页 {len(items)} 条 · 共 {result['count']} 条")


def resource_spec(data):
    cpu, memory, npu = (data.get(key) for key in ('cpu', 'memory', 'npu'))
    if cpu is None or memory is None:
        return '-'
    result = f"{cpu}C{str(memory).removesuffix('G')}G"
    if npu is not None and npu != '':
        try:
            if Decimal(str(npu)) != 0:
                result += f'{npu}NPU'
        except InvalidOperation:
            return result + f' / NPU: {npu}'
    return result


def render_detail(payload, framework, output):
    if output == 'json':
        typer.echo(json.dumps({'resourceTemplate': payload, 'frameworkPackage': framework}, ensure_ascii=False))
        return
    data = payload['result']
    fields = [('容器资源模板名称', value('dockerResourceTemplateName', data)),
              ('资源类型', '-' if data.get('templateType') in (None, '') else
               '容器' if data['templateType'] == 'docker' else '虚拟机'), ('环境', value('env', data)),
              ('集群名称', value('clusterName', data)),
              ('镜像', ' '.join(str(data[key]) for key in ('appImageName', 'imageTag') if data.get(key)) or '-'),
              ('自定义 YAML', value('containerSpec', data)),
              ('配额类型', '-' if not data.get('quotaType') else
               '核心配额' if data['quotaType'] == 'guaranteed' else '弹性配额'),
              ('框架类型', {'rtc': '推理框架', 'gateway': '网关框架', 'algo': '算子框架'}.get(
                  data.get('frameworkType'), value('frameworkType', data))), ('默认资源规格', resource_spec(data)),
              ('挂载 SFS 标识', value('sfsLocation', data)), ('实例数', value('replicas', data))]
    console.print('1、基本信息', style='bold cyan')
    console.print(table_for(['编号', '字段', '值'], [(f'1.{i}', label, val) for i, (label, val) in enumerate(fields, 1)]))
    console.print('2、推理框架', style='bold cyan')
    package = framework['result']['data'] if framework else None
    console.print(Text('2.1、推理框架名称：' + (f"{package['name']}@{package['version']}" if package else '未关联推理框架' if not data.get('frameworkPkgId') else '框架信息不可用')))
    console.print('2.2、参数配置', style='bold')
    config = data.get('frameworkConfiguration')
    parse_error = False
    if config:
        try:
            config = json.loads(config) if isinstance(config, str) else config
            if not isinstance(config, dict):
                raise ValueError('参数配置应为 JSON 对象')
        except (ValueError, TypeError):
            console.print('参数配置解析失败')
            parse_error = True
            config = None
    if config:
        for index, (group, parameters) in enumerate(config.items(), 1):
            console.print(Text(f'2.2.{index}、{group}'), style='bold')
            rows = parameters.items() if isinstance(parameters, dict) else [('值', parameters)]
            console.print(table_for(['编号', '参数名', '参数值'], [
                (f'2.2.{index}.{i}', key, json.dumps(val, ensure_ascii=False) if isinstance(val, (dict, list)) else val)
                for i, (key, val) in enumerate(rows, 1)]))
    elif not parse_error:
        console.print('暂无参数配置')
    console.print('3、扩展信息', style='bold cyan')
    for index, (title, field, headers, keys) in enumerate((
        ('环境变量', 'envs', ['变量名', '变量值'], ['envKey', 'envValue']),
        ('Hosts 映射', 'hostIpNames', ['域名', '映射 IP'], ['hostName', 'hostIp']),
        ('主机调度', 'hostLabels', ['主机标签键', '主机标签值'], ['hostLabelKey', 'hostLabelValue']),
    ), 1):
        console.print(f'3.{index}、{title}', style='bold')
        items = data.get(field)
        if items:
            if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
                raise ValueError(f'{field} 应为对象列表')
            console.print(table_for(['编号'] + headers, [[f'3.{index}.{i}'] + [value(key, item) for key in keys]
                                                        for i, item in enumerate(items, 1)]))
        else:
            console.print('暂无')
    console.print('3.4、启动参数', style='bold')
    args = data.get('args')
    if args:
        if not isinstance(args, list):
            raise ValueError('args 应为列表')
        console.print(table_for(['编号', '参数'], [[f'3.4.{i}', arg] for i, arg in enumerate(args, 1)]))
    else:
        console.print('暂无')
    console.print(Text('3.5、自定义启动命令：' + value('customStartupCommand', data)))
    if parse_error:
        raise ValueError('frameworkConfiguration 参数配置解析失败')


@template_app.command('list')
def list_templates(context: typer.Context,
                   page: int = typer.Option(1, '--page', min=1, help='页码'),
                   page_size: int = typer.Option(10, '--page-size', min=1, help='每页条数'),
                   name: str = typer.Option('', '--name', help='模板名称条件'),
                   env: Optional[str] = typer.Option(None, '--env', help='模板环境条件，不切换连接环境'),
                   framework_name: str = typer.Option('', '--framework-name', help='推理框架包名称条件'),
                   framework_type: Optional[str] = typer.Option(None, '--framework-type', help='框架类型条件'),
                   resource_type: str = typer.Option('docker', '--resource-type', help='资源类型条件'),
                   template_type: str = typer.Option('docker', '--template-type', help='模板类型条件'),
                   output: Optional[str] = typer.Option(None, '--output', '-o', help='table 或 json')):
    """查询资源模板列表"""
    try:
        runtime = runtime_from_context(context)
        selected = selected_output(runtime, output)
        with redirect_stdout(sys.stderr):
            payload = runtime.authenticated_call(lambda client: selected_service(runtime, client).list_templates(
                page, page_size, name, env, framework_name, framework_type, resource_type, template_type))
        render_list(payload, page, page_size, selected)
    except Exception as exc:
        fail(exc)


@template_app.command('detail')
def detail(context: typer.Context,
           template_id: str = typer.Argument(..., help='资源模板 ID'),
           output: Optional[str] = typer.Option(None, '--output', '-o', help='table 或 json')):
    """查询资源模板详情"""
    try:
        if not template_id.strip():
            raise ValueError('资源模板 ID 不能为空')
        runtime = runtime_from_context(context)
        selected = selected_output(runtime, output)
        def query(client):
            service = selected_service(runtime, client)
            payload = service.detail(template_id)
            package_id = payload['result'].get('frameworkPkgId')
            if package_id is None or package_id == '':
                return payload, None, None
            if not isinstance(package_id, str) or not package_id.strip():
                return payload, None, ValueError('frameworkPkgId 应为非空字符串')
            try:
                return payload, service.framework(package_id), None
            except (AuthenticationError, BusinessError):
                raise
            except Exception as exc:
                return payload, None, exc
        with redirect_stdout(sys.stderr):
            payload, framework, error = runtime.authenticated_call(query)
        render_detail(payload, framework, selected)
        if error:
            raise ValueError(f'推理框架查询失败：{error}')
    except Exception as exc:
        fail(exc)
