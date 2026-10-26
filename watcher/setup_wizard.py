"""配置向导（多主机版）：管理多台 Linux 主机、部署密钥与查询脚本。

用法：
    python run.py --setup                图形向导
    python run.py --setup-cli --host ... 命令行（单台）
"""

import os
import socket
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import paramiko

from .config import (APP_DIR, HOST_DEFAULTS, load_config, normalize_host,
                     save_config as persist_config)
from .ssh_client import SshError, _load_key

STATUS_LABELS = [
    ("succeeded", "成功"),
    ("failed", "失败"),
    ("timed_out", "超时"),
    ("cancelled", "取消"),
]


def resource_path(*parts):
    base = getattr(sys, "_MEIPASS", APP_DIR)
    return os.path.join(base, *parts)


def _run(transport, cmd, timeout=30):
    chan = transport.open_session()
    chan.settimeout(timeout)
    chan.set_combine_stderr(True)
    chan.exec_command(cmd)
    out = b""
    while True:
        chunk = chan.recv(65536)
        if not chunk:
            break
        out += chunk
    rc = chan.recv_exit_status()
    chan.close()
    return rc, out.decode("utf-8", "replace")


def ensure_key(key_path):
    key_path = os.path.expanduser(key_path)
    if not os.path.exists(key_path) or not os.path.exists(key_path + ".pub"):
        parent = os.path.dirname(key_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", key_path, "-N", "", "-q"],
            check=True,
        )
    with open(key_path + ".pub", "r", encoding="utf-8") as f:
        return f.read().strip()


def provision_host(host, password=None, log=print):
    """连接主机：授权公钥 + 部署查询脚本，返回更新后的 host 字典。"""
    host = normalize_host(host)
    key_path = host["key_path"]
    pub = ensure_key(key_path)
    log(f"[{host['name']}] 密钥就绪：{key_path}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(12)
    if host.get("bind_address"):
        sock.bind((host["bind_address"], 0))
    sock.connect((host["host"], int(host["port"])))
    transport = paramiko.Transport(sock)
    transport.start_client(timeout=12)
    if password:
        transport.auth_password(host["user"], password, fallback=True)
    else:
        transport.auth_publickey(host["user"], _load_key(key_path))
    log(f"[{host['name']}] SSH 认证成功")

    try:
        rc, out = _run(
            transport,
            "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
            "touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys",
        )
        if rc != 0:
            raise SshError(f"准备远端 .ssh 失败：{out.strip()}")

        body = pub.split()[1]
        rc, out = _run(
            transport,
            f"grep -qF '{body}' ~/.ssh/authorized_keys || "
            f"echo '{pub}' >> ~/.ssh/authorized_keys",
        )
        if rc != 0:
            raise SshError(f"写入公钥失败：{out.strip()}")

        rc, out = _run(transport, "mkdir -p ~/.openclaw-watcher && echo $HOME")
        home = out.strip().splitlines()[-1] if out.strip() else ""
        if rc != 0 or not home.startswith("/"):
            raise SshError(f"无法确定远端 HOME：{out.strip()}")

        remote_script = f"{home}/.openclaw-watcher/query.py"
        sftp = paramiko.SFTPClient.from_transport(transport)
        sftp.put(resource_path("watcher", "remote_query.py"), remote_script)
        sftp.close()
        _run(transport, f"chmod 755 {remote_script}")

        rc, out = _run(transport, f"python3 {remote_script} --init", timeout=40)
        if rc != 0:
            raise SshError(f"远端脚本自检失败：{out.strip()[:300]}")
        log(f"[{host['name']}] 部署完成，自检 {out.strip()}")
    finally:
        transport.close()

    host["remote_query_path"] = remote_script
    return host


def test_host(host, password=None):
    """测试连接与查询脚本，返回远端最大 sequence。"""
    from .poller import Poller
    host = normalize_host(host)
    poller = Poller(host)
    if password:
        # 先用密码验证连通性
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(12)
        if host.get("bind_address"):
            sock.bind((host["bind_address"], 0))
        sock.connect((host["host"], int(host["port"])))
        transport = paramiko.Transport(sock)
        transport.start_client(timeout=12)
        transport.auth_password(host["user"], password, fallback=True)
        transport.close()
    return poller.init_cursor()


def register_autostart():
    import winreg
    if getattr(sys, "frozen", False):
        command = f'"{sys.executable}"'
    else:
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        command = f'"{pythonw}" "{os.path.join(APP_DIR, "run.py")}"'
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, "OpenClawWatcher", 0, winreg.REG_SZ, command)
    return command


def start_watcher():
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    if getattr(sys, "frozen", False):
        subprocess.Popen([sys.executable], creationflags=flags)
    else:
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        subprocess.Popen([pythonw, os.path.join(APP_DIR, "run.py")],
                         cwd=APP_DIR, creationflags=flags)


# ---------------------------------------------------------------- 主机编辑对话框

class HostDialog:
    def __init__(self, parent, host=None, title="添加主机"):
        self.result = None
        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.geometry("480x520")
        self.win.resizable(False, False)
        self.win.transient(parent)
        self.win.grab_set()
        host = host or {}

        frm = ttk.Frame(self.win, padding=16)
        frm.pack(fill="both", expand=True)
        grid = ttk.Frame(frm)
        grid.pack(fill="x")

        self.vars = {}
        rows = [
            ("name", "名称", host.get("name", "")),
            ("host", "地址", host.get("host", "")),
            ("port", "端口", str(host.get("port", 22))),
            ("user", "用户名", host.get("user", "")),
            ("password", "密码（可选）", ""),
            ("key_path", "私钥路径", host.get("key_path", "~/.ssh/id_openclaw2")),
            ("bind_address", "绑定网卡", host.get("bind_address", "")),
            ("poll_interval_seconds", "轮询秒数", str(host.get("poll_interval_seconds", 30))),
        ]
        for idx, (key, label, default) in enumerate(rows):
            ttk.Label(grid, text=label).grid(row=idx, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=default)
            entry = ttk.Entry(grid, textvariable=var, width=34)
            if key == "password":
                entry.configure(show="*")
            entry.grid(row=idx, column=1, sticky="we", pady=3)
            self.vars[key] = var
        grid.columnconfigure(1, weight=1)

        ttk.Label(frm, text="提醒哪些结束状态：").pack(anchor="w", pady=(10, 2))
        status_row = ttk.Frame(frm)
        status_row.pack(anchor="w")
        self.status_vars = {}
        current = set(host.get("notify_statuses") or ["succeeded", "failed", "timed_out"])
        for code, label in STATUS_LABELS:
            var = tk.BooleanVar(value=code in current)
            ttk.Checkbutton(status_row, text=label, variable=var).pack(side="left", padx=(0, 10))
            self.status_vars[code] = var

        self.enabled_var = tk.BooleanVar(value=host.get("enabled", True))
        ttk.Checkbutton(frm, text="启用这台主机", variable=self.enabled_var).pack(
            anchor="w", pady=(12, 0))

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(16, 0))
        ttk.Button(btns, text="确定", command=self._ok).pack(side="left")
        ttk.Button(btns, text="取消", command=self.win.destroy).pack(side="right")

    def _ok(self):
        host = dict(HOST_DEFAULTS)
        host.update(self.result or {})
        for key in ("name", "host", "user", "key_path", "bind_address"):
            host[key] = self.vars[key].get().strip()
        try:
            host["port"] = int(self.vars["port"].get().strip() or 22)
            host["poll_interval_seconds"] = int(
                self.vars["poll_interval_seconds"].get().strip() or 30)
        except ValueError:
            messagebox.showerror("参数错误", "端口和轮询秒数必须是数字", parent=self.win)
            return
        if not host["host"] or not host["user"]:
            messagebox.showerror("参数错误", "地址和用户名必填", parent=self.win)
            return
        host["notify_statuses"] = [c for c, v in self.status_vars.items() if v.get()]
        host["enabled"] = self.enabled_var.get()
        password = self.vars["password"].get().strip()
        self.result = normalize_host(host)
        self.result["__password"] = password
        self.win.destroy()

    def show(self):
        self.win.wait_window()
        return self.result


# ---------------------------------------------------------------- 主窗口

class SetupWizard:
    def __init__(self):
        self.hosts = list(load_config().get("hosts") or [])
        self.passwords = {}
        self.root = tk.Tk()
        self.root.title("OpenClaw Watcher 配置")
        self.root.geometry("640x460")
        self.root.resizable(False, False)
        self._build()

    def _build(self):
        frm = ttk.Frame(self.root, padding=16)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="监控哪些 Linux 主机？",
                  font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        ttk.Label(
            frm,
            text="添加主机后会生成/授权密钥，并把它加入开机自启。"
                 "不填密码时要求该主机已信任当前密钥。",
            foreground="#555",
        ).pack(anchor="w", pady=(2, 10))

        columns = ("name", "host", "user", "state")
        self.tree = ttk.Treeview(frm, columns=columns, show="headings", height=8)
        widths = {"name": 140, "host": 200, "user": 100, "state": 70}
        titles = {"name": "名称", "host": "地址", "user": "用户", "state": "状态"}
        for col in columns:
            self.tree.heading(col, text=titles[col])
            self.tree.column(col, width=widths[col], anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _e: self._edit())

        ops = ttk.Frame(frm)
        ops.pack(fill="x", pady=(10, 0))
        ttk.Button(ops, text="添加", command=self._add).pack(side="left")
        ttk.Button(ops, text="编辑", command=self._edit).pack(side="left", padx=6)
        ttk.Button(ops, text="删除", command=self._delete).pack(side="left")
        ttk.Button(ops, text="测试连接", command=self._test).pack(side="left", padx=18)

        self.status = tk.StringVar(value="就绪")
        ttk.Label(frm, textvariable=self.status, foreground="#0a7").pack(
            anchor="w", pady=(12, 0))

        bottom = ttk.Frame(frm)
        bottom.pack(fill="x", pady=(12, 0))
        self.autostart = tk.BooleanVar(value=True)
        ttk.Checkbutton(bottom, text="注册开机自启", variable=self.autostart).pack(side="left")
        ttk.Button(bottom, text="取消", command=self.root.destroy).pack(side="right")
        self.save_btn = ttk.Button(bottom, text="保存并启动", command=self._save)
        self.save_btn.pack(side="right", padx=8)

        self._refresh()

    def _refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for host in self.hosts:
            self.tree.insert(
                "", "end", iid=host["id"],
                values=(host.get("name"), host.get("host"),
                        host.get("user"), "启用" if host.get("enabled", True) else "停用"),
            )

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择一台主机")
            return None
        return next((h for h in self.hosts if h["id"] == sel[0]), None)

    def _add(self):
        result = HostDialog(self.root, title="添加主机").show()
        if result:
            pw = result.pop("__password", "")
            if pw:
                self.passwords[result["id"]] = pw
            self.hosts.append(result)
            self._refresh()

    def _edit(self):
        host = self._selected()
        if not host:
            return
        result = HostDialog(self.root, host=host, title="编辑主机").show()
        if result:
            pw = result.pop("__password", "")
            if pw:
                self.passwords[result["id"]] = pw
            host.update(result)
            self._refresh()

    def _delete(self):
        host = self._selected()
        if not host:
            return
        if not messagebox.askyesno("删除", f"确定删除「{host.get('name')}」？"):
            return
        self.hosts.remove(host)
        self.passwords.pop(host["id"], None)
        self._refresh()

    def _test(self):
        host = self._selected()
        if not host:
            return
        self.status.set(f"正在测试 {host['name']} ...")

        def worker():
            try:
                seq = test_host(host, self.passwords.get(host["id"]))
                self.root.after(0, lambda: self.status.set(
                    f"[{host['name']}] 连接成功，当前 sequence={seq}"))
            except Exception as exc:
                self.root.after(0, lambda: self.status.set(
                    f"[{host['name']}] 连接失败：{exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _save(self):
        if not self.hosts:
            messagebox.showinfo("提示", "至少添加一台主机")
            return
        self.save_btn.configure(state="disabled")

        def worker():
            errors = []
            for host in self.hosts:
                try:
                    self._set_status(f"正在配置 {host['name']} ...")
                    updated = provision_host(host, self.passwords.get(host["id"]),
                                             log=self._set_status)
                    host.update(updated)
                except Exception as exc:
                    errors.append(f"{host['name']}：{exc}")
            if errors:
                self.root.after(0, lambda: self._fail(errors))
                return
            cfg = load_config()
            cfg["hosts"] = self.hosts
            persist_config(cfg)
            if self.autostart.get():
                register_autostart()
            self.root.after(0, self._done)

        threading.Thread(target=worker, daemon=True).start()

    def _set_status(self, text):
        self.root.after(0, lambda: self.status.set(text))

    def _fail(self, errors):
        self.save_btn.configure(state="normal")
        messagebox.showerror("配置失败", "\n".join(errors))

    def _done(self):
        messagebox.showinfo("完成", "配置已保存，正在启动监控。")
        self.root.destroy()
        start_watcher()

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------- CLI

def main_cli(argv):
    import argparse
    parser = argparse.ArgumentParser(description="OpenClaw Watcher 配置（命令行）")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", default="")
    parser.add_argument("--key", default="")
    parser.add_argument("--bind", default="")
    parser.add_argument("--name", default="")
    args = parser.parse_args(argv)

    cfg = load_config()
    host = {
        "name": args.name or args.host,
        "host": args.host, "port": args.port, "user": args.user,
        "key_path": args.key or "~/.ssh/id_openclaw2",
        "bind_address": args.bind,
    }
    host = provision_host(host, args.password or None)
    existing = [h for h in cfg["hosts"]
                if not (h["host"] == host["host"] and h["user"] == host["user"])]
    existing.append(host)
    cfg["hosts"] = existing
    path = persist_config(cfg)
    print("配置已写入:", path, "| 主机数:", len(existing))
    return 0


def run_wizard():
    SetupWizard().run()
