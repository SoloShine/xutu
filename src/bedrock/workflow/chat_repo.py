# src/bedrock/workflow/chat_repo.py
"""作者助手 agent 的会话/消息/提案 repo(项目 bedrock.db)。

agent 产的结构化提案(chat_proposal)需作者审批才落库经 repo 函数 —— 守铁律
(作者主导 + 写库经 repo + amendment 审计;L2/verify 信任锚零改)。
"""
import json


def create_session(conn, title=""):
    s = conn.execute("SELECT datetime('now')").fetchone()[0]
    cur = conn.execute("INSERT INTO chat_session(title, created_at, updated_at) VALUES(?,?,?)",
                       (title, s, s))
    conn.commit()
    return cur.lastrowid


def list_sessions(conn):
    rows = conn.execute(
        "SELECT s.id, s.title, s.created_at, s.updated_at, "
        "(SELECT COUNT(*) FROM chat_message m WHERE m.session_id=s.id) AS msg_n "
        "FROM chat_session s ORDER BY s.id DESC").fetchall()
    return [{"id": r["id"], "title": r["title"], "created_at": r["created_at"],
             "updated_at": r["updated_at"], "message_count": r["msg_n"]} for r in rows]


def get_session(conn, sid):
    r = conn.execute("SELECT * FROM chat_session WHERE id=?", (sid,)).fetchone()
    return dict(r) if r else None


def add_message(conn, session_id, role, content):
    cur = conn.execute("INSERT INTO chat_message(session_id, role, content) VALUES(?,?,?)",
                       (session_id, role, content))
    conn.execute("UPDATE chat_session SET updated_at=datetime('now') WHERE id=?", (session_id,))
    conn.commit()
    return cur.lastrowid


def list_messages(conn, session_id):
    rows = conn.execute(
        "SELECT id, role, content, ts FROM chat_message WHERE session_id=? ORDER BY id",
        (session_id,)).fetchall()
    return [{"id": r["id"], "role": r["role"], "content": r["content"], "ts": r["ts"]} for r in rows]


def add_proposal(conn, session_id, action_type, payload):
    cur = conn.execute(
        "INSERT INTO chat_proposal(session_id, action_type, payload, status) VALUES(?,?,?,'pending')",
        (session_id, action_type, json.dumps(payload, ensure_ascii=False)))
    conn.commit()
    return cur.lastrowid


def list_proposals(conn, session_id, *, only_pending=False):
    sql = "SELECT id, session_id, action_type, payload, status, result, created_at, decided_at FROM chat_proposal WHERE session_id=?"
    if only_pending:
        sql += " AND status='pending'"
    sql += " ORDER BY id"
    rows = conn.execute(sql, (session_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["payload"] = json.loads(r["payload"] or "{}")
        except (ValueError, TypeError):
            d["payload"] = {}
        try:
            d["result"] = json.loads(r["result"]) if r["result"] else None
        except (ValueError, TypeError):
            d["result"] = None
        out.append(d)
    return out


def get_proposal(conn, pid):
    r = conn.execute(
        "SELECT id, session_id, action_type, payload, status, result, created_at, decided_at "
        "FROM chat_proposal WHERE id=?", (pid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["payload"] = json.loads(r["payload"] or "{}")
    except (ValueError, TypeError):
        d["payload"] = {}
    return d


def decide_proposal(conn, pid, *, approved, result=None):
    """标记提案 approved/rejected + 记执行结果。返回更新后的提案 dict 或 None。"""
    status = "approved" if approved else "rejected"
    conn.execute(
        "UPDATE chat_proposal SET status=?, result=?, decided_at=datetime('now') WHERE id=?",
        (status, json.dumps(result, ensure_ascii=False) if result is not None else None, pid))
    conn.commit()
    return get_proposal(conn, pid)
