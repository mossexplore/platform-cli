# 业务 Skill 安装

将业务 Skill 的 ZIP 文件直接放在 `skill-business/` 下。每个 ZIP 只包含一个与 ZIP 基础名一致的目录，目录顶层须有非空的 `SKILL.md`。例如，`example-skill.zip` 的结构如下。

```text
example-skill/
  SKILL.md
  references/
```

在 Windows 下双击 `script\install.cmd`。脚本使用系统自带的 Windows PowerShell，无需管理员权限。它会校验 `skill-business/` 下的所有 ZIP，再把每个 Skill 安装到当前用户的两个目录。

- `%USERPROFILE%\.agents\skills\<Skill 名称>\`
- `%USERPROFILE%\.cac\skills\<Skill 名称>\`

每次运行都会整目录替换同名 Skill。手工添加在同名 Skill 里的文件也会被替换，其他名称的 Skill 会保留。每个 Skill 的两份新副本会先准备完成，再替换原目录。ZIP 结构校验失败时会在写入前停止。单个 Skill 替换失败时，脚本会尝试恢复它的旧目录，报告具体错误，并继续安装其他已校验的 Skill。没有 ZIP 文件时会提示并退出。

## 打包平台 Skill

在项目源码中双击 `script\build.cmd`，使用 Python 3.11 或以上生成 `skill-business\wiserec-platform.zip`。ZIP 顶层只有 `wiserec-platform/`，包含 `SKILL.md` 和引用文档。新 ZIP 完整生成后替换旧的同名 ZIP。

打开终端也可以运行以下命令。只有目标 CLI 环境已启用共享 Wiki 时才加 `--include-kb`。

```powershell
python skill-business/script/build.py
python skill-business/script/build.py --include-kb
python skill-business/script/build.py --output-dir 'D:\skill-packages'
```

分发时，把生成的平台 ZIP 和业务 ZIP 放在同一目录，保留 `script\install.cmd` 和 `script\install.ps1` 的相对位置。目标电脑只需运行安装入口，打包所需的 Python 和项目源码留在打包电脑。
