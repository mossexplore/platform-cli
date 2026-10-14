"""模型发布命令、部署摘要和交互确认。"""
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Optional

import typer
from rich.text import Text

from ..errors import BusinessError
from ..output import console
from ..services.deploy_payload import HEALTH_DEFAULTS, HEALTH_MODES, UPDATE_MODES
from ..services.model_deploy import ModelDeployService
from .common import fail, runtime_from_context
from .model import selected_output
from .resource import table_for


def context_identity(runtime, client):
    profile = runtime.config.current_profile()
    selected = runtime.business.selected_business_id(profile.name, client.username)
    if selected != client.business_id:
        raise BusinessError('当前环境 selected.businessId 与业务目录不一致，请运行 ml business refresh')
    selection = runtime.business.require_selection(profile.name, client.username)
    if not selection.tenant_id:
        raise BusinessError('缺少真实租户 ID，请重新选择业务')
    return profile.name, profile.api_endpoint, client.username, selected, selection.tenant_id


def interactive_input():
    return sys.stdin.isatty()


def read_document(path):
    return '' if path is None else path.read_text(encoding='utf-8')


def preview(payload, template, identity, template_id, request_file, response_file):
    data = payload['data']
    service, model = data['serviceInfo'], data['modelInfo']
    console.print('1、部署目标', style='bold cyan')
    console.print(table_for(['字段', '值'], [
        ('当前平台环境', identity[0]), ('当前业务', identity[3]), ('真实租户', identity[4]),
        ('模型 ID', model['modelId']), ('模型名称', model['modelName']), ('模型版本', model['modelVersion']),
        ('部署模板 ID', template_id), ('部署模板名称', template.get('deployTemplateName', '-')),
        ('服务名称', service['serviceName']), ('服务版本', service['serviceVersion']),
        ('部署目标环境', service['env']),
    ]))
    console.print('2、服务参数', style='bold cyan')
    components = data['comptPkgs']
    console.print(table_for(['字段', '值'], [
        ('推理类型', {'online': '在线推理', 'offline': '离线推理'}.get(service['inferenceType'], service['inferenceType'])),
        ('更新模式', '滚动更新' if service['updateMode'] == '1' else '原地更新'),
        ('调用超时（ms）', service['serviceTimeout']), ('最大并发数', service['executeLimit']),
        ('单实例最大 QPS', service.get('requestLimit', '未指定，使用平台规则')),
        ('组件包', ','.join(f"{p['comptPkgName']}@{p['comptPkgVersion']}" for p in components if p['businessId'] != 'common') or '-'),
        ('公共组件包', ','.join(f"{p['comptPkgName']}@{p['comptPkgVersion']}" for p in components if p['businessId'] == 'common') or '-'),
    ]))
    console.print('3、健康检查', style='bold cyan')
    health_rows = []
    for field, val in data['extendConfiguration'].items():
        if field in HEALTH_DEFAULTS:
            source = HEALTH_DEFAULTS[field][0]
            origin = '默认值' if template.get(source) is None or template.get(source) == '' else '部署模板'
        elif field == 'terminationGracePeriodSeconds':
            origin = '默认值' if template.get(field) is None or template.get(field) == '' else '部署模板'
        else:
            origin = '真实租户' if field == 'alarmWiseEyeScope' else '命令参数或默认值'
        health_rows.append((field, val, origin))
    console.print(table_for(['参数', '值', '来源'], health_rows))
    console.print('4、部署区域', style='bold cyan')
    names = template['dockerResourceTemplate']
    rows = []
    for name, block in zip(names, data['serviceBlocks']):
        resource = block['resourceRequire']
        spec = f"{resource['cpu']}C{resource['memory']}G / GPU {resource['gpu']} / NPU {resource['npu']}"
        rows.append((name, block['clusterName'], block['imageName'], block['imageVersion'], spec, resource['replicas']))
    console.print(table_for(['模板名称', '集群', '镜像', '镜像标签', '资源规格', '实际实例数'], rows))
    console.print(Text(f"部署区域：{len(rows)}；各区域实例数：1，使用部署命令固定默认值；弹性伸缩：未配置"))
    console.print('5、服务文档', style='bold cyan')
    document = data['serviceDocument']
    console.print(table_for(['字段', '值'], [
        ('描述', document['description'] or '-'),
        ('输入报文文件', str(request_file) if request_file else '-'),
        ('输入报文长度（字符）', len(document['requestContent'])),
        ('输出报文文件', str(response_file) if response_file else '-'),
        ('输出报文长度（字符）', len(document['responseContent'])),
    ]))


def deploy(context: typer.Context,
           model_id: str = typer.Argument(..., help='模型 ID'),
           template_id: str = typer.Option(..., '--template', help='部署模板 ID'),
           qps: Optional[int] = typer.Option(None, '--qps', min=1, help='单实例最大 QPS，未指定时不提交该字段'),
           update_mode: str = typer.Option('rolling', '--update-mode', help='rolling 或 in-place'),
           health_mode: str = typer.Option('default', '--health-check-mode', help='default、response-code 或 response-code-and-data'),
           health_port: int = typer.Option(18090, '--health-port', min=1, max=65535, help='容器健康检查端口'),
           description: str = typer.Option('', '--description', help='服务文档描述'),
           request_file: Optional[Path] = typer.Option(None, '--request-file', exists=True, dir_okay=False, readable=True, help='UTF-8 输入报文文件'),
           response_file: Optional[Path] = typer.Option(None, '--response-file', exists=True, dir_okay=False, readable=True, help='UTF-8 输出报文文件'),
           dry_run: bool = typer.Option(False, '--dry-run', help='查询并预览完整部署配置，不提交'),
           yes: bool = typer.Option(False, '--yes', help='跳过提交确认'),
           output: Optional[str] = typer.Option(None, '--output', '-o', help='table 或 json')):
    """使用部署模板将模型部署为服务"""
    try:
        model_id, template_id = model_id.strip(), template_id.strip()
        if not model_id or not template_id:
            raise ValueError('模型 ID 和部署模板 ID 不能为空')
        if update_mode not in UPDATE_MODES or health_mode not in HEALTH_MODES:
            raise ValueError('更新模式或健康检查模式不合法，请查看 --help')
        if not dry_run and not yes and not interactive_input():
            raise ValueError('非交互环境提交部署必须指定 --yes，可先使用 --dry-run 预览')
        request_content, response_content = read_document(request_file), read_document(response_file)
        runtime = runtime_from_context(context)
        selected = selected_output(runtime, output)
        def prepare(client):
            identity = context_identity(runtime, client)
            payload, template = ModelDeployService(client).prepare(
                model_id, template_id, identity[4], qps=qps, update_mode=update_mode,
                health_mode=health_mode, health_port=health_port, description=description,
                request_content=request_content, response_content=response_content)
            return payload, template, identity
        with redirect_stdout(sys.stderr):
            payload, template, identity = runtime.authenticated_call(prepare)
        if dry_run and selected == 'json':
            typer.echo(json.dumps(payload, ensure_ascii=False))
            return
        with redirect_stdout(sys.stderr) if selected == 'json' else redirect_stdout(sys.stdout):
            preview(payload, template, identity, template_id, request_file, response_file)
        if dry_run:
            console.print('预览完成，未提交部署')
            return
        if not yes and not typer.confirm('确认提交以上部署配置？', err=True):
            typer.echo('已取消部署', err=True)
            return
        def publish(client):
            if context_identity(runtime, client) != identity:
                raise BusinessError('环境、账号或业务上下文已变化，请重新预览后部署')
            return ModelDeployService(client).publish(payload)
        with redirect_stdout(sys.stderr):
            response = runtime.authenticated_call(publish, retry_auth=False)
        result = response['result']
        if selected == 'json':
            typer.echo(json.dumps(response, ensure_ascii=False))
        elif result['code'] == 0:
            console.print('部署成功', style='bold green')
            console.print(Text(f"服务 ID：{result.get('serviceId', '-')}"))
            console.print(Text(f"结果：{result.get('des', '')}"))
        if result['code'] != 0:
            raise ValueError(f"部署失败：code={result['code']}，des={result.get('des', '')}")
    except Exception as exc:
        fail(exc)
