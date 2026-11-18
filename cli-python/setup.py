"""Build the Python CLI with the formal configuration and Skill resources."""

from pathlib import Path
from shutil import copyfile, rmtree
import hashlib
import json
import runpy

from setuptools import setup
from setuptools.command.build_py import build_py as BaseBuildPy
from setuptools.command.sdist import sdist as BaseSdist

project = Path(__file__).resolve().parent
# An extracted sdist contains its own copy of the shared build inputs.
repository = project if (project / "versions.toml").is_file() else project.parent
version_tools = runpy.run_path(str(repository / "scripts/sync_versions.py"))
version_tools["sync"](repository)


def build_config():
    for directory in (project, repository):
        source = directory / "config.json"
        if source.is_file():
            return source
    raise FileNotFoundError(
        "Missing config.json: copy cli-python/config.example.json to cli-python/config.json "
        "and edit the deployment settings. An existing repository-root config.json is also supported."
    )


class Sdist(BaseSdist):
    def make_release_tree(self, base_dir, files):
        config = build_config()
        super().make_release_tree(base_dir, files)
        # Vendor the selected build inputs so an extracted sdist is standalone.
        sources = [
            "versions.toml", "scripts/sync_versions.py", "docs/Jupyter本地开发指南.md",
            "skill/commands/ml.md",
            *(path.relative_to(repository) for path in
              sorted((repository / "skill/wiserec-platform").rglob("*.md"))),
        ]
        for source in sources:
            target = Path(base_dir) / source
            target.parent.mkdir(parents=True, exist_ok=True)
            copyfile(repository / source, target)
        copyfile(config, Path(base_dir) / "config.json")


class BuildPy(BaseBuildPy):
    def run(self) -> None:
        source = build_config()
        # Wheel assembly copies all of build_lib, including obsolete packages
        # left by older builds. Package discovery does not filter those files.
        build_lib = Path(self.build_lib)
        if build_lib.exists():
            rmtree(build_lib)
        super().run()
        destination = Path(self.build_lib) / "wiserec_cli" / "config.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        copyfile(source, destination)

        resources = Path(self.build_lib) / "wiserec_cli" / "opencode_resources"
        if resources.exists():
            rmtree(resources)
        directory = repository / "skill/wiserec-platform"
        prefix = "skills/wiserec-platform/"
        sources = [
            (repository / "skill/commands/ml.md", "commands/ml.md"),
            (directory / "SKILL.md", prefix + "SKILL.md"),
            *((path, prefix + path.relative_to(directory).as_posix())
              for path in sorted((directory / "references").rglob("*.md"))),
        ]
        source_hashes = {relative: hashlib.sha256(source.read_bytes()).hexdigest()
                         for source, relative in sources}
        source_digest = hashlib.sha256(json.dumps(
            source_hashes, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        cli_version = version_tools["read_versions"](repository)[0]["cli"]
        hashes = {}
        for source, relative in sources:
            target = resources / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.name == "SKILL.md":
                text = source.read_text(encoding="utf-8")
                if text.count("\nmetadata:\n") != 1:
                    raise ValueError("Formal skill needs exactly one metadata mapping")
                text = text.replace("\nmetadata:\n", "\nmetadata:\n"
                                    f'  source_cli_version: "{cli_version}"\n'
                                    f'  source_sha256: "{source_digest}"\n', 1)
                target.write_text(text, encoding="utf-8")
            else:
                copyfile(source, target)
            hashes[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
        (resources / "manifest.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")


setup(cmdclass={"build_py": BuildPy, "sdist": Sdist})
