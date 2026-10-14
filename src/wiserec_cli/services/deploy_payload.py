"""将模型、部署模板及区域资源转换为发布接口请求。"""
import json
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from ..errors import ApiError

MODEL_FIELDS = {
    'modelSource': 'source', 'modelSourceId': 'sourceId', 'modelSourceEnv': 'sourceEnv',
    'modelTag': 'modelTag', 'modelId': 'modelId', 'modelPkgLocationReplicas': 'modelHistoryList',
    'modelName': 'modelName', 'modelVersion': 'modelVersion', 'modelPkgId': 'pkgId',
    'modelType': 'modelType', 'modelSize': 'pkgSize', 'modelPkgLocation': 'pkgLocation',
    'businessId': 'businessId', 'teamId': 'teamId', 'storeType': 'storeType', 'tags': 'tags',
}
COMPONENT_FIELDS = {
    'comptPkgId': 'comptPkgId', 'comptPkgName': 'name', 'comptPkgVersion': 'version',
    'nspPkgId': 'nspPkgId', 'nspPkgLocation': 'nspPkgLocation',
    'businessId': 'businessId', 'comptPkgFileName': 'comptPkgFileName',
}
HEALTH_DEFAULTS = {
    'healthCheckTimeout': ('healthCheckTimeout', '5'), 'startTimeout': ('startTimeOut', '120'),
    'initialDelaySeconds': ('initialDelaySeconds', '120'), 'periodSeconds': ('periodSeconds', '10'),
    'failureThreshold': ('failureThreshold', '3'), 'healthPath': ('healthPath', 'health'),
    'healthType': ('healthType', 'httpGet'),
}
UPDATE_MODES = {'rolling': '1', 'in-place': '0'}
HEALTH_MODES = {'default': 'Default', 'response-code': 'RespCodeMatch',
                'response-code-and-data': 'RespCodeAndDataMatch'}


def required(data, key, *, allow_empty=False):
    if key not in data or data[key] is None or (not allow_empty and data[key] == ''):
        raise ApiError(f'部署配置缺少必填字段 {key}')
    return deepcopy(data[key])


def mapped(data, fields):
    return {target: required(data, source, allow_empty=True) for target, source in fields.items()}


def integer(value, field, minimum=0):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number != number.to_integral_value() or number < minimum:
            raise InvalidOperation
        return int(number)
    except (InvalidOperation, ValueError):
        raise ApiError(f'{field} 必须为不小于 {minimum} 的整数') from None


def resource_block(resource_id, resource, framework):
    raw = required(resource, 'frameworkConfiguration')
    try:
        configuration = json.loads(raw) if isinstance(raw, str) else deepcopy(raw)
    except (ValueError, TypeError):
        raise ApiError('frameworkConfiguration 不是有效的 JSON 对象') from None
    if not isinstance(configuration, dict) or not configuration:
        raise ApiError('frameworkConfiguration 必须为非空 JSON 对象')
    memory = required(resource, 'memory')
    if not isinstance(memory, str) or not memory.endswith('G'):
        raise ApiError('memory 必须为以 G 为单位的字符串')
    try:
        amount = Decimal(memory[:-1])
        if not amount.is_finite() or amount <= 0:
            raise InvalidOperation
    except InvalidOperation:
        raise ApiError('memory 必须包含有效的正数') from None
    block = {
        'quotaType': required(resource, 'quotaType'), 'sfsReplicas': [], 'blockName': '',
        'description': None, 'resourceDockerId': resource_id,
        'templateId': required(resource, 'containerSpec'), 'clusterName': required(resource, 'clusterName'),
        'imageName': required(resource, 'appImageName'), 'imageVersion': required(resource, 'imageTag'),
        'swrInstanceId': None,
        'resourceRequire': {'cpu': required(resource, 'cpu'),
                            **{key: '0' if resource.get(key) is None else deepcopy(resource[key])
                               for key in ('gpu', 'npu')}},
        'inferFramework': {
            'inferFrameId': required(resource, 'frameworkPkgId'),
            'inferFrameObjectId': required(framework, 'pkgStorageId'),
            'inferFrameBucketId': required(framework, 'pkgStorageLocation'),
            'inferFrameStoreType': required(framework, 'storageType'), 'configuration': configuration,
        },
        'volumes': [], 'sfsLocation': required(resource, 'sfsLocation', allow_empty=True),
        'customStartupCommand': required(resource, 'customStartupCommand', allow_empty=True),
        'elasticConfig': None,
    }
    block['resourceRequire'].update(memory=memory[:-1], replicas='1')
    for key in ('hostLabels', 'hostIpNames', 'envs', 'args'):
        items = resource.get(key)
        if items is None:
            items = []
        if not isinstance(items, list):
            raise ApiError(f'{key} 必须为数组')
        block[key] = deepcopy(items)
    return block


class MissingDeployOptions(ApiError):
    """缺失参数的命令指引应原样输出，避免终端折行破坏可复制命令。"""


def resolve_service_fields(model, template, service_timeout=None, execute_limit=None):
    resolved_timeout = template.get('serviceTimeout') if service_timeout is None else service_timeout
    resolved_limit = template.get('executeLimit') if execute_limit is None else execute_limit
    missing = []
    if resolved_timeout is None or resolved_timeout == '':
        missing.append(('--service-timeout', '调用方最大容忍超时时间（ms）', 'TIMEOUT_MS'))
    if resolved_limit is None or resolved_limit == '':
        missing.append(('--execute-limit', '单实例最大能承受并发数', 'MAX_CONCURRENT_REQUESTS'))
    if missing:
        details = '；'.join(f'{option}（{label}）' for option, label, _ in missing)
        command = f"ml model deploy {model['modelId']} --template {template.get('deployTemplateId', 'DEPLOY_TEMPLATE_ID')}"
        command += ''.join(f' {option} {placeholder}' for option, _, placeholder in missing)
        raise MissingDeployOptions(f'部署模板未配置且命令未提供：{details}。请填写对应参数后重试\n'
                       f'命令格式：{command}\n将占位符替换为实际数值：超时时间为正整数，单位毫秒；并发数为非负整数')
    integer(resolved_timeout, 'serviceTimeout', 1)
    integer(resolved_limit, 'executeLimit')
    return resolved_timeout, resolved_limit


def build_payload(model, template, blocks, scope, *, service_timeout=None, execute_limit=None, qps=None, update_mode='rolling',
                  health_mode='default', health_port=18090, description='', request_content='', response_content=''):
    if update_mode not in UPDATE_MODES or health_mode not in HEALTH_MODES:
        raise ApiError('更新模式或健康检查模式不合法')
    if not blocks:
        raise ApiError('部署模板必须关联至少一个有效容器资源模板')
    for key in ('modelId', 'modelName', 'modelVersion'):
        required(model, key)
    model_info = mapped(model, MODEL_FIELDS)
    for key in ('tags', 'modelPkgLocationReplicas'):
        if not isinstance(model_info[key], list):
            raise ApiError(f'{key} 必须为数组')
    resolved_timeout, resolved_limit = resolve_service_fields(model, template, service_timeout, execute_limit)
    service = {
        'inferenceType': required(template, 'inferenceType'), 'serviceId': None,
        'serviceName': model['modelName'], 'serviceVersion': model['modelVersion'],
        'serviceTimeout': resolved_timeout,
        'executeLimit': str(resolved_limit) if execute_limit is not None else resolved_limit,
        'updateMode': UPDATE_MODES[update_mode], 'env': required(template, 'env'),
    }
    integer(service['serviceTimeout'], 'serviceTimeout', 1)
    integer(service['executeLimit'], 'executeLimit')
    if qps is not None:
        service['requestLimit'] = integer(qps, 'requestLimit', 1)
    health = {'healthCheckTypeInContainer': HEALTH_MODES[health_mode],
              'healthPort': str(integer(health_port, 'healthPort', 1)), 'alarmWiseEyeScope': scope}
    if int(health['healthPort']) > 65535:
        raise ApiError('healthPort 不能大于 65535')
    for target, (source, default) in HEALTH_DEFAULTS.items():
        raw = template.get(source)
        health[target] = default if raw is None or raw == '' else str(raw)
        if target not in ('healthPath', 'healthType'):
            integer(health[target], target, 0 if target == 'initialDelaySeconds' else 1)
    grace = template.get('terminationGracePeriodSeconds')
    health['terminationGracePeriodSeconds'] = integer(10 if grace is None or grace == '' else grace,
                                                     'terminationGracePeriodSeconds')
    components = required(template, 'comptPkgInfoList', allow_empty=True)
    if not isinstance(components, list) or not all(isinstance(item, dict) for item in components):
        raise ApiError('comptPkgInfoList 必须为对象数组')
    return {
        'version': '1.0.0', 'meta': {'uuid': str(uuid4())},
        'data': {'modelInfo': model_info, 'serviceInfo': service,
                 'comptPkgs': [mapped(item, COMPONENT_FIELDS) for item in components],
                 'extendConfiguration': health, 'serviceBlocks': blocks,
                 'serviceDocument': {'description': description, 'requestContent': request_content,
                                     'responseContent': response_content}},
        'eFlowInfo': {'actionType': 'service_publish', 'modelInfoList': [
            {'modelName': model['modelName'], 'modelVersion': model['modelVersion']}]},
    }
