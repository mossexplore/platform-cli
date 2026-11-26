# 共享 Wiki 只读网关

先升级权限服务并在挂载的 service.env 中配置 KB_TICKET_AK 和 KB_TICKET_SK。SK 使用至少 32 字节随机密钥。部署网关时设置 KB_TICKET_KEYS 为 AK:SK；轮换时先加入新验签密钥，切换签发端，待旧票据过期及宽限结束后移除旧密钥。仅在企业内网部署，客户端必须验证签票服务与网关的 HTTPS 证书。

CLI 与两个 HTTPS 服务共用 access_control 的 CA 配置。使用 custom 时，ca_file 的 PEM 证书集合须同时覆盖两个服务的信任链。

用仅具 retrieve 能力且限定库范围的 WeKnora Key 填写 kb-gateway.env.example 的部署副本。正式库与灰度库 ID 分开列出，调试账号按环境:账号精确匹配。此机制用于非涉密资料的灰度调试，签票账号由客户端声明。调试通过后将库 ID 从灰度移至正式名单，使用更新后的 env 文件重建容器，保留日志卷和网络；回退时执行相反变更。

在本目录构建 `docker build --platform linux/amd64 -t wiserec-kb-gateway:0.1.1 .`。使用设计方案 §4.4 的 docker run 参数。宿主机日志目录授权 UID 65532 写入并限制读取权限。默认按连接对端 IP 限流并记录审计。需要按员工 IP 限流时，将确实覆写 X-Real-IP 的反代地址段加入 KB_GATEWAY_TRUSTED_PROXY_CIDRS，并在 KB_GATEWAY_ALLOWED_CIDRS 中允许该反代连接。无效票据和动作不匹配均写入拒绝审计，只有验签通过才记录票据身份。转发前设置员工 IP 限流；访问日志不记录原始查询串或票据头。运维安排每日压缩已结束日期的日志并删除超过 365 天的归档，数据库同口径清理。签票与数据面通过 ticket_id 关联。时钟以 NTP 同步。

验收时确认容器健康、审计文件可写、两个身份并发查灰度库的结果不同；检查草稿、中文检索、带斜线 slug、候选窗口已满及大页截断。先部署网关再分发 CLI。

## 管理员调试示例

假设正式库 ID 为 `kb_public`，待校对库 ID 为 `kb_preview`，调试账号为测试环境的 `alice`。先在 WeKnora 发布待测页面，让网关的 Scoped Key 可以读取两个库，再用以下配置重建网关容器。

```dotenv
WEKNORA_ALLOWED_KB_IDS=kb_public
WEKNORA_PREVIEW_KB_IDS=kb_preview
KB_PREVIEW_USERS=test:alice
```

在测试环境登录并选中业务后，管理员在终端或 DSH 中使用同一份 CLI 验证搜索结果与原文。

```shell
ml kb list
ml kb search "训练超时" --kb kb_preview
ml kb page show concept/rag --kb kb_preview
```

将最后一条命令的 slug 替换为搜索实际返回的值。用普通账号检查列表仅含正式库，指定灰度库 ID 应收到 `404 KB_NOT_FOUND`。验收通过后将 `kb_preview` 从灰度名单移到正式名单，使用更新后的配置重建网关，再用普通账号复查同一条搜索。整个过程中员工和管理员沿用原安装包。

## 原始文件列表和下载

先部署支持文件动作签票的权限服务，再部署网关和启用知识库的 Go CLI。分别用 `KB_FILE_LIST_GRANTS` 和 `KB_FILE_DOWNLOAD_GRANTS` 填写逗号分隔的 `环境:账号:知识库ID`，区分大小写。留空时关闭对应操作。库还须满足正式库或灰度库名单。权限服务复用客户端声明的账号签票，这条链路只适用于非涉密资料。WeKnora Key 须限制在指定库内，并在实际部署版本验证该 Key 能列出文档和下载原文件。

`KB_GATEWAY_MAX_FILE_BYTES` 默认为 64 MiB，上限 512 MiB。大文件场景还需核对网关、反代和 CLI 的超时。部署后用只获列表权限的账号验证无法下载，用获下载授权的账号验证文件内容完整，并用另一库的知识条目 ID 验证请求被拒绝。查询、拒绝和下载开始及结果均进入网关审计。
