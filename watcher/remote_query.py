#!/usr/bin/env python3
"""在 Linux 主机上运行：从 OpenClaw 的 audit_events 表读取"agent 任务结束"事件。

零侵入：只读打开状态库，不修改 OpenClaw 任何数据。

用法：
    python3 query.py --init
    python3 query.py --since 12345 --limit 20
输出：JSON（events + max_sequence）
"""

import argparse
import json
import os
import sqlite3
import sys

DB_PATH = os.path.expanduser("~/.openclaw/state/openclaw.sqlite")
AGENTS_DIR = os.path.expanduser("~/.openclaw/agents")


def open_db():
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def read_tail_lines(path, max_bytes=256 * 1024):
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - max_bytes))
        data = f.read()
    return data.decode("utf-8", "replace").splitlines()


def last_assistant_text(session_file):
    """从会话 JSONL 尾部找最后一条 assistant 文本消息。"""
    if not session_file or not os.path.exists(session_file):
        return ""
    try:
        lines = read_tail_lines(session_file)
    except OSError:
        return ""
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get("type") != "message":
            continue
        msg = obj.get("message") or {}
        if msg.get("role") != "assistant":
            continue
        parts = []
        for part in msg.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "text":
                text = (part.get("text") or "").strip()
                if text:
                    parts.append(text)
        text = "\n".join(parts).strip()
        if text:
            return text
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", type=int, default=0)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--init", action="store_true")
    args = parser.parse_args()

    try:
        con = open_db()
    except sqlite3.Error as exc:
        print(json.dumps({"error": f"无法读取状态库：{exc}"}))
        sys.exit(1)

    with con:
        max_seq = con.execute(
            "select coalesce(max(sequence), 0) from audit_events"
        ).fetchone()[0]
        if args.init:
            print(json.dumps({"max_sequence": int(max_seq)}))
            return

        rows = con.execute(
            """select sequence, occurred_at, status, agent_id, session_key,
                      session_id, run_id, error_code
               from audit_events
               where action = 'agent.run.finished' and sequence > ?
               order by sequence asc limit ?""",
            (args.since, args.limit),
        ).fetchall()

        events = []
        for row in rows:
            started = con.execute(
                """select occurred_at from audit_events
                   where run_id = ? and action = 'agent.run.started'
                   order by sequence desc limit 1""",
                (row["run_id"],),
            ).fetchone()
            duration = None
            if started and row["occurred_at"]:
                duration = int(row["occurred_at"] - started["occurred_at"])
            session_file = ""
            if row["agent_id"] and row["session_id"]:
                session_file = os.path.join(
                    AGENTS_DIR, row["agent_id"], "sessions",
                    f'{row["session_id"]}.jsonl',
                )
            events.append({
                "sequence": int(row["sequence"]),
                "occurred_at": int(row["occurred_at"] or 0),
                "status": row["status"],
                "agent_id": row["agent_id"],
                "session_key": row["session_key"],
                "session_id": row["session_id"],
                "run_id": row["run_id"],
                "error_code": row["error_code"],
                "duration_ms": duration,
                "summary": last_assistant_text(session_file)[:1500],
            })

    print(json.dumps({
        "events": events,
        "max_sequence": int(max_seq),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
