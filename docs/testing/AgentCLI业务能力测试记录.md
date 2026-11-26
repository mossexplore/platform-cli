# Agent CLI 业务能力测试记录

验证日期：2026-10-30（北京时间）。

## 本次验证范围

本次补齐 Agent 的 CLI 业务能力：87 个业务工具、1 个发现工具，映射当前 78 个 CLI 业务叶子命令；25 个有副作用工具使用网页人工确认。源码、设计和使用说明一并提交 main；没有发布 Release 或部署生产。

## 自动化结果

| 测试范围 | 最终结果 |
| --- | --- |
| Agent Python 全量，包含真实本机 Jupyter 联调 | 200 passed，0 skipped |
| Agent 浏览器逻辑 Node 测试 | 10 passed，0 skipped |
| CLI Python 全量，包含真实本机 Jupyter 联调 | 1180 passed；另有 212 subtests passed，0 skipped |
| 权限服务 Python 全量，包含隔离 MySQL 专用用例 | 260 passed，0 skipped |
| 权限服务浏览器逻辑 Node 测试 | 23 passed，0 skipped |
| Git 差异检查 | `git diff --check` 通过 |

Python 测试有既有 Typer/Click 或 Starlette 弃用警告，无测试失败。权限服务首次未配置 MySQL 时有一个可选用例跳过；随后启动独立 MySQL 8.4 测试容器，配置专用 `notification_test` 数据库，重新运行整套权限服务测试，最终没有跳过。未连接生产数据库。

## 关键测试用例

| 文件 | 验证内容 |
| --- | --- |
| `agent-service/tests/test_business_coverage.py` | 从真实 Typer 命令树核对所有业务命令覆盖；拒绝不存在的权限命令；发现分页完整、不超过四个工具；Schema 禁止账号、Cookie、业务和任意请求注入 |
| `agent-service/tests/test_business_actions.py` | 确认前零写请求；确认后真实 Service HTTP 请求；准确的 CLI 命令、业务和操作者；CSRF、参数不可变、重复确认、跨会话、拒绝、撤权、取消；服务端直接执行不能绕过确认 |
| `agent-service/tests/test_business_files.py` | 上传与下载隔离、路径处理、文件上限、不可伪造的部署计划、发布保存的同一 payload；下载主机限制与凭据隔离；CSV Multipart 上传、YAML 流式导出及权限门禁；附件清理 |
| `agent-service/tests/test_business_jupyter.py` | Jupyter HTTP 文件操作、逐请求检查、businessid；Web Studio 连接发现及 Token 不进入结果；可信网关校验；WebSocket 撤权阻止发送 |
| `agent-service/tests/test_business_jupyter_live.py` | 隔离本机真实 Jupyter：二进制上传/下载、文本读写、目录、复制、移动、删除、独立 Kernel 命令及清理、Notebook 执行与结果附件、持久终端创建/输入/关闭 |
| `agent-service/tests/test_actions.cjs` | 确认卡片以纯文本展示不可信参数；没有点击时不批准；点击仅提交绑定 action ID 与批准值；处理后禁用按钮 |
| 既有 Agent、CLI、权限服务用例 | SDK Chat Completions/Responses、工具可见性、对话并发隔离、权限、流式事件、会话生命周期、业务协议和正式/Mock 打包隔离回归 |

测试过程中发现并修复了 Web Studio 服务包装异常导致权限拒绝被降级为普通工具错误的问题。现已保留网关拒绝状态，并停止该运行；已有请求无法撤销这一限制仍然适用。

## 复现命令

先按各服务要求安装依赖。下面命令中的 Python 路径是本次工作区使用的虚拟环境；其他机器换成安装对应锁定依赖的 Python。Jupyter 配置必须指向独立的本机测试实例，不要指向用户工作环境。

在仓库根目录运行：

```bash
ML_JUPYTER_TEST_CONFIG=/PATH/TO/ISOLATED/config.json \
ML_JUPYTER_AGENT_LIVE=1 \
.venv/bin/python -m pytest tests -q

ML_JUPYTER_TEST_CONFIG=/PATH/TO/ISOLATED/config.json \
.venv-agent/bin/python -m pytest agent-service/tests -q

node --test agent-service/tests/*.cjs

# 先配置 NOTIFIER_TEST_DATABASE_URL，只能使用独立的 notification_test 数据库
PYTHONPATH=access-service .venv/bin/python -m pytest access-service/tests -q

node --test access-service/tests/*.cjs
git diff --check
```

本机 Jupyter 测试使用 `scripts/jupyter_local.py` 的隔离配置生成逻辑和真实 JupyterLab；新 Agent 联调用例只允许 localhost/127.0.0.1。权限服务 MySQL 用例会创建和调整测试表，必须使用独立测试库。

## 验证边界

模型 HTTP、业务平台 HTTP、权限撤销与浏览器认证使用测试桩；执行和文件协议另有真实本机 Jupyter 验证，权限服务另有真实隔离 MySQL 验证。以上结果不代表已完成真实业务平台、真实模型服务、生产 MySQL 和 Windows Edge 的部署联调。

没有修改正式 CLI 包构建范围、CLI 命令或数据库结构。新模块均位于独立 `agent-service`，正式 CLI 的源码包规则没有增加 Agent 或 Mock 依赖。原本地 Agent 的生产部署限制继续适用。
