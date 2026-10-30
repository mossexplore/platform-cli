"""Sync from the repository manifest when building from a full checkout."""
from pathlib import Path
import runpy
from setuptools import setup

root = Path(__file__).resolve().parents[1]
if (root / 'versions.toml').is_file():
    runpy.run_path(str(root / 'scripts/sync_versions.py'))['sync'](root)

setup()
