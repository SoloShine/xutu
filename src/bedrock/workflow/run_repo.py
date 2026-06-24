# src/bedrock/workflow/run_repo.py
"""工作流运行事件 repo（phase 2 实时可观测性）。

纯遥测旁路:runner（当前 .js / 将来 LangGraph）边跑边写 run + event;
Web 面板 Vue Flow 只读图轮询 list_recent_runs / get_run / list_events 渲染。
不影响 L2/verify-persisted 信任锚,不进控制流判决（emit 全程非阻断,调用方 try/catch）。
"""
import json


def start_run(conn, chapter_global=None, volume_id=None, runner="js"):
    """新建一行 run(status=running),返回 run_id。

    幂等:若该章已有 running 态 run,复用之。start-run 经自治 agent relay 执行,
    agent 常把同一条命令重试多次(实测一次 relay 跑了 3 次);非幂等会一次执行产生多行。
    复用也顺带吸收脚本整体重跑(harness 瞬态重试)产生的孤儿。串行管线保证同时至多一个 active run/章。
    """
    if chapter_global is not None:
        existing = conn.execute(
            "SELECT id FROM workflow_run WHERE chapter_global=? AND status='running' "
            "ORDER BY id DESC LIMIT 1", (chapter_global,)).fetchone()
        if existing:
            return existing["id"]
    cur = conn.execute(
        "INSERT INTO workflow_run(chapter_global, volume_id, runner, status, current_node) "
        "VALUES(?, ?, ?, 'running', 'start')",
        (chapter_global, volume_id, runner))
    conn.commit()
    return cur.lastrowid


def _next_seq(conn, run_id):
    r = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) AS m FROM workflow_run_event WHERE run_id=?", (run_id,)).fetchone()
    return r["m"] + 1


def _now(conn):
    r = conn.execute("SELECT datetime('now')").fetchone()
    return r[0]


def _insert_event(conn, run_id, seq, node, kind, payload, ts):
    conn.execute(
        "INSERT INTO workflow_run_event(run_id, seq, node, kind, payload, ts) "
        "VALUES(?, ?, ?, ?, ?, ?)",
        (run_id, seq, node, kind,
         json.dumps(payload, ensure_ascii=False) if payload is not None else "{}", ts))


def emit_event(conn, run_id, node, kind, payload=None):
    """追加单条事件;seq 单调递增;更新 run.current_node。返回 seq。"""
    run = conn.execute("SELECT id FROM workflow_run WHERE id=?", (run_id,)).fetchone()
    if run is None:
        raise ValueError(f"run_id={run_id} 不存在")
    seq = _next_seq(conn, run_id)
    ts = _now(conn)
    _insert_event(conn, run_id, seq, node, kind, payload, ts)
    conn.execute("UPDATE workflow_run SET current_node=? WHERE id=?", (node, run_id))
    conn.commit()
    return seq


def emit_events_batch(conn, run_id, events):
    """批量追加事件（一次提交,省 relay）。events=[{node, kind, payload?}, ...]。
    seq 连续递增;current_node 更新为末条 node。返回写入条数。"""
    run = conn.execute("SELECT id FROM workflow_run WHERE id=?", (run_id,)).fetchone()
    if run is None:
        raise ValueError(f"run_id={run_id} 不存在")
    if not events:
        return 0
    seq = _next_seq(conn, run_id)
    ts = _now(conn)
    last_node = ""
    for ev in events:
        node = ev.get("node", "")
        kind = ev.get("kind", "")
        payload = ev.get("payload")
        _insert_event(conn, run_id, seq, node, kind, payload, ts)
        last_node = node
        seq += 1
    if last_node:
        conn.execute("UPDATE workflow_run SET current_node=? WHERE id=?", (last_node, run_id))
    conn.commit()
    return len(events)


def end_run(conn, run_id, status, current_node=None):
    """结束 run:status=completed|failed|aborted + ended_at。current_node 可选覆盖。"""
    if status not in ("completed", "failed", "aborted"):
        raise ValueError("status 必须 completed|failed|aborted")
    sets, vals = ["status=?", "ended_at=?"], [status, _now(conn)]
    if current_node is not None:
        sets.append("current_node=?"); vals.append(current_node)
    vals.append(run_id)
    conn.execute(f"UPDATE workflow_run SET {', '.join(sets)} WHERE id=?", vals)
    conn.commit()


def get_run(conn, run_id):
    """单 run 行(dict)或 None。"""
    r = conn.execute("SELECT * FROM workflow_run WHERE id=?", (run_id,)).fetchone()
    if r is None:
        return None
    return dict(r)


def list_events(conn, run_id):
    """run 的事件列表（按 seq 升序）。payload 解析回 dict。"""
    rows = conn.execute(
        "SELECT id, run_id, seq, node, kind, payload, ts FROM workflow_run_event "
        "WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()
    out = []
    for r in rows:
        raw = r["payload"]
        try:
            payload = json.loads(raw) if raw else {}
        except (ValueError, TypeError):
            payload = {}
        out.append({"id": r["id"], "run_id": r["run_id"], "seq": r["seq"],
                    "node": r["node"], "kind": r["kind"], "payload": payload, "ts": r["ts"]})
    return out


def run_telemetry(conn, run_id):
    """聚合 run 的 LLM 遥测(从 llm_call event 求)。成本核算用。

    返回 {run_id, llm_calls, tokens_in, tokens_out, llm_time_ms, by_process:{process:{calls,tokens_in,tokens_out}},
    run_started_at, run_ended_at, run_duration_s(总耗时,含非 LLM)}。无 llm_call event → calls=0。
    """
    evs = list_events(conn, run_id)
    by_proc = {}
    tin = tout = ttime = 0
    for e in evs:
        if e["kind"] != "llm_call":
            continue
        p = e["payload"] or {}
        key = e["node"]   # 按 node(write/revise/consistency)归并
        b = by_proc.setdefault(key, {"calls": 0, "tokens_in": 0, "tokens_out": 0, "latency_ms": 0,
                                     "endpoint": p.get("endpoint"), "model": p.get("model")})
        b["calls"] += 1
        b["tokens_in"] += p.get("tokens_in") or 0
        b["tokens_out"] += p.get("tokens_out") or 0
        b["latency_ms"] += p.get("latency_ms") or 0
        tin += p.get("tokens_in") or 0
        tout += p.get("tokens_out") or 0
        ttime += p.get("latency_ms") or 0
    run = get_run(conn, run_id) or {}
    started = run.get("started_at")
    ended = run.get("ended_at")
    duration_s = None
    if started and ended:
        try:
            from datetime import datetime
            s = datetime.strptime(started, "%Y-%m-%d %H:%M:%S")
            e2 = datetime.strptime(ended, "%Y-%m-%d %H:%M:%S")
            duration_s = (e2 - s).total_seconds()
        except Exception:
            duration_s = None
    return {"run_id": run_id, "llm_calls": sum(b["calls"] for b in by_proc.values()),
            "tokens_in": tin, "tokens_out": tout, "llm_time_ms": ttime,
            "by_process": by_proc, "run_started_at": started, "run_ended_at": ended,
            "run_duration_s": duration_s}


def list_recent_runs(conn, limit=20, chapter_global=None):
    """最近 N 个 run(含 event 计数 + 末节点)。可按章过滤。"""
    if chapter_global is not None:
        rows = conn.execute(
            "SELECT * FROM workflow_run WHERE chapter_global=? ORDER BY id DESC LIMIT ?",
            (chapter_global, limit)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM workflow_run ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        cnt = conn.execute(
            "SELECT COUNT(*) AS n FROM workflow_run_event WHERE run_id=?", (r["id"],)).fetchone()
        out.append({"id": r["id"], "chapter_global": r["chapter_global"],
                    "volume_id": r["volume_id"], "runner": r["runner"], "status": r["status"],
                    "current_node": r["current_node"], "started_at": r["started_at"],
                    "ended_at": r["ended_at"], "event_count": cnt["n"]})
    return out
