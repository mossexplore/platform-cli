"""数据集目录与 Multipart 上传的真实请求序列化验证。"""

import json
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID
from unittest.mock import patch

import httpx
import pytest

import test_dataset
from wiserec_cli.services.dataset_files import child_path, normalize_dir, validate_file


@pytest.fixture
def fixture():
    test = test_dataset.DatasetCommandTest()
    test.setUp()
    yield test
    test.doCleanups()


def test_directory_navigation_and_beijing_display(fixture):
    def handler(request):
        body = json.loads(request.content)
        UUID(body['meta']['uuid'])
        assert body['version'] == '1.0'
        assert body['data'] == {'dataSetId': 'dataset-id', 'businessId': 'mep', 'dir': '/event'}
        assert request.headers['businessid'] == 'mep'
        return httpx.Response(200, json={'result': {'code': 0, 'fileInfos': {
            'files': [{'name': '20240815', 'path': '/20240815', 'dir': True,
                       'size': 4096, 'lastModifyDate': 1725354614096}], 'hasMore': False}}})
    result = fixture.invoke(['files', 'list', 'dataset-id', '--dir', '/event'], handler)
    assert result.exit_code == 0, result.output
    assert '当前位置：/event' in result.output
    assert '/event/20240815' in result.output
    assert '2024-09-03 17:10:14' in result.output
    assert child_path('/event', '/20240815') == '/event/20240815'


def test_empty_json_preserves_fields_and_warns_partial(fixture):
    payload = {'extra': 'kept', 'result': {'code': 0, 'fileInfos': {'files': [], 'hasMore': True}}}
    result = fixture.invoke(['files', 'list', 'id', '-o', 'json'],
        lambda request: httpx.Response(200, json=payload))
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {'currentDir': '/', 'response': payload}
    assert '不完整' in result.stderr


@pytest.mark.parametrize('directory,wire_dir', [('/', ''), ('/logs', '/logs')])
def test_upload_multipart_bytes_and_business(fixture, directory, wire_dir):
    calls = []
    with TemporaryDirectory() as root:
        path = Path(root) / '1.txt'
        path.write_bytes(b'hello\x00world')
        def handler(request):
            calls.append(request)
            assert request.headers['businessid'] == 'mep'
            if request.url.path.endswith('queryDetail'):
                return httpx.Response(200, json={'result': {'code': 0, 'data': {'dataSetName': 'dog cat&x'}}})
            assert request.url.params['target'] == 'dog cat&x'
            assert request.headers['content-type'].startswith('multipart/form-data; boundary=')
            message = BytesParser(policy=default).parsebytes(
                b'Content-Type: ' + request.headers['content-type'].encode() + b'\r\n\r\n' + request.content)
            parts = {part.get_param('name', header='content-disposition'): part for part in message.iter_parts()}
            body = json.loads(parts['params'].get_payload(decode=True))
            UUID(body['meta']['uuid'])
            assert body['data'] == {'dataSetId': 'id', 'businessId': 'mep', 'dir': wire_dir, 'target': 'dog cat&x'}
            assert parts['content'].get_filename() == '1.txt'
            assert parts['content'].get_payload(decode=True) == b'hello\x00world'
            return httpx.Response(200, json={'result': {'code': 0}, 'extra': 'kept'})
        result = fixture.invoke(['files', 'upload', 'id', str(path), '--dir', directory, '-o', 'json'], handler)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)['extra'] == 'kept'
    assert len(calls) == 2


def test_upload_auth_rejection_is_not_replayed(fixture):
    uploads = []
    with TemporaryDirectory() as root:
        path = Path(root) / 'a.csv'
        path.write_text('a,b')
        def handler(request):
            if request.url.path.endswith('queryDetail'):
                return httpx.Response(200, json={'result': {'code': 0, 'data': {'dataSetName': 'dataset'}}})
            uploads.append(request)
            return httpx.Response(401)
        result = fixture.invoke(['files', 'upload', 'id', str(path)], handler)
    assert result.exit_code != 0
    assert len(uploads) == 1


@pytest.mark.parametrize('directory', ['../a', '/event/../a', 'a\\b', '/a\n'])
def test_invalid_directory(directory):
    with pytest.raises(ValueError):
        normalize_dir(directory)


def test_filename_and_size_boundaries(tmp_path):
    for name in ['中文.txt', '_a.txt', 'a.exe']:
        path = tmp_path / name
        path.touch()
        with pytest.raises(ValueError):
            validate_file(path)
    path = tmp_path / 'a.txt'
    path.touch()
    with patch('wiserec_cli.services.dataset_files.MAX_FILE_SIZE', 4):
        path.write_bytes(b'1234')
        validate_file(path)
        path.write_bytes(b'12345')
        with pytest.raises(ValueError):
            validate_file(path)


def test_upload_timeout_does_not_replay(fixture, tmp_path):
    path = tmp_path / 'a.txt'
    path.write_bytes(b'content')
    uploads = []
    def handler(request):
        if request.url.path.endswith('queryDetail'):
            return httpx.Response(200, json={'result': {'code': 0, 'data': {'dataSetName': 'dataset'}}})
        uploads.append(request)
        raise httpx.ReadTimeout('timeout', request=request)
    result = fixture.invoke(['files', 'upload', 'id', str(path)], handler)
    assert result.exit_code != 0
    assert len(uploads) == 1
    assert '上传结果未确认' in result.stderr


@pytest.mark.parametrize('body', [{}, {'files': []}, {'files': [], 'hasMore': None},
    {'files': [{'name': 'a', 'path': '/a'}], 'hasMore': False}])
def test_invalid_directory_response_fails(fixture, body):
    result = fixture.invoke(['files', 'list', 'id'], lambda request: httpx.Response(
        200, json={'result': {'code': 0, 'fileInfos': body}}))
    assert result.exit_code != 0


def test_empty_directory_still_displays_root(fixture):
    result = fixture.invoke(['files', 'list', 'id'], lambda request: httpx.Response(
        200, json={'result': {'code': 0, 'fileInfos': {'files': [], 'hasMore': False}}}))
    assert result.exit_code == 0, result.output
    assert '当前位置：/' in result.output
    assert '当前目录为空' in result.output


def test_progress_stream_reads_in_bounded_chunks(tmp_path):
    from wiserec_cli.upload_progress import upload_content
    path = tmp_path / 'large.txt'
    path.write_bytes(b'x' * 200_000)
    with upload_content(path) as content:
        assert len(content.read(65_536)) == 65_536
        assert content.tell() == 65_536
        assert len(content.read(65_536)) == 65_536
