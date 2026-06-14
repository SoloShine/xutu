# src/bedrock/orchestration/cross_volume_gate.py
"""跨卷悬链收敛门禁：dispatch 下一卷前查 planned_resolve_volume <= 本卷 number 的 high 未兑现悬链。
纯 Python。卷间 BLOCKING：非空 → dispatch 下一卷被阻断。
注意：planned_resolve_volume 存卷 number（非 id）；仅 high BLOCKING。

⚠️ 与 SP2 check_cross_volume_anchors 的比较器分歧（已知，待 SP2 修）：
   - SP5 本函数：planned_resolve_volume <= volume.number（正确，number 是卷序号）
   - SP2 cross_volume.py：planned_resolve_volume <= volume_id（传 raw id，autoincrement，
     id≠number 时比较错位——SP2 latent bug）
   本函数用 number 才是对的。SP2 修复后两者才真正单一真相。"""
from dataclasses import dataclass, field


@dataclass
class CrossVolumeDebtReport:
    volume_id: int
    unresolved_threads: list = field(default_factory=list)   # [{thread_id, content, importance}]
    blocking: bool = False


def check_cross_volume_debt(conn, volume_id):
    """volume_id → volume.number → 查 planned_resolve_volume<=number AND high AND 未兑现。
    卷间 BLOCKING：若欠债，OR 进 volume_review.blocking（与 watchdog 同字段，单一真相）。
    不 reset 为 0——blocking 的清零由 run_watchdog 重跑负责；本函数只升不降。"""
    vrow = conn.execute("SELECT number FROM volume WHERE id=?", (volume_id,)).fetchone()
    if vrow is None:
        return CrossVolumeDebtReport(volume_id=volume_id)
    volume_number = vrow["number"]

    rows = conn.execute(
        "SELECT id, content, importance FROM suspense_thread "
        "WHERE planned_resolve_volume IS NOT NULL AND planned_resolve_volume<=? "
        "AND importance='high' AND status NOT IN ('resolved','abandoned')",
        (volume_number,)).fetchall()
    unresolved = [{"thread_id": r["id"], "content": r["content"], "importance": r["importance"]}
                  for r in rows]
    blocking = len(unresolved) > 0

    # I1 修正：欠债时 OR 进 volume_review.blocking（与 watchdog 共享门禁字段）。
    # 只升不降——清零由 run_watchdog 重跑负责（§六.0 顺序：watchdog 先跑设基线，本函数后跑只加不减）。
    if blocking:
        conn.execute(
            "INSERT INTO volume_review(volume_id, blocking) VALUES(?, 1) "
            "ON CONFLICT(volume_id) DO UPDATE SET blocking=1",
            (volume_id,))
        conn.commit()

    return CrossVolumeDebtReport(
        volume_id=volume_id,
        unresolved_threads=unresolved,
        blocking=blocking,
    )
