# CLI 演示环境测试报告

测试日期：2026-10-18。环境：Linux x86_64、Python 3.12。目标源码版本：CLI / 权限服务 1.0.7.2，演示扩展 0.1.0。基线提交：fa6c431；本报告与实现一起提交，未发布正式 Release。

## 测试结果

| 范围 | 结果 |
| --- | --- |
| 正式 CLI 全量回归（启用真实本地 Jupyter） | 993 passed，另有 121 个 subtest passed，0 skipped |
| 权限管理系统回归 | 234 passed，0 skipped |
| Node 时间与时区测试 | 3 passed，0 skipped |
| 演示跨进程业务、隔离、Jupyter、权限与上下文联合回归 | 67 passed，0 skipped，548.39 秒 |
| 补充真实权限测试 | 10 passed，0 skipped |
| 完整连续流程与训练取消状态一致性专项 | 1 passed（包含多条独立 CLI 进程调用） |
| 正式 Wheel / sdist 构建及内容检查 | 通过 |
| 源码目录外正式 Wheel 干净安装 | 版本与包元数据均为 1.0.7.2，无模拟模块 |
| 最终演示联网、离线包安装与实际权限调用 | 均通过；离线安装禁止访问包索引 |
| 文档结构、工作流 YAML、差异检查 | 通过 |

正式 CLI、权限服务与演示联合回归各有 2 个依赖弃用警告，无失败。联合回归包含 64 个演示用例和 3 个正式上下文用例；随后扩充的 4 个权限用例已在 10 项权限专项中全部通过。因此当前收集到的 68 个演示用例均有通过记录，未将重复执行计入唯一用例数。首次回归发现 Typer 新版异常类型兼容问题，已限制在既有兼容版本范围；同步修正既有测试中 stderr 输出、企业 CA 和独立 Jupyter 测试配置的断言。演示回归曾在同时运行多个测试集时出现单个子进程启动超时，已将端到端子进程预算从 30 秒调整至 90 秒，并重新执行验证；没有屏蔽失败或跳过用例。

## 权限验证证据

`devtools/mock-platform/tests/permission_server.py` 启动仓库 access-service 的真实应用和临时数据库，通过 TCP 接受演示 CLI 请求。测试直接检查数据库中的 CallLog，而不是只检查 CLI 文本。

已验证：放行日志中的账号、环境、businessid、命令、CLI 版本和请求标识；撤销授权、服务端版本封禁阻止写入；权限服务不可用时业务状态不变；无授权账号被拒；禁止关闭权限和指定模拟权限地址；精确网络路径允许列表；reset、advance、fault 和保活请求也经过权限系统。原权限系统回归补充环境匹配、授权有效期、用户启停等规则。

演示本地登录不验证平台身份；权限服务沿用客户端上报用户名协议。本次没有访问或修改用户的生产权限服务、授权库或真实业务平台。

## 产物验证

- 正式 Wheel 和 sdist 经过 `scripts/releasing/check-cli-package.py` 检查；负向用例验证嵌套 Wheel 含 mock 时失败。
- 正式 Wheel 在源码目录之外的全新虚拟环境安装，核对 `ml --version`、包元数据和模块可用性。
- 演示独立 ZIP 在新目录解压，以 `PIP_NO_INDEX=1` 安装离线依赖；同名 ml 查询 context 和业务列表，并检查真实权限调用日志。
- 包装器使用 Python 隔离模式，验证继承的 PYTHONPATH 不会替换包内核心模块。
- 状态、模拟凭据、业务选择、历史、导出及本地 Jupyter 均使用临时工作区；未写入正式安装目录。

## 复现入口

```bash
python -m pip install -e '.[jupyter-local]' -e ./devtools/mock-platform pytest build
python -m pip install -r access-service/requirements.lock
python -m pytest devtools/mock-platform/tests tests/test_execution_context.py -q
PYTHONPATH=access-service python -m pytest access-service/tests -q
node --test access-service/tests/test_time_presets.cjs
python -m build --outdir /tmp/formal-cli
python scripts/releasing/check-cli-package.py /tmp/formal-cli/*
python scripts/demo/build-demo.py --offline --output /tmp/demo-cli
python devtools/mock-platform/tests/validate_bundle.py /tmp/demo-cli/*-demo-offline.zip
git diff --check
```

正式 Jupyter 全量回归先在另一终端启动 `python scripts/jupyter_local.py`，再运行：

```bash
ML_JUPYTER_TEST_CONFIG="$PWD/.jupyter-local/config.json" ML_JUPYTER_AGENT_LIVE=1 python -m pytest tests -q
```

本次实际使用 `/tmp/wiserec-jupyter-regression/config.json` 的隔离服务和相同环境开关完成正式回归；演示 Jupyter 测试自行创建并关闭独立服务。

## 验证范围限制

Windows 原生脚本执行、Windows 离线包安装以及生产 MySQL/外部权限网关联调未在本 Linux 工作区执行。独立 demo 工作流已提供 Windows 构建和安装用例，不能把工作流配置当作已运行结果。正式发布仍需完成仓库规定的 Windows 与发布产物验证。本次只交付代码、设计和测试文档，不发布 Release、不部署生产、不修改现有授权策略。
