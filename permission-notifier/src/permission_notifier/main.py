"""Independent application entry; no imports or resources from the business CLI."""
import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import threading
import webbrowser
import uvicorn
from .lifecycle import Instance, private_directory, ensure_port_free, wait_ready
from .store import Store
from .worker import Worker
from .web import create_app


def main():
    parser = argparse.ArgumentParser(description='独立权限通知助手')
    parser.add_argument('--headless', action='store_true', help='不显示托盘（诊断/测试）')
    parser.add_argument('--autostart', action='store_true', help='登录启动，不自动打开浏览器')
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'PermissionNotifier')
    args = parser.parse_args()
    private_directory(args.data_dir)
    instance = Instance(args.data_dir)
    if not instance.acquire():
        instance.close()
        if not args.autostart:
            webbrowser.open('http://127.0.0.1:18765')
        return
    logs = args.data_dir / 'logs'
    logs.mkdir(exist_ok=True)
    handler = RotatingFileHandler(logs / 'assistant.log', maxBytes=5_000_000, backupCount=4, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, handlers=[handler], format='%(asctime)s %(levelname)s %(message)s')
    # HTTP client INFO logs can contain user-configured URLs; retain only our
    # bounded error codes, never raw message endpoints or response bodies.
    logging.getLogger('httpx').setLevel(logging.CRITICAL)
    logging.getLogger('httpcore').setLevel(logging.CRITICAL)
    server = None
    worker = None
    try:
        ensure_port_free(18765)
        store = Store(args.data_dir / 'assistant.json')
        worker = Worker(store)
        stop_lock = threading.Lock()

        def stop():
            if not stop_lock.acquire(blocking=False):
                return
            worker.shutdown()
            if worker.thread and worker.thread is not threading.current_thread():
                worker.thread.join(timeout=90)
            server.should_exit = True

        app = create_app(store, worker, shutdown=stop)
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=18765,
            access_log=False, log_level='warning', timeout_graceful_shutdown=5))
        web_thread = threading.Thread(target=server.run, name='local-web', daemon=True)
        web_thread.start()
        if not wait_ready(server):
            raise RuntimeError('本地网页启动失败，请检查端口占用')
        worker.start()
        if not args.autostart and not args.headless:
            webbrowser.open('http://127.0.0.1:18765')
        if os.name == 'nt' and not args.headless:
            from .tray import run_tray
            run_tray(store, worker, stop, logs)
            stop()
        else:
            signal.signal(signal.SIGINT, lambda *_: threading.Thread(target=stop, daemon=True).start())
            signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=stop, daemon=True).start())
        web_thread.join()
        if worker.thread:
            worker.thread.join(timeout=90)
    except Exception as exc:
        logging.error('启动或运行失败：%s', type(exc).__name__)
        if os.name == 'nt' and not args.headless:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, '助手启动失败，请检查端口 18765 和日志目录。', '权限通知助手', 16)
        raise SystemExit(1) from None
    finally:
        if worker:
            worker.shutdown()
        if server:
            server.should_exit = True
        instance.close()


if __name__ == '__main__':
    main()
