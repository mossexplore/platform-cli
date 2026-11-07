"""Initialize the user configuration explicitly during installation."""

import json
from importlib import resources
from pathlib import Path
from tempfile import NamedTemporaryFile

from .config import ConfigManager, user_config_dir
from .errors import ConfigError


def packaged_config_text():
    try:
        return resources.files("wiserec_cli").joinpath("config.json").read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError("安装包中缺少 config.json，请重新安装 wiserec-cli") from exc


def install_config(destination):
    template = packaged_config_text()
    settings = json.loads(template)
    if not isinstance(settings, dict):
        raise ConfigError("安装包配置顶层必须是 JSON 对象")
    candidate = ConfigManager.__new__(ConfigManager)
    candidate.path = destination
    candidate._data = settings
    candidate._validate()
    try:
        previous = json.loads(destination.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        previous = {}
    current = previous.get("current") if isinstance(previous, dict) else None
    if isinstance(current, str) and any(profile["name"] == current for profile in settings["profiles"]):
        settings["current"] = current
        template = json.dumps(settings, ensure_ascii=False, indent=2) + "\n"

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(template)
        temporary_path.replace(destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def reset_packaged_config():
    destination = user_config_dir() / "config.json"
    install_config(destination)
    return destination


if __name__ == "__main__":
    print(reset_packaged_config())
