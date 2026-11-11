"""Build real wheels from a checkout containing obsolete build outputs."""
import json
import hashlib
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import zipfile


def check_skill_provenance(archive, project):
    prefix = "wiserec_cli/opencode_resources/"
    manifest = json.loads(archive.read(prefix + "manifest.json"))
    sources = {"commands/ml.md": project / "skill/commands/ml.md"}
    directory = project / "skill/wiserec-platform"
    for path in [directory / "SKILL.md", *sorted((directory / "references").rglob("*.md"))]:
        sources["skills/wiserec-platform/" + path.relative_to(directory).as_posix()] = path
    assert manifest.keys() == sources.keys()
    source_hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                     for name, path in sources.items()}
    digest = hashlib.sha256(json.dumps(
        source_hashes, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    version = runpy.run_path(str(project / "scripts/sync_versions.py"))["read_versions"](project)[0]["cli"]
    source_skill = (directory / "SKILL.md").read_text(encoding="utf-8")
    assert "source_cli_version:" not in source_skill
    for name, path in sources.items():
        data = archive.read(prefix + name)
        assert hashlib.sha256(data).hexdigest() == manifest[name]
        if path.name == "SKILL.md":
            stamped = data.decode("utf-8")
            assert f'  source_cli_version: "{version}"\n' in stamped
            assert f'  source_sha256: "{digest}"\n' in stamped
            assert stamped.replace(f'  source_cli_version: "{version}"\n', "").replace(
                f'  source_sha256: "{digest}"\n', "") == source_skill
        else:
            assert data == path.read_bytes()
    metadata, = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
    assert f"Version: {version}\n" in archive.read(metadata).decode()
    assert f'__version__ = "{version}"' in archive.read("wiserec_cli/__init__.py").decode()
    return version


def test_wheel_excludes_stale_build_modules(tmp_path):
    root = Path(__file__).resolve().parents[1]
    project = tmp_path / "project"
    project.mkdir()
    for name in ("setup.py", "pyproject.toml", "MANIFEST.in", "config.example.json", "versions.toml"):
        shutil.copy2(root / name, project / name)
    custom = json.loads((project / 'config.example.json').read_text())
    custom['profiles'][0]['api_endpoint'] = 'https://custom-package.example/dashboard'
    (project / 'config.json').write_text(json.dumps(custom))
    (project / 'scripts').mkdir()
    shutil.copy2(root / 'scripts/sync_versions.py', project / 'scripts/sync_versions.py')
    for name in ("src", "skill"):
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
            assert archive.read("wiserec_cli/config.json") == (project / "config.json").read_bytes()
            assert "wiserec_cli/opencode_resources/manifest.json" in names
            check_skill_provenance(archive, project)
    (project / 'config.json').unlink()
    result = subprocess.run([sys.executable, 'setup.py', 'bdist_wheel'], cwd=project,
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert 'Missing project-root config.json' in result.stdout + result.stderr



def test_sdist_excludes_lab_and_builds_formal_skill(tmp_path):
    import tarfile
    root = Path(__file__).resolve().parents[1]
    project = tmp_path / "project"
    project.mkdir()
    for name in ("setup.py", "pyproject.toml", "MANIFEST.in", "config.example.json", "versions.toml"):
        shutil.copy2(root / name, project / name)
    custom = json.loads((project / 'config.example.json').read_text())
    custom['profiles'][0]['api_endpoint'] = 'https://sdist-config.example/dashboard'
    packaged_config = json.dumps(custom).encode()
    (project / 'config.json').write_bytes(packaged_config)
    (project / "scripts").mkdir()
    shutil.copy2(root / "scripts/sync_versions.py", project / "scripts/sync_versions.py")
    for name in ("src", "skill"):
        shutil.copytree(root / name, project / name, ignore=shutil.ignore_patterns("*.egg-info", "__pycache__"))
    # Exclusion must hold even if an archive or old entry is present in a checkout.
    (project / "skill-lab/commands").mkdir(parents=True)
    (project / "skill-lab/commands/ml-lab.md").write_text("archived")
    (project / "skill/commands/ml-lab.md").write_text("obsolete")
    result = subprocess.run([sys.executable, "setup.py", "sdist"], cwd=project, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    archive, = (project / "dist").glob("*.tar.gz")
    with tarfile.open(archive) as source:
        names = source.getnames()
        assert any(name.endswith("/config.json") for name in names)
        assert not any("skill-lab" in name or name.endswith("/ml-lab.md") for name in names)
        assert any(name.endswith("/skill/wiserec-platform/SKILL.md") for name in names)
        source.extractall(tmp_path / "extracted")
    restored, = (tmp_path / "extracted").iterdir()
    result = subprocess.run([sys.executable, "setup.py", "bdist_wheel"], cwd=restored, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    wheel, = (restored / "dist").glob("*.whl")
    with zipfile.ZipFile(wheel) as source:
        names = source.namelist()
        assert source.read("wiserec_cli/config.json") == packaged_config
        assert "wiserec_cli/opencode_resources/skills/wiserec-platform/SKILL.md" in names
        assert not any("wiserec-platform-detailed" in name or "ml-lab.md" in name for name in names)
        version = check_skill_provenance(source, restored)
        installed = tmp_path / "installed"
        source.extractall(installed)
    # Check the exact built resources through the real installer in isolated paths.
    from wiserec_cli.opencode_install import install_resources
    resources = installed / "wiserec_cli/opencode_resources"
    for name in ("opencode", "cac"):
        destination = tmp_path / name
        install_resources(destination, resources)
        skill = "skills/wiserec-platform/SKILL.md"
        assert (destination / skill).read_bytes() == (resources / skill).read_bytes()
    result = subprocess.run(
        [sys.executable, "-c", "from wiserec_cli.cli import run; run()", "--version"],
        cwd=tmp_path, env=dict(os.environ, PYTHONPATH=str(installed)),
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"ml {version}"
