"""setuptools 构建扩展：将项目根目录 config.json 放入 Wheel。"""

from pathlib import Path
from shutil import copyfile, rmtree
import hashlib
import json
import runpy

from setuptools import setup
from setuptools.command.build_py import build_py as BaseBuildPy

root = Path(__file__).resolve().parent
runpy.run_path(str(root / 'scripts/sync_versions.py'))['sync'](root)


class BuildPy(BaseBuildPy):
    def run(self) -> None:
        # Wheel assembly copies all of build_lib, including obsolete packages
        # left by older builds. Package discovery does not filter those files.
        build_lib = Path(self.build_lib)
        if build_lib.exists():
            rmtree(build_lib)
        super().run()
        source = Path("config.json")
        destination = Path(self.build_lib) / "wiserec_cli" / "config.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        copyfile(source, destination)

        resources = Path(self.build_lib) / "wiserec_cli" / "opencode_resources"
        if resources.exists():
            rmtree(resources)
        sources = [(Path("skill/commands") / name, "commands/" + name)
                   for name in ("ml.md", "ml-lab.md")]
        for directory in (Path("skill/wiserec-platform"),
                          Path("skill-lab/wiserec-platform-detailed")):
            prefix = "skills/" + directory.name + "/"
            sources.append((directory / "SKILL.md", prefix + "SKILL.md"))
            sources += [(path, prefix + path.relative_to(directory).as_posix())
                        for path in sorted((directory / "references").rglob("*.md"))]
        hashes = {}
        for source, relative in sources:
            target = resources / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            copyfile(source, target)
            hashes[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
        (resources / "manifest.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")


setup(cmdclass={"build_py": BuildPy})
