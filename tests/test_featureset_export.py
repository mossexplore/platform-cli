import inspect
import gzip
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from wiserec_cli.business import BusinessSelection
from wiserec_cli.cli import app
from wiserec_cli.client import PlatformClient
from wiserec_cli.errors import ApiError, AuthenticationError, BusinessError
from wiserec_cli.featureset_export import export_features, export_filename, readable_size
from wiserec_cli.models import Credentials, Profile


CSV = '\ufeff特征名称,描述,扩展字段\r\nclick_label,"逗号,换行\n双引号""",[]\r\n'.encode()


def client(handler):
    return PlatformClient(
        Profile('dev', 'https://dev.example.com/dashboard'),
        Credentials.create('dev', 'session=a', 'csrf', 'jack', 1800),
        30000, 0, True, transport=httpx.MockTransport(handler),
        business_selection=BusinessSelection(
            type='team', department_id='d', department_name='D', tenant_id='t',
            tenant_name='T', team_id='team', team_name='Team', business_id='chosen'),
    )


@pytest.mark.parametrize('lang', ['zh_cn', 'en_us'])
def test_gzip_mislabeled_json_preserves_bytes_and_business(tmp_path, monkeypatch, lang):
    monkeypatch.chdir(tmp_path)
    def handler(request):
        assert request.method == 'GET'
        assert request.url.host == 'dev.example.com'
        assert request.url.path == '/ai/backend/dpp/proxy/featureStore/featureset/exportFeatures'
        assert dict(request.url.params) == {'setId': 'id', 'businessId': 'chosen', 'lang': lang}
        assert request.headers['businessid'] == 'chosen'
        return httpx.Response(200, content=gzip.compress(CSV), headers={
            'content-type': 'application/json; charset=UTF-8', 'content-encoding': 'gzip',
            'content-disposition': 'attachment;fileName=featuresInSet.csv'})
    with client(handler) as api:
        for name in ('featuresInSet.csv', 'featuresInSet (1).csv', 'featuresInSet (2).csv'):
            result = export_features(api, ' id ', lang)
            assert result == {'setId': 'id', 'lang': lang, 'file': str(tmp_path / name), 'bytes': len(CSV)}
            assert Path(result['file']).read_bytes() == CSV
    assert len(list(tmp_path.iterdir())) == 3


@pytest.mark.parametrize('body,error', [
    (b'', ApiError), (b' \r\n', ApiError),
    (b'{"result":{"code":17,"des":"denied"}}', ApiError),
    (b'<!DOCTYPE html><html>login</html>', AuthenticationError),
])
def test_error_bodies_leave_no_files(tmp_path, body, error):
    with client(lambda _: httpx.Response(200, content=body)) as api:
        with pytest.raises(error):
            export_features(api, 'id', destination=tmp_path / 'f.csv')
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('status,error', [(401, AuthenticationError), (302, AuthenticationError), (500, ApiError)])
def test_http_errors_leave_no_files(tmp_path, status, error):
    with client(lambda _: httpx.Response(status, content=b'error')) as api:
        with pytest.raises(error):
            export_features(api, 'id', destination=tmp_path / 'f.csv')
    assert list(tmp_path.iterdir()) == []


def test_header_only_custom_path_collision_and_gap(tmp_path):
    target = tmp_path / 'custom.csv'
    target.write_bytes(b'original')
    (tmp_path / 'custom (2).csv').write_bytes(b'original2')
    with client(lambda _: httpx.Response(200, content=b'name,description\r\n')) as api:
        result = export_features(api, 'id', destination=target)
    assert Path(result['file']).name == 'custom (1).csv'
    assert target.read_bytes() == b'original'
    assert Path(result['file']).read_bytes() == b'name,description\r\n'


def test_validation_before_network(tmp_path):
    fake = SimpleNamespace(business_id='chosen')
    for set_id, lang in [(' ', 'zh_cn'), ('id', 'invalid')]:
        with pytest.raises(ValueError):
            export_features(fake, set_id, lang)
    with pytest.raises(BusinessError):
        export_features(SimpleNamespace(business_id=''), 'id')
    with pytest.raises(ApiError, match='目标目录不存在'):
        export_features(fake, 'id', destination=tmp_path / 'missing' / 'f.csv')


@pytest.mark.parametrize('header,name', [
    ('', 'featuresInSet.csv'),
    ('attachment;fileName=featuresInSet.csv', 'featuresInSet.csv'),
    ("attachment; filename*=UTF-8''%E7%89%B9%E5%BE%81.csv", '特征.csv'),
    ('attachment; filename="../../features.csv"', 'features.csv'),
    ('attachment; filename="CON.csv"', '_CON.csv'),
])
def test_filename(header, name):
    assert export_filename(header) == name


@pytest.mark.parametrize('size,text', [(0, '0 B'), (123, '123 B'), (1024, '1 KB'),
                                        (12345, '12.06 KB'), (1048576, '1 MB'), (1073741824, '1 GB')])
def test_readable_size(size, text):
    assert readable_size(size) == text


def test_stream_failure_cleans_temporary(tmp_path):
    class Broken(httpx.SyncByteStream):
        def __iter__(self):
            yield b'name,value\n'
            raise httpx.ReadError('interrupted')
    with client(lambda _: httpx.Response(200, stream=Broken())) as api:
        with pytest.raises(ApiError):
            export_features(api, 'id', destination=tmp_path / 'f.csv')
    assert list(tmp_path.iterdir()) == []


def test_concurrent_target_creation_is_not_overwritten(tmp_path):
    original = __import__('os').link
    def race(source, target):
        if target.name == 'f.csv':
            target.write_bytes(b'other download')
        return original(source, target)
    with client(lambda _: httpx.Response(200, content=CSV)) as api, patch(
        'wiserec_cli.featureset_export.os.link', side_effect=race,
    ):
        result = export_features(api, 'id', destination=tmp_path / 'f.csv')
    assert (tmp_path / 'f.csv').read_bytes() == b'other download'
    assert Path(result['file']).read_bytes() == CSV
    assert Path(result['file']).name == 'f (1).csv'


@pytest.mark.parametrize('output', ['text', 'json'])
@pytest.mark.parametrize("kind", ["wide", "model"])
def test_cli_summary_and_auth_stdout_separation(tmp_path, output, kind):
    with client(lambda _: httpx.Response(200, content=CSV)) as api:
        def authenticated(operation):
            print('正在刷新认证', flush=True)
            return operation(api)
        runtime = SimpleNamespace(authenticated_call=authenticated)
        with patch('wiserec_cli.cli.Runtime', return_value=runtime), patch(
            'wiserec_cli.commands.featureset.runtime_from_context', return_value=runtime,
        ):
            options = {'mix_stderr': False} if 'mix_stderr' in inspect.signature(CliRunner).parameters else {}
            result = CliRunner(**options).invoke(app, ['featureset', kind, 'export', 'id', '--file',
                                              str(tmp_path / 'f.csv'), '-o', output])
    assert result.exit_code == 0, result.output
    assert '正在刷新认证' in result.stderr, repr((result.stdout, result.stderr))
    if output == 'json':
        assert json.loads(result.stdout)['bytes'] == len(CSV)
    else:
        assert f'大小：{len(CSV)} B' in result.stdout
        assert '字节' not in result.stdout


@pytest.mark.parametrize('args', [[], [' '], ['id', '--lang', 'bad'], ['id', '-o', 'csv']])
def test_cli_invalid_input_does_not_authenticate(args):
    with patch('wiserec_cli.commands.featureset.runtime_from_context') as runtime:
        result = CliRunner().invoke(app, ['featureset', 'wide', 'export'] + args)
    assert result.exit_code != 0
    runtime.assert_not_called()
