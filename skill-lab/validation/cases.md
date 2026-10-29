# 详细 skill 验收与隔离测试

## 使用方式

只在独立测试配置中加载 `skill-lab/wiserec-platform-detailed`，不要覆盖正式 `wiserec-platform` 或正式 `/ml` command。加载目录应包含 SKILL.md 与整个 references 子树。不要把源码证据路径当作运行时依赖。

本目录的 coverage.json 记录命令元数据和源码摘要；verify.py 只读取命令定义，不执行平台命令。命令变更后先人工复核语义，再更新文档和记录，不能只更新 hash 消除失败。

## 静态验收

在仓库根目录使用安装项目依赖的 Python：

```text
.venv/bin/python skill-lab/validation/verify.py
.venv/bin/python skill-lab/validation/verify_package.py
```

第一项核对所有叶子、命令组、参数和引用的覆盖，并检查证据文件是否漂移；第二项在临时副本构建 Wheel/sdist，再核对安装资源，不改正式构建配置或安装位置。Windows ZIP 的构建链路需结合 scripts/windows/build-release.ps1 和 test_windows_packaging.py；本机不宣称完成 Windows 联网/离线安装实测。

## 行为场景

下表是输入与预期判断，用于人工或独立模型评估。仅阅读文档答题不运行真实写操作；模拟调用时使用现有 mock 客户端。尚未进行独立模型对照评估，不将此清单视为已通过记录。

| 用户场景 | 预期行为 / 失败判据 |
| --- | --- |
| 查询数据集，page-size=0 或 1 | 0 被解析拒绝；1 合法，不编造最大 100 |
| 上传恰好 2,000,000,000 字节，或多 1 字节 | 前者通过本地大小边界，后者拒绝；不保证前者一定被服务器接受；用 mock stat，不创建大文件 |
| 数据集筛选纯空白，bucket-name 未提供/空字符串 | 前者拒绝；后两者明确区分 |
| 要求训练执行记录第 2 页 | 指出命令固定第 1 页 10 条，不能构造 --page 2 |
| 样本任务 source=new 并传 status=started | 指出组合非法；new 不支持 status |
| 周期开始结束相等，或开始晚于结束 | 相等允许；倒置拒绝；服务端是否包含端点不猜测 |
| 特征日志 start=10/end=9 或 scope=D | 拒绝；合法 scope 为 A/B/C |
| 模型部署 health-port=65535/65536 | 前者在 CLI 范围，后者拒绝；预览和正式响应结构分开 |
| 部署模板关联资源重名，stdout 有 JSON 但退出 1 | 部分结果，提示歧义，不默认选第一个 |
| 服务 mock 一个节点 retCode 非零 | 即使有节点结果仍整体失败，保留各节点诊断 |
| 服务日志 --list 同时显式 --lines 200 | 即使等于默认值也非法；Agent 使用 --no-input |
| 服务部署列表没有 total | 说明未知总数，不补成 0 |
| 特征配置返回 JSON 数组或 NaN | 拒绝；必须合法 JSON 对象 |
| Jupyter write 同时 from-file 与 stdin | 拒绝；必须且只能选择一个来源 |
| Jupyter read start=2/end=2 | 仅第二行；底层下载完整文件 |
| Jupyter 路径 ../x 或 /x | 拒绝；不得套用数据集以 / 开头的目录规则 |
| exec 超时或 LOST | 分别识别 124/2；先查远端状态，不直接重跑 |
| exec 输出 truncated=true 但 status=SUCCEEDED | 命令成功而捕获输出不完整，不宣称拿到全部输出 |
| Notebook 失败但存在 executed.ipynb | 保存部分结果不等于运行成功；检查 status、退出码、cleanup_errors |
| auth status 退出 0 但 expired | 要求登录，不继续业务操作 |
| 要求关闭终端 | 区分 terminal name 与 studio/kernel ID，核对影响，不运行 attach 绕路 |
| history clear --before 截止时刻 | 相等记录保留，只删除严格早于截止时刻的记录 |
| 打包前存在测试 skill | Wheel/sdist 及正式资源 manifest 不得包含测试目录或标识 |

## 新旧 skill 对照

同一组问题分别在只加载旧 skill 和只加载新 skill 的新会话中评估。记录：命令选择正确率、参数/组合错误、响应提取路径错误、未知约束是否被虚构、失联后是否重放，以及读取了哪些参考文件。不以篇幅更长作为改进证据。

## 后续补证

真实接口契约和脱敏响应仅补充到对应命令页，注明环境和观察范围。一次实测不能证明全部可空性、枚举或最大值；不要用示例反推完整封闭响应 schema。发布正式 skill 前再决定迁移，不自动纳入当前 CLI 包。

## 本次本地验证记录

- 日期：2026-10-29（北京时间）
- verify.py：96 个叶子命令、52 个含根入口的组记录通过覆盖、参数、示例选项、源码摘要、链接和可达性检查
- verify_package.py：临时副本实际构建 Wheel/sdist，均不包含测试 skill；正式 OpenCode 资源清单和文件摘要通过核验
- skill-creator quick_validate.py：通过
- 46 份构造的 JSON 响应示例全部可解析；Markdown 无尾随空白或不稳定对象地址
- 现有 test_skill_resources.py、test_windows_packaging.py、test_package_build.py、test_opencode_install.py：20 passed
- 未执行真实业务/Jupyter 联调、独立模型新旧对照或 Windows 安装；不可将上述本地检查视为这些验证已完成
