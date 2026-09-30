"""自动保活子进程入口。"""

import os
from pathlib import Path
import sys

from .ping import PingStore, run_worker


if __name__ == "__main__":
    if len(sys.argv) != 6:
        raise SystemExit(2)
    try:
        run_worker(*(Path(value) if index != 1 else value
                     for index, value in enumerate(sys.argv[1:])))
    except Exception as exc:
        state = PingStore(Path(sys.argv[5]))
        with state.locked():
            data = state.read()
            entry = data["profiles"].get(sys.argv[2], {})
            if entry.get("worker_pid") == os.getpid():
                entry.update(status="failed", worker_pid=None,
                             worker_identity=None,
                             last_error=f"{type(exc).__name__}: {exc}")
                state.write(data)
        raise
