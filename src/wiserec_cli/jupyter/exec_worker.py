"""在专用远端 Python Kernel 中执行的标准库助手。"""
import os
import signal
import subprocess
import threading


def run_process(argv, timeout, max_output):
    if os.name != 'posix':
        return {'status': 'FAILED', 'exit_code': None, 'error': 'exec 当前要求远端 POSIX 系统',
                'stdout': '', 'stderr': '', 'truncated': False}
    buffers = [bytearray(), bytearray()]
    truncated = [False, False]

    def drain(pipe, index):
        with pipe:
            while True:
                chunk = pipe.read(8192)
                if not chunk:
                    break
                remaining = max_output - len(buffers[index])
                buffers[index].extend(chunk[:max(remaining, 0)])
                if len(chunk) > remaining:
                    truncated[index] = True

    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
    except OSError as exc:
        return {'status': 'FAILED', 'exit_code': None, 'error': str(exc),
                'stdout': '', 'stderr': '', 'truncated': False}
    readers = [threading.Thread(target=drain, args=(pipe, i), daemon=True)
               for i, pipe in enumerate((process.stdout, process.stderr))]
    for thread in readers:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        # 清理同组子进程，防止后台子进程持有管道使收集永久阻塞。
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    for thread in readers:
        thread.join(timeout=2)
    incomplete = any(thread.is_alive() for thread in readers)
    return {'status': 'TIMED_OUT' if timed_out else ('SUCCEEDED' if process.returncode == 0 else 'FAILED'),
            'exit_code': process.returncode, 'stdout': buffers[0].decode('utf-8', errors='replace'),
            'stderr': buffers[1].decode('utf-8', errors='replace'),
            'truncated': any(truncated), 'output_incomplete': incomplete,
            'termination': 'process_group_killed' if timed_out else 'completed'}
