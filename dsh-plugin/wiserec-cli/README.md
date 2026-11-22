# WiseRec CLI 保活插件

插件在 DeepSeek Harness 宿主内定时调用 Go CLI，续期当前会话已经绑定的环境和业务。宿主调用不会发送模型消息。普通交互终端仍使用 Go CLI worker。

## Windows Desktop 离线安装

1. 准备支持 `dsh-keepalive-v1` 的 Go CLI 构建。运行 `ml auth ping tick --capabilities` 检查协议；旧的同版本构建可能没有该命令。默认从 MSI 登记或每用户安装目录定位 `ml.exe`，便携版需要在插件配置中填写绝对 `mlPath`。
2. 将构建生成的 `dsh-wiserec-cli-<版本>.tgz` 保存在长期保留的目录。
3. 在目标 Desktop Profile 的“插件 → 添加插件”中选择本地 Bundle，直接选择该 `.tgz` 文件。确认插件已启用。若宿主提示重启，请完全退出桌面端及系统托盘后再打开。
4. 在 DSH 会话中绑定环境、登录并选择业务。执行 `ml auth ping status` 查看最近报到和上次平台确认成功时间。插件调度默认每两分钟检查一次，是否请求平台仍由 CLI 的空闲间隔决定。

同一环境同时有符合条件的 DSH 会话和交互终端时，插件优先保活。终端保留后台进程，`ml auth ping status` 显示「DSH 托管，终端待命」和进程 ID。会话关闭或插件报到过期后，符合条件的终端会自动接手。

Bundle 的 DSH 安装门槛为 `>=0.2.2-rc.2`。Windows Desktop 离线加载与真实平台长时保活需按宿主版本执行实机验收。插件依赖宿主 Node.js 内置模块，无额外 npm 依赖。Web Profile 支持范围以单独验收为准。

## 插件配置

包内的 [config.json](config.json) 提供默认值。Windows 上插件首次启用时会生成 `%LOCALAPPDATA%\WiseRec\dsh-plugins\wiserec-cli\config.json`，预填日志参数。升级保留已有文件。修改后完全退出 DSH（含系统托盘）再打开即可生效。

用户文件中填写的字段优先。缺失字段沿用原 Profile 的保活配置或包内默认值。`enabled` 启停本插件，`pollSeconds` 设置检查间隔（60–180 秒），`idleWindowMinutes` 设置会话空闲窗口（默认 120 分钟），`timeoutSeconds` 为 `0` 时按 CLI 调用预算计算。使用便携版时在用户配置文件加上绝对路径，例如 `"mlPath": "C:\\WiseRec\\ml.exe"`。空字符串启用安装目录自动定位。

| `logging` 字段 | 默认值 | 用途 |
| --- | ---: | --- |
| `directoryName` | `logs` | 插件数据目录下的日志子目录名，使用英文字母、数字、连字符或下划线 |
| `maxFileKB` | `256` | 单个日志段的轮转阈值 |
| `maxTotalKB` | `10240` | 日志目录容量软上限 |
| `retentionMinutes` | `10080` | 根据最后修改时间保留旧日志，默认 7 天 |
| `cleanupIntervalMinutes` | `1440` | 定时清理间隔，默认 24 小时；启动时额外清理一次 |

容量按 1 KB = 1024 字节换算。容量和时间均填写正整数，定时清理间隔最长为 35791 分钟。配置文件无法读取或日志字段无效时，插件记录 `config_invalid`，暂停自动清理并继续按有效设置保活和写日志。

### 快速验证 Windows 日志清理

在 Windows 用户配置的 `logging` 中将 `directoryName` 改为 `logs-test`，`retentionMinutes` 改为 `2`，`cleanupIntervalMinutes` 改为 `1`，保存并重启 DSH。让该目录先生成一轮测试日志。取一份已退出宿主的测试日志，把文件的最后修改时间调到 3 分钟前。重启后检查清理摘要中的 `trigger: startup`，或在运行期间准备另一份到期的测试日志，等约 1 分钟检查 `trigger: periodic`。查看 `expired_deleted` 和 `deleted_kb`。测试后可将目录及时间参数改回默认值并重启 DSH。

## 会话保活标识

DSH 会话列表的行尾图标显示该会话所绑定的 WiseRec 环境状态。绿点表示保活正常，红点表示登录已过期，黄点表示本次检查待确认，灰点表示待检查、未登录、未选业务或保活已暂停。鼠标移到会话行后可在 DSH 悬浮卡片里查看状态、已解析的环境、最近检查时间及该环境上次续期成功时间。时间使用北京时间。

会话状态随插件轮询刷新，重新登录或切换环境后以该会话的下一次检查为准。行尾标识仅出现在插件已接管检查的会话上。精确区分「本地登录已过期」和「待登录」需要支持该状态的 Go CLI 构建。

## 构建

在 Windows 安装 Git 和 Python 3.11 或更新版本后，双击本目录的 `build.cmd`。窗口会显示 Git 提交、版本校验、包元数据准备和 `.tgz` 打包进度。成功后显示 SHA-256 和产物完整路径，失败时保留错误信息。按任意键关闭窗口。

每次双击都会在 `build.cmd` 同目录的 `dist\` 下创建 `dsh-YYYYMMDD-HHmmss-xxxxxxxx` 子目录，里面只有一个可直接安装的 `dsh-wiserec-cli-<版本>.tgz`。脚本在包内记录本地 `HEAD` 的完整提交 SHA。

在仓库根目录也可直接执行以下命令。

```powershell
python scripts/build_dsh_plugin.py --output dsh-plugin/wiserec-cli/dist --bundle-only --new-output-directory --verbose
```

Windows CI 验证 `build.cmd` 的产物路径、Bundle 内容和校验值，以及 CLI 调度协议。

## 保活日志

Windows 上，日志默认位于 `%LOCALAPPDATA%\WiseRec\dsh-plugins\wiserec-cli\logs\keepalive-<宿主PID>.jsonl`。每行记录一个事件，时间为北京时间，表示写入宿主日志的时间。文件默认达到 256 KB 时轮转，同一宿主保留当前段和上一段。

按默认配置，插件启动时及运行期间每 24 小时清理一次。已退出宿主的日志按最后修改时间保留 7 天。插件日志合计超过 10 MiB 时，按最旧优先额外清理已退出宿主的日志。运行中的宿主及存活状态不明的宿主日志受保护，目录可能暂时超过容量上限。卸载插件时保留配置和日志。

每轮清理在同一日志中写一条摘要，`trigger` 为 `startup`（启动）或 `periodic`（定时）。`expired_deleted` 和 `capacity_deleted` 分别表示本轮按保留期和容量成功删除的文件数。`deleted_kb` 按 1 KB = 1024 字节换算，最多保留两位小数。无文件可删时计数为 0。成功使用 `log_cleanup_completed`，部分或全部失败使用 `log_cleanup_failed`，并记录固定错误分类 `scan_failed` 或 `delete_failed`。

```json
{"time":"2026-11-22 09:00:00","level":"info","event":"log_cleanup_completed","trigger":"startup","expired_deleted":3,"capacity_deleted":1,"deleted_kb":512}
```

`scheduler_started` 表示调度器已启动，`keepalive_confirmed` 表示平台确认续期。请求可用 `request_id` 与 `ml auth ping status` 对照。`keepalive_unconfirmed` 表示本次未获确认，`session_expired` 表示 CLI 判定平台会话已失效，`cli_timeout` 表示调用超时。`session_id` 来自 DSH，`env` 来自本次 CLI 响应。CLI 在返回环境或请求 ID 前中断时，对应字段省略。

正常跳过探活不写日志。相同会话、环境和原因的重复警告五分钟内合并，成功确认逐次记录。清理摘要按宿主记录，会话与请求字段仅用于保活事件。

## 停止、恢复和卸载

从会话执行 `ml auth ping stop` 停止当前环境的保活，包含终端 worker。插件重新报到后，`ml auth ping start` 恢复该环境的插件调度。宿主退出、会话关闭、休眠或登录失效会中断保活，具体状态以 `ml auth ping status` 为准。

从目标 Profile 的插件管理器移除插件。仍有其他 Profile 使用该本地 Bundle 时继续保留其归档。卸载后 DSH 的登录及业务命令仍可使用，自动保活随插件停止。
