# src/bedrock/orchestration/watchdog.py
"""跨章 statistical watchdog：检测贴边走（threshold-hugging）+ drift 聚合。纯 Python 零 LLM。
卷间 BLOCKING：任一 flag → volume_review.blocking=1，dispatch 下一卷被阻断。"""
import json
from dataclasses import dataclass, field

WATCHDOG_HUG_RATIO = 0.70        # ≥70% 章贴边 → flagged
WATCHDOG_THRESHOLD_BAND = 0.85   # 值 >= 0.85*max 算"贴边"
WATCHDOG_DRIFT_RATIO = 0.50      # >50% 章 drift 非空 → drift_flagged

# 起步只检测上界指标（dash/notXisY per-kchar）；period/word_count 区间贴边后置（YAGNI）
_METRIC_THRESHOLDS = {
    "dash_per_kchar": 3.0,        # config dashes_per_k_max
    "notXisY_per_kchar": 1.5,     # ≈ 每 4000 字 6 处（config notXisY_max=5 量级）
}


@dataclass
class VolumeWatchdogReport:
    volume_id: int
    hug_findings: dict = field(default_factory=dict)   # {metric: {hug_ratio, threshold, flagged}}
    drift_ratio: float = 0.0
    drift_flagged: bool = False
    blocking: bool = False


def _chapter_ids_in_volume(conn, volume_id):
    rows = conn.execute("SELECT id FROM chapter WHERE volume_id=?", (volume_id,)).fetchall()
    return [r["id"] for r in rows]


def run_watchdog(conn, volume_id):
    """跨章读 chapter_metrics，检测贴边走 + drift 聚合，写 volume_review 行。"""
    cids = _chapter_ids_in_volume(conn, volume_id)
    n = len(cids)

    hug_findings = {}
    if n > 0:
        per_metric_values = {m: [] for m in _METRIC_THRESHOLDS}
        for cid in cids:
            row = conn.execute("SELECT grep_metrics FROM chapter_metrics WHERE chapter_id=?",
                               (cid,)).fetchone()
            if row is None:
                for m in _METRIC_THRESHOLDS:
                    per_metric_values[m].append(None)
                continue
            gm = json.loads(row["grep_metrics"]) if row["grep_metrics"] else {}
            for m in _METRIC_THRESHOLDS:
                per_metric_values[m].append(gm.get(m))

        for metric, threshold in _METRIC_THRESHOLDS.items():
            values = per_metric_values[metric]
            valid = [v for v in values if v is not None]
            if not valid:
                continue
            band = threshold * WATCHDOG_THRESHOLD_BAND
            hugging = sum(1 for v in valid if v >= band)
            ratio = hugging / len(valid)
            hug_findings[metric] = {
                "hug_ratio": ratio,
                "threshold": threshold,
                "flagged": ratio >= WATCHDOG_HUG_RATIO,
            }

    drift_ratio = 0.0
    if n > 0:
        drift_nonempty = 0
        for cid in cids:
            row = conn.execute("SELECT advisory_drift FROM chapter_review_flag WHERE chapter_id=?",
                               (cid,)).fetchone()
            if row is not None and row["advisory_drift"] and row["advisory_drift"] != "{}":
                drift_nonempty += 1
        drift_ratio = drift_nonempty / n
    drift_flagged = drift_ratio > WATCHDOG_DRIFT_RATIO

    blocking = any(f["flagged"] for f in hug_findings.values()) or drift_flagged

    report = VolumeWatchdogReport(
        volume_id=volume_id,
        hug_findings=hug_findings,
        drift_ratio=drift_ratio,
        drift_flagged=drift_flagged,
        blocking=blocking,
    )

    findings_json = json.dumps({
        "hug_findings": hug_findings,
        "drift_ratio": drift_ratio,
        "drift_flagged": drift_flagged,
    }, ensure_ascii=False)
    conn.execute(
        "INSERT INTO volume_review(volume_id, watchdog_findings, blocking) VALUES(?,?,?) "
        "ON CONFLICT(volume_id) DO UPDATE SET watchdog_findings=excluded.watchdog_findings, "
        "blocking=excluded.blocking",
        (volume_id, findings_json, 1 if blocking else 0))
    conn.commit()

    return report
