# WiseRec Go CLI 1.1.1 构建说明

- 普通交互终端继续使用后台 worker。DeepSeek Harness 自动保活由单独安装的宿主插件调度，关闭或卸载插件后仍可正常登录和执行业务命令。
- Go CLI 输出仍为 `ml 1.1.1`。插件通过 `ml auth ping tick --capabilities` 检查 `dsh-keepalive-v1`，可以识别缺少接口的同版本旧构建。
- Go CLI 继续提供 Windows x64 MSI 和便携 ZIP。DSH 插件提供可直接在 Desktop 安装的 `.tgz`，构建入口见 [插件说明](../dsh-plugin/wiserec-cli/README.md)，用户命令见 [使用手册](WiseRec%20CLI%20使用手册.md)。
- Windows Desktop 离线加载及真实平台长时保活以实机验收为准。本文记录源码构建能力，不表示已完成正式发布。
