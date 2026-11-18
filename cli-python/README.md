# WiseRec Python CLI

这是正式发布的 `ml` 客户端。源码位于 `src/wiserec_cli/`，Python CLI 测试位于 `tests/`，Windows 打包与安装入口位于 `scripts/windows/`。

从仓库根目录执行开发安装和回归测试。

```sh
python -m pip install -e ./cli-python
python -m pytest cli-python/tests tests -q
```

制作安装包前，将 `cli-python/config.example.json` 复制为 `cli-python/config.json` 并填写环境配置。已有的仓库根目录 `config.json` 也可用于打包。

```sh
python -m build cli-python
```
