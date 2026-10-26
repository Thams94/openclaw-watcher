"""本地状态持久化：每台主机的游标、暂停状态。"""

import json
import os
import time

from .config import DATA_DIR


class State:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.path = os.path.join(DATA_DIR, "state.json")
        self.data = {}
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}

    # ---- 游标 ----
    def cursor(self, host_id):
        return (self.data.get("cursors") or {}).get(host_id)

    def set_cursor(self, host_id, sequence):
        cursors = self.data.setdefault("cursors", {})
        cursors[host_id] = int(sequence)
        self.save()

    # ---- 暂停 ----
    @property
    def pause_until(self):
        return self.data.get("pause_until")

    def is_paused(self):
        until = self.pause_until
        return bool(until) and int(time.time() * 1000) < int(until)

    def pause(self, hours):
        until = int(time.time() * 1000) + int(hours * 3600 * 1000)
        self.data["pause_until"] = until
        self.save()
        return until

    def resume(self):
        self.data.pop("pause_until", None)
        self.save()

    # ---- 通用 ----
    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)
