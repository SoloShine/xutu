# tests/bedrock/test_watchdog_drift.py
"""Unit C:watchdog 计真实 drift(非快照)+ 卷级连续同向门控。"""
import json

from src.bedrock.db.connection import get_connection
from src.bedrock.orchestration.watchdog import run_watchdog
from src.bedrock.repositories.plot_tree import create_chapter, create_volume


def make_volume_with_chapters(tmp_project, n=3):
    """建项目 + 1 卷 + n 章,返回 (project_dir, volume_id, [chapter_ids])。
    tmp_project 由 conftest 的 tmp_project fixture 提供(已 apply_migrations)。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, n, "opening")
    cids = []
    for i in range(n):
        cids.append(create_chapter(conn, volume_id=vid, global_number=i + 1, title=f"t{i}"))
    conn.commit()
    conn.close()
    return tmp_project, vid, cids


def _flag(conn, cid, drifted, ok=True):
    conn.execute("INSERT OR IGNORE INTO chapter_review_flag(chapter_id) VALUES(?)", (cid,))
    conn.execute("UPDATE chapter_review_flag SET advisory_drift=? WHERE chapter_id=?",
                 (json.dumps({"drifted": drifted, "ok": ok}, ensure_ascii=False), cid))


def _metrics(conn, cids):
    for cid in cids:
        conn.execute("INSERT OR IGNORE INTO chapter_metrics(chapter_id,grep_metrics) VALUES(?,?)",
                     (cid, "{}"))


def test_counts_real_drift_not_snapshot(tmp_project):
    proj, vol_id, cids = make_volume_with_chapters(tmp_project, n=3)
    conn = get_connection(proj)
    for cid in cids:
        _flag(conn, cid, drifted=[])   # 有快照但 drifted 空
    _metrics(conn, cids); conn.commit()
    run_watchdog(conn, vol_id)
    row = conn.execute("SELECT watchdog_findings,blocking FROM volume_review WHERE volume_id=?", (vol_id,)).fetchone()
    find = json.loads(row["watchdog_findings"])
    assert find["drift_ratio"] == 0.0          # bug 修后:drifted 全空 → 0
    assert find["drift_flagged"] is False
    assert row["blocking"] == 0
    conn.close()


def test_consecutive_same_direction_flags(tmp_project):
    proj, vol_id, cids = make_volume_with_chapters(tmp_project, n=3)
    conn = get_connection(proj)
    d = [{"metric": "rhetoric_per_k", "actual": 6.0, "target": 1.69, "severity": 3.6, "hint": "修辞过密"}]
    for cid in cids:
        _flag(conn, cid, drifted=d, ok=False)
    _metrics(conn, cids); conn.commit()
    run_watchdog(conn, vol_id)
    row = conn.execute("SELECT watchdog_findings,blocking FROM volume_review WHERE volume_id=?", (vol_id,)).fetchone()
    find = json.loads(row["watchdog_findings"])
    assert find["drift_flagged"] is True       # 3 章连续同指标同向
    assert row["blocking"] == 1
    assert "rhetoric_per_k" in find.get("consecutive_drift_metrics", [])
    conn.close()


def test_non_consecutive_does_not_flag(tmp_project):
    proj, vol_id, cids = make_volume_with_chapters(tmp_project, n=4)
    conn = get_connection(proj)
    d = [{"metric": "rhetoric_per_k", "actual": 6.0, "target": 1.69, "severity": 3.6, "hint": "修辞过密"}]
    # 仅 ch1 和 ch3 drift(不连续)→ 不 flag
    _flag(conn, cids[0], drifted=d, ok=False)
    _flag(conn, cids[1], drifted=[], ok=True)
    _flag(conn, cids[2], drifted=d, ok=False)
    _flag(conn, cids[3], drifted=[], ok=True)
    _metrics(conn, cids); conn.commit()
    run_watchdog(conn, vol_id)
    row = conn.execute("SELECT watchdog_findings FROM volume_review WHERE volume_id=?", (vol_id,)).fetchone()
    find = json.loads(row["watchdog_findings"])
    assert find["drift_flagged"] is False
    conn.close()
