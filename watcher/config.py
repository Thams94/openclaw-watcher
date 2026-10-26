"""配置加载（多主机版）。

config.json 结构：
{
  "hosts": [ {主机1}, {主机2} ],
  "notifier": "popup",
  "sound": true,
  "tray": true,
  ...
}
旧版单主机配置（顶层 host 字段）会自动迁移为 hosts 列表。
"""

import json
import os
import sys
import uuid

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if not getattr(
    sys, "frozen", False) else os.path.dirname(sys.executable)
DATA_DIR = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"), "OpenClawWatcher"
)

HOST_DEFAULTS = {
    "id": "",
    "name": "",
    "host": "",
    "port": 22,
    "user": "",
    "key_path": "~/.ssh/id_openclaw2",
    "bind_address": "",
    "connect_timeout": 10,
    "poll_interval_seconds": 30,
    "query_limit": 20,
    "remote_python": "python3",
    "remote_query_path": "~/.openclaw-watcher/query.py",
    "notify_statuses": ["succeeded", "failed", "timed_out"],
    "ignore_fast_turns_ms": 0,
    "enabled": True,
}

DEFAULTS = {
    "hosts": [],
    "notifier": "popup",
    "sound": True,
    "popup_timeout_seconds": 25,
    "tray": True,
    "log_level": "INFO",
}

_LEGACY_KEYS = (
    "host", "port", "user", "key_path", "bind_address", "connect_timeout",
    "poll_interval_seconds", "query_limit", "remote_python",
    "remote_query_path", "notify_statuses", "ignore_fast_turns_ms",
)


class Config(dict):
    """支持 cfg.notifier 访问方式的字典。"""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(item) from None


def _expand(value):
    return os.path.expandvars(os.path.expanduser(value)) if isinstance(value, str) else value


def normalize_host(raw):
    host = dict(HOST_DEFAULTS)
    host.update({k: v for k, v in (raw or {}).items() if k in HOST_DEFAULTS})
    host["port"] = int(host["port"] or 22)
    host["key_path"] = _expand(host["key_path"])
    if not host["id"]:
        host["id"] = uuid.uuid4().hex[:8]
    if not host["name"]:
        host["name"] = host["host"] or "未命名主机"
    return host


def config_path():
    return os.path.join(APP_DIR, "config.json")


def load_config(path=None):
    path = path or config_path()
    data = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig") as f:
            data.update(json.load(f))

    if not data.get("hosts"):
        legacy = {k: data.get(k) for k in _LEGACY_KEYS if data.get(k)}
        if legacy.get("host"):
            data["hosts"] = [legacy]

    data["hosts"] = [normalize_host(h) for h in data.get("hosts") or []]
    return Config(data)


def save_config(cfg, path=None):
    path = path or config_path()
    cfg = dict(cfg)
    cfg["hosts"] = [normalize_host(h) for h in cfg.get("hosts") or []]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def enabled_hosts(cfg):
    return [h for h in cfg.get("hosts") or [] if h.get("enabled", True)]
