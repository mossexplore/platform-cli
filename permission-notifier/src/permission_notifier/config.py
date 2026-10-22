"""Validated local settings, independent of all CLI settings."""
from urllib.parse import urlsplit
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def url(value, service=False):
    value = value.strip().rstrip('/')
    if not value:
        return value
    parsed = urlsplit(value)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or
            parsed.password or parsed.fragment or (service and parsed.query)):
        raise ValueError('地址须为不含账号、密码、片段的 HTTP/HTTPS URL')
    if service and parsed.scheme != 'https' and parsed.hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('权限系统必须使用 HTTPS（本机联调除外）')
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Receiver(StrictModel):
    uid: str = Field(min_length=1, max_length=256)
    label: str = Field(default='', max_length=100)
    enabled: bool = True

    @field_validator('uid')
    @classmethod
    def clean_uid(cls, value):
        if not value.strip():
            raise ValueError('UID 不能为空')
        return value.strip()


class Network(StrictModel):
    proxy: str = ''
    ca_file: str = ''
    trust_env: bool = True

    @field_validator('proxy')
    @classmethod
    def valid_proxy(cls, value):
        return url(value)


class Message(StrictModel):
    url: str = ''
    auth: str = Field(default='', max_length=8192)
    sender: str = Field(default='', max_length=256)
    receivers: list[Receiver] = Field(default_factory=list, max_length=100)
    success_mode: Literal['unconfirmed', 'http_2xx', 'json_equals'] = 'unconfirmed'
    success_field: str = Field(default='', max_length=128)
    success_value: str = Field(default='true', max_length=256)
    network: Network = Field(default_factory=Network)

    @field_validator('url')
    @classmethod
    def valid_url(cls, value):
        return url(value)

    @model_validator(mode='after')
    def receivers_unique(self):
        ids = [r.uid for r in self.receivers]
        if len(ids) != len(set(ids)):
            raise ValueError('接收 UID 不得重复')
        if self.success_mode == 'json_equals':
            import json
            if not self.success_field:
                raise ValueError('请填写业务成功字段')
            try:
                json.loads(self.success_value)
            except ValueError:
                raise ValueError('成功期望值须为合法 JSON') from None
        return self


class Config(StrictModel):
    permission_service_url: str = ''
    assistant_token: str = Field(default='', max_length=256)
    poll_interval_seconds: int = Field(default=10, ge=2, le=3600)
    message_timeout_seconds: int = Field(default=20, ge=2, le=45)
    service_network: Network = Field(default_factory=Network)
    message: Message = Field(default_factory=Message)

    @field_validator('permission_service_url')
    @classmethod
    def valid_service(cls, value):
        return url(value, service=True)


def ready(config):
    return bool(config['permission_service_url'] and config['assistant_token'] and
                config['message']['url'] and config['message']['auth'] and
                config['message']['success_mode'] != 'unconfirmed' and
                any(r['enabled'] for r in config['message']['receivers']))
