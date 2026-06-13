# src/bedrock/repositories/suspense.py
from src.bedrock.enums import LEGAL_THREAD_TRANSITIONS, ThreadStatus


class IllegalTransition(Exception):
    pass


def plant_thread(conn, content, thread_type, importance, planted_at_beat,
                 origin, planned_plant_volume=None, planned_resolve_volume=None,
                 status="planted"):
    cur = conn.execute(
        "INSERT INTO suspense_thread(content,thread_type,importance,origin,status,"
        "planted_at_beat,planned_plant_volume,planned_resolve_volume) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (content, thread_type, importance, origin, status, planted_at_beat,
         planned_plant_volume, planned_resolve_volume))
    conn.commit()
    return cur.lastrowid


def get_thread(conn, thread_id):
    return conn.execute("SELECT * FROM suspense_thread WHERE id=?", (thread_id,)).fetchone()


def consumed_by_thread(conn, thread_id):
    """单向 SSOT：从 thread 反查哪些 beat 消费过它。"""
    return conn.execute(
        "SELECT * FROM thread_consumption WHERE thread_id=? ORDER BY chapter",
        (thread_id,)).fetchall()


def threads_advanced_at_beat(conn, beat_id):
    """beat 反查：这个 beat 推进了哪些悬链（派生视图，替代 beat.advance_threads）。"""
    return conn.execute(
        "SELECT thread_id, new_status FROM thread_consumption WHERE beat_id=?",
        (beat_id,)).fetchall()


def record_consumption(conn, thread_id, beat_id, new_status, chapter):
    """记录 beat 对悬链的消费（推进/回收）。校验状态机迁移合法性。"""
    prev_row = get_thread(conn, thread_id)
    if prev_row is None:
        raise ValueError(f"thread {thread_id} not found")
    prev = ThreadStatus(prev_row["status"])
    target = ThreadStatus(new_status)
    if target not in LEGAL_THREAD_TRANSITIONS.get(prev, set()):
        raise IllegalTransition(f"{prev.value}→{target.value} 非法迁移 (thread {thread_id})")
    if prev == ThreadStatus.PLANTED and target == ThreadStatus.RESOLVED:
        # spec §3.3: planted→resolved 禁跳，除非 importance=high
        if prev_row["importance"] != "high":
            raise IllegalTransition(
                f"planted→resolved 需 importance=high (thread {thread_id}, "
                f"实际 {prev_row['importance']})")

    resolved_beat = beat_id if target == ThreadStatus.RESOLVED else None
    conn.execute(
        "INSERT OR IGNORE INTO thread_consumption(thread_id,beat_id,new_status,chapter) "
        "VALUES(?,?,?,?)", (thread_id, beat_id, new_status, chapter))
    if target == ThreadStatus.RESOLVED:
        conn.execute(
            "UPDATE suspense_thread SET status=?, resolved_at_beat=? WHERE id=?",
            (new_status, resolved_beat, thread_id))
    else:
        conn.execute(
            "UPDATE suspense_thread SET status=? WHERE id=?", (new_status, thread_id))
    conn.commit()


def threads_planted_at_beat(conn, beat_id):
    return conn.execute(
        "SELECT thread_id FROM thread_planting WHERE beat_id=?", (beat_id,)).fetchall()


def declare_planting(conn, beat_id, thread_id):
    conn.execute(
        "INSERT OR IGNORE INTO thread_planting(beat_id,thread_id) VALUES(?,?)",
        (beat_id, thread_id))
    conn.commit()
