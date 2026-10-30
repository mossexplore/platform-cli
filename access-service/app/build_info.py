"""Release image version, with the repository version for local development."""
import os
from pathlib import Path
import tomllib


def application_version():
    built = os.environ.get('WISEREC_APP_VERSION', '').strip()
    if built and built != 'development':
        return built
    try:
        with (Path(__file__).resolve().parents[2] / 'pyproject.toml').open('rb') as source:
            return tomllib.load(source)['project']['version']
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return 'development'
