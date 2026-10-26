"""一次性部署：把远端查询脚本上传到 Linux 主机（取配置中第一台启用主机）。

用法（在 openclaw-watcher 目录下）：
    python tools/setup_remote.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paramiko  # noqa: E402

from watcher.config import enabled_hosts, load_config  # noqa: E402
from watcher.ssh_client import SshSession  # noqa: E402

REMOTE_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "watcher", "remote_query.py")


def main():
    cfg = load_config()
    hosts = enabled_hosts(cfg)
    if not hosts:
        print("没有启用的主机")
        return 1
    host = hosts[0]
    session = SshSession(
        host=host["host"], port=host["port"], user=host["user"],
        key_path=host["key_path"], bind_address=host.get("bind_address", ""),
        connect_timeout=host.get("connect_timeout", 10),
    )
    transport = session.connect()
    try:
        sftp = paramiko.SFTPClient.from_transport(transport)
        rc, out = session.run(
            transport, "mkdir -p ~/.openclaw-watcher && echo $HOME")
        home = out.strip().splitlines()[-1] if out.strip() else ""
        if rc != 0 or not home.startswith("/"):
            raise RuntimeError(f"无法确定远端 HOME：rc={rc} out={out!r}")
        remote_path = f"{home}/.openclaw-watcher/query.py"
        sftp.put(REMOTE_SCRIPT, remote_path)
        sftp.close()
        session.run(transport, f"chmod 755 {remote_path}")

        rc, out = session.run(
            transport, f"{host.get('remote_python', 'python3')} {remote_path} --init",
            timeout=30)
        print("远端脚本部署完成：", remote_path)
        print("初始化输出：", out.strip())
    finally:
        transport.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
