#!/usr/bin/env bash
# 包内安装，无 curl/apt/yum，也不从索引下载任何 Python 包。
set -euo pipefail
# 不继承 root 的严格 umask，避免服务账号无法执行 Python。
umask 022
[[ $(id -u) == 0 ]] || { echo '请使用 sudo bash install.sh'; exit 1; }
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || { echo '本离线包仅支持 Linux x86_64'; exit 1; }
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$source_dir"
[[ -f SHA256SUMS && -f python-runtime.tar.gz && -d wheelhouse ]] || { echo '请使用完整离线发布包，不能直接安装源码目录'; exit 1; }
sha256sum --check --quiet SHA256SUMS
libc_version=$(getconf GNU_LIBC_VERSION | awk '{print $2}')
[[ $(printf '%s\n' '2.28' "$libc_version" | sort -V | head -n 1) == 2.28 ]] || {
    echo "当前 glibc $libc_version，依赖包要求 glibc >= 2.28，请提供系统版本以构建兼容包"; exit 1;
}
install -d -m 755 /opt/cli-access
install -d -m 700 /etc/cli-access
if [[ ! -f /etc/cli-access/env ]]; then
    install -m 600 .env.example /etc/cli-access/env
    echo '已创建 /etc/cli-access/env。请填写 MySQL 连接与监听配置后重新执行安装。'
    exit 1
fi
# 从完整发布包安装到专用目录；保留管理员配置与数据库。
if [[ "$source_dir" == /opt/cli-access ]]; then
    echo '请在发布包解压目录运行安装，不要在 /opt/cli-access 中运行'; exit 1
fi
id cli-access >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin cli-access
chgrp cli-access /etc/cli-access
chmod 750 /etc/cli-access
if systemctl is-active --quiet cli-access; then systemctl stop cli-access; fi
cp -R app /opt/cli-access/
tar --no-same-owner --no-same-permissions -xzf python-runtime.tar.gz -C /opt/cli-access
/opt/cli-access/python/bin/python3 -m venv /opt/cli-access/.venv
PIP_CONFIG_FILE=/dev/null /opt/cli-access/.venv/bin/python -m pip install \
    --no-index --no-cache-dir --disable-pip-version-check --require-hashes \
    --find-links "$source_dir/wheelhouse" -r "$source_dir/requirements.lock"
# 同时修复旧安装遗留的 700/600 权限；不给服务账号写权限。
chgrp -R cli-access /opt/cli-access/python /opt/cli-access/.venv /opt/cli-access/app
chmod -R g+rX /opt/cli-access/python /opt/cli-access/.venv /opt/cli-access/app
cd /opt/cli-access
/opt/cli-access/.venv/bin/python -m pip check
/opt/cli-access/.venv/bin/python -m app.manage --env-file /etc/cli-access/env migrate
install -m 644 "$source_dir/cli-access.service" /etc/systemd/system/cli-access.service
systemctl daemon-reload
systemctl enable cli-access
systemctl restart cli-access
echo '离线安装完成。首次安装请创建管理员：'
echo 'cd /opt/cli-access && sudo .venv/bin/python -m app.manage --env-file /etc/cli-access/env create-admin'
echo '服务状态：systemctl status cli-access；日志：journalctl -u cli-access -n 100'
