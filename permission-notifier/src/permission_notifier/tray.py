"""Windows tray is imported only on Windows; web/core tests remain portable."""
import os
import threading
import time
import webbrowser
from datetime import datetime, timezone
from .config import ready
from .store import effective


def run_tray(store, worker, stop, log_directory):
    import pystray
    from PIL import Image, ImageDraw

    def picture(color):
        image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((5, 5, 59, 59), radius=15, fill=color)
        draw.line((18, 32, 28, 43, 47, 22), fill='white', width=6)
        return image

    def toggle(icon, item):
        try:
            if store.snapshot()['state']['paused'] and not ready(effective(store.snapshot())):
                webbrowser.open('http://127.0.0.1:18765')
                return
            store.change(lambda d: d['state'].update(paused=not d['state']['paused']))
            worker.wake.set()
            icon.update_menu()
        except Exception:
            webbrowser.open('http://127.0.0.1:18765')

    icon = pystray.Icon('PermissionNotifier', picture('#c68b23'), '权限通知助手', menu=pystray.Menu(
        pystray.MenuItem('打开管理页面', lambda: webbrowser.open('http://127.0.0.1:18765'), default=True),
        pystray.MenuItem('查看当前状态', lambda: webbrowser.open('http://127.0.0.1:18765')),
        pystray.MenuItem(lambda item: '恢复通知' if store.snapshot()['state']['paused'] else '暂停通知', toggle),
        pystray.MenuItem('打开日志目录', lambda: os.startfile(str(log_directory))),
        pystray.MenuItem('退出助手', lambda: threading.Thread(target=stop, daemon=True).start())))

    def monitor():
        previous = None
        while not worker.stop.wait(2):
            data = store.snapshot()
            attention = any(i['state'] in ('failed', 'uncertain') for t in data['state']['tasks'].values()
                            for i in t['deliveries'].values())
            dead = not worker.thread or not worker.thread.is_alive() or time.time() - worker.last_loop > 120
            red = bool(store.fault or worker.error not in ('', 'UNCONFIGURED', 'SUCCESS_RULE_OR_CONFIG_REQUIRED') or attention or dead)
            paused = data['state']['paused']
            expires = worker.client_info.get('expires_at')
            expiring = bool(expires and (datetime.fromisoformat(expires.replace('Z', '+00:00')) -
                datetime.now(timezone.utc)).total_seconds() < 7 * 86400)
            waiting = paused or expiring or bool(data['state']['config_apply']['pending_fields']) or bool(worker.error)
            color = '#bd3542' if red else '#c68b23' if waiting else '#24845a'
            if color != previous:
                icon.icon = picture(color)
                icon.title = '权限通知助手 · ' + ('需要处理' if red else '凭据即将到期' if expiring else '已暂停' if paused else '等待配置' if waiting else '运行中')
                previous = color
            icon.update_menu()
        # Keep tray visible until shutdown has saved the in-flight outcome.
        if worker.thread:
            worker.thread.join(timeout=90)
        icon.stop()
    threading.Thread(target=monitor, daemon=True).start()
    icon.run()
