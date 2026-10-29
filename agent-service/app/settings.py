"""Validated local-only configuration. Secrets are never public DTOs."""

import json
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from sqlalchemy import URL


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Environment(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    name: str
    enabled: bool = True
    api_endpoint: str
    verify_ssl: bool = True

    @model_validator(mode="after")
    def url_valid(self):
        u = urlsplit(self.api_endpoint)
        if (
            u.scheme not in ("http", "https")
            or not u.hostname
            or u.username
            or u.password
            or u.query
            or u.fragment
        ):
            raise ValueError("api_endpoint 必须是无凭据的 HTTP(S) 入口")
        return self


class Server(Strict):
    host: Literal["127.0.0.1", "localhost"] = "127.0.0.1"
    port: int = Field(default=8000, ge=1024, le=65535)
    workers: Literal[1] = 1


class Database(Strict):
    host: str
    port: int = 3306
    database: str = Field(pattern=r"^[a-zA-Z0-9_]+$")
    username: str
    password: SecretStr
    charset: Literal["utf8mb4"] = "utf8mb4"

    def url(self):
        return URL.create(
            "mysql+pymysql",
            username=self.username,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=self.database,
            query={"charset": self.charset},
        )


class LLM(Strict):
    use_env_proxy: bool = False
    base_url: str
    model: str
    api_key: SecretStr
    api_mode: Literal["chat_completions", "responses"] = "chat_completions"
    timeout_seconds: int = Field(default=120, ge=1, le=300)
    tracing_enabled: Literal[False] = False


class Access(Strict):
    use_env_proxy: bool = False
    url: str
    gateway_token: SecretStr = Field(min_length=32)
    timeout_seconds: int = Field(default=15, ge=1, le=60)


class Login(Strict):
    provider: Literal["local_edge"] = "local_edge"
    browser_channel: Literal["msedge"] = "msedge"
    timeout_seconds: int = Field(default=600, ge=30, le=900)
    profile_root: Path = Path("var/browser-profiles")


class SessionConfig(Strict):
    keepalive_enabled: bool = True
    keepalive_interval_seconds: int = Field(default=600, ge=60, le=3600)
    browser_cookie_max_age_seconds: int = Field(default=31536000, ge=3600, le=31536000)
    idle_timeout_seconds: int = Field(default=1800, ge=60)
    absolute_timeout_seconds: int = Field(default=28800, ge=60)
    credential_ttl_seconds: int = Field(default=1800, ge=60)
    cookie_name: str = "wiserec_agent_session"

    @model_validator(mode="after")
    def keepalive_before_expiry(self):
        if self.keepalive_enabled and self.keepalive_interval_seconds >= min(
            self.idle_timeout_seconds,
            self.absolute_timeout_seconds,
            self.credential_ttl_seconds,
        ):
            raise ValueError("保活间隔必须小于空闲、会话及凭据超时")
        return self


class Runtime(Strict):
    state_dir: Path = Path("var/state")
    platform_timeout_seconds: int = Field(default=30, ge=1, le=120)
    max_turns: int = Field(default=12, ge=1, le=30)
    max_tool_calls: int = Field(default=20, ge=1, le=50)
    max_discovery_calls: int = Field(default=4, ge=1, le=10)
    max_loaded_tools: int = Field(default=16, ge=4, le=100)
    run_timeout_seconds: int = Field(default=180, ge=10, le=600)
    max_page_size: int = Field(default=50, ge=1, le=100)
    max_auto_pages: int = Field(default=5, ge=1, le=20)
    max_tool_output_chars: int = Field(default=20000, ge=1000, le=200000)
    max_log_lines: int = Field(default=200, ge=1, le=1000)
    max_history_messages: int = Field(default=40, ge=2, le=100)
    max_history_chars: int = Field(default=60000, ge=1000, le=200000)
    event_retention_hours: int = Field(default=24, ge=1)
    history_retention_days: int = Field(default=30, ge=1)


class Settings(Strict):
    server: Server = Field(default_factory=Server)
    database: Database
    llm: LLM
    environments: list[Environment] = Field(min_length=1)
    access_control: Access
    login: Login = Field(default_factory=Login)
    session: SessionConfig = Field(default_factory=SessionConfig)
    runtime: Runtime = Field(default_factory=Runtime)

    @model_validator(mode="after")
    def unique(self):
        if len({e.id for e in self.environments}) != len(self.environments):
            raise ValueError("环境标识不能重复")
        for value in (self.llm.base_url, self.access_control.url):
            u = urlsplit(value)
            if (
                u.scheme not in ("http", "https")
                or not u.hostname
                or u.username
                or u.password
                or u.query
                or u.fragment
            ):
                raise ValueError("服务地址必须是无凭据 HTTP(S) URL")
        return self

    def env(self, key):
        return next((e for e in self.environments if e.id == key and e.enabled), None)


def load_settings(path=None):
    path = Path(
        path
        or os.getenv(
            "WISEREC_AGENT_CONFIG", Path(__file__).parents[1] / "config.local.json"
        )
    ).resolve()
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    for name, group, field in [
        ("LLM_API_KEY", "llm", "api_key"),
        ("DB_PASSWORD", "database", "password"),
        ("GATEWAY_TOKEN", "access_control", "gateway_token"),
    ]:
        if value := os.getenv("WISEREC_AGENT_" + name):
            data.setdefault(group, {})[field] = value
    config = Settings.model_validate(data)
    for obj, field in [(config.login, "profile_root"), (config.runtime, "state_dir")]:
        value = getattr(obj, field)
        setattr(obj, field, (path.parent / value).resolve())
    return config
