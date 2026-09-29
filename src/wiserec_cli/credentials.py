"""认证信息的本地持久化。"""

from __future__ import annotations

import json
import os
import time
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Optional

from .config import user_config_dir
from .errors import CredentialError
from .models import Credentials


class CredentialStore:
    def __init__(
        self,
        path: Optional[Path] = None,
    ):
        self.path = (path or (user_config_dir() / "credentials.json")).expanduser()

    def load(self, profile: str) -> Optional[Credentials]:
        data = self._read()
        value = data.get("profiles", {}).get(profile)
        if value is None:
            return None
        try:
            credentials = Credentials.from_dict(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise CredentialError(f"profile {profile!r} 的本地认证信息已损坏") from exc
        if isinstance(value, dict) and (
            type(value.get("acquired_at")) in {int, float}
            or type(value.get("expires_at")) in {int, float}
        ):
            self._migrate_legacy_times(profile)
        return credentials

    def _migrate_legacy_times(self, profile: str) -> None:
        """首次读取旧凭据时，将数字时间戳改为可读格式。"""
        with self._locked():
            data = self._read()
            value = data.get("profiles", {}).get(profile)
            if not isinstance(value, dict) or not (
                type(value.get("acquired_at")) in {int, float}
                or type(value.get("expires_at")) in {int, float}
            ):
                return
            try:
                data["profiles"][profile] = Credentials.from_dict(value).to_dict()
            except (KeyError, TypeError, ValueError) as exc:
                raise CredentialError(f"profile {profile!r} 的本地认证信息已损坏") from exc
            self._write(data)

    def save(self, credentials: Credentials) -> None:
        with self._locked():
            data = self._read()
            data.setdefault("profiles", {})[credentials.profile] = credentials.to_dict()
            self._write(data)

    def extend_if_current(self, credentials: Credentials, ttl_seconds: int) -> Credentials:
        """只延长仍与本次请求相同的凭据，避免覆盖随后发生的重新登录。"""
        with self._locked():
            data = self._read()
            value = data.get("profiles", {}).get(credentials.profile)
            try:
                current = Credentials.from_dict(value) if isinstance(value, dict) else None
            except (KeyError, TypeError, ValueError) as exc:
                raise CredentialError(
                    f"profile {credentials.profile!r} 的本地认证信息已损坏"
                ) from exc
            if current is None or (
                current.username, current.cookie, current.csrftoken
            ) != (
                credentials.username, credentials.cookie, credentials.csrftoken
            ):
                return credentials
            extended = replace(
                current, expires_at=max(current.expires_at, time.time() + ttl_seconds)
            )
            if extended.expires_at > current.expires_at:
                data["profiles"][credentials.profile] = extended.to_dict()
                self._write(data)
            return extended

    def delete(self, profile: Optional[str] = None) -> None:
        with self._locked():
            if profile is None:
                if self.path.exists():
                    self.path.unlink()
                return
            data = self._read()
            data.setdefault("profiles", {}).pop(profile, None)
            self._write(data)

    @contextmanager
    def _locked(self):
        """序列化各 CLI 进程的凭据更新，防止续期覆盖新登录。"""
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock:
            if os.name == "nt":
                import msvcrt
                lock.seek(0, os.SEEK_END)
                if lock.tell() == 0:
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"profiles": {}}
        try:
            with self.path.open("r", encoding="utf-8") as file:
                value = json.load(file)
        except json.JSONDecodeError as exc:
            raise CredentialError(f"本地认证文件已损坏: {self.path}") from exc
        if not isinstance(value, dict):
            raise CredentialError(f"本地认证文件格式错误: {self.path}")
        return value

    def _write(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=f".{self.path.name}.", suffix=".tmp", delete=False,
            ) as file:
                temporary = Path(file.name)
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write("\n")
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            temporary.replace(self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
