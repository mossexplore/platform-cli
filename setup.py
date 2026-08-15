"""setuptools 构建扩展：将项目根目录 config.json 放入 Wheel。"""

from pathlib import Path
from shutil import copyfile

from setuptools import setup
from setuptools.command.build_py import build_py as BaseBuildPy


class BuildPy(BaseBuildPy):
    def run(self) -> None:
        super().run()
        source = Path("config.json")
        destination = Path(self.build_lib) / "wisemlops_cli" / "config.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        copyfile(source, destination)


setup(cmdclass={"build_py": BuildPy})
