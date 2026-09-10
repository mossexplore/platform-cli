"""Load an optional mounted configuration without storing secrets in Docker metadata."""
import os
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_ENV_FILE = '/run/cli-access/service.env'


def load_service_config():
    """Mounted values win over image defaults; an explicit path must exist."""
    explicit = os.environ.get('SERVICE_ENV_FILE')
    path = Path(explicit or DEFAULT_ENV_FILE)
    try:
        with path.open(encoding='utf-8') as stream:
            load_dotenv(stream=stream, override=True, interpolate=False)
    except FileNotFoundError:
        if not explicit:
            return False
        raise RuntimeError('SERVICE_ENV_FILE 指定的配置文件不存在') from None
    except (OSError, UnicodeError):
        raise RuntimeError('无法读取服务配置文件，请检查文件权限和 UTF-8 编码') from None
    return True
