"""Read and write OpenCode config files without following symlinks."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

SCHEMA = "https://opencode.ai/config.json"
_COMMENT = re.compile(r"(?<!:)//|/\*")


def read_existing(path: Path):
    if path.is_symlink():
        raise ValueError(f"OpenCode config must not be a symlink: {path}")
    if path.exists() and not path.is_file():
        raise ValueError(f"OpenCode config must be a file: {path}")
    if not path.is_file():
        return None, {"$schema": SCHEMA}
    original = path.read_bytes()
    return original, load_config(original, path.name)


def read_config_file(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError(f"OpenCode config must not be a symlink: {path}")
    if not path.is_file():
        raise ValueError(f"OpenCode config must be a file: {path}")
    return load_config(path.read_bytes(), path.name)


def config_path(target: Path) -> Path:
    json_path = target / "opencode.json"
    jsonc_path = target / "opencode.jsonc"
    json_present = json_path.exists() or json_path.is_symlink()
    jsonc_present = jsonc_path.exists() or jsonc_path.is_symlink()
    if json_present and jsonc_present:
        raise ValueError(
            "Both opencode.json and opencode.jsonc exist. OpenCode loads jsonc after json. "
            "Combine them into opencode.json and remove opencode.jsonc, then rerun the installer."
        )
    if jsonc_present:
        return jsonc_path
    return json_path


def load_config(original: bytes, name: str = "opencode.json") -> dict:
    try:
        text = decode(original)
    except UnicodeError as error:
        raise ValueError("OpenCode config must be UTF-8") from error
    if not text.strip():
        return {}
    try:
        config = json.loads(text)
    except json.JSONDecodeError as error:
        if _COMMENT.search(text):
            raise ValueError(
                f"{name} contains comments. This installer does not continue with JSONC comments. "
                "Remove the comments and rerun. The file was left unchanged."
            ) from error
        raise ValueError(
            f"{name} is not strict JSON ({error}). The installer stopped. The file was left unchanged."
        ) from error
    if not isinstance(config, dict):
        raise ValueError("OpenCode config must be a JSON object")
    return config


def decode(original: bytes) -> str:
    return original.decode("utf-8-sig")


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def dump(config: dict) -> str:
    return json.dumps(config, ensure_ascii=False, indent=2) + "\n"


def backup_path(path: Path) -> Path:
    primary = path.with_name(path.name + ".bak")
    if not primary.exists() and not primary.is_symlink():
        return primary
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    candidate = path.with_name(f"{path.name}.bak.{stamp}")
    suffix = 2
    while candidate.exists() or candidate.is_symlink():
        candidate = path.with_name(f"{path.name}.bak.{stamp}-{suffix}")
        suffix += 1
    return candidate


def restore(path: Path, original: bytes | None) -> None:
    if original is None:
        if path.is_file() and not path.is_symlink():
            path.unlink()
        return
    path.write_bytes(original)
