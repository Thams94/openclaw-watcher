"""基于 paramiko Transport 的 SSH 连接（带重试）。

使用 Transport 而非 SSHClient：SSHClient 在本机环境与 OpenSSH 8.9
服务端组合下会出现 KEX 卡死，Transport 低层方式稳定。
"""

import socket
import time

import paramiko


class SshError(Exception):
    """SSH 连接或执行失败。"""


def _load_key(path):
    for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            return cls.from_private_key_file(path)
        except paramiko.PasswordRequiredException:
            raise SshError(f"私钥受密码保护，无法自动使用：{path}")
        except Exception:
            continue
    raise SshError(f"无法加载私钥：{path}")


class SshSession:
    def __init__(self, host, port, user, key_path, bind_address="",
                 connect_timeout=10):
        self.host = host
        self.port = int(port)
        self.user = user
        self.key_path = key_path
        self.bind_address = bind_address
        self.connect_timeout = connect_timeout

    def connect(self, retries=3, delay=2.0):
        last = None
        for _ in range(retries):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.connect_timeout)
                if self.bind_address:
                    sock.bind((self.bind_address, 0))
                sock.connect((self.host, self.port))
                transport = paramiko.Transport(sock)
                transport.start_client(timeout=self.connect_timeout)
                transport.auth_publickey(self.user, _load_key(self.key_path))
                return transport
            except SshError:
                raise
            except Exception as exc:  # 网络抖动/链路断开
                last = exc
                time.sleep(delay)
        raise SshError(f"SSH 连接失败：{last}")

    def run(self, transport, command, timeout=30):
        chan = transport.open_session()
        chan.settimeout(timeout)
        chan.set_combine_stderr(True)
        chan.exec_command(command)
        out = b""
        while True:
            chunk = chan.recv(65536)
            if not chunk:
                break
            out += chunk
        rc = chan.recv_exit_status()
        chan.close()
        return rc, out.decode("utf-8", "replace")
