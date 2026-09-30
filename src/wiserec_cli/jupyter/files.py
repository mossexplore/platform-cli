"""Jupyter Contents 单文件操作；写入前检查不是原子并发锁。"""
import base64
import json
from pathlib import Path

from .connection import JupyterError, remote_path


def target(path):
    path = remote_path(path)
    if not path:
        raise JupyterError("此操作不能以 Jupyter 根目录为目标")
    return path


def get(client, path, content=False, format=None):
    query = '?content=' + str(int(content))
    if format:
        query += '&type=file&format=' + format
    return client.request('GET', client.contents(path) + query)


def absent(client, path, overwrite=False):
    try:
        model = get(client, path)
    except JupyterError as exc:
        if getattr(exc, 'status_code', None) == 404:
            return
        raise
    if model['type'] == 'directory' or not overwrite:
        raise JupyterError("目标已存在；文件覆盖须显式指定 --overwrite，目录不能被覆盖")


def save(client, path, data, overwrite=False, text=False):
    path = target(path)
    absent(client, path, overwrite)
    return client.request('PUT', client.contents(path), {
        'type': 'file', 'format': 'text' if text else 'base64',
        'content': data.decode('utf-8') if text else base64.b64encode(data).decode('ascii')})


def mkdir(client, path):
    path = target(path)
    absent(client, path)
    return client.request('PUT', client.contents(path), {'type': 'directory'})


def move(client, source, destination):
    source, destination = target(source), target(destination)
    absent(client, destination)
    return client.request('PATCH', client.contents(source), {'path': destination})


def copy(client, source, directory):
    source = target(source)
    if get(client, source)['type'] == 'directory':
        raise JupyterError('copy 仅支持单文件，不支持递归目录复制')
    if get(client, directory)['type'] != 'directory':
        raise JupyterError('复制目标必须是已有目录')
    return client.request('POST', client.contents(directory), {'copy_from': source})


def delete(client, path):
    path = target(path)
    model = get(client, path, content=True)
    if model['type'] == 'directory' and model.get('content'):
        raise JupyterError('仅允许删除空目录，不支持递归删除')
    client.request('DELETE', client.contents(path))
    return {'path': path, 'deleted': True}


def download(client, remote, local: Path, overwrite=False):
    model = get(client, target(remote), content=True)
    if model['type'] == 'directory':
        raise JupyterError('download 仅支持单文件')
    content = model['content']
    if model['format'] == 'base64':
        data = base64.b64decode(content)
    elif model['format'] == 'json':
        data = json.dumps(content, ensure_ascii=False, indent=2).encode('utf-8')
    else:
        data = (''.join(content) if isinstance(content, list) else content).encode('utf-8')
    with local.open('wb' if overwrite else 'xb') as stream:
        stream.write(data)
    return {'path': remote, 'local_path': str(local.resolve()), 'bytes': len(data)}
