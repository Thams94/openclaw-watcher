"""OpenClaw Watcher 入口：多主机轮询 + 托盘 + 暂停。"""

import ctypes
import logging
import os
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

from .config import DATA_DIR, enabled_hosts, load_config
from .notifier import create_notifier
from .poller import Poller
from .state import State

log = logging.getLogger("watcher")


def setup_logging(level="INFO"):
    root = logging.getLogger()
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    os.makedirs(DATA_DIR, exist_ok=True)
    handler = RotatingFileHandler(
        os.path.join(DATA_DIR, "watcher.log"),
        maxBytes=1_000_000, backupCount=3, encoding="utf-8",
    )
    handler.setFormatter(fmt)
    root.addHandler(handler)
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)


def message_box(text, title="OpenClaw Watcher"):
    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)
    except Exception:
        pass


class App:
    def __init__(self, cfg, state, notifier):
        self.cfg = cfg
        self.state = state
        self.notifier = notifier
        self.hosts = enabled_hosts(cfg)
        self.stop = threading.Event()
        self.tray = None
        self._paused_flag = False

    # ---- 托盘回调 ----
    def status_text(self):
        if self.state.is_paused():
            until = time.strftime(
                "%H:%M", time.localtime(int(self.state.pause_until) / 1000))
            return f"已暂停 · 恢复于 {until}"
        return f"监控中 · {len(self.hosts)} 台主机"

    def pause(self, hours):
        until = self.state.pause(hours)
        self._paused_flag = True
        log.info("暂停监控 %.1f 小时，至 %s", hours,
                 time.strftime("%Y-%m-%d %H:%M", time.localtime(until / 1000)))
        if self.tray:
            self.tray.refresh()

    def resume(self):
        self.state.resume()
        self._paused_flag = False
        log.info("已恢复监控")
        if self.tray:
            self.tray.refresh()

    def open_config(self):
        import subprocess
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--setup"]
        else:
            from .config import APP_DIR
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            cmd = [pythonw, os.path.join(APP_DIR, "run.py"), "--setup"]
        subprocess.Popen(cmd, close_fds=True)

    def open_logs(self):
        import subprocess
        path = os.path.join(DATA_DIR, "watcher.log")
        try:
            subprocess.Popen(["notepad.exe", path])
        except Exception:
            pass

    def quit(self):
        log.info("托盘请求退出")
        self.stop.set()
        try:
            self.notifier.request_stop()
        except Exception:
            pass
        if self.tray:
            self.tray.stop()

    def start_tray(self):
        try:
            from .tray import TrayController
            self.tray = TrayController(self)
            self.tray.start()
        except Exception:
            log.exception("托盘启动失败（不影响监控）")


def _host_loop(app, host):
    name = host.get("name") or host.get("host")
    interval = int(host.get("poll_interval_seconds", 30))
    poller = Poller(host)
    cursors_ready = False

    while not app.stop.is_set():
        try:
            host_id = host["id"]
            if not cursors_ready:
                if app.state.cursor(host_id) is None:
                    seq = poller.init_cursor()
                    app.state.set_cursor(host_id, seq)
                    log.info("[%s] 初始化游标，跳过历史事件：sequence=%s", name, seq)
                    app.stop.wait(interval)
                    continue
                cursors_ready = True

            since = app.state.cursor(host_id)
            events = poller.fetch(since)
            for event in events:
                app.state.set_cursor(host_id, event["sequence"])
                if app.state.is_paused():
                    log.info("[%s] 暂停中，跳过提醒 seq=%s", name, event["sequence"])
                    continue
                status = event.get("status")
                if status not in host.get("notify_statuses", []):
                    continue
                duration = event.get("duration_ms") or 0
                if duration and duration < int(host.get("ignore_fast_turns_ms", 0)):
                    continue
                event["host_name"] = name
                log.info("[%s] 任务结束 seq=%s status=%s agent=%s duration=%sms",
                         name, event["sequence"], status,
                         event.get("agent_id"), duration)
                app.notifier.show(event)
        except Exception as exc:
            log.warning("[%s] 轮询失败：%s", name, exc)
        app.stop.wait(interval)


def _status_loop(app):
    """暂停到期后刷新托盘状态。"""
    while not app.stop.is_set():
        app.stop.wait(30)
        if app.tray:
            app.tray.refresh()


def main():
    cfg = load_config()
    setup_logging(cfg.get("log_level", "INFO"))

    hosts = enabled_hosts(cfg)
    if not hosts:
        log.error("没有启用中的主机，请先运行配置向导")
        message_box("OpenClaw Watcher 还没有配置主机。\n请双击 setup.cmd 添加。")
        return

    log.info("启动 OpenClaw Watcher：%d 台主机，通知后端 %s，托盘 %s",
             len(hosts), cfg.get("notifier"), cfg.get("tray", True))

    state = State()
    notifier = create_notifier(cfg)
    app = App(cfg, state, notifier)

    for host in hosts:
        threading.Thread(target=_host_loop, args=(app, host),
                         daemon=True, name=f"poll-{host['id']}").start()

    if cfg.get("tray", True):
        app.start_tray()
        threading.Thread(target=_status_loop, args=(app,), daemon=True,
                         name="status").start()

    try:
        notifier.start()
    finally:
        app.stop.set()
        notifier.stop()
        log.info("程序退出")


if __name__ == "__main__":
    main()
