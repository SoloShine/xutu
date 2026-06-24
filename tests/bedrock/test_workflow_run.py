import json
from src.bedrock.db.connection import get_connection
from src.bedrock.workflow.run_repo import (
    start_run, emit_event, emit_events_batch, end_run, get_run, list_events, list_recent_runs,
)


def test_start_run_returns_id_running(tmp_project):
    conn = get_connection(tmp_project)
    rid = start_run(conn, chapter_global=13, volume_id=2, runner="js")
    assert rid
    r = get_run(conn, rid)
    assert r["status"] == "running"
    assert r["chapter_global"] == 13
    assert r["runner"] == "js"
    assert r["current_node"] == "start"
    assert r["ended_at"] is None
    conn.close()


def test_start_run_idempotent_while_running(tmp_project):
    """同章已有 running 态 run → 复用,不新建(agent relay 重试命令/脚本重跑都不应产多行)。"""
    conn = get_connection(tmp_project)
    r1 = start_run(conn, chapter_global=13)
    r2 = start_run(conn, chapter_global=13)  # agent 重试
    r3 = start_run(conn, chapter_global=13)  # 再重试
    assert r1 == r2 == r3
    n = conn.execute("SELECT COUNT(*) AS n FROM workflow_run WHERE chapter_global=13").fetchone()["n"]
    assert n == 1
    conn.close()


def test_start_run_new_after_completed(tmp_project):
    """章 run 完成后再次 start-run → 新建(不复用 completed 的)。"""
    conn = get_connection(tmp_project)
    r1 = start_run(conn, chapter_global=7)
    end_run(conn, r1, "completed")
    r2 = start_run(conn, chapter_global=7)
    assert r2 != r1
    conn.close()


def test_emit_event_seq_monotonic_and_updates_current_node(tmp_project):
    conn = get_connection(tmp_project)
    rid = start_run(conn)
    s1 = emit_event(conn, rid, "write", "enter", {"iter": 1})
    s2 = emit_event(conn, rid, "write", "iteration", {"iter": 2})
    assert s1 == 1 and s2 == 2
    assert get_run(conn, rid)["current_node"] == "write"
    evs = list_events(conn, rid)
    assert [e["seq"] for e in evs] == [1, 2]
    assert evs[1]["payload"] == {"iter": 2}
    conn.close()


def test_emit_events_batch_contiguous_seq(tmp_project):
    conn = get_connection(tmp_project)
    rid = start_run(conn)
    n = emit_events_batch(conn, rid, [
        {"node": "boot", "kind": "start"},
        {"node": "write", "kind": "iteration", "payload": {"words": 3135, "rounds": 2}},
        {"node": "l2", "kind": "l2_verdict", "payload": {"passed": True}},
    ])
    assert n == 3
    evs = list_events(conn, rid)
    assert [e["seq"] for e in evs] == [1, 2, 3]
    assert get_run(conn, rid)["current_node"] == "l2"  # 末条 node
    assert evs[1]["payload"] == {"words": 3135, "rounds": 2}
    conn.close()


def test_batch_after_single_continues_seq(tmp_project):
    """单条 emit 后再 batch,seq 接续不重置。"""
    conn = get_connection(tmp_project)
    rid = start_run(conn)
    emit_event(conn, rid, "boot", "start")
    emit_events_batch(conn, rid, [{"node": "write", "kind": "enter"}, {"node": "revise", "kind": "enter"}])
    evs = list_events(conn, rid)
    assert [e["seq"] for e in evs] == [1, 2, 3]
    conn.close()


def test_empty_batch_noop(tmp_project):
    conn = get_connection(tmp_project)
    rid = start_run(conn)
    assert emit_events_batch(conn, rid, []) == 0
    assert list_events(conn, rid) == []
    conn.close()


def test_end_run_sets_status_and_ended(tmp_project):
    conn = get_connection(tmp_project)
    rid = start_run(conn)
    emit_event(conn, rid, "finalize", "enter")
    end_run(conn, rid, "completed", current_node="finalize")
    r = get_run(conn, rid)
    assert r["status"] == "completed"
    assert r["ended_at"] is not None
    assert r["current_node"] == "finalize"
    conn.close()


def test_end_run_rejects_bad_status(tmp_project):
    conn = get_connection(tmp_project)
    rid = start_run(conn)
    try:
        end_run(conn, rid, "oops")
        assert False
    except ValueError:
        pass
    conn.close()


def test_emit_rejects_unknown_run(tmp_project):
    conn = get_connection(tmp_project)
    try:
        emit_event(conn, 9999, "x", "y")
        assert False
    except ValueError:
        pass
    conn.close()


def test_cascade_delete_on_run_delete(tmp_project):
    """删 run 后 events 级联清掉（FK ON DELETE CASCADE）。"""
    conn = get_connection(tmp_project)
    conn.execute("PRAGMA foreign_keys=ON")
    rid = start_run(conn)
    emit_events_batch(conn, rid, [{"node": "write", "kind": "enter"}])
    assert conn.execute("SELECT COUNT(*) AS n FROM workflow_run_event WHERE run_id=?", (rid,)).fetchone()["n"] == 1
    conn.execute("DELETE FROM workflow_run WHERE id=?", (rid,))
    conn.commit()
    assert conn.execute("SELECT COUNT(*) AS n FROM workflow_run_event WHERE run_id=?", (rid,)).fetchone()["n"] == 0
    conn.close()


def test_list_recent_runs_order_and_count(tmp_project):
    conn = get_connection(tmp_project)
    r1 = start_run(conn, chapter_global=1)
    r2 = start_run(conn, chapter_global=2)
    emit_events_batch(conn, r2, [{"node": "write", "kind": "enter"}])
    runs = list_recent_runs(conn, limit=10)
    assert [x["id"] for x in runs] == [r2, r1]  # DESC
    by_id = {x["id"]: x for x in runs}
    assert by_id[r2]["event_count"] == 1
    assert by_id[r1]["event_count"] == 0
    conn.close()


def test_list_recent_runs_filter_by_chapter(tmp_project):
    conn = get_connection(tmp_project)
    start_run(conn, chapter_global=1)
    r2 = start_run(conn, chapter_global=5)
    runs = list_recent_runs(conn, chapter_global=5)
    assert len(runs) == 1 and runs[0]["id"] == r2
    conn.close()


def test_payload_corrupt_falls_back_to_empty(tmp_project):
    """payload 损坏时 list_events 不崩,回退 {}。"""
    conn = get_connection(tmp_project)
    rid = start_run(conn)
    conn.execute("INSERT INTO workflow_run_event(run_id,seq,node,kind,payload,ts) VALUES(?,1,'n','k','{bad','x')", (rid,))
    conn.commit()
    evs = list_events(conn, rid)
    assert evs[0]["payload"] == {}
    conn.close()


def test_migration_idempotent(tmp_project):
    from src.bedrock.db.migrate import apply_migrations
    apply_migrations(tmp_project)
    apply_migrations(tmp_project)
    conn = get_connection(tmp_project)
    n = conn.execute("SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table' AND name IN ('workflow_run','workflow_run_event')").fetchone()
    assert n["n"] == 2
    conn.close()


# ── run_telemetry:从 llm_call event 聚合 token/调用/耗时 ──

def test_run_telemetry_aggregates_llm_calls(tmp_project):
    from src.bedrock.workflow.run_repo import run_telemetry
    conn = get_connection(tmp_project)
    rid = start_run(conn, chapter_global=1, volume_id=1, runner="langgraph")
    # 模拟 write 1 次 + revise 1 次 + consistency 1 次 LLM 调用
    emit_event(conn, rid, "write", "llm_call",
               {"endpoint": "GLM", "model": "glm-5.2", "tokens_in": 1000, "tokens_out": 2000, "latency_ms": 5000})
    emit_event(conn, rid, "revise", "llm_call",
               {"endpoint": "GLM", "model": "glm-5.2", "tokens_in": 3000, "tokens_out": 1500, "latency_ms": 6000})
    emit_event(conn, rid, "consistency", "llm_call",
               {"endpoint": "GLM", "model": "glm-5.2", "tokens_in": 800, "tokens_out": 50, "latency_ms": 1000})
    end_run(conn, rid, "completed", current_node="finalize")
    t = run_telemetry(conn, rid)
    assert t["llm_calls"] == 3
    assert t["tokens_in"] == 4800       # 1000+3000+800
    assert t["tokens_out"] == 3550      # 2000+1500+50
    assert t["llm_time_ms"] == 12000
    # by_process 按 node 归并
    assert set(t["by_process"].keys()) == {"write", "revise", "consistency"}
    assert t["by_process"]["write"]["tokens_out"] == 2000
    assert t["by_process"]["consistency"]["calls"] == 1
    assert t["run_duration_s"] is not None and t["run_duration_s"] >= 0
    conn.close()


def test_run_telemetry_no_llm_calls(tmp_project):
    from src.bedrock.workflow.run_repo import run_telemetry
    conn = get_connection(tmp_project)
    rid = start_run(conn, chapter_global=2, volume_id=1, runner="langgraph")
    emit_event(conn, rid, "boot", "start", {"beats": 1})   # 非 llm_call
    end_run(conn, rid, "completed", current_node="finalize")
    t = run_telemetry(conn, rid)
    assert t["llm_calls"] == 0
    assert t["tokens_in"] == 0 and t["tokens_out"] == 0
    assert t["by_process"] == {}
    conn.close()
