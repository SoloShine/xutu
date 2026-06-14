# src/bedrock/checks/consumption.py
"""悬链消费重算（authoritative，零 LLM）。
权重：resolved×1.0 + developing×0.5 + mature×0.5 + partially_resolved×0.5 + abandoned×0.3
（abandoned 计 0.3 防批量凑配额；developing/mature 视为推进 0.5）
balance = consumed − 本章新种悬链数

语义：consumed 按 thread_consumption **行**求和（非按 thread 去重）。thread_consumption
有 UNIQUE(thread_id, beat_id, new_status)，故同一线程在本章多个 beat 推进会产生多行，
每行都计——一次推进 = 一份工作。scheduled/planted 不在 _WEIGHTS → 0.0（仅播种不算消费）。"""
from src.bedrock.repositories.plot_tree import list_beats_in_chapter

_WEIGHTS = {
    "resolved": 1.0,
    "developing": 0.5,
    "mature": 0.5,
    "partially_resolved": 0.5,
    "abandoned": 0.3,
}


def _global_chapter_number(conn, chapter_id):
    row = conn.execute("SELECT global_number FROM chapter WHERE id=?", (chapter_id,)).fetchone()
    return row["global_number"] if row else None


def compute_consumption(conn, chapter_id):
    """返回 (consumed, balance)。无 global_number 或无记录 → (0.0, 0.0)。
    consumed 按 thread_consumption 行求和（见模块 docstring 语义说明）。"""
    gnum = _global_chapter_number(conn, chapter_id)
    if gnum is None:
        return (0.0, 0.0)

    rows = conn.execute(
        "SELECT new_status FROM thread_consumption WHERE chapter=?", (gnum,)).fetchall()
    consumed = sum(_WEIGHTS.get(r["new_status"], 0.0) for r in rows)

    # 本章新种悬链 = planted_at_beat 落在本章某 beat 上的 suspense_thread 数
    beat_ids = [b["id"] for b in list_beats_in_chapter(conn, chapter_id)]
    planted = 0
    if beat_ids:
        placeholders = ",".join("?" * len(beat_ids))
        planted = conn.execute(
            f"SELECT COUNT(*) AS n FROM suspense_thread WHERE planted_at_beat IN ({placeholders})",
            beat_ids).fetchone()["n"]

    balance = consumed - planted
    return (consumed, balance)
