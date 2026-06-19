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
    if not fields:
        # 空 fields(ensure_flag)只需保证行存在,跳过 UPDATE(空 SET 子句是 SQL 语法错)。
        conn.commit()
        return
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


def mark_advisory_drift(conn, chapter_id, drift):
    """持久化 L2Report.drift（SP5 VolumeReview 读，识别自报造假高亮章）。
    drift = {metric: {declared, recomputed, drifted}}（来自 run_l2 的 report.drift）。

    读改合并:保留 advisory_drift 既有兄弟键(如 proper_noun_autoedit),不整体覆盖。
    工作流里专名校验(phase 4b2)先于 finalize 的 mark-advisory-drift(phase 5),
    整体替换会静默吞掉专名自动改的审计痕迹。"""
    row = conn.execute(
        "SELECT advisory_drift FROM chapter_review_flag WHERE chapter_id=?",
        (chapter_id,)).fetchone()
    existing = {}
    if row and row["advisory_drift"] and row["advisory_drift"] != "{}":
        try:
            existing = json.loads(row["advisory_drift"])
        except (ValueError, TypeError):
            existing = {}
    existing.update(drift)  # drift 键覆盖,保留 proper_noun_autoedit 等兄弟键
    _upsert(conn, chapter_id, {"advisory_drift": json.dumps(existing, ensure_ascii=False)})


def ensure_flag(conn, chapter_id):
    """A3:无条件保证 flag 行存在(零违规/零 drift 也建)。幂等。

    verify-persisted 末尾调用,治"过 L2 修复轮的章无 flag 行"漏判
    (has_flag 取不到 flag=None 而漏标)。_upsert({}) 走 INSERT OR IGNORE + 空 UPDATE。"""
    _upsert(conn, chapter_id, {})


def get_review_flag(conn, chapter_id):
    row = conn.execute(
        "SELECT * FROM chapter_review_flag WHERE chapter_id=?", (chapter_id,)).fetchone()
    return dict(row) if row else None


def compute_has_flag(flag):
    """任一硬 flag != 0 或 advisory_drift 有真实内容 → True。
    likely_rule_or_model_issue 不计入（l2_unresolved 的诊断子字段）。flag=None → False。

    advisory_drift 判空走语义:仅当存在非空 drifted 列表或非空 proper_noun_autoedit 列表才计 flag。
    finalize 永远写完整 style-drift dict({"drifted":[],"ok":true,...}),字符串比对 '{}' 会让每章恒 True,
    击穿 VolumeReview 的 has_flag 章过滤——故此处 JSON 解析后检真实内容。"""
    if flag is None:
        return False
    advisory = flag.get("advisory_drift")
    advisory_flagged = False
    if advisory and advisory != "{}":
        try:
            d = json.loads(advisory)
        except (ValueError, TypeError):
            d = None
        # malformed → 保守 flag;否则仅有真实 drift/自动改才 flag
        if d is None or d.get("drifted") or d.get("proper_noun_autoedit"):
            advisory_flagged = True
    return (flag.get("l2_unresolved", 0) != 0
            or flag.get("polish_broke_beat", 0) != 0
            or flag.get("forced_persist_failed", 0) != 0
            or advisory_flagged)
