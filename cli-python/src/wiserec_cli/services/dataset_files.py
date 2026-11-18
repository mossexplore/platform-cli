"""数据集内部目录与单文件追加协议。"""

import re
from pathlib import Path
from uuid import uuid4

from ..errors import ApiError
from .dataset import DatasetService

# 服务端精确的 2GB 边界尚待确认，采用更保守的十进制上限。
MAX_FILE_SIZE = 2_000_000_000
EXTENSIONS = {'.txt', '.csv', '.zip', '.tar', '.gz', '.json'}


def normalize_dir(value):
    if not value or '\\' in value or any(ord(char) < 32 for char in value):
        raise ValueError('目录不能为空或包含反斜杠、控制字符')
    parts = [part for part in value.split('/') if part]
    if any(part in {'.', '..'} for part in parts):
        raise ValueError('目录不能包含 . 或 .. 路径段')
    return '/' + '/'.join(parts)


def child_path(current, relative):
    return normalize_dir(normalize_dir(current).rstrip('/') + '/' + relative.lstrip('/'))


def validate_file(path: Path):
    if not path.is_file():
        raise ValueError('上传路径必须为存在的普通文件')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', path.name):
        raise ValueError('文件名须以英文字母或数字开头，且仅包含英文字母、数字、_、-、.')
    if path.suffix.lower() not in EXTENSIONS:
        raise ValueError('仅支持 .txt、.csv、.zip、.tar、.gz、.json 文件')
    if path.stat().st_size > MAX_FILE_SIZE:
        raise ValueError('文件不能超过 2GB（2,000,000,000 字节）')
    with path.open('rb'):
        pass


class DatasetFilesService(DatasetService):
    def _body(self, dataset_id, directory):
        if not dataset_id.strip():
            raise ValueError('数据集 ID 不能为空')
        return {'version': '1.0', 'meta': {'uuid': str(uuid4())}, 'data': {
            'dataSetId': dataset_id.strip(), 'businessId': self._business_id(),
            'dir': directory}}

    def list_files(self, dataset_id, directory):
        directory = normalize_dir(directory)
        payload = self.client.request('POST', '/ai/backend/mtp/dataSet/file/queryList',
            json_body=self._body(dataset_id, directory),
            headers={'businessid': self._business_id()})
        info = self._result(payload, '查询数据集目录').get('fileInfos')
        if not isinstance(info, dict) or not isinstance(info.get('files'), list):
            raise ApiError('目录响应缺少有效的 result.fileInfos.files')
        if type(info.get('hasMore')) is not bool:
            raise ApiError('目录响应缺少有效的 hasMore')
        for entry in info['files']:
            if not isinstance(entry, dict) or type(entry.get('dir')) is not bool or not all(
                isinstance(entry.get(key), str) for key in ('name', 'path')
            ):
                raise ApiError('目录条目缺少有效的 name、path 或 dir')
        return payload

    def upload(self, dataset_id, file_path, directory, timeout):
        validate_file(file_path)
        directory = normalize_dir(directory)
        detail = self.dataset_detail(dataset_id)
        name = detail.get('dataSetName')
        if not isinstance(name, str) or not name.strip():
            raise ApiError('数据集详情缺少有效的 dataSetName，无法确定上传 target')
        body = self._body(dataset_id, '' if directory == '/' else directory)
        body['data']['target'] = name
        payload = self.client.upload_file('/ai/backend/mtp/dataSet/file/upload',
            params={'target': name}, metadata=body, file_path=file_path, timeout=timeout)
        self._result(payload, '追加文件')
        return payload
