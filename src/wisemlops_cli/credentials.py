"""认证信息的本地持久化。"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from .config import legacy_user_config_dir, user_config_dir
from .errors import CredentialError
from .models import Credentials


class CredentialStore:
    def __init__(
        self,
        path: Optional[Path] = None,
        legacy_path: Optional[Path] = None,
    ):
        using_default_path = path is None
        self.path = (path or (user_config_dir() / "credentials.json")).expanduser()
        self.legacy_path = (
            legacy_path
            if legacy_path is not None
            else legacy_user_config_dir() / "credentials.json"
            if using_default_path
            else None
        )
        self._migrate_legacy_credentials()

    def _migrate_legacy_credentials(self) -> None:
        if (
            self.path.exists()
            or self.legacy_path is None
            or not self.legacy_path.exists()
        ):
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.legacy_path, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def load(self, profile: str) -> Optional[Credentials]:
        data = self._read()
        value = data.get("profiles", {}).get(profile)
        if value is None:
            return None
        try:
            return Credentials.from_dict(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise CredentialError(f"profile {profile!r} 的本地认证信息已损坏") from exc

    def save(self, credentials: Credentials) -> None:
        data = self._read()
        profiles = data.setdefault("profiles", {})
        profiles[credentials.profile] = credentials.to_dict()
        self._write(data)

    def delete(self, profile: Optional[str] = None) -> None:
        if profile is None:
            if self.path.exists():
                self.path.unlink()
            return
        data = self._read()
        data.setdefault("profiles", {}).pop(profile, None)
        self._write(data)

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
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(self.path)
