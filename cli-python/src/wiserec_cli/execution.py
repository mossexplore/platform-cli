"""Explicit process-local dependencies for alternate execution hosts.

The production entry point never discovers or imports external providers.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional
import httpx


@dataclass(frozen=True)
class ExecutionContext:
    mode: str = "真实平台"
    state_dir: Optional[Path] = None
    config_path: Optional[Path] = None
    transport_factory: Optional[Callable] = None
    auth_factory: Optional[Callable] = None
    validate_config: Optional[Callable] = None
    validate_connection: Optional[Callable] = None
    worker_module: str = "wiserec_cli.ping_worker"
    details: dict = field(default_factory=dict)


_current = ExecutionContext()


def current():
    return _current


def configure(context):
    """Called explicitly by a host before CLI imports and command recording."""
    global _current
    _current = context


def transport(default=None):
    factory = current().transport_factory
    return factory() if factory else default


def create_client(**kwargs):
    if current().transport_factory:
        kwargs["transport"] = transport()
        kwargs["trust_env"] = False
    return httpx.Client(**kwargs)
