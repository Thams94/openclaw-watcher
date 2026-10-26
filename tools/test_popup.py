"""模拟弹窗测试：渲染两条示例事件，截图用。"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from watcher.notifier.popup import PopupNotifier  # noqa: E402

notifier = PopupNotifier(timeout_seconds=30, sound=False)


def feed():
    now = int(time.time() * 1000)
    notifier.show({
        "status": "succeeded",
        "agent_id": "main",
        "occurred_at": now,
        "duration_ms": 156662,
        "summary": "故障原因已确认：物理链路在反复中断，属于硬件和线缆层的问题，"
                   "与 SSH 或网络配置无关。内核日志里的 link 事件与报障时间精确吻合。",
    })
    time.sleep(0.8)
    notifier.show({
        "status": "failed",
        "agent_id": "code-writer",
        "occurred_at": now - 60000,
        "duration_ms": 12000,
        "summary": "示例失败事件：API 调用超时，任务未完成。",
    })
    time.sleep(10)
    notifier.stop()


threading.Thread(target=feed, daemon=True).start()
notifier.start()
