# src/bedrock/checks/cross_volume.py
import json
from dataclasses import dataclass, field
from src.bedrock.repositories.outline import get_master_outline


@dataclass
class Anchor:
    kind: str          # "thread_overdue" | "milestone_unmet"
    ref_id: str        # 悬链 id 或里程碑 name
    importance: str    # high/medium/low
    detail: str


@dataclass
class CrossVolumeDebtReport:
    blocking: list = field(default_factory=list)   # high 未兑现
    advisory: list = field(default_factory=list)   # medium/low 未兑现


def _classify(anchor, report):
    if anchor.importance == "high":
        report.blocking.append(anchor)
    else:
        report.advisory.append(anchor)


def _max_importance(importances):
    rank = {"high": 3, "medium": 2, "low": 1}
    return max(importances, key=lambda i: rank.get(i, 0))


def check_cross_volume_anchors(conn, volume_id):
    """卷收尾时检查跨卷锚点兑现。high 未兑现 → blocking；其他 → advisory。"""
    report = CrossVolumeDebtReport()

    # 1. 悬链 planned_resolve_volume 兑现
    rows = conn.execute(
        "SELECT id, content, importance, status FROM suspense_thread "
        "WHERE planned_resolve_volume IS NOT NULL AND planned_resolve_volume <= ? "
        "AND status NOT IN ('resolved','abandoned')",
        (volume_id,)).fetchall()
    for r in rows:
        _classify(Anchor(
            kind="thread_overdue", ref_id=str(r["id"]),
            importance=r["importance"],
            detail=f"悬链 {r['id']}（{r['content'][:20]}）应于卷{volume_id}回收但 status={r['status']}"),
            report)

    # 2. 里程碑兑现
    mo = get_master_outline(conn)
    if mo:
        milestones = json.loads(mo["key_milestones"]) if mo["key_milestones"] else []
        for ms in milestones:
            if ms.get("expected_volume") != volume_id:
                continue
            resolves = ms.get("resolves_threads", [])
            if not resolves:
                continue
            placeholders = ",".join("?" * len(resolves))
            threads = conn.execute(
                f"SELECT id, importance, status FROM suspense_thread WHERE id IN ({placeholders})",
                resolves).fetchall()
            unmet = [t for t in threads if t["status"] != "resolved"]
            if unmet:
                max_imp = _max_importance([t["importance"] for t in unmet])
                _classify(Anchor(
                    kind="milestone_unmet", ref_id=ms.get("name", "?"),
                    importance=max_imp,
                    detail=f"里程碑 {ms.get('name')} 的 resolves_threads 有 {len(unmet)} 条未 resolved"),
                    report)

    return report
