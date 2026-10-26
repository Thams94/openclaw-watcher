# OpenClaw Watcher

Linux 上 OpenClaw 把活干完了，Windows 右下角立即弹窗提醒你——不用再反复切到终端确认。

## 痛点

- Linux 主机跑 OpenClaw，Windows 主机办公（用 Termius SSH 派活）；
- 任务交出去后不知道什么时候跑完，得反复盯着终端。

## 方案（零侵入）

直接在 Windows 端 SSH 轮询 OpenClaw 的 **`audit_events` 审计事件表**里的
`agent.run.finished` 事件——不需要给 OpenClaw 装钩子、不需要重启网关、
不修改它的任何数据（数据库以只读模式打开）。

```
你给 OpenClaw 派活（Termius → openclaw-tui）
        │
        ▼  OpenClaw 每次 agent 回合结束，写入 audit_events
Linux: ~/.openclaw/state/openclaw.sqlite
        │
        ▼  Windows 每 30 秒 SSH 执行一次只读查询
Windows: query.py --since <上次游标> → 新事件 + 结果摘要 + 耗时
        │
        ▼
通知后端（可插拔）→ 右下角卡片 + 提示音
```

## 组件

| 位置 | 文件 | 作用 |
|---|---|---|
| Windows | `run.py` | 启动入口（pythonw 无窗口运行，未配置时自动打开向导） |
| Windows | `watcher/main.py` | 主循环：多主机轮询、暂停判断、托盘接入 |
| Windows | `watcher/tray.py` | 系统托盘：状态、暂停/恢复、打开配置、退出 |
| Windows | `watcher/setup_wizard.py` | 多主机配置向导（GUI + CLI） |
| Windows | `watcher/poller.py` | SSH 拉取单台主机事件 |
| Windows | `watcher/ssh_client.py` | paramiko 连接（带重试，支持绑定源网卡） |
| Windows | `watcher/state.py` | 每台主机游标、暂停截止时间 |
| Windows | `watcher/notifier/` | 通知后端接口 + 弹窗实现（卡通小人升级点） |
| Linux | `~/.openclaw-watcher/query.py` | 只读查询 audit_events + 提取会话摘要 |
| 配置 | `config.json` | 多主机列表 + 全局通知设置 |

## 部署到其他机器（软件包）

### 需要装什么？

| 机器 | 需要 | 说明 |
|---|---|---|
| 要弹提醒的 Windows | OpenClaw Watcher 客户端 | 本文的软件包 |
| 跑 OpenClaw 的 Linux | **什么都不用装** | 安装器自动上传一个约 6KB 的只读查询脚本，无常驻进程 |

一个客户端实例监控一台 Linux 主机。要监控多台 Linux，就在多台 Windows
各装一份客户端（或同一台电脑放多份目录、各自配置）。

### 方式一：免 Python（推荐，拷贝即用）

1. 解压 `OpenClawWatcher-0.1.0-win64.zip` 到任意目录（如 `C:\Tools\OpenClawWatcher`）；
2. 双击 `setup.cmd`；
3. 填 Linux 主机地址、端口、用户名、密码（密码仅首次授权用，之后走密钥）；
4. 点「安装并启动」：自动生成密钥 → 授权 → 上传查询脚本 → 写配置 → 注册开机自启 → 启动。

卸载：双击 `uninstall.cmd`。

### 方式二：有 Python 的电脑

```powershell
python run.py --setup          # 图形向导
# 或命令行自动化（适合批量部署）：
python run.py --setup-cli --host 192.168.1.100 --port 22 --user youruser --password yourpassword --bind 192.168.1.50
python install.ps1             # 注册开机自启（也可由向导完成）
```

### 重新打包（开发机上）

```powershell
powershell -ExecutionPolicy Bypass -File package.ps1 -Python "C:\...\pythoncore-3.12-64\python.exe"
# 输出：dist\OpenClawWatcher\（onedir）与 dist\OpenClawWatcher-0.1.0-win64.zip
```

> 打包请用 **Python 3.12**：Python 3.15 下 cryptography 的 Rust 扩展 `_rust.pyd`
> 会被 PyInstaller 漏掉依赖（报 `python3t.dll` 缺失），打出的 exe 无法加载 SSH 库。
> 源码运行不受影响。

### 换一台 Linux 主机 / 增加主机

在客户端重新运行 `setup.cmd`（或 `run.py --setup`），在列表里添加、编辑或删除主机。
支持同时监控多台 Linux 主机（每台可单独设置轮询间隔和提醒状态）。
旧主机上的查询脚本可留可删（`~/.openclaw-watcher/`）。

## 托盘与暂停

启动后系统托盘会出现一个圆形图标，右键菜单：

| 菜单项 | 作用 |
|---|---|
| 状态行 | 显示「监控中 · N 台主机」或「已暂停 · 恢复于 HH:MM」 |
| 暂停监控 | 30 分钟 / 1 / 2 / 4 / 8 小时；暂停期间仍会拉取并推进游标，但**不弹提醒** |
| 恢复监控 | 立即恢复 |
| 打开配置 | 重新打开发置向导（可加/删主机） |
| 查看日志 | 用记事本打开 `watcher.log` |
| 退出 | 停止监控并退出程序 |

暂停状态持久化在 `state.json`，程序重启后仍然有效。

## 安装步骤（手动，可选）

1. **配置密钥**（一次性）：把公钥追加到 Linux 的 `~/.ssh/authorized_keys`。
   本仓库的密钥路径默认为 `~/.ssh/id_openclaw2`。
2. **部署远端脚本**（一次性）：
   ```powershell
   python tools/setup_remote.py
   ```
   会把 `watcher/remote_query.py` 上传为 `~/.openclaw-watcher/query.py`。
3. **注册开机自启并启动**：
   ```powershell
   powershell -ExecutionPolicy Bypass -File install.ps1
   ```
   卸载：`install.ps1 -Uninstall`

## 配置说明（config.json，多主机）

```json
{
  "hosts": [
    {
      "id": "h-main",
      "name": "主服务器",
      "host": "192.168.1.100",
      "port": 22,
      "user": "youruser",
      "key_path": "C:\\Users\\iiok\\.ssh\\id_openclaw2",
      "bind_address": "192.168.1.50",
      "poll_interval_seconds": 30,
      "notify_statuses": ["succeeded", "failed", "timed_out"],
      "ignore_fast_turns_ms": 0,
      "enabled": true
    }
  ],
  "notifier": "popup",
  "sound": true,
  "tray": true,
  "popup_timeout_seconds": 25
}
```

每台主机的字段：

| 键 | 默认 | 说明 |
|---|---|---|
| `name` / `host` / `port` / `user` | — | 连接信息 |
| `key_path` | `~/.ssh/id_openclaw2` | SSH 私钥 |
| `bind_address` | 空 | **绑定网卡源地址**，避免流量绕到无线（见下） |
| `poll_interval_seconds` | 30 | 该主机的轮询间隔 |
| `notify_statuses` | succeeded/failed/timed_out | 该主机提醒哪些结束状态 |
| `ignore_fast_turns_ms` | 0 | 忽略耗时短于该值的任务 |
| `enabled` | true | 是否监控 |

全局字段：`notifier`（popup/console）、`sound`、`tray`、`popup_timeout_seconds`、`log_level`。

> 旧版单主机配置（顶层 `host` 字段）会在启动时自动迁移为 `hosts` 列表。

### 为什么绑定源地址

这台 Windows 同时接了有线（192.168.1.50）和无线（办公室网络）。
办公室网络里也能路由到 `192.168.1.100` 这个地址（会绕公网 6 跳、且 22 端口被过滤），
如果不绑源地址，SSH 可能被路由到那条"假"路径上。`bind_address` 强制走有线口。

## 升级：卡通形象小人提醒

通知层是接口化的（`watcher/notifier/base.py`）：

1. 新建 `watcher/notifier/mascot.py`，实现 `Notifier` 的 `start / show / stop`；
2. 在 `watcher/notifier/__init__.py` 的 `_BACKENDS` 注册 `"mascot"`；
3. `config.json` 改 `"notifier": "mascot"`。

轮询、状态、判定逻辑完全不用改。

## 常见问题

- **断线**：有线链路存在载波抖动（实测载波变化 34 次、只协商到 100Mbps），
  watcher 每次轮询失败只记日志、下一轮自动重试，不影响后台运行。
- **提醒太吵**：调大 `ignore_fast_turns_ms`（例如 60000），或把 `notify_statuses`
  改成只保留 `failed`。
- **日志**：`%APPDATA%\OpenClawWatcher\watcher.log`；状态：同目录 `state.json`。

## 安全

- 软件只读打开 OpenClaw 数据库，不修改任何数据；
- SSH 使用密钥认证，不存储明文密码；
- 事件文件与摘要仅在本地内存与日志中短暂存在。

## License

[MIT](LICENSE) © 2026 Thams94

