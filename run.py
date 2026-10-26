"""OpenClaw Watcher 启动入口。

用法：
    run.py                正常运行 watcher（未配置时自动打开发置向导）
    run.py --setup        图形配置向导
    run.py --setup-cli   命令行配置（单台主机，自动化用）
    run.py --version      版本
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_MUTEX = None


def _acquire_single_instance():
    """Windows 单实例锁：重复双击时安静退出，避免重复弹窗。"""
    global _MUTEX
    import ctypes
    kernel32 = ctypes.windll.kernel32
    _MUTEX = kernel32.CreateMutexW(None, False, "Local\\OpenClawWatcher_SingleInstance")
    return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--setup":
        from watcher.setup_wizard import run_wizard
        run_wizard()
        return 0
    if argv and argv[0] == "--setup-cli":
        from watcher.setup_wizard import main_cli
        return main_cli(argv[1:])
    if argv and argv[0] in ("--version", "-V"):
        from watcher import __version__
        print(f"OpenClaw Watcher {__version__}")
        return 0

    if not _acquire_single_instance():
        return 0  # 已有实例在运行

    from watcher.config import enabled_hosts, load_config
    if not enabled_hosts(load_config()):
        # 首次启动：没有配置就打开向导
        from watcher.setup_wizard import run_wizard
        run_wizard()
        return 0

    from watcher.main import main as watcher_main
    watcher_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
