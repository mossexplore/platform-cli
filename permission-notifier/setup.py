"""Sync from the repository manifest; standalone packages use generated metadata."""
from pathlib import Path
import runpy
from setuptools import setup

root = Path(__file__).resolve().parents[1]
if (root / 'versions.toml').is_file():
    runpy.run_path(str(root / 'scripts/sync_versions.py'))['sync'](root)

setup()
