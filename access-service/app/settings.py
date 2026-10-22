import os
from dataclasses import dataclass


@dataclass
class Settings:
    database_url: str
    secure_cookie: bool = True
    session_hours: int = 8
    gateway_token: str = ""
    notification_owner_admin_id: int = 0

    @classmethod
    def load(cls):
        url = os.environ.get('DATABASE_URL', '')
        if not url.startswith('mysql+pymysql://'):
            raise RuntimeError('DATABASE_URL 必须使用 mysql+pymysql://，请配置 MySQL 连接')
        return cls(url, os.environ.get('COOKIE_SECURE', 'true').lower() == 'true',
                   gateway_token=os.environ.get('CLI_GATEWAY_TOKEN', ''),
                   notification_owner_admin_id=int(os.environ.get('NOTIFICATION_OWNER_ADMIN_ID', '0')))
