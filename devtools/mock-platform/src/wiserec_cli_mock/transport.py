"""Fail-closed HTTP transport, including bounded multipart and file responses."""
import io
import json
import zipfile
from email.parser import BytesParser
from email.policy import default
import httpx
from .storage import Store
from .seeds import PROFILES, business_ids
from .routes import read
from .actions import write
from .contracts import supported
from .permissions import PermissionTransport

MAX_UPLOAD = 16 * 1024 * 1024


def ok(**fields):
    return httpx.Response(200, json={'result': {'code': 0, 'des': 'success', **fields}})


class Transport(httpx.BaseTransport):
    def __init__(self, root):
        self.root = root
        self.store = Store(root)
        self.permissions = PermissionTransport(root)

    def close(self):
        self.permissions.close()

    def handle_request(self, request):
        if self.permissions.matches(request):
            return self.permissions.handle_request(request)
        if request.url.scheme != 'https' or request.url.port not in (None, 443):
            raise httpx.ConnectError('演示环境禁止访问此地址', request=request)
        host = request.url.host
        allowed = {'artifacts.mock.invalid'} | {p+'.mock.invalid' for p in PROFILES}
        if host not in allowed:
            raise httpx.ConnectError('演示环境禁止访问真实平台或未知地址', request=request)
        size = 0
        chunks = []
        for chunk in request.stream:
            size += len(chunk)
            if size > MAX_UPLOAD:
                return httpx.Response(413, json={'error': '演示请求上限为 16 MiB'})
            chunks.append(chunk)
        raw = b''.join(chunks)
        multipart = request.headers.get('content-type', '').startswith('multipart/')
        body = {} if multipart or not raw else json.loads(raw)
        data = body.get('data', body)
        data = {**dict(request.url.params), **data}
        path = request.url.path
        if path == '/ai/backend/mep/tenant/queryTeamList':
            from .permissions import authorize
            authorize(self.root, host.removesuffix('.mock.invalid'),
                      request.headers.get('businessid', ''), 'ml auth ping')
        scenario = json.loads((self.root / 'workspace.json').read_text())['scenario']
        with self.store.transaction() as db:
            fault = db.execute('SELECT status,remaining FROM faults WHERE path=?', (path,)).fetchone()
            if fault and fault['remaining'] > 0:
                db.execute('UPDATE faults SET remaining=remaining-1 WHERE path=?', (path,))
                return httpx.Response(fault['status'], json={'error': 'Injected failure'})
            try:
                if host == 'artifacts.mock.invalid':
                    return self.artifact(db, path)
                if not supported(request.method, path):
                    return httpx.Response(501, json={'error': f'模拟接口未实现: {request.method} {path}'})
                if request.headers.get('cookie') != 'demo-session' or request.headers.get('csrftoken') != 'demo-csrf':
                    return httpx.Response(401)
                scope = request.headers.get('businessid', '')
                profile = host.removesuffix('.mock.invalid')
                if path == '/ai/user/info' and request.method == 'GET':
                    username = json.loads((self.root/'workspace.json').read_text()).get('username', 'demo')
                    return ok(data={'username': username, 'userName': username, 'cnName': '演示用户', 'department': '推荐技术部'})
                if scope not in business_ids(profile):
                    return httpx.Response(403, json={'error': 'businessid 与当前环境不匹配'})
                if data.get('businessId') and data['businessId'] != scope and path != '/ai/user/queryTenantDetail':
                    return httpx.Response(403, json={'error': '请求业务与请求头不匹配'})
                if scenario == 'malformed-response':
                    return httpx.Response(200, json={'result': {'code': 0, 'data': None}})
                result = self.files(db, scope, path, data, request, raw, multipart)
                if result is not None:
                    return result
                if path.endswith('/dataExplorer/accessUrl'):
                    studio = Store.get(db, scope, 'studio', data['envId'])
                    settings = self.root / 'jupyter.json'
                    if studio['status'] != 'online' or not settings.exists():
                        raise ValueError('WebStudio 或本地 Jupyter 未启动')
                    connection = json.loads(settings.read_text())
                    return ok(accessUrl=connection['url']+'lab?token='+connection['token'])
                result = write(db, scope, path, data) if request.method == 'POST' else None
                if result is None:
                    result = read(db, scope, path, data)
                if result is None:
                    return httpx.Response(501, json={'error': f'模拟接口未实现: {request.method} {path}'})
                return ok(**result)
            except (KeyError, ValueError) as exc:
                return httpx.Response(400, json={'result': {'code': 1, 'des': str(exc)}})

    def files(self, db, scope, path, data, request, raw, multipart):
        if path.endswith('/downloadurl') or path.endswith('/downloadLogUrl'):
            kind = 'algorithm' if path.endswith('/downloadurl') else 'job'
            identifier = data['algorithmId'] if kind == 'algorithm' else data['jobId']
            item = Store.get(db, scope, kind, identifier)
            if kind == 'job' and item['taskId'] != data['taskId']:
                raise ValueError('实例与任务不匹配')
            return ok(url=f'https://artifacts.mock.invalid/{scope}/{kind}/{identifier}.zip')
        if path == '/ai/backend/mtp/traintask/export':
            task = Store.get(db, scope, 'train', data.get('taskId', data.get('id')))
            return httpx.Response(200, content=('task: '+json.dumps(task, ensure_ascii=False)+'\n').encode(),
                                  headers={'content-type': 'application/yaml'})
        if path.endswith('/exportFeatures'):
            Store.get(db, scope, 'feature', data['setId'])
            return httpx.Response(200, content=b'user_id,clicks\nu001,12\nu002,7\n',
                                  headers={'content-type': 'text/csv'})
        if path.endswith('/dataSet/file/upload') and multipart:
            message = BytesParser(policy=default).parsebytes(
                ('Content-Type: '+request.headers['content-type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
            parts = {p.get_param('name', header='content-disposition'): p for p in message.iter_parts()}
            metadata = json.loads(parts['params'].get_payload(decode=True))['data']
            Store.get(db, scope, 'dataset', metadata['dataSetId'])
            if metadata['businessId'] != scope:
                raise ValueError('上传业务不匹配')
            filename = parts['content'].get_filename()
            from wiserec_cli.services.dataset_files import normalize_dir
            directory = normalize_dir(metadata.get('dir') or '/')
            if not filename or '/' in filename or '\\' in filename or filename in {'.', '..'}:
                raise ValueError('非法文件名')
            key = metadata['dataSetId'] + directory.rstrip('/') + '/' + filename
            import base64
            Store.put(db, scope, 'file', key, dict(name=filename, path=directory.rstrip('/')+'/'+filename,
                      dir=False, dataSetId=metadata['dataSetId'], parent=directory,
                      content=base64.b64encode(parts['content'].get_payload(decode=True)).decode()))
            return ok()
        if path.endswith('/dataSet/file/queryList'):
            Store.get(db, scope, 'dataset', data['dataSetId'])
            entries = [{k: v for k, v in i.items() if k != 'content'} for i in Store.items(db, scope, 'file')
                       if i['dataSetId'] == data['dataSetId'] and i['parent'] == data['dir']]
            return ok(fileInfos={'files': entries, 'hasMore': False})
        return None

    def artifact(self, db, path):
        scope, kind, filename = path.strip('/').split('/')
        if kind not in {'algorithm', 'job'} or not filename.endswith('.zip'):
            raise ValueError('未知下载文件')
        value = Store.get(db, scope, kind, filename[:-4])
        content = io.BytesIO()
        with zipfile.ZipFile(content, 'w') as archive:
            archive.writestr('README.txt', 'Synthetic CLI demonstration artifact\n')
            archive.writestr('metadata.json', json.dumps(value))
            archive.writestr('train.py' if kind == 'algorithm' else 'training.log',
                             'print("training demo")\n' if kind == 'algorithm' else 'Epoch 1 loss=0.5\nEpoch 10 loss=0.1\n')
        payload = content.getvalue()
        return httpx.Response(200, stream=httpx.ByteStream(payload), headers={
            'content-type': 'application/zip', 'content-length': str(len(payload))})
