# WiseRec 遥测网关

网关接收 WiseRec DSH 完整包的 OTLP HTTP/JSON Trace。它校验来源、限制请求大小和并发，过滤属性并二次脱敏，再用项目密钥写入 Langfuse v4。

## 下载与导入

在 [GitHub Actions 的 DSH Windows plugin 工作流](https://github.com/mossexplore/platform-cli/actions/workflows/dsh-plugin-windows.yml) 中打开 `main` 的成功构建，下载 `wiserec-telemetry-gateway-0.1.0-linux-amd64`。解压外层 ZIP，将其中的 `.tar.gz` 和 `SHA256SUMS` 复制到 Linux x86_64 主机的同一目录。

```sh
sha256sum -c SHA256SUMS && \
  docker load -i wiserec-telemetry-gateway-0.1.0-linux-amd64.tar.gz
```

校验通过后导入。导入完成后使用镜像标签 `wiserec-telemetry-gateway:0.1.0`。构建产物保留 30 天。

## 构建与部署

也可从仓库根目录构建 Linux amd64 镜像。

```sh
docker build --platform linux/amd64 -t wiserec-telemetry-gateway:0.1.0 telemetry-gateway
```

以 [gateway.env.example](gateway.env.example) 创建服务器上的 `gateway.env`，设置 Langfuse v4 的地址和项目密钥。内部 Docker 地址示例为 `http://langfuse-web:3000`。将 `WISEREC_LANGFUSE_NETWORK` 设置为 Langfuse 容器使用的 Docker 网络名。

```sh
docker run -d --name wiserec-telemetry-gateway \
  --restart unless-stopped --network "$WISEREC_LANGFUSE_NETWORK" \
  --env-file /opt/wiserec-telemetry-gateway/gateway.env \
  -p 127.0.0.1:8088:8088 --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 \
  wiserec-telemetry-gateway:0.1.0
```

使用企业内网 HTTPS 入口转发 `/v1/traces`。将 `GATEWAY_ALLOWED_CIDRS` 配置为网关直接看到的客户端或反向代理网段。限流按直接连接的 IP 计数。使用反向代理时，在代理层同步限制客户端来源和请求速率。配置 `GATEWAY_INGEST_TOKEN` 时，完整包构建使用同一个写入 Token。Langfuse 密钥只配置在服务器。

## 验收

- `GET /health` 检查网关进程。其他读取或管理路径返回 `404`。
- 从完整包触发一轮带唯一会话标记的测试，确认 Langfuse Observations 中可以查询根 Span 和相关子 Span。网关访问日志包含状态、Span 数量和上游拒绝数量。
- 测试网关不可达后，确认 DSH 对话和保活继续工作。部署前检查采集范围与 Langfuse 数据访问和留存设置。

DSH Bundle 的网关配置和双版本使用见 [插件说明](../dsh-plugin/wiserec-cli/README.md)。
