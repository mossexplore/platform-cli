"""setuptools 构建扩展：将项目根目录正式 config.json 放入 Wheel。"""

from pathlib import Path
from shutil import copyfile, rmtree
import hashlib
import json
import runpy

from setuptools import setup
from setuptools.command.build_py import build_py as BaseBuildPy

root = Path(__file__).resolve().parent
version_tools = runpy.run_path(str(root / 'scripts/sync_versions.py'))
version_tools['sync'](root)


class BuildPy(BaseBuildPy):
    def run(self) -> None:
        source = root / "config.json"
        if not source.is_file():
            raise FileNotFoundError(
                "Missing project-root config.json: copy config.example.json to config.json, "
                "edit the deployment settings, then rebuild. The example is never packaged as a fallback."
            )
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
        sources = [(Path("skill/commands") / name, "commands/" + name)
                   for name in ("ml.md",)]
        for directory in (Path("skill/wiserec-platform"),):
            prefix = "skills/" + directory.name + "/"
            sources.append((directory / "SKILL.md", prefix + "SKILL.md"))
            sources += [(path, prefix + path.relative_to(directory).as_posix())
                        for path in sorted((directory / "references").rglob("*.md"))]
        source_hashes = {relative: hashlib.sha256((root / source).read_bytes()).hexdigest()
                         for source, relative in sources}
        source_digest = hashlib.sha256(json.dumps(
            source_hashes, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        cli_version = version_tools['read_versions'](root)[0]['cli']
        hashes = {}
        for source, relative in sources:
            target = resources / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.name == "SKILL.md":
                text = (root / source).read_text(encoding="utf-8")
                if text.count("\nmetadata:\n") != 1:
                    raise ValueError("Formal skill needs exactly one metadata mapping")
                text = text.replace("\nmetadata:\n", "\nmetadata:\n"
                                    f'  source_cli_version: "{cli_version}"\n'
                                    f'  source_sha256: "{source_digest}"\n', 1)
                target.write_text(text, encoding="utf-8")
            else:
                copyfile(root / source, target)
            hashes[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
        (resources / "manifest.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")


setup(cmdclass={"build_py": BuildPy})
