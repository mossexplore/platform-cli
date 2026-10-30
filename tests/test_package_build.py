"""Build real wheels from a checkout containing obsolete build outputs."""
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import zipfile


def test_wheel_excludes_stale_build_modules(tmp_path):
    root = Path(__file__).resolve().parents[1]
    project = tmp_path / "project"
    project.mkdir()
    for name in ("setup.py", "pyproject.toml", "MANIFEST.in", "config.json", "versions.toml"):
        shutil.copy2(root / name, project / name)
    (project / 'scripts').mkdir()
    shutil.copy2(root / 'scripts/sync_versions.py', project / 'scripts/sync_versions.py')
    for name in ("src", "skill", "skill-lab"):
        shutil.copytree(root / name, project / name,
                        ignore=shutil.ignore_patterns("*.egg-info", "__pycache__"))

    stale_files = ("wisemlops_cli/__init__.py", "obsolete.py",
                   "wiserec_cli/removed.py")
    for name in stale_files:
        path = project / "build" / "lib" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# obsolete build output\n", encoding="utf-8")

    check = runpy.run_path(str(root / "scripts/releasing/check-cli-package.py"))["check"]
    # Also exercise a second build in the same checkout, as online/offline builds do.
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "setup.py", "bdist_wheel"], cwd=project,
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        wheel, = (project / "dist").glob("*.whl")
        check(wheel)
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
            assert names.isdisjoint(stale_files)
            assert "wiserec_cli/cli.py" in names
            assert archive.read("wiserec_cli/config.json") == (root / "config.json").read_bytes()
            assert "wiserec_cli/opencode_resources/manifest.json" in names


def test_both_skills_survive_sdist_and_installation():
    root = Path(__file__).resolve().parents[1]
    runpy.run_path(str(root / "skill-lab/validation/verify_package.py"))["main"]()
