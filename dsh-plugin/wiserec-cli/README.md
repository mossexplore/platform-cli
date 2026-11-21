# WiseRec CLI 保活插件

插件在 DeepSeek Harness 宿主内定时调用 Go CLI，续期当前会话已经绑定的环境和业务。宿主调用不会发送模型消息。普通交互终端仍使用 Go CLI worker。

## Windows Desktop 离线安装

1. 准备支持 `dsh-keepalive-v1` 的 Go CLI 构建。运行 `ml auth ping tick --capabilities` 检查协议；旧的同版本构建可能没有该命令。默认从 MSI 登记或每用户安装目录定位 `ml.exe`，便携版需要在插件配置中填写绝对 `mlPath`。
2. 解压独立 ZIP。在解压目录执行 `./stage-wiserec-dsh-plugin.ps1`。脚本校验 Bundle 并将其保存到版本化的稳定目录，输出本地归档路径。
3. 在目标 Desktop Profile 的“插件 → 添加插件”中选择本地 Bundle，填入脚本输出的本地归档绝对路径。确认插件已启用。若宿主提示重启，请完全退出桌面端及系统托盘后再打开。
4. 在 DSH 会话中绑定环境、登录并选择业务。执行 `ml auth ping status` 查看最近报到和上次平台确认成功时间。插件调度默认每两分钟检查一次，是否请求平台仍由 CLI 的空闲间隔决定。

Bundle 的 DSH 安装门槛为 `>=0.2.2-rc.2`。Windows Desktop 离线加载与真实平台长时保活需按宿主版本执行实机验收。插件依赖宿主 Node.js 内置模块，无额外 npm 依赖。Web Profile 支持范围以单独验收为准。

默认会话空闲窗口为 120 分钟。可配置 `pollSeconds`（60–180）、`idleWindowMinutes`、`mlPath`、`enabled`，以及 `timeoutSeconds`（默认按 CLI 调用预算计算）。

若使用便携版且宿主未提供插件配置表，可在该 Profile 的 `cordis.patch.yml` 为插件添加如下配置覆盖。Windows 路径使用单引号。使用中已有此条目时，在原条目中填写 `mlPath`。

```yaml
- id: wiserec-cli-keepalive
  config:
    mlPath: 'C:\WiseRec\ml.exe'
```

## 构建

在 Windows 安装 Git 和 Python 3.11 或更新版本后，双击本目录的 `build.cmd`。窗口会显示 Git 提交、版本校验、Bundle 生成、校验清单和 ZIP 打包进度。成功后显示完整产物路径，失败时保留错误信息。按任意键关闭窗口。

每次双击都会在 `build.cmd` 同目录的 `dist\` 下创建 `dsh-YYYYMMDD-HHmmss-xxxxxxxx` 子目录。目录名沿用 Go CLI 的日期、时间和 8 位十六进制后缀，增加 `dsh-` 前缀。ZIP 文件名为 `dsh-wiserec-cli-<版本>-windows.zip`。脚本自动记录本地 `HEAD` 的完整提交 SHA。

在仓库根目录也可直接执行以下命令。

```powershell
python scripts/build_dsh_plugin.py --output dsh-plugin/wiserec-cli/dist --new-output-directory --verbose
```

Windows CI 验证 ZIP 校验值、CLI 调度协议以及稳定目录的暂存流程。

## 保活日志

Windows 上，日志位于 `%LOCALAPPDATA%\WiseRec\dsh-plugins\wiserec-cli\logs\keepalive-<宿主PID>.jsonl`。每行记录一个事件，时间为北京时间，表示写入宿主日志的时间。文件达到 256 KiB 时轮转，同一宿主保留当前段和上一段。

`scheduler_started` 表示调度器已启动，`keepalive_confirmed` 表示平台确认续期。请求可用 `request_id` 与 `ml auth ping status` 对照。`keepalive_unconfirmed` 表示本次未获确认，`session_expired` 表示 CLI 判定平台会话已失效，`cli_timeout` 表示调用超时。`session_id` 来自 DSH，`env` 来自本次 CLI 响应。CLI 在返回环境或请求 ID 前中断时，对应字段省略。

正常跳过不写日志。相同会话、环境和原因的重复警告五分钟内合并，成功确认逐次记录。日志只保留时间、级别、事件、已知会话和环境标识、请求 ID 和固定错误分类。

## 停止、恢复和卸载

从会话执行 `ml auth ping stop` 停止当前环境的保活，包含终端 worker。插件重新报到后，`ml auth ping start` 恢复该环境的插件调度。宿主退出、会话关闭、休眠或登录失效会中断保活，具体状态以 `ml auth ping status` 为准。

从目标 Profile 的插件管理器移除插件。仍有其他 Profile 使用该本地 Bundle 时继续保留其归档。卸载后 DSH 的登录及业务命令仍可使用，自动保活随插件停止。
