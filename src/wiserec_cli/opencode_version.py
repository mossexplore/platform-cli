"""Choose the OpenCode permission shape from ``opencode --version``."""

from __future__ import annotations

import re
import shutil
import subprocess


# v1.1.1 release notes introduced granular permission.bash patterns.
MINIMUM_BASH = (1, 1, 1)
# Major 2 selects the permissions array. @opencode/cli 2.1.0 is the release
# known to load it; 2.0.x still takes this path and is rolled back if
# ``opencode debug config`` rejects the file.
MINIMUM_PERMISSIONS = (2, 0, 0)
_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")


class OpenCodeVersionError(ValueError):
    """The installed OpenCode cannot be identified or is too old to update."""


def permission_format_for_version(version: str) -> str:
    """Return ``permissions`` for major >= 2, ``bash`` for 1.1.1 through 1.x."""
    parsed = _parse_version(version)
    if parsed is None:
        raise OpenCodeVersionError(
            "OpenCode version could not be read from `opencode --version`. "
            "Install OpenCode 1.1.1 or newer and rerun. opencode.json was left unchanged."
        )
    if parsed >= MINIMUM_PERMISSIONS:
        return "permissions"
    if parsed >= MINIMUM_BASH:
        return "bash"
    found = ".".join(str(part) for part in parsed)
    raise OpenCodeVersionError(
        f"OpenCode {found} is older than 1.1.1. Permission rules were not written. "
        "opencode.json was left unchanged."
    )


def detect_permission_format(run_version=None) -> str:
    """Read ``opencode --version`` only. A missing binary aborts before any write."""
    run_version = run_version or command_version
    text = run_version("opencode")
    if text is None:
        raise OpenCodeVersionError(
            "OpenCode version could not be detected from `opencode --version`. "
            "Install OpenCode 1.1.1 or newer and rerun. opencode.json was left unchanged."
        )
    return permission_format_for_version(text)


def command_version(name: str):
    resolved = shutil.which(name)
    if not resolved:
        return None
    try:
        completed = subprocess.run(
            [resolved, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return (completed.stdout or completed.stderr or "").strip()


def _parse_version(text: str):
    if not text:
        return None
    match = _VERSION.search(text)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())
