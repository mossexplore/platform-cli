# CLI 快速使用指南

安装完成后，重新打开 CMD 或 PowerShell，按以下四步操作。

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

更多命令见 [CLI 参考使用指南](CLI参考使用指南.md)。
