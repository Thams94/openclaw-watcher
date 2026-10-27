"""SSH 连接诊断：定位是网络、端口、认证方式还是密码的问题。

用法示例：
    python tools/diagnose_ssh.py --host 1.2.3.4 --port 22 --user root --password 你的密码
    python tools/diagnose_ssh.py --host 1.2.3.4 --user root --key ~/.ssh/id_openclaw2
"""

import argparse
import socket
import sys

import paramiko

try:  # 兼容 GBK 控制台/管道输出
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SUGGESTIONS = {
    "no_password": (
        "服务器只允许密钥登录（云主机默认常见）。\n"
        "  解决 A：在服务器上启用密码登录：\n"
        "    sudo sed -i 's/^#\\?PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config\n"
        "    sudo systemctl restart ssh\n"
        "  解决 B：改用密钥登录（把公钥加到服务器 ~/.ssh/authorized_keys）。"
    ),
    "bad_password": (
        "用户名或密码不正确。注意：\n"
        "  - 阿里云 Linux 默认用户通常是 root（部分镜像为 ecs-user / ubuntu）\n"
        "  - 若改过端口，确认端口号正确\n"
        "  - 密码含特殊字符时注意是否被截断"
    ),
    "no_port": (
        "端口连不上。检查：\n"
        "  - 阿里云安全组是否放行了该端口（入方向）\n"
        "  - 服务器防火墙（ufw/firewalld）\n"
        "  - 公网 IP 是否变化（ECS 停机再启动可能变）"
    ),
}


def main():
    parser = argparse.ArgumentParser(description="OpenClaw Watcher SSH 诊断")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", default="")
    parser.add_argument("--key", default="")
    parser.add_argument("--bind", default="")
    args = parser.parse_args()

    print(f"[1/4] TCP 连接 {args.host}:{args.port} ...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    if args.bind:
        sock.bind((args.bind, 0))
    try:
        sock.connect((args.host, args.port))
        print("      OK：端口可连接")
    except Exception as exc:
        print(f"      失败：{exc}")
        print(SUGGESTIONS["no_port"])
        return 1

    try:
        transport = paramiko.Transport(sock)
        transport.start_client(timeout=15)
        print(f"[2/4] SSH 握手成功：{transport.remote_version}")
    except Exception as exc:
        print(f"      失败：{exc}")
        print("      服务器不是标准 SSH 服务，或端口上跑的是别的服务")
        return 1

    allowed = []
    print("[3/4] 查询该用户允许的认证方式 ...")
    try:
        transport.auth_none(args.user)
        print("      服务器允许无认证登录（不建议）")
    except paramiko.BadAuthenticationType as exc:
        allowed = exc.allowed_types
    except paramiko.AuthenticationException as exc:
        allowed = getattr(exc, "allowed_types", []) or []
    except Exception as exc:
        print(f"      查询失败：{exc}")
    print(f"      允许方式：{allowed or '未知'}")

    password_ok = "password" in allowed or not allowed
    if not password_ok:
        print("      => 服务器【不允许密码登录】")
        print("      " + SUGGESTIONS["no_password"].replace("\n", "\n      "))

    if args.password:
        print("[4/4] 尝试密码登录 ...")
        try:
            transport.auth_password(args.user, args.password, fallback=True)
            print("      密码登录成功 [OK]（配置向导里应该也能通过）")
        except paramiko.BadAuthenticationType as exc:
            print(f"      服务器拒绝密码方式：{exc.allowed_types}")
            print("      " + SUGGESTIONS["no_password"].replace("\n", "\n      "))
        except paramiko.AuthenticationException:
            print("      密码登录失败：用户名或密码错误")
            print("      " + SUGGESTIONS["bad_password"].replace("\n", "\n      "))
        except Exception as exc:
            print(f"      失败：{exc}")

    if args.key:
        print("[4/4] 尝试密钥登录 ...")
        key = None
        for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
            try:
                key = cls.from_private_key_file(args.key)
                break
            except Exception:
                continue
        if key is None:
            print("      无法读取私钥文件")
        else:
            try:
                transport.auth_publickey(args.user, key)
                print("      密钥登录成功 [OK]")
            except paramiko.BadAuthenticationType as exc:
                print(f"      服务器拒绝密钥方式：{exc.allowed_types}")
            except paramiko.AuthenticationException:
                print("      密钥登录失败：公钥未授权到该用户，或密钥不匹配")
            except Exception as exc:
                print(f"      失败：{exc}")

    transport.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
