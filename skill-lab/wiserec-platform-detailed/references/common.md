# 共同规则

## 环境、认证与业务

- 当前聊天首次缺少已确认上下文时，仅运行 `ml context --json` 与 `ml auth status`。context 已包含 CLI 版本、路径、当前环境和配置来源，无需另查版本和环境。保留已确认的非敏感上下文，后续普通查询直接执行；新的一条意图、再次调用 `/ml-lab` 或再次加载 skill 不视为新会话。
- `ml tree`、`ml history` 不需要平台登录；`ml context` 不访问网络，但需要可读取的生效配置。登录、退出、环境管理和认证检查按各自说明执行，不要求先选业务再登录。
- 业务资源查询/操作需要有效认证、当前环境业务选择及对应权限。Jupyter 按当前配置连接；Web Studio 模式使用当前平台业务和选择实例，direct 模式使用其 Jupyter 配置；不要混用两种模式的目标。direct 模式传 --studio-id 会报错；其 studio_id 输出为空字符串。
- 环境通常包括 dev/mirror/explore/product。用户未指定时沿用已确认环境，不擅自切换；与已确认环境相同则不重复 env use。切换环境、CLI 路径或配置来源，或上下文丢失时，重新运行 context --json 与 auth status；登录、退出或业务切换后按结果更新受影响的上下文。
- `auth status` 检查 status=valid、profile 与当前环境一致，以及有效的 businessId；剩余时间字段为 remaining_minutes，并有 expires_at。businessId 读取当前环境 selected.businessId，不用旧字段或其他环境的 ID。缺少有效 businessId 或需要租户/团队名称时才补查 business show，需要选择业务时才列候选。
- 平台请求 businessid 来源应为 business.json 当前具体环境 selected.businessId；接口根地址来自配置 api_endpoint。这些由 CLI 负责，skill 不手工读取或修改文件实现绕过。
- 缺少认证时让用户通过 `ml login` 的 Edge 流程登录，不索取 Cookie、Token、密码或验证码。登录和 business refresh 的工具时限至少预留 10 分钟。

- 上下文只在当前聊天内复用，不跨账号或聊天共享。CLI 每次业务调用仍执行认证、业务与权限校验；skill 的前置检查不能替代它们。其他终端的环境或业务变化无法靠聊天记录自动发现，提交写操作前重新运行 context --json 与 auth status 核对实际环境、账号和业务，必要时补查 business show；生产写操作仍需复述目标与参数并取得明确确认。
- 已确认且适用当前安装版本的语法可复用；不熟悉的命令、用法错误或说明不一致时再查对应 --help，安装或版本异常再查版本与路径。认证、业务及权限报错按对应项处理，不重新跑全套预检。

## 参数与输出

- 全局 `--config`、`--no-history` 放在子命令之前。不要把根 `--version` 与算法克隆必填的 `--version VERSION` 混淆。
- 参数表的 None 是未指定；命令行写 `None`、`null` 会成为普通字符串。必填参数不一定自动拒绝空字符串，是否去空白、拒绝空值由各命令业务校验决定。
- 类型、范围、默认值取自实际命令定义；参数帮助中的枚举还需结合组合规则。布尔开关不写 `--yes true`。可重复选项按多个 `--tag VALUE` 的形式传入。
- 仅支持输出开关的命令才能加 `-o json`。部分命令固定输出 JSON（如特征配置、Web Studio show），部分只输出表格或文本。
- JSON 顶层可能是对象或数组；result/data/items/count/total 不统一。需要先按命令文档判断结构，不能套用单一提取路径。
- 表格可能转换时间、字节、百分比或状态码；JSON 未必同步转换。Jupyter files 会转换 created/last_modified，其他多数业务命令 JSON 保留原始时间。解释已带时区时间时转换到 UTC+8，不仅替换 T；无时区的原值不擅自猜测其时区。
- 展示字段可能缺失、null 或有扩展；除明确验证的字段外，不宣称其为必填或固定类型。透传响应文档是已知结构，不能作为封闭 schema 校验未知字段。
- 空数组不表示账号没有其他资源，可能受分页、业务和过滤条件影响。固定第一页的命令不能附加不存在的翻页参数。
- ID 使用完整值，不能从截断表格拼回 ID。表格首列设计要求固定宽度 36、不截断；已有实现是否满足应以实际展示为准，发现偏差报告，不在测试 skill 中隐式修改 CLI。

## Shell 与非交互执行

- 以执行工具实际 shell 为准。示例的 ID 和路径均是需替换的占位值；带空格的路径或日期加引号。PowerShell、zsh 和 bash 的引号/转义不可混用。
- 无交互 stdin 时，business use 显式传 --tenant，service logs 加 --no-input，history 使用 list -o json；会询问确认的命令仅在已获具体授权后加 --yes。
- 不运行 jupyter terminal open/attach，不分配 TTY/PTY 绕过限制；使用 files、exec 或 notebook run。终端命令文档用于覆盖现有能力并说明人工使用边界。
- jupyter exec 的 `--` 后是程序与参数，不隐式展开 shell 管道、通配符或重定向。需要 shell 的任务须明确执行已授权的 shell 命令，不能误以为程序参数自动执行 shell 语法。
- 为长任务显式设置执行工具时限。Jupyter 至少考虑 startup-timeout + timeout，再加 60 秒用于传输和清理；大文件操作还需按实际文件大小预留时间。工具时限不等于 CLI 网络操作时限。
- 非交互环境自动保活不生效，auth ping start 不能替代重新登录；长任务前只查 auth status 核对有效期，不重查版本与业务列表。长时间中断后无法确认认证状态也只补查认证。

## 错误、部分成功和副作用

- 默认解析错误通常为退出 2，业务/运行时错误通常为 1，本地中断可为 130。exec 和 notebook 的状态及退出码另见命令页。
- 同时检查 stdout、stderr 和退出码。认证提示在部分较早命令中可能混入 stdout，不能在混合文本中硬取第一个 JSON 片段；先解决认证，再重试只读查询。
- 有些命令先输出部分结果，再报错退出，例如资源/部署模板关联查询、服务 mock。记录可用结果与失败部分，不把整个输出认定为成功。
- 训练启动/克隆、模型部署、服务 mock、上传、文件写入、exec、Notebook 都可能有远端副作用；退出码或网络失败不能单独证明未生效。先只读核验再决定是否重试。
- 本地文件写入也有副作用：训练配置/日志/算法下载不覆盖同名文件；特征 CSV 导出自动编号；Jupyter download 只有明确 --overwrite 才覆盖。
- 配置/历史/短期会话缓存由 CLI 管理；即便是只读业务查询，也可能触发这些本地维护行为。“只读”描述业务意图，不保证进程完全不写磁盘。

## 凭据与测试边界

不运行 login --show-secrets。access status --diagnose 只用于故障诊断。模板参数、远端内容、日志、下载地址可能有秘密，不整段复制到共享报告。

本 skill 基于当前仓库实现与已有测试资料，未宣称真实平台/Jupyter 联调完成。超大输入、异常响应和写操作边界使用 mock 测试；需要真实环境时先确认目标与权限。测试 skill 的独立目录不是安全沙箱，执行命令仍可影响真实环境。
