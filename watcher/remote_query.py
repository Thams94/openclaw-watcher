#!/usr/bin/env python3
"""在 Linux 主机上运行：从 OpenClaw 的 audit_events 表读取"agent 任务结束"事件。

零侵入：只读打开状态库，不修改 OpenClaw 任何数据。

兼容两种会话存储：
- 旧版（如 2026.7.x）：agents/<agent>/sessions/<session_id>.jsonl
- 新版（如 2026.10.x）：agents/<agent>/agent/openclaw-agent.sqlite 的 transcript_events 表

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


def _text_from_event(obj):
    """从一条 transcript 事件里取 assistant 文本。"""
    if obj.get("type") != "message":
        return ""
    msg = obj.get("message") or {}
    if msg.get("role") != "assistant":
        return ""
    parts = []
    for part in msg.get("content") or []:
        if isinstance(part, dict) and part.get("type") == "text":
            text = (part.get("text") or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def _from_jsonl(path, max_bytes=256 * 1024):
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            data = f.read()
    except OSError:
        return ""
    for line in reversed(data.decode("utf-8", "replace").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        text = _text_from_event(obj)
        if text:
            return text
    return ""


def _from_agent_db(db_path, session_id, limit=200):
    """新版：agent 自己的 SQLite 里取最近事件。"""
    if not session_id or not os.path.exists(db_path):
        return ""
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        rows = con.execute(
            "select event_json from transcript_events "
            "where session_id = ? order by seq desc limit ?",
            (session_id, limit),
        ).fetchall()
        con.close()
    except sqlite3.Error:
        return ""
    for (raw,) in rows:
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        text = _text_from_event(obj)
        if text:
            return text
    return ""


def last_assistant_text(agent, session_id):
    if not agent or not session_id:
        return ""
    old_path = os.path.join(AGENTS_DIR, agent, "sessions", f"{session_id}.jsonl")
    text = _from_jsonl(old_path)
    if text:
        return text
    db_path = os.path.join(AGENTS_DIR, agent, "agent", "openclaw-agent.sqlite")
    return _from_agent_db(db_path, session_id)


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
            summary = last_assistant_text(row["agent_id"], row["session_id"])
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
                "summary": summary[:1500],
            })

    print(json.dumps({
        "events": events,
        "max_sequence": int(max_seq),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
