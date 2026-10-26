"""Windows 桌面弹窗通知：屏幕右下角卡片 + 提示音。"""

import datetime
import queue
import tkinter as tk

from .base import Notifier

try:
    import winsound
except ImportError:  # 非 Windows 平台（仅调试用）
    winsound = None

STATUS_STYLE = {
    "succeeded": ("#22c55e", "✅", "任务完成"),
    "failed": ("#ef4444", "❌", "任务失败"),
    "timed_out": ("#f59e0b", "⏱", "任务超时"),
    "cancelled": ("#94a3b8", "⛔", "任务取消"),
}

WIDTH = 420
HEIGHT = 200
MARGIN = 20
GAP = 12


def _fmt_time(ms):
    try:
        return datetime.datetime.fromtimestamp(ms / 1000).strftime("%H:%M:%S")
    except (ValueError, OSError, TypeError):
        return "--:--:--"


def _fmt_duration(ms):
    if not ms or ms <= 0:
        return ""
    seconds = ms / 1000
    if seconds < 60:
        return f"耗时 {seconds:.0f} 秒"
    minutes = seconds / 60
    if minutes < 60:
        return f"耗时 {minutes:.1f} 分钟"
    return f"耗时 {minutes / 60:.1f} 小时"


class PopupNotifier(Notifier):
    name = "popup"

    def __init__(self, timeout_seconds=25, sound=True):
        self.timeout_seconds = timeout_seconds
        self.sound = sound
        self._queue = queue.Queue()
        self._windows = []
        self._root = None

    # ---- 生命周期（主线程） ----
    def start(self):
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.after(150, self._drain)
        self._root.mainloop()

    def stop(self):
        if self._root is not None:
            try:
                self._root.after(0, self._root.quit)
            except Exception:
                pass

    def request_stop(self):
        """可从任意线程调用，安全退出 mainloop。"""
        self._queue.put(None)

    def show(self, event):
        """可从任意线程调用。"""
        self._queue.put(event)

    # ---- 内部 ----
    def _drain(self):
        while True:
            try:
                event = self._queue.get_nowait()
            except queue.Empty:
                break
            if event is None:
                try:
                    self._root.quit()
                except Exception:
                    pass
                return
            self._spawn(event)
        self._root.after(150, self._drain)

    def _spawn(self, event):
        color, icon, label = STATUS_STYLE.get(
            event.get("status", ""), ("#64748b", "•", "任务结束")
        )
        win = tk.Toplevel(self._root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg="#0f172a")
        win.geometry(f"{WIDTH}x{HEIGHT}")
        self._windows.append(win)
        self._layout()

        accent = tk.Frame(win, bg=color, height=4)
        accent.pack(side="top", fill="x")

        header = tk.Frame(win, bg="#0f172a")
        header.pack(side="top", fill="x", padx=16, pady=(10, 0))

        tk.Label(
            header, text=f"{icon} {label}", fg=color, bg="#0f172a",
            font=("Microsoft YaHei UI", 12, "bold"), anchor="w",
        ).pack(side="left")

        close = tk.Label(
            header, text="✕", fg="#64748b", bg="#0f172a",
            font=("Microsoft YaHei UI", 10), cursor="hand2",
        )
        close.pack(side="right")
        close.bind("<Button-1>", lambda _e: self._close(win))

        agent = event.get("agent_id") or "-"
        host = event.get("host_name") or ""
        parts = [p for p in (host, agent) if p]
        subtitle = f"{' · '.join(parts)} · {_fmt_time(event.get('occurred_at'))}"
        tk.Label(
            win, text=subtitle, fg="#94a3b8", bg="#0f172a",
            font=("Microsoft YaHei UI", 9), anchor="w",
        ).pack(side="top", fill="x", padx=16, pady=(2, 6))

        summary = (event.get("summary") or "").strip()
        summary = " ".join(summary.split())
        if not summary:
            summary = "（没有拿到结果摘要，可登录终端查看）"
        if len(summary) > 220:
            summary = summary[:220] + "…"

        tk.Label(
            win, text=summary, fg="#e2e8f0", bg="#0f172a",
            font=("Microsoft YaHei UI", 9), justify="left", anchor="nw",
            wraplength=WIDTH - 32,
        ).pack(side="top", fill="both", expand=True, padx=16)

        footer_parts = [_fmt_duration(event.get("duration_ms"))]
        footer_parts = [p for p in footer_parts if p]
        tk.Label(
            win, text="  ".join(footer_parts), fg="#64748b", bg="#0f172a",
            font=("Microsoft YaHei UI", 8), anchor="w",
        ).pack(side="bottom", fill="x", padx=16, pady=(0, 10))

        win.bind("<Button-1>", lambda _e: self._close(win))
        win.after(self.timeout_seconds * 1000, lambda: self._close(win))

        if self.sound and winsound is not None:
            try:
                winsound.PlaySound(
                    "SystemNotification",
                    winsound.SND_ALIAS | winsound.SND_ASYNC,
                )
            except Exception:
                try:
                    winsound.MessageBeep()
                except Exception:
                    pass

    def _layout(self):
        try:
            screen_w = self._root.winfo_screenwidth()
            screen_h = self._root.winfo_screenheight()
        except Exception:
            return
        for idx, win in enumerate(self._windows):
            x = screen_w - WIDTH - MARGIN
            y = screen_h - HEIGHT - 70 - idx * (HEIGHT + GAP)
            try:
                win.geometry(f"+{x}+{y}")
            except tk.TclError:
                pass

    def _close(self, win):
        if win in self._windows:
            self._windows.remove(win)
        try:
            win.destroy()
        except tk.TclError:
            pass
        self._layout()
