from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Identity(BaseModel):
    model_config = ConfigDict(extra='forbid')
    protocol_version: int = 1
    installation_id: str = Field(min_length=8, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')


class Lease(Identity):
    lease_generation: int = Field(ge=1)
    lease_token: str = Field(min_length=16, max_length=128)


class Prepare(Lease):
    snapshot_id: str = Field(min_length=8, max_length=64)
    delivery_ids: list[str] = Field(min_length=1, max_length=100)


class Resume(Identity):
    snapshot_id: str = Field(default='', max_length=64)


class DeliveryUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    delivery_id: str = Field(min_length=8, max_length=64)
    attempt_id: str = Field(default='', max_length=64)
    state: Literal['sending', 'accepted', 'retry_wait', 'failed', 'uncertain', 'skipped', 'pending']
    error_code: str = Field(default='', max_length=64, pattern=r'^[A-Z0-9_]*$')
    message_id: str | None = Field(default=None, max_length=128)
    manual: bool = False


class Report(Lease):
    report_id: str = Field(min_length=8, max_length=64)
    report_seq: int = Field(ge=1)
    updates: list[DeliveryUpdate] = Field(min_length=1, max_length=100)


class Heartbeat(Identity):
    agent_version: str = Field(default='', max_length=32, pattern=r'^[0-9A-Za-z.\-]*$')
    health_code: Literal['running', 'paused', 'network_error', 'auth_error', 'worker_error',
                         'storage_error', 'needs_attention', 'unconfigured'] = 'running'
