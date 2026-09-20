"""前台逐单元格执行；始终保留本地部分结果并清理专用 Kernel。"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import nbformat

from .connection import JupyterError, remote_path
from .protocol import KernelChannel, Outputs, execute_cell


def save_local(path, notebook):
    temporary = path.with_suffix(".ipynb.tmp")
    nbformat.write(notebook, temporary)
    temporary.replace(path)


def run_notebook(client, source: Path, download: Path, *, kernel=None, cwd="",
                 timeout=600, startup_timeout=60, emit=print):
    notebook = nbformat.read(source, as_version=4)
    nbformat.validate(notebook)
    for cell in notebook.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
    # 旧 Widget 状态与本次新 Kernel 不对应。
    notebook.metadata.pop("widgets", None)
    execution_id = str(uuid4())
    directory = download / execution_id
    directory.mkdir(parents=True, exist_ok=False)
    result = directory / (source.stem + ".executed.ipynb")
    root = remote_path(cwd)
    remote_dir = "/".join(p for p in [root, "ml-runs", execution_id] if p)
    remote_file = remote_dir + "/input.ipynb"
    summary = {"id": execution_id, "status": "STARTING", "remote_directory": remote_dir,
               "notebook": str(result.resolve()), "started_at": now(), "completed_cells": 0,
               "cleanup_errors": []}
    kernel_id = None
    socket = None
    error = None
    save_local(result, notebook)
    emit(f"执行 ID：{execution_id}\n本地结果：{result.resolve()}\n")
    try:
        client.ensure_directory(remote_dir)
        client.save_notebook(remote_file, notebook)
        created = client.request("POST", "api/kernels", {
            "name": kernel or client.connection.kernel, "path": root or remote_dir})
        kernel_id = created["id"]
        summary["kernel_id"] = kernel_id
        socket = client.socket(f"api/kernels/{kernel_id}/channels")
        channel = KernelChannel(socket)
        channel.ready(startup_timeout)
        summary["status"] = "RUNNING"
        deadline = time.monotonic() + timeout
        outputs = Outputs(emit)
        cells = [cell for cell in notebook.cells if cell.cell_type == "code" and cell.source.strip()]
        for index, cell in enumerate(cells, 1):
            emit(f"\n正在执行代码单元格 {index}/{len(cells)}\n")
            execute_cell(channel, cell, outputs, deadline)
            summary["completed_cells"] = index
            save_local(result, notebook)
        summary["status"] = "SUCCEEDED"
    except KeyboardInterrupt:
        error = "用户中断；已停止提交后续单元格"
        summary["status"] = "INTERRUPTED"
    except TimeoutError:
        error = "Notebook 执行或 Kernel 启动超时"
        summary["status"] = "TIMED_OUT"
    except Exception as exc:
        error = str(exc) if isinstance(exc, JupyterError) else "执行发生异常：" + type(exc).__name__
        summary["status"] = "LOST" if "待确认" in error else "FAILED"
    finally:
        summary["finished_at"] = now()
        if error:
            summary["error"] = error
        # 本地结果优先落盘；远程断线不能阻止已收集输出的保存。
        try:
            save_local(result, notebook)
        finally:
            if socket is not None:
                try:
                    socket.close()
                except Exception:
                    pass
            if kernel_id:
                if error:
                    try:
                        client.request("POST", f"api/kernels/{kernel_id}/interrupt")
                    except Exception:
                        summary["cleanup_errors"].append("中断 Kernel 失败")
                try:
                    client.request("DELETE", f"api/kernels/{kernel_id}")
                except Exception:
                    summary["cleanup_errors"].append("释放 Kernel 失败，请按 kernel_id 检查远程资源")
        try:
            client.save_notebook(remote_dir + "/executed.ipynb", notebook)
        except Exception:
            summary["cleanup_errors"].append("远程结果保存失败，本地结果已保留")
        (directory / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def now():
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
