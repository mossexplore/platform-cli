import os
import re
from dataclasses import dataclass


@dataclass
class Settings:
    database_url: str
    secure_cookie: bool = True
    session_hours: int = 8
    gateway_token: str = ""
    notification_owner_admin_id: int = 0

    kb_ticket_ak: str = ""
    kb_ticket_sk: str = ""

    def __post_init__(self):
        if self.kb_ticket_ak or self.kb_ticket_sk:
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', self.kb_ticket_ak) or len(self.kb_ticket_sk.encode()) < 32:
                raise ValueError('无效 KB 签票配置')

    @classmethod
    def load(cls):
        url = os.environ.get('DATABASE_URL', '')
        if not url.startswith('mysql+pymysql://'):
            raise RuntimeError('DATABASE_URL 必须使用 mysql+pymysql://，请配置 MySQL 连接')
        return cls(url, os.environ.get('COOKIE_SECURE', 'true').lower() == 'true',
                   kb_ticket_ak=os.environ.get("KB_TICKET_AK", ""), kb_ticket_sk=os.environ.get("KB_TICKET_SK", ""),
                   gateway_token=os.environ.get('CLI_GATEWAY_TOKEN', ''),
                   notification_owner_admin_id=int(os.environ.get('NOTIFICATION_OWNER_ADMIN_ID', '0')))
