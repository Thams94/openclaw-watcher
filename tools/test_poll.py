"""手动测试轮询链路：拉取最近几条任务结束事件。"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from watcher.config import enabled_hosts, load_config  # noqa: E402
from watcher.poller import Poller  # noqa: E402


def main():
    cfg = load_config()
    hosts = enabled_hosts(cfg)
    if not hosts:
        print("没有启用的主机")
        return 1
    for host in hosts:
        print("=" * 60)
        print("主机:", host["name"], host["host"])
        poller = Poller(host)
        max_seq = poller.init_cursor()
        print("当前最大 sequence:", max_seq)
        events = poller.fetch(max_seq - 3)
        print(f"最近事件数: {len(events)}")
        for ev in events:
            print("-" * 50)
            print("seq:", ev["sequence"], "| status:", ev["status"],
                  "| agent:", ev.get("agent_id"),
                  "| duration_ms:", ev.get("duration_ms"))
            print("summary:", (ev.get("summary") or "")[:150].replace("\n", " "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
