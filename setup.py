"""setuptools 构建扩展：将项目根目录 config.json 放入 Wheel。"""

from pathlib import Path
from shutil import copyfile, rmtree
import hashlib
import json

from setuptools import setup
from setuptools.command.build_py import build_py as BaseBuildPy


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
        sources = [(Path("skill/wiserec-platform/SKILL.md"), "skills/wiserec-platform/SKILL.md"),
                   (Path("skill/commands/ml.md"), "commands/ml.md")]
        sources += [(path, "skills/wiserec-platform/references/" + path.name)
                    for path in sorted(Path("skill/wiserec-platform/references").glob("*.md"))]
        hashes = {}
        for source, relative in sources:
            target = resources / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            copyfile(source, target)
            hashes[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
        (resources / "manifest.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")


setup(cmdclass={"build_py": BuildPy})
