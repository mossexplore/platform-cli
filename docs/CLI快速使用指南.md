# CLI 快速使用指南

安装完成后，重新打开 CMD 或 PowerShell，先按以下四步完成基础操作。需要使用 Jupyter 时，再执行第五步。

## 1. 查看版本

```powershell
ml --version
```

显示 `ml` 和当前安装的版本号，表示命令可以正常使用。

## 2. 选择环境

```powershell
ml env list
ml env use dev
```

先查看环境列表，再将 `dev` 换成列表中要使用的环境名称。

## 3. 登录并选择业务

```powershell
ml login
ml business use
```

在自动打开的 Edge 浏览器中完成登录，回到终端后，按提示输入序号选择部门、租户或团队。
查询训练任务前需要选好业务；切换环境后，请重新完成这一步。

## 4. 查看训练任务

```powershell
ml train list
```

显示当前环境、所选业务下的训练任务列表，包括任务 ID、任务名称和更新时间等。

## 5. 使用 Jupyter（可选）

管理员已为当前环境配置 Web Studio Jupyter 网关时，先查询并登录一个在线实例：

```powershell
ml webstudio list --status online
ml webstudio login <Web-Studio-ID>
ml jupyter doctor
```

将 `<Web-Studio-ID>` 换成列表第一列显示的完整 `envId`。登录成功后，可以执行 Notebook 或使用远程终端：

```powershell
ml jupyter notebook run .\analysis.ipynb --download .\results
ml jupyter terminal open
ml jupyter terminal list
ml jupyter terminal attach <终端名称>
ml jupyter terminal close <终端名称>
```

- `doctor` 只检查 Kernel 和 Terminal HTTP 接口，不创建资源。
- Notebook 在前台执行，结果写入 `--download` 下新建的 UUID 目录。
- Terminal 中按 `Ctrl+]` 仅断开本地连接；执行 `exit` 或 `terminal close` 才会关闭远程终端。
- `webstudio login` 以及 Web Studio 模式下的每条 Jupyter 命令都会重新查询实例地址。输出的完整访问地址可能包含 Token，不要转发到群聊、工单或公共日志。
- 临时操作其他实例可在 Jupyter 命令后增加 `--studio-id <Web-Studio-ID>`，不会修改默认实例。

完整参数见 [CLI 参考使用指南](CLI参考使用指南.md)；本地 Jupyter Server 的开发和联调方式见 [Jupyter 本地开发与 Web Studio 联调](Jupyter本地开发指南.md)。
