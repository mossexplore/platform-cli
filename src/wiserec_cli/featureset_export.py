"""特征集 CSV 原文下载与不覆盖保存。"""

import json
import os
import re
import tempfile
from email.message import Message
from pathlib import Path
from typing import Optional

from .client_metadata import handle_version_result
from .errors import ApiError, AuthenticationError, BusinessError


def export_filename(disposition: str) -> str:
    message = Message()
    message['Content-Disposition'] = disposition
    name = message.get_filename() or 'featuresInSet.csv'
    name = name.replace('\\', '/').rsplit('/', 1)[-1]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_', name).strip(' .')
    if not name:
        return 'featuresInSet.csv'
    if name.split('.')[0].upper() in {
        'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
        *(f'LPT{i}' for i in range(1, 10)),
    }:
        name = '_' + name
    return name if name.lower().endswith('.csv') else name + '.csv'


def readable_size(size: int) -> str:
    value = float(size)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1024 or unit == 'TB':
            return f"{value:.2f}".rstrip('0').rstrip('.') + f' {unit}'
        value /= 1024


def _validate_download(path: Path) -> None:
    # 只读取有界前缀识别错误响应，不解析或重写 CSV，也不固定列数。
    with path.open('rb') as source:
        prefix = source.read(65536).decode('utf-8-sig', errors='replace').lstrip()
    if not prefix:
        raise ApiError('特征集导出失败：响应内容为空')
    if prefix.startswith(('{', '[')):
        try:
            handle_version_result(json.loads(prefix))
        except ValueError:
            pass
        raise ApiError('特征集导出失败：接口返回 JSON，未返回 CSV 文件')
    if prefix.lower().startswith(('<!doctype html', '<html', '<head', '<body')):
        raise AuthenticationError('特征集导出返回 HTML 页面，请重新登录')


def export_features(client, set_id: str, lang: str = 'zh_cn',
                    destination: Optional[Path] = None):
    set_id = set_id.strip()
    if not set_id:
        raise ValueError('特征集 ID 不能为空')
    if lang not in {'zh_cn', 'en_us'}:
        raise ValueError('--lang 仅支持 zh_cn 或 en_us')
    if not client.business_id.strip():
        raise BusinessError('尚未选择租户或团队，请运行 ml business use')
    target = destination.expanduser().absolute() if destination is not None else None
    if target is not None and not target.parent.is_dir():
        raise ApiError(f'目标目录不存在：{target.parent}')
    temporary = None
    try:
        with client.stream(
            'GET', '/ai/backend/dpp/proxy/featureStore/featureset/exportFeatures',
            params={'setId': set_id, 'businessId': client.business_id, 'lang': lang},
            inspect_json=False,
        ) as response:
            if target is None:
                target = Path(export_filename(response.headers.get('content-disposition', ''))).absolute()
            received = 0
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.ml-features-',
                                             suffix='.part', delete=False) as output:
                temporary = Path(output.name)
                # iter_bytes 解压 gzip；原文编码、BOM、换行及所有字段不变。
                for chunk in response.iter_bytes():
                    output.write(chunk)
                    received += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            _validate_download(temporary)
            candidate = target
            number = 0
            while True:
                try:
                    os.link(temporary, candidate)
                    return {'setId': set_id, 'lang': lang, 'file': str(candidate), 'bytes': received}
                except FileExistsError:
                    number += 1
                    candidate = target.with_name(f'{target.stem} ({number}){target.suffix}')
    except OSError as exc:
        raise ApiError(f'特征集导出保存失败：{exc.strerror}') from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
