# Go CLI 1.1.3 源码变更

相较 1.1.2，新增 `ml train logs download TASK_ID [JOB_ID]`。登录 WiseRec 或 MLOps 并选择业务后，可直接下载历史或执行实例的日志。历史普通日志支持限时只读等待。执行实例报告归档失败时，用户可确认并指定作业 ID 和 `--retry`，让服务端处理整个作业的重新下载。旧入口继续支持原有脚本。

Windows x64 交付格式为每用户 MSI 和便携 ZIP。命令、参数与退出状态见[使用手册](../guides/WiseRec%20CLI%20使用手册.md)。发布前应验证 Windows 安装与升级，并在实际管理台验证归档及签名文件下载。本说明记录源码变更。
