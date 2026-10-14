"""按 Web 部署表单结构展示最终待提交数据。"""
import json
from decimal import Decimal

from rich.text import Text

from ..output import console
from ..services.deploy_payload import HEALTH_DEFAULTS
from .resource import table_for

HEALTH_LABELS = {
    'healthType': '健康检查类型', 'healthPath': '健康检查方法',
    'startTimeout': '服务拉起超时时间（s）', 'healthCheckTimeout': '健康检查超时时间（s）',
    'healthPort': '容器健康检查端口', 'initialDelaySeconds': '运行多少时间后开始健康检查（s）',
    'periodSeconds': '健康检查间隔时间（s）', 'failureThreshold': '不健康阈值',
    'alarmWiseEyeScope': '告警上报云眼领域', 'terminationGracePeriodSeconds': '优雅下线时间（s）',
    'healthCheckTypeInContainer': '使用样例报文健康检查',
}


def heading(text):
    console.print(Text(text), style='bold cyan')


def shown(value):
    if value is None or value == '':
        return '未填写'
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def region_preview(index, name, block, framework_names):
    prefix = f'2.{index}'
    heading(f"{prefix}、{block['clusterName']}")
    heading(f'{prefix}.1、基本信息')
    resource = block['resourceRequire']
    spec = f"{resource['cpu']}C{resource['memory']}G"
    for field, suffix in [('gpu', 'GPU'), ('npu', 'NPU')]:
        if Decimal(str(resource[field])) != 0:
            spec += f'{resource[field]}{suffix}'
    console.print(table_for(['字段', '值'], [
        ('集群名称', block['clusterName']), ('镜像', f"{block['imageName']} {block['imageVersion']}"),
        ('自定义 YAML', block['templateId']), ('默认资源规格', spec), ('实例数', resource['replicas']),
        ('名称', shown(block['blockName'])), ('描述', shown(block['description'])),
    ]))
    heading(f'{prefix}.2、推理框架')
    framework = block['inferFramework']
    console.print(table_for(['字段', '值'], [
        ('推理框架名', framework_names.get(framework['inferFrameId'], framework['inferFrameId']))]))
    for group_index, (group, values) in enumerate(framework['configuration'].items(), 1):
        heading(f'{prefix}.2.{group_index}、{group}')
        rows = values.items() if isinstance(values, dict) else [('值', values)]
        console.print(table_for(['参数名', '参数值'], [(key, shown(val)) for key, val in rows]))
    heading(f'{prefix}.3、弹性伸缩')
    console.print(table_for(['字段', '值'], [('弹性开关', '停用' if block['elasticConfig'] is None else '启用')]))
    heading(f'{prefix}.4、扩展信息')
    for sub, (title, field, headers, keys) in enumerate([
        ('环境变量', 'envs', ['变量名', '变量值'], ['envKey', 'envValue']),
        ('Hosts 映射', 'hostIpNames', ['域名', '映射 IP'], ['hostName', 'hostIp']),
        ('主机调度', 'hostLabels', ['主机标签键', '主机标签值'], ['hostLabelKey', 'hostLabelValue']),
    ], 1):
        heading(f'{prefix}.4.{sub}、{title}')
        if block[field]:
            console.print(table_for(headers, [[shown(item.get(key)) for key in keys] for item in block[field]]))
        else:
            console.print('未填写')
    heading(f'{prefix}.4.4、启动参数')
    if block['args']:
        console.print(table_for(['参数'], [[shown(arg)] for arg in block['args']]))
    else:
        console.print('未填写')
    heading(f'{prefix}.4.5、自定义启动命令')
    console.print(Text(shown(block['customStartupCommand'])))


def preview(payload, template, identity, template_id, request_file, response_file, framework_names):
    data = payload['data']
    service, model = data['serviceInfo'], data['modelInfo']
    components = data['comptPkgs']
    heading('1、基本信息')
    console.print(table_for(['字段', '值'], [
        ('模型名称', model['modelName']), ('模型版本', model['modelVersion']),
        ('部署方式', '容器部署'), ('更新模式', '滚动更新' if service['updateMode'] == '1' else '原地更新'),
        ('环境', service['env']),
        ('推理类型', {'online': '在线推理', 'offline': '离线推理'}.get(service['inferenceType'], service['inferenceType'])),
        ('单服务实例最大QPS（超过了会触发流控）', service.get('requestLimit', '-')),
        ('单服务实例最大能承受并发数（超过了会触发流控）', service['executeLimit']), ('服务调用方最大容忍超时时间（ms）', service['serviceTimeout']),
        ('自定义组件包', ','.join(f"{p['comptPkgName']}@{p['comptPkgVersion']}" for p in components if p['businessId'] != 'common') or '-'),
        ('公共组件包（平台提供）', ','.join(f"{p['comptPkgName']}@{p['comptPkgVersion']}" for p in components if p['businessId'] == 'common') or '-'),
    ]))
    heading('2、部署区域')
    for index, (name, block) in enumerate(zip(template['dockerResourceTemplate'], data['serviceBlocks']), 1):
        region_preview(index, name, block, framework_names)
    heading('3、扩展参数')
    rows = []
    health = data['extendConfiguration']
    for field, label in HEALTH_LABELS.items():
        if field in HEALTH_DEFAULTS or field == 'terminationGracePeriodSeconds':
            source = HEALTH_DEFAULTS[field][0] if field in HEALTH_DEFAULTS else field
            origin = '默认值' if template.get(source) is None or template.get(source) == '' else '部署模板'
        else:
            origin = '真实租户' if field == 'alarmWiseEyeScope' else '命令参数或默认值'
        val = health[field]
        if field == 'healthType':
            val = {'httpGet': 'http', 'tcpSocket': 'tcp'}.get(val, val)
        rows.append((label, val, origin))
    console.print(table_for(['参数', '值', '来源'], rows))
    heading('4、服务文档')
    document = data['serviceDocument']
    heading('4.1、服务描述')
    console.print(Text(shown(document['description'])))
    for index, (title, key, path) in enumerate([
        ('输入报文', 'requestContent', request_file), ('输出报文', 'responseContent', response_file),
    ], 2):
        heading(f'4.{index}、{title}')
        if path:
            console.print(Text(f'文件：{path}'))
        console.print(Text(shown(document[key])))
