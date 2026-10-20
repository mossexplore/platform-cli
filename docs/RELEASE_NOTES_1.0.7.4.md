# 1.0.7.4 CLI 开发说明（尚未发布）

新增 `ml feature-task execution list TASK_ID`，支持分页和包含历史执行实例。表格转换北京时间、文件大小、分钟时长和最新实例标志，JSON 保留原始记录。

新增 `ml feature-task execution logs search JOB_ID`，支持行范围、重复关键词、A/B/C 搜索范围和范围行数。默认仅发送 jobId、当前业务 ID 和行范围，可选条件未指定时省略。默认原样输出 `result.logs[0].log`，保留空格、制表符和换行，不添加终端排版或额外换行；`-o json` 保留完整响应。

CLI 版本递增；权限服务与数据库结构未修改。使用前需选择环境、登录并选择业务。验证采用模拟 HTTP、CLI 自动化和 Wheel 检查，不代表真实平台或 Windows 原生联调通过，未发布正式 Release。
