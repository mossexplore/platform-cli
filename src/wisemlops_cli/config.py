"""config.json 读取、校验与 profile 管理。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from .errors import ConfigError
from .models import Profile


def default_config_path() -> Path:
    configured = os.environ.get("ML_CONFIG") or os.environ.get("WO_CONFIG")
    if configured:
        return Path(configured).expanduser().resolve()

    local_config = Path.cwd() / "config.json"
    if local_config.exists():
        return local_config.resolve()

    preferred = user_config_dir() / "config.json"
    legacy = legacy_user_config_dir() / "config.json"
    return legacy if not preferred.exists() and legacy.exists() else preferred


def user_config_dir() -> Path:
    return _user_config_dir("ml")


def legacy_user_config_dir() -> Path:
    return _user_config_dir("wo")


def _user_config_dir(application_name: str) -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return root / application_name
    if os.sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / application_name
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / application_name


class ConfigManager:
    def __init__(self, path: Optional[Path] = None):
        self.path = (path or default_config_path()).expanduser().resolve()
        self._data = self._read()
        self._validate()

    def _read(self) -> Dict[str, Any]:
        try:
            with self.path.open("r", encoding="utf-8") as file:
                value = json.load(file)
        except FileNotFoundError as exc:
            raise ConfigError(
                f"配置文件不存在: {self.path}。可通过 --config 或 ML_CONFIG 指定。"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ConfigError(f"配置文件不是有效的 JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ConfigError("配置文件顶层必须是 JSON 对象")
        return value

    def _validate(self) -> None:
        current = self._data.get("current")
        if not isinstance(current, str) or not current:
            raise ConfigError("config.json 中的 current 必须是非空字符串")
        if not isinstance(self._data.get("api", {}), dict):
            raise ConfigError("config.json 中的 api 必须是对象")
        if not isinstance(self._data.get("auth", {}), dict):
            raise ConfigError("config.json 中的 auth 必须是对象")
        profiles = self._data.get("profiles")
        if not isinstance(profiles, list) or not profiles:
            raise ConfigError("config.json 中的 profiles 必须是非空数组")
        names = set()
        for item in profiles:
            if not isinstance(item, dict):
                raise ConfigError("profiles 中的每一项都必须是对象")
            name = item.get("name")
            endpoint = item.get("api_endpoint")
            parsed = urlsplit(endpoint) if isinstance(endpoint, str) else None
            if not isinstance(name, str) or not name:
                raise ConfigError("profile.name 必须是非空字符串")
            if name in names:
                raise ConfigError(f"profile.name 重复: {name}")
            if not parsed or parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ConfigError(f"profile {name!r} 的 api_endpoint 无效")
            names.add(name)
        if current not in names:
            raise ConfigError(f"profiles 中不存在 current 指定的环境: {current}")
        if self.auth_ttl_seconds <= 0:
            raise ConfigError("auth.expires_in_seconds 必须大于 0")

    @property
    def current_name(self) -> str:
        return str(self._data["current"])

    @property
    def timeout_ms(self) -> int:
        value = self._data.get("api", {}).get("timeout", 30000)
        return int(value) if isinstance(value, (int, float)) and value > 0 else 30000

    @property
    def retry_times(self) -> int:
        value = self._data.get("api", {}).get("retry_times", 3)
        return max(0, int(value)) if isinstance(value, (int, float)) else 3

    @property
    def verify_ssl(self) -> bool:
        return bool(self._data.get("api", {}).get("verify_ssl", True))

    @property
    def auth_ttl_seconds(self) -> int:
        value = self._data.get("auth", {}).get("expires_in_seconds", 1800)
        return int(value) if isinstance(value, (int, float)) else 1800

    def profiles(self) -> List[Profile]:
        return [
            Profile(
                name=item["name"],
                api_endpoint=item["api_endpoint"],
                output_format=item.get("output_format", "table"),
            )
            for item in self._data["profiles"]
        ]

    def current_profile(self) -> Profile:
        for profile in self.profiles():
            if profile.name == self.current_name:
                return profile
        raise ConfigError(f"找不到当前环境: {self.current_name}")

    def use_profile(self, name: str) -> Profile:
        target = next((item for item in self.profiles() if item.name == name), None)
        if target is None:
            raise ConfigError(f"不存在 profile: {name}")
        self._data["current"] = name
        self._write()
        return target

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(self._data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        temporary.replace(self.path)
