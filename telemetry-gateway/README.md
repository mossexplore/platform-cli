# WiseRec 遥测网关

网关接收 WiseRec DSH 完整包的 OTLP HTTP/JSON Trace。它校验来源、限制请求大小和并发，过滤属性并二次脱敏，再用项目密钥写入 Langfuse v4。

## 下载与导入

在 [GitHub Actions 的 DSH Windows plugin 工作流](https://github.com/mossexplore/platform-cli/actions/workflows/dsh-plugin-windows.yml) 中打开 `main` 的成功构建，下载 `wiserec-telemetry-gateway-0.1.1-linux-amd64`。解压外层 ZIP，将其中的 `.tar.gz` 和 `SHA256SUMS` 复制到 Linux x86_64 主机的同一目录。

```sh
sha256sum -c SHA256SUMS && \
  docker load -i wiserec-telemetry-gateway-0.1.1-linux-amd64.tar.gz
```

校验通过后导入。导入完成后使用镜像标签 `wiserec-telemetry-gateway:0.1.1`。构建产物保留 30 天。

## 构建与部署

也可从仓库根目录构建 Linux amd64 镜像。

```sh
docker build --platform linux/amd64 -t wiserec-telemetry-gateway:0.1.1 telemetry-gateway
```

以 [gateway.env.example](gateway.env.example) 创建服务器上的 `gateway.env`，设置 Langfuse v4 的地址和项目密钥。内部 Docker 地址示例为 `http://langfuse-web:3000`。将 `WISEREC_LANGFUSE_NETWORK` 设置为 Langfuse 容器使用的 Docker 网络名。

```sh
docker run -d --name wiserec-telemetry-gateway \
  --restart unless-stopped --network "$WISEREC_LANGFUSE_NETWORK" \
  --env-file /opt/wiserec-telemetry-gateway/gateway.env \
  -p 127.0.0.1:8088:8088 --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 \
  wiserec-telemetry-gateway:0.1.1
```

使用企业内网 HTTPS 入口转发 `/v1/traces`。将 `GATEWAY_ALLOWED_CIDRS` 配置为网关直接看到的客户端或反向代理网段。限流按直接连接的 IP 计数。使用反向代理时，在代理层同步限制客户端来源和请求速率。配置 `GATEWAY_INGEST_TOKEN` 时，完整包构建使用同一个写入 Token。Langfuse 密钥只配置在服务器。

## 按环境控制写入

在 `gateway.env` 中分别设置两道筛选。下面的示例只转发 `sit` 和 `uat` 的 trace，其中只有 `sit` 可以保留脱敏正文。

```dotenv
GATEWAY_ALLOWED_ENVIRONMENTS=sit,uat
GATEWAY_ALLOW_CONTENT_FOR_ENVIRONMENTS=sit
```

| 配置 | 行为 |
| --- | --- |
| `GATEWAY_ALLOWED_ENVIRONMENTS` | 决定哪些 trace 转发给 Langfuse。逗号分隔环境名，忽略大小写。默认 `*`，也允许未标记环境的 trace。指定名单时，未标记环境或同一批次中环境标记不一致的 trace 会被过滤。`-` 禁止全部 trace。 |
| `GATEWAY_ALLOW_CONTENT_FOR_ENVIRONMENTS` | 决定已放行的 trace 能否保留问答和工具输入输出。支持逗号分隔名单。默认 `*`，允许环境已确认的 trace 保留脱敏正文。`-` 只转发元数据。 |

改动环境变量后重建容器。网关以 Span 的 `langfuse.environment` 为准，并按批次中的 Trace ID 分组。同一批次中被环境规则过滤的 Span 会计入 `partialSuccess.rejectedSpans` 和访问日志中的 `filtered_spans`。即使 HTTP 返回 200，也应检查响应正文。网关无法根据环境标签验证客户端身份。

## 将日志保存到宿主机

容器内的日志目录固定为 `/var/log/wiserec-telemetry-gateway`。未挂载时通过 `docker logs` 查看。要同步写入宿主机文件，先按容器非 root 用户的 UID/GID 创建宿主机目录。

```sh
sudo install -d -o 65532 -g 65532 -m 0750 /opt/wiserec-telemetry-gateway/logs
```

在上面的 `docker run` 中、镜像名之前追加挂载参数。

```sh
--mount type=bind,source=/opt/wiserec-telemetry-gateway/logs,target=/var/log/wiserec-telemetry-gateway
```

重建容器后，可用 `sudo tail -f /opt/wiserec-telemetry-gateway/logs/gateway.log` 查看日志，`docker logs` 也会继续输出。如果挂载目录存在但无法写入，网关会报告启动错误。宿主机日志文件以追加方式写入，由宿主机管理保留周期。若用 `logrotate`，配置 `copytruncate` 以继续写入原文件。Docker 的日志轮转参数只管理 `docker logs` 对应的日志。

## 验收

- `GET /health` 检查网关进程。其他读取或管理路径返回 `404`。
- 从完整包触发一轮带唯一会话标记的测试，确认 Langfuse Observations 中可以查询根 Span 和相关子 Span。网关访问日志包含状态、Span 数量和上游拒绝数量。
- 测试网关不可达后，确认 DSH 对话和保活继续工作。部署前检查采集范围与 Langfuse 数据访问和留存设置。

DSH Bundle 的网关配置和双版本使用见 [插件说明](../dsh-plugin/wiserec-cli/README.md)。
