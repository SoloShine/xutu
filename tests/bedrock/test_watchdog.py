# tests/bedrock/test_watchdog.py
import json
from src.bedrock.db.connection import get_connection
from src.bedrock.orchestration.watchdog import run_watchdog, VolumeWatchdogReport
from src.bedrock.repositories.plot_tree import create_volume, create_chapter
from src.bedrock.repositories.telemetry import write_chapter_metrics


def _seed_volume_with_chapters(conn, n_chapters):
    vid = create_volume(conn, 1, "v", 1, n_chapters, "opening")
    cids = []
    for i in range(n_chapters):
        cid = create_chapter(conn, volume_id=vid, global_number=i + 1, title=f"t{i}")
        cids.append(cid)
    return vid, cids


def test_no_metrics_no_hug(tmp_project):
    conn = get_connection(tmp_project)
    vid, _ = _seed_volume_with_chapters(conn, 3)
    report = run_watchdog(conn, vid)
    assert isinstance(report, VolumeWatchdogReport)
    assert report.blocking is False   # 无 metrics，无发现
    conn.close()


def test_dash_hug_detected(tmp_project):
    """8/10 章 dash_per_kchar >= 0.85*3=2.55 → dash hug flagged → blocking。"""
    conn = get_connection(tmp_project)
    vid, cids = _seed_volume_with_chapters(conn, 10)
    for i, cid in enumerate(cids):
        dash = 2.6 if i < 8 else 0.5
        write_chapter_metrics(conn, cid,
                              grep_metrics={"notXisY_per_kchar": 0.0, "dash_per_kchar": dash, "period_density": 0.2})
    report = run_watchdog(conn, vid)
    assert report.hug_findings["dash_per_kchar"]["flagged"] is True
    assert report.hug_findings["dash_per_kchar"]["hug_ratio"] >= 0.70
    assert report.blocking is True
    conn.close()


def test_no_hug_when_below_ratio(tmp_project):
    """3/10 章贴边（< 70%）→ 不 flagged。"""
    conn = get_connection(tmp_project)
    vid, cids = _seed_volume_with_chapters(conn, 10)
    for i, cid in enumerate(cids):
        dash = 2.6 if i < 3 else 0.5
        write_chapter_metrics(conn, cid,
                              grep_metrics={"notXisY_per_kchar": 0.0, "dash_per_kchar": dash, "period_density": 0.2})
    report = run_watchdog(conn, vid)
    assert report.hug_findings["dash_per_kchar"]["flagged"] is False
    assert report.blocking is False
    conn.close()


def test_drift_aggregation(tmp_project):
    """6/10 章 advisory_drift 非空（>50%）→ drift_flagged → blocking。"""
    from src.bedrock.orchestration.review_flag import mark_advisory_drift
    conn = get_connection(tmp_project)
    vid, cids = _seed_volume_with_chapters(conn, 10)
    for i, cid in enumerate(cids):
        write_chapter_metrics(conn, cid,
                              grep_metrics={"notXisY_per_kchar": 0.0, "dash_per_kchar": 0.5, "period_density": 0.2})
        if i < 6:
            mark_advisory_drift(conn, cid, {"word_count": {"declared": 1, "recomputed": 2, "drifted": True}})
    report = run_watchdog(conn, vid)
    assert report.drift_ratio >= 0.50
    assert report.drift_flagged is True
    assert report.blocking is True
    conn.close()


def test_volume_review_row_written(tmp_project):
    conn = get_connection(tmp_project)
    vid, cids = _seed_volume_with_chapters(conn, 10)
    for cid in cids:
        write_chapter_metrics(conn, cid,
                              grep_metrics={"notXisY_per_kchar": 0.0, "dash_per_kchar": 2.6, "period_density": 0.2})
    run_watchdog(conn, vid)
    row = conn.execute("SELECT * FROM volume_review WHERE volume_id=?", (vid,)).fetchone()
    assert row is not None
    assert row["blocking"] == 1
    findings = json.loads(row["watchdog_findings"])
    assert "hug_findings" in findings
    conn.close()
