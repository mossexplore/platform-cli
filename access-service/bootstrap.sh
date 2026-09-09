#!/usr/bin/env bash
# Shared preparation for portable start and administrator commands.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
export PIP_CONFIG_FILE=/dev/null
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || { echo '此离线包仅支持 Linux x86_64。'; exit 1; }
for tool in sha256sum getconf sort tar awk; do
    command -v "$tool" >/dev/null || { echo "缺少系统工具：$tool"; exit 1; }
done
[[ -f SHA256SUMS && -f python-runtime.tar.gz && -d wheelhouse ]] || { echo '请使用完整离线包，不能直接运行源码目录。'; exit 1; }
libc_version=$(getconf GNU_LIBC_VERSION | awk '{print $2}')
[[ $(printf '%s\n' '2.28' "$libc_version" | sort -V | head -n 1) == 2.28 ]] || {
    echo "当前 glibc $libc_version；此包要求 glibc >= 2.28。"; exit 1;
}
sha256sum --check --quiet SHA256SUMS
# Path is part of the marker: a moved installation must refresh venv paths.
package_stamp="$(pwd -P):$(sha256sum SHA256SUMS | awk '{print $1}')"
previous_stamp=$(cat .portable-ready 2>/dev/null || true)
if [[ "$package_stamp" != "$previous_stamp" || ! -x .venv/bin/python ]]; then
    echo '正在准备内置 Python 和离线依赖（不访问网络）…'
    tar --no-same-owner --no-same-permissions -xzf python-runtime.tar.gz
    ./python/bin/python3 -m venv .venv
    .venv/bin/python -m pip install --no-index --no-cache-dir --disable-pip-version-check \
        --require-hashes --find-links ./wheelhouse -r requirements.lock
    .venv/bin/python -m pip check
    printf '%s\n' "$package_stamp" > .portable-ready
fi
if [[ ! -f .env ]]; then
    (umask 077; cp .env.example .env)
    echo '已创建当前目录 .env。请填写 DATABASE_URL（MySQL 连接信息），然后重新执行 bash start.sh。'
    exit 1
fi
