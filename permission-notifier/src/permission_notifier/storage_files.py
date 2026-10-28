"""Two independent atomic documents: settings and runtime/delivery records."""
import copy
import json
import os
import tempfile

CONFIG_STATE = ('active_config_revision', 'config_apply')


def split(data):
    state = data['state']
    settings = {'file_version': 2, 'installation_id': state['installation_id'],
                'config_revision': data['config_revision'], 'config': data['config'],
                'state': {key: state[key] for key in CONFIG_STATE}}
    records = {'file_version': 1, 'state': {key: value for key, value in state.items()
                                         if key not in CONFIG_STATE}}
    return settings, records


def read(path, records_path):
    settings = json.loads(path.read_text(encoding='utf-8'))
    if settings['file_version'] == 1:
        # Keep the old source intact until the runtime file is durably saved.
        if records_path.exists():
            existing = json.loads(records_path.read_text(encoding='utf-8'))
            if existing['state']['installation_id'] != settings['state']['installation_id']:
                raise ValueError('记录文件与配置不匹配')
        return settings, True
    if settings['file_version'] != 2:
        raise ValueError('文件版本不兼容')
    records = json.loads(records_path.read_text(encoding='utf-8'))
    if records['file_version'] != 1 or records['state']['installation_id'] != settings['installation_id']:
        raise ValueError('记录文件与配置不匹配')
    state = copy.deepcopy(records['state'])
    state.update({key: settings['state'][key] for key in CONFIG_STATE})
    return {'file_version': 1, 'config_revision': settings['config_revision'],
            'config': settings['config'], 'state': state}, False


def atomic_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.stem+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)
            file.write('\n')
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, path)
        if os.name != 'nt':
            os.chmod(path, 0o600)
        else:
            return
        # Persist the directory entry as well as the JSON contents.
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)
