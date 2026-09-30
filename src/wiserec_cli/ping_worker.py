"""自动保活子进程入口。"""

from pathlib import Path
import sys

from .ping import run_worker


if __name__ == "__main__":
    if len(sys.argv) != 6:
        raise SystemExit(2)
    run_worker(*(Path(value) if index != 1 else value
                 for index, value in enumerate(sys.argv[1:])))
