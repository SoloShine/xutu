# src/bedrock/orchestration/review_flag.py
"""chapter_review_flag 写回（SP5 VolumeReview 消费）。"""
import json
from dataclasses import asdict

# _upsert 允许写入的列（白名单，防列名 f-string 注入脚枪）
_ALLOWED_FLAG_COLUMNS = frozenset({
    "l2_unresolved", "persisted_violations", "likely_rule_or_model_issue",
    "polish_broke_beat", "forced_persist_failed", "advisory_drift",
})


def _beat_violation_to_dict(v):
    """BeatViolation dataclass → dict（含 fix_hint/detail）。"""
    try:
        return asdict(v)
    except TypeError:
        return {"beat_id": getattr(v, "beat_id", None), "kind": getattr(v, "kind", ""),
                "detail": getattr(v, "detail", ""), "fix_hint": getattr(v, "fix_hint", "")}


def _upsert(conn, chapter_id, fields):
    """INSERT OR UPDATE chapter_review_flag（保留既有列）。

    flagged_at 仅在首次 INSERT 时设（datetime('now') 默认值），后续 UPDATE 不动它——
    记录"首次标记时间"，非"最后更新时间"。"""
    bad = set(fields) - _ALLOWED_FLAG_COLUMNS
    if bad:
        raise ValueError(f"unknown review_flag columns: {sorted(bad)}")
    conn.execute(
        "INSERT INTO chapter_review_flag(chapter_id) VALUES(?) "
        "ON CONFLICT(chapter_id) DO NOTHING", (chapter_id,))
    set_clause = ", ".join(f"{k}=?" for k in fields)
    conn.execute(
        f"UPDATE chapter_review_flag SET {set_clause} WHERE chapter_id=?",
        [*fields.values(), chapter_id])
    conn.commit()


def mark_unresolved(conn, chapter_id, persisted_violations, likely_rule_or_model_issue):
    """3 轮重试耗尽：l2_unresolved=1 + persisted_violations JSON。"""
    pv = [_beat_violation_to_dict(v) for v in persisted_violations]
    _upsert(conn, chapter_id, {
        "l2_unresolved": 1,
        "persisted_violations": json.dumps(pv, ensure_ascii=False),
        "likely_rule_or_model_issue": 1 if likely_rule_or_model_issue else 0,
    })


def mark_polish_broke_beat(conn, chapter_id):
    _upsert(conn, chapter_id, {"polish_broke_beat": 1})


def mark_forced_persist_failed(conn, chapter_id):
    _upsert(conn, chapter_id, {"forced_persist_failed": 1})


def get_review_flag(conn, chapter_id):
    row = conn.execute(
        "SELECT * FROM chapter_review_flag WHERE chapter_id=?", (chapter_id,)).fetchone()
    return dict(row) if row else None
