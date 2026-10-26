"""系统托盘：状态、暂停/恢复、打开配置、查看日志、退出。"""

import logging
import subprocess
import sys
import threading

import pystray
from PIL import Image, ImageDraw

log = logging.getLogger("watcher")

PAUSE_OPTIONS = [("30 分钟", 0.5), ("1 小时", 1), ("2 小时", 2),
                 ("4 小时", 4), ("8 小时", 8)]


def make_icon_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((3, 3, 61, 61), fill=(15, 23, 42, 255))
    draw.ellipse((13, 13, 51, 51), outline=(56, 189, 248, 255), width=7)
    draw.ellipse((26, 26, 38, 38), fill=(56, 189, 248, 255))
    return img


class TrayController:
    def __init__(self, app):
        self.app = app
        self._thread = None
        self.icon = pystray.Icon(
            "OpenClawWatcher",
            make_icon_image(),
            "OpenClaw Watcher",
            menu=self._build_menu(),
        )

    def _build_menu(self):
        pause_items = [
            pystray.MenuItem(
                label,
                (lambda hours: lambda: self._safe(self.app.pause, hours))(hours),
            )
            for label, hours in PAUSE_OPTIONS
        ]
        return pystray.Menu(
            pystray.MenuItem(self.app.status_text(), None, enabled=False),
            pystray.MenuItem("暂停监控", pystray.Menu(*pause_items)),
            pystray.MenuItem("恢复监控", lambda: self._safe(self.app.resume)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("打开配置", lambda: self._safe(self.app.open_config)),
            pystray.MenuItem("查看日志", lambda: self._safe(self.app.open_logs)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda: self._safe(self.app.quit)),
        )

    def _safe(self, func, *args):
        try:
            func(*args)
        except Exception:
            log.exception("托盘操作失败: %s", getattr(func, "__name__", func))

    def start(self):
        self._thread = threading.Thread(target=self.icon.run, daemon=True,
                                        name="tray")
        self._thread.start()
        log.info("托盘图标已启动")

    def refresh(self):
        try:
            self.icon.title = self.app.status_text()
            self.icon.menu = self._build_menu()
            self.icon.update_menu()
        except Exception:
            log.exception("刷新托盘失败")

    def stop(self):
        try:
            self.icon.stop()
        except Exception:
            pass
