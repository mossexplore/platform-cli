"""命令共享的运行时依赖与认证重试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from .auth import AuthManager
from .client import PlatformClient
from .config import ConfigManager
from .credentials import CredentialStore
from .errors import AuthenticationError


class Runtime:
    def __init__(
        self,
        config_path: Optional[Path] = None,
        credential_path: Optional[Path] = None,
    ):
        self.config = ConfigManager(config_path)
        self.credentials = CredentialStore(credential_path)
        self.auth = AuthManager(self.config, self.credentials)

    def authenticated_call(
        self,
        operation: Callable[[PlatformClient], Any],
    ) -> Any:
        for attempt in range(2):
            credentials = self.auth.ensure_credentials(force_refresh=attempt == 1)
            profile = self.config.current_profile()
            try:
                with PlatformClient(
                    profile=profile,
                    credentials=credentials,
                    timeout_ms=self.config.timeout_ms,
                    retry_times=self.config.retry_times,
                    verify_ssl=self.config.verify_ssl,
                ) as client:
                    return operation(client)
            except AuthenticationError:
                if attempt == 0:
                    print("服务端认证已失效，将重新打开 Edge 刷新本地认证信息。")
                    continue
                raise
        raise AuthenticationError("重新登录后认证仍然失败")
