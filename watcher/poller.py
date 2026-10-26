"""轮询单台主机的 audit_events。"""

import json

from .ssh_client import SshError, SshSession


class Poller:
    def __init__(self, host):
        self.host = host
        self.session = SshSession(
            host=host["host"],
            port=host["port"],
            user=host["user"],
            key_path=host["key_path"],
            bind_address=host.get("bind_address", ""),
            connect_timeout=host.get("connect_timeout", 10),
        )
        self.python = host.get("remote_python", "python3")
        self.script = host.get("remote_query_path", "~/.openclaw-watcher/query.py")

    def _cmd(self, extra):
        return f"{self.python} {self.script} {extra}"

    def _call(self, extra, retries=3):
        transport = self.session.connect(retries=retries)
        try:
            rc, out = self.session.run(transport, self._cmd(extra), timeout=30)
        finally:
            try:
                transport.close()
            except Exception:
                pass
        if rc != 0:
            raise SshError(f"远端查询失败 rc={rc}: {out.strip()[:300]}")
        try:
            return json.loads(out)
        except ValueError:
            raise SshError(f"远端返回非 JSON：{out.strip()[:300]}")

    def init_cursor(self):
        data = self._call("--init")
        return int(data.get("max_sequence", 0))

    def fetch(self, since_sequence):
        data = self._call(
            f"--since {int(since_sequence)} --limit {int(self.host.get('query_limit', 20))}"
        )
        if data.get("error"):
            raise SshError(data["error"])
        return data.get("events", [])
