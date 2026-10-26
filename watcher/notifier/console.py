"""控制台通知（调试用）。"""

import logging

from .base import Notifier


class ConsoleNotifier(Notifier):
    name = "console"

    def start(self):
        logging.getLogger("watcher").info("通知后端：console（调试）")

    def show(self, event):
        logging.getLogger("watcher").info(
            "任务结束 event: %s", event,
        )

    def stop(self):
        pass
