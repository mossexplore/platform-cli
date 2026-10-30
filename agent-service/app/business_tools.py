"""Allowlisted CLI service operations and bounded schemas (never arbitrary dispatch)."""
from dataclasses import dataclass
from importlib import import_module
from inspect import signature, Parameter
from typing import get_type_hints, Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, create_model, BeforeValidator
from wiserec_cli.services.quality import normalize_type


class Arguments(BaseModel):
    model_config = ConfigDict(extra='forbid')


@dataclass(frozen=True)
class Operation:
    command: str
    domain: str
    description: str
    schema: type
    service: type | None = None
    method: str = ''
    write: bool = False


OPERATIONS = {}


def field(kind=str, default=...):
    if kind is str:
        return kind, Field(default=default, max_length=16000)
    return kind, default


def add(name, command, domain, description, fields, *, write=False, service=None, method=''):
    schema = create_model(name + '_arguments', __base__=Arguments, **fields)
    OPERATIONS[name] = Operation('ml ' + command, domain, description, schema, service, method, write)


def service(name, module, cls, method, command, domain, description, *, write=False, exclude=(), overrides=None):
    cls = getattr(import_module('wiserec_cli.services.' + module), cls)
    fn = getattr(cls, method)
    hints = get_type_hints(fn)
    fields = {}
    for key, param in signature(fn).parameters.items():
        if key == 'self' or key in exclude:
            continue
        default = ... if param.default is Parameter.empty else param.default
        kind = hints.get(key, bool if isinstance(default, bool) else int if isinstance(default, int) else str)
        if default is None: kind = kind | None
        fields[key] = field(kind, default)
        if key in ('page', 'page_index', 'page_num', 'page_size', 'start_line', 'end_line'):
            fields[key] = (int, Field(default=default, ge=1, le=100 if key == 'page_size' else 10000))
    fields.update(overrides or {})
    add(name, command, domain, description, fields, write=write, service=cls, method=method)


# Every entry explicitly maps to the same CLI permission command.
service('list_algorithms', 'algorithm', 'AlgorithmService', 'list_algorithms', 'algorithm list', 'algorithms', '查询算法仓')
service('clone_algorithm', 'algorithm', 'AlgorithmService', 'clone', 'algorithm clone', 'algorithms', '克隆算法仓，需网页确认', write=True)
service('list_datasets', 'dataset', 'DatasetService', 'list_datasets', 'dataset list', 'datasets', '查询数据集')
service('get_dataset', 'dataset', 'DatasetService', 'dataset_detail', 'dataset detail', 'datasets', '查询数据集详情')
service('list_dataset_files', 'dataset_files', 'DatasetFilesService', 'list_files', 'dataset files list', 'datasets', '浏览数据集目录，directory 使用绝对数据集目录')
service('list_deployment_templates', 'deployment', 'DeploymentTemplateService', 'list_templates', 'deployment template list', 'templates', '查询部署模板')
service('get_deployment_template', 'deployment', 'DeploymentTemplateService', 'detail', 'deployment template detail', 'templates', '读取部署模板及关联资源')
service('list_resource_templates', 'resource', 'ResourceTemplateService', 'list_templates', 'resource template list', 'resources', '查询资源模板')
service('get_resource_template', 'resource', 'ResourceTemplateService', 'detail', 'resource template detail', 'resources', '读取资源模板')
service('get_resource_framework', 'resource', 'ResourceTemplateService', 'framework', 'resource template detail', 'resources', '读取资源框架')
service('list_offline_projects', 'experiment', 'ExperimentService', 'list_projects', 'offline experiment list', 'offline', '查询离线实验项目')
service('list_offline_trials', 'experiment', 'ExperimentService', 'list_trials', 'offline experiment trial list', 'offline', '查询离线实验运行')
service('get_offline_project', 'experiment', 'ExperimentService', 'get_project', 'offline experiment list', 'offline', '读取离线实验详情')
service('get_featureset_config', 'featureset', 'FeatureSetService', 'get_config', 'featureset wide config', 'featuresets', '查询特征集配置')
service('list_featuresets', 'featureset', 'FeatureSetService', 'list_sets', 'featureset wide list', 'featuresets', '查询特征集；set_type 选择宽表或模型特征集', overrides={'set_type': (Literal['wide', 'model'], ...)})
service('get_mep_config', 'mep', 'MepService', 'query_config', 'mep config get', 'mep', '按键查询 MEP 配置')
service('get_current_user', 'user', 'UserService', 'info', 'user info', 'account', '查询当前登录账号资料')
service('list_feature_tasks', 'feature_task', 'FeatureTaskService', 'list_tasks', 'feature-task list', 'feature_tasks', '查询特征任务')
service('list_feature_executions', 'feature_execution', 'FeatureExecutionService', 'list_executions', 'feature-task execution list', 'feature_tasks', '查询特征执行记录')
service('search_feature_logs', 'feature_execution', 'FeatureExecutionService', 'search_logs', 'feature-task execution logs search', 'feature_tasks', '检索特征执行日志', overrides={'keywords': (list[str] | None, None), 'scope_lines': (int | None, Field(default=None, ge=1, le=1000))})

# Keep enum schemas bounded while accepting the same Chinese/case-insensitive inputs as CLI.
QualityType = Annotated[Literal['CONTINUOUS', 'DISCRETE', 'ORDINAL', 'CATEGORICAL',
    'SEQUENCE', 'LONG_SEQUENCE', 'VECTOR'], BeforeValidator(normalize_type)]
QUALITY_PAGING = {
    'page': (int, Field(default=1, ge=1, le=10000, strict=True)),
    'page_size': (int, Field(default=10, ge=1, le=100, strict=True)),
}
service('list_quality_features', 'quality', 'QualityService', 'list_features',
    'quality feature list', 'quality', '查询质量监控特征列表，支持名称、表名、特征值类型和指标类型；返回原始数值与周期',
    overrides={**QUALITY_PAGING, 'feature_value_type': (QualityType | None, None),
               'indicator_type': (QualityType | None, None)})
service('list_quality_wide_featuresets', 'quality', 'QualityService', 'list_wide_featuresets',
    'quality wide-featureset list', 'quality', '查询质量监控宽表特征集，支持名称筛选；不同于普通宽表特征集列表',
    overrides=QUALITY_PAGING)

service('list_sample_tasks', 'sample_task', 'SampleTaskService', 'list_tasks', 'sample-task list', 'samples', '查询样本任务', overrides={'types': (list[str] | None, None), 'status': (Literal['all', 'stopped', 'started'] | None, None), 'sort': (str | None, None)})
service('list_sample_periods', 'sample_execution', 'SampleExecutionService', 'list_periods', 'sample-task period list', 'samples', '查询样本执行周期', overrides={'states': (list[str] | None, None)})
service('list_sample_executions', 'sample_execution', 'SampleExecutionService', 'list_executions', 'sample-task execution list', 'samples', '查询样本执行记录')
for name, method, command, description in [
    ('list_swan_projects', 'list_projects', 'mtp swanboard project list', '查询 SwanBoard 项目'),
    ('list_swan_namespaces', 'list_namespaces', 'mtp swanboard project namespace list', '查询项目命名空间'),
    ('list_swan_experiments', 'list_experiments', 'mtp swanboard project experiment list', '查询项目实验'),
    ('list_swan_features', 'list_features', 'mtp swanboard experiment feature list', '查询实验特征'),
    ('get_swan_environment', 'get_environment', 'mtp swanboard experiment environment get', '查询实验环境'),
    ('get_swan_metrics', 'get_metric_stats', 'mtp swanboard experiment metrics', '查询实验指标'),
    ('get_swan_config', 'get_config', 'mtp swanboard experiment config list', '查询实验配置'),
    ('inspect_swan_experiment', 'inspect_experiment', 'mtp swanboard experiment inspect', '综合检查实验')]:
    service(name, 'swanboard', 'SwanBoardService', method, command, 'swanboard', description)
service('list_webstudios', 'webstudio', 'WebStudioService', 'list', 'webstudio list', 'webstudio', '查询开发环境', exclude=('business_id',))
service('get_webstudio', 'webstudio', 'WebStudioService', 'get', 'webstudio show', 'webstudio', '查询指定开发环境')
for action in ('start', 'stop'):
    service(action + '_webstudio', 'webstudio', 'WebStudioService', action, 'webstudio ' + action, 'webstudio', '启动' if action == 'start' else '停止开发环境', write=True)
service('run_service_mock', 'service_mock', 'ServiceMock', 'run', 'service mock', 'inference', '发送推理测试请求，需确认', write=True)

ID = field()
for name, command, fields, description in [
    ('start_train_task', 'train start', {'task_id': ID}, '启动训练任务'),
    ('cancel_train_instance', 'train cancel', {'task_id': ID, 'job_id': ID}, '取消指定训练实例'),
    ('delete_train_task', 'train delete', {'task_id': ID}, '删除训练任务'),
    ('clone_train_task', 'train clone', {'task_id': ID, 'name': ID, 'customize_config': (str | None, None)}, '克隆训练任务'),
    ('update_train_config', 'train config update', {'task_id': ID, 'customize_config': ID}, '更新训练配置'),
    ('clone_offline_project', 'offline experiment clone', {'project_id': ID, 'name': ID}, '克隆离线实验项目')]:
    add(name, command, 'training_write' if 'train' in name else 'offline', description + '，需确认', fields, write=True)
for name, command, domain, fields, description in [
    ('download_algorithm', 'algorithm download', 'algorithms', {'algorithm_id': ID}, '下载算法包为附件'),
    ('export_train_config', 'train config export', 'training_files', {'task_id': ID}, '导出训练配置为附件'),
    ('download_train_logs', 'train history logs download', 'training_files', {'task_id': ID, 'job_id': ID}, '下载训练日志为附件'),
    ('export_featureset', 'featureset wide export', 'featuresets', {'set_id': ID}, '导出特征集配置为附件'),
    ('upload_dataset_file', 'dataset files upload', 'datasets', {'dataset_id': ID, 'directory': field(str, '/'), 'artifact_id': ID}, '追加已上传附件到数据集')]:
    add(name, command, domain, description, fields, write=name.startswith('upload'))

DEPLOY_FIELDS = {'model_id': ID, 'template_id': ID,
    'service_timeout': (int | None, Field(default=None, ge=1)),
    'execute_limit': (int | None, Field(default=None, ge=0)),
    'qps': (int | None, Field(default=None, ge=1)),
    'update_mode': (Literal['rolling', 'in-place'], 'rolling'),
    'health_mode': (Literal['default', 'response-code', 'response-code-and-data'], 'default'),
    'health_port': (int, Field(default=18090, ge=1, le=65535)),
    'description': field(str, ''), 'request_sample': (str | None, None), 'response_sample': (str | None, None)}
add('preview_model_deployment', 'model deploy', 'deployment', '解析部署参数，生成不可变部署计划附件；不发布', DEPLOY_FIELDS)
add('publish_model_deployment', 'model deploy', 'deployment', '发布已预览计划，需网页确认该计划完整内容', {'artifact_id': ID}, write=True)

STUDIO = {'studio_id': ID}
for action in ('list', 'stat', 'read', 'download', 'write', 'mkdir', 'upload', 'move', 'copy', 'delete'):
    fields = {**STUDIO, 'path': field(str, '') if action == 'list' else ID}
    if action in ('move', 'copy'): fields['destination'] = ID
    if action == 'write': fields['content'] = ID
    if action == 'upload': fields['artifact_id'] = ID
    if action in ('write', 'upload'): fields['overwrite'] = (bool, False)
    add('jupyter_files_' + action, 'jupyter files ' + action, 'jupyter_files', 'Jupyter 文件 ' + action + '；路径相对服务器根目录', fields, write=action in ('write', 'mkdir', 'upload', 'move', 'copy', 'delete'))
add('jupyter_doctor', 'jupyter doctor', 'jupyter', '检查 Web Studio/Jupyter 连接', STUDIO)
add('jupyter_exec', 'jupyter exec', 'jupyter', '在指定 Web Studio 执行参数数组，需确认；不是 Agent 主机命令', {**STUDIO, 'argv': (list[str], Field(min_length=1, max_length=100)), 'cwd': field(str, ''), 'timeout': (int, Field(default=60, ge=1, le=120))}, write=True)
add('jupyter_notebook_run', 'jupyter notebook run', 'jupyter', '执行上传的 notebook 并返回结果附件', {**STUDIO, 'artifact_id': ID, 'cwd': field(str, ''), 'timeout': (int, Field(default=60, ge=1, le=120))}, write=True)
for action in ('list', 'create', 'stop', 'attach'):
    fields = dict(STUDIO)
    if action in ('stop', 'attach'): fields['name'] = ID
    if action == 'attach': fields['input'] = field(str, '')
    add('jupyter_terminal_' + action, 'jupyter terminal ' + {'create': 'open', 'stop': 'close'}.get(action, action), 'jupyter_terminals', 'Jupyter 终端 ' + action + ('：发送输入并读取有界输出' if action == 'attach' else ''), fields, write=action != 'list')

add('login_webstudio', 'webstudio login', 'webstudio', '验证指定 Web Studio 连接；后续工具显式传 studio_id，无全局默认实例', STUDIO)

from dataclasses import replace
OPERATIONS['list_feature_null_rates'] = replace(OPERATIONS['list_quality_features'],
    description='仅查询每条特征的空值率，用于分布、占比统计；返回 nullValueRates 数值数组与分页信息，'
                '原始比例 0～1，null 表示未知，不能当作 0；仅当前页，跨页统计须翻页，不返回其他特征字段')
for original, alias in [('list_featuresets', 'list_model_featuresets'), ('get_featureset_config', 'get_model_featureset_config'), ('export_featureset', 'export_model_featureset')]:
    old = OPERATIONS[original]
    OPERATIONS[alias] = replace(old, command=old.command.replace('wide', 'model'), description=old.description + '（模型特征集）')
old = OPERATIONS['run_service_mock']
OPERATIONS['run_service_host_mock'] = replace(old, command='ml service host mock', description='测试指定服务主机，必须提供 pod_ip，需确认')

add('preview_train_cancellation', 'train cancel', 'training_write', '枚举训练任务全部实例，生成固定取消计划；超出分页上限时拒绝，绝不部分冒充全部', {'task_id': ID})
add('cancel_train_task', 'train cancel', 'training_write', '取消已预览计划中的全部实例，需要确认；不包含预览后新建实例', {'artifact_id': ID}, write=True)
add('preview_offline_clone', 'offline experiment clone', 'offline', '预览离线实验克隆请求，不提交', {'project_id': ID, 'name': ID})
# Separate fixed feature types preserve distinct CLI permission identifiers.
for name, kind in [('list_featuresets', 'wide'), ('list_model_featuresets', 'model')]:
    old = OPERATIONS[name]
    fields = {key: (f.annotation, f) for key, f in old.schema.model_fields.items() if key != 'set_type'}
    OPERATIONS[name] = replace(old, schema=create_model(name + '_arguments', __base__=Arguments, **fields))
for name in ('export_featureset', 'export_model_featureset'):
    old = OPERATIONS[name]
    OPERATIONS[name] = replace(old, schema=create_model(name + '_arguments', __base__=old.schema,
        lang=(Literal['zh_cn', 'en_us'], 'zh_cn')))
