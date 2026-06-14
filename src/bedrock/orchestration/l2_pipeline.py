# src/bedrock/orchestration/l2_pipeline.py
"""L2 trust-anchor orchestrator：单章全部重算（零 LLM）。

职责：
- 硬门禁：beat 兑现（check_beat_fulfillment）→ passed_hard_gate。
- advisory 重算：grep 风格指标 + 悬链消费 + 跨卷锚点。
- authoritative metrics：word_count / grep / consumption / beat_yield_rate。
- drift 检测：chapter_metrics.declared_json 与重算值差超 10% → drifted。
"""
import json
from dataclasses import dataclass, field, asdict

from src.bedrock.repositories.plot_tree import (
    list_paragraphs_in_chapter, list_beats_in_chapter,
)
from src.bedrock.repositories.telemetry import get_chapter_metrics
from src.bedrock.checks.beat_fulfillment import check_beat_fulfillment
from src.bedrock.checks.cross_volume import check_cross_volume_anchors
from src.bedrock.checks.word_count import compute_word_count
from src.bedrock.checks.grep_metrics import compute_grep_metrics
from src.bedrock.checks.consumption import compute_consumption

DRIFT_THRESHOLD = 0.10  # |Δ|/recomputed > 10% → drifted


def _volume_id_of_chapter(conn, chapter_id):
    row = conn.execute("SELECT volume_id FROM chapter WHERE id=?", (chapter_id,)).fetchone()
    return row["volume_id"] if row else None


def _drift_metric(declared, recomputed):
    """单指标 drift 检测。返回 {declared, recomputed, drifted}。

    当前仅用于 word_count（recomputed=0 = 空初稿，由硬门禁 unwritten_beat 兜住，
    不算 drift）。若日后扩到 grep/consumption（0 可能是合法重算值），需为各指标
    分别处理 0 分母语义，勿复用本函数的 recomputed==0 短路。"""
    if declared is None or recomputed is None:
        return {"declared": declared, "recomputed": recomputed, "drifted": False}
    if recomputed == 0:
        # word_count 专用：空初稿不算 drift（硬门禁兜底）
        return {"declared": declared, "recomputed": recomputed, "drifted": False}
    delta = abs(declared - recomputed)
    drifted = (delta / abs(recomputed)) > DRIFT_THRESHOLD
    return {"declared": declared, "recomputed": recomputed, "drifted": drifted}


@dataclass
class L2Report:
    beat_violations: list = field(default_factory=list)
    advisory: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    drift: dict = field(default_factory=dict)
    passed_hard_gate: bool = True


def run_l2(conn, chapter_id):
    """跑全部 L2 重算，分流硬门禁/advisory，检测 drift。纯 Python 零 LLM。"""
    volume_id = _volume_id_of_chapter(conn, chapter_id)
    paragraphs = [p["text"] for p in list_paragraphs_in_chapter(conn, chapter_id)]

    # 硬门禁：beat 兑现
    beat_violations = check_beat_fulfillment(conn, chapter_id)

    # advisory 重算
    grep = compute_grep_metrics(paragraphs)
    consumed, balance = compute_consumption(conn, chapter_id)
    cross = None
    if volume_id is not None:
        cross_report = check_cross_volume_anchors(conn, volume_id)
        # CrossVolumeDebtReport / Anchor 是 dataclass，转 dict 保证 JSON 可序列化。
        cross = {
            "blocking": [asdict(a) for a in cross_report.blocking],
            "advisory": [asdict(a) for a in cross_report.advisory],
        }

    # authoritative metrics
    wc = compute_word_count(paragraphs)
    total_beats = len(list_beats_in_chapter(conn, chapter_id))
    # yield = written/total；只数 unwritten_beat（结构缺失）。missing_character/
    # thread_not_advanced 是内容失败（已由 passed_hard_gate 兜），不算结构未兑现。
    unwritten = sum(1 for v in beat_violations if v.kind == "unwritten_beat")
    beat_yield = ((total_beats - unwritten) / total_beats) if total_beats else 0.0

    metrics = {
        "word_count": wc,
        "grep_metrics": grep,
        "threads_consumed": consumed,
        "consumption_balance": balance,
        "beat_yield_rate": beat_yield,
    }

    # drift：对比既有 chapter_metrics.declared_json
    drift = {}
    prev = get_chapter_metrics(conn, chapter_id)
    if prev is not None:
        declared = json.loads(prev["declared_json"]) if prev["declared_json"] else {}
        if "word_count_declared" in declared:
            drift["word_count"] = _drift_metric(declared["word_count_declared"], wc)

    advisory = {"grep": grep, "consumption": {"consumed": consumed, "balance": balance}}
    if cross is not None:
        advisory["cross_volume"] = cross

    return L2Report(
        beat_violations=beat_violations,
        advisory=advisory,
        metrics=metrics,
        drift=drift,
        passed_hard_gate=(len(beat_violations) == 0),
    )
