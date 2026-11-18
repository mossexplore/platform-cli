# Go CLI 预览

本目录为 WiseRec CLI 的原生 Go 客户端。按 Python 命令树核对，原生入口覆盖 WiseRec 的 106 个公开命令及 MLOps 的 77 个支持命令，包括训练、服务、模型部署、Web Studio 和 Jupyter。当前交付为可独立试运行的 Windows x64 二进制，正式安装及 Agent 的 `/ml` 入口继续使用已发布客户端。

## 构建 Windows x64 二进制

开发机构建需要 Go 1.25 或以上。以下 PowerShell 命令从仓库根目录执行。构建脚本读取 `versions.toml` 的 CLI 版本，输出目录选一个空目录，启动时显式使用二进制路径。

```powershell
$preview = Join-Path $env:TEMP 'wiserec-go-preview'
./cli-go/scripts/build-windows.ps1 -OutputDirectory $preview
$mlPreview = Join-Path $preview 'ml.exe'
& $mlPreview --version
```

## 准备独立配置

在 `%APPDATA%\ml-go-preview\config.json` 内创建配置。把示例域名替换为已授权的测试平台和权限服务。两边的环境标识及平台源地址需对应。对于 MLOps 测试环境，将 `platform_type` 填为 `mlops`。需要企业 CA 时，可配置 `access_control.ca_source` 为 `custom`，同时填写 CA 文件绝对路径 `ca_file`；默认读取环境 CA 或系统信任库。

```json
{
  "current": "preview",
  "profiles": [
    {
      "name": "preview",
      "api_endpoint": "https://platform.example.test/",
      "platform_type": "wiserec",
      "output_format": "table"
    }
  ],
  "access_control": {
    "enable": true,
    "url": "https://permissions.example.test/cli-permission"
  }
}
```

浏览器缓存、登录缓存和当前业务均保存在同一个预览目录，同一系统账号的预览命令使用共同的业务选择。平台地址变更后重新登录。状态更新使用操作系统文件锁，进程退出会释放锁。预览凭据文件包含当前会话信息，请保留在当前账号目录内。

## 试运行

在测试平台的网页先选择一个有效业务。登录时如提示未识别当前业务，在打开的 Edge 窗口完成选择，再运行登录。预览登录使用系统已安装的 Microsoft Edge 正式版和独立浏览器目录。

```powershell
& $mlPreview context --json
& $mlPreview tree --all
& $mlPreview login
& $mlPreview mep config get -o json
```

登录成功后以表格显示环境、账号、中文名、部门和 `businessId`。`context` 和 MEP 查询沿用同样的表格样式，选择 JSON 时输出缩进后的数据。

查询从当前环境的 `business.json` 读取 `selected.businessId`，实时鉴权成功后才访问 MEP。预览的登录即凭据刷新入口。可用 `ml env use NAME` 和 `ml business use --tenant TENANT_ID` 切换环境和租户；使用 `ml auth status` 核对登录、业务 ID 和有效期。CLI 对已确认的成功响应更新有效期，交互终端支持自动保活。缓存过期或平台拒绝时，用 `ml login` 建立新会话。

## 验证

在 `cli-go` 下运行 `go test ./...` 和 `go vet ./...`。集成测试临时启动本机 HTTP 服务，验证鉴权先于业务请求、选定业务 ID 和请求关联、权限拒绝以及平台地址变化。浏览器事件单测覆盖同源身份响应与业务目录解析。命令对照测试从 Python 基线核对命令、参数与平台支持范围。模拟接口另外覆盖训练列表的两套协议、并发切换业务时阻断写入、模型部署预览及 Jupyter 独立 Kernel 执行和清理。

后续在受管 Windows 上验收完整迁移行为。核对两种管理台的首次登录、重复登录、缓存过期后重新登录、业务选择、在线权限允许与拒绝。性能比较在同机同网络环境记录 Go 和 Python CLI 的进程冷启动、重复执行以及 MEP 查询端到端耗时，分别记录中位数及 P95。

开发机已完成 Go 测试、竞态检测、静态检查及 Windows x64 交叉构建。macOS arm64 上交替启动两个客户端执行 `--version`，预热后各采集 30 次新进程。Go 的 P50/P95 为 5.0/5.3 ms，Python 为 146.2/148.8 ms。这组数据衡量本地进程启动，首轮 Edge 登录与 MEP 查询已由用户在 Windows 试运行通过。完整命令的真实环境执行、交互终端、保活以及 Windows 性能仍待验收。


Web Studio 默认实例按环境、账号和业务保存。当前 Go 客户端每次建立新 Jupyter 连接时向平台重新获取访问地址。Notebook 执行接受 nbformat 4 文件。预览目录中的会话与正式安装分别登录，正式安装器、状态原地迁移及回滚流程仍待目标环境验证。
