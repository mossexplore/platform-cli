# Agent 数据库迁移

初始结构版本为 1，定义在 app/models.py；app/db.py 的 migrate 是显式初始化入口。执行 `python -m app.manage migrate --config config.local.json`。先创建独立 MySQL 库并备份已有数据，不在服务启动阶段建表。

只有 Agent 表完全不存在时才创建全部表并最后写入版本；存在不完整表或不同版本时拒绝自动操作。MySQL DDL 不保证事务回滚，初始化中断需管理员核查并恢复后重试。后续结构变更需增加顺序迁移、备份及回滚说明，不覆盖初始版本或修改版本号掩盖结构差异。
