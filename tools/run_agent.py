"""通过 SSH 触发一次真实的 OpenClaw agent 运行（端到端测试用）。

用法：python tools/run_agent.py [agent] [message] [host_index]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from watcher.config import enabled_hosts, load_config  # noqa: E402
from watcher.ssh_client import SshSession  # noqa: E402


def main():
    cfg = load_config()
    hosts = enabled_hosts(cfg)
    if not hosts:
        print("没有启用的主机")
        return 1
    index = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    host = hosts[index]
    agent = sys.argv[1] if len(sys.argv) > 1 else "code-writer"
    message = sys.argv[2] if len(sys.argv) > 2 else "仅回复一句话：watcher 端到端测试通过"
    session = SshSession(
        host=host["host"], port=host["port"], user=host["user"],
        key_path=host["key_path"], bind_address=host.get("bind_address", ""),
        connect_timeout=host.get("connect_timeout", 10),
    )
    transport = session.connect()
    try:
        # 兼容两种安装方式：系统 PATH 里的 openclaw，或 ~/.openclaw/bin/openclaw
        cmd = (f'OC=$(command -v openclaw || echo "$HOME/.openclaw/bin/openclaw"); '
               f'"$OC" agent --agent {agent} -m \'{message}\'')
        rc, out = session.run(transport, cmd, timeout=180)
        print("rc =", rc)
        print(out[:2000])
    finally:
        transport.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
