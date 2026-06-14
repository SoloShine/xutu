# tests/bedrock/test_l2_pipeline.py
from src.bedrock.db.connection import get_connection
from src.bedrock.orchestration.l2_pipeline import run_l2, L2Report
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat, create_paragraph,
    update_beat_status,
)
from src.bedrock.repositories.outline import (
    save_volume_outline, lock_volume_outline, unlock_volume_outline, update_beat_contract,
)


# purpose 必须 ≥10 chars（schema CHECK(length(purpose) >= 10)）。
_BEAT_PURPOSE = "林深推门走进房间里面"  # 10 chars


def _seed_clean(conn):
    """一个 beat clean 的章节（段落 + beat 推进到 written + 契约 advance_threads 空）。"""
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose=_BEAT_PURPOSE)
    create_paragraph(conn, chapter_id=cid, seq=1, text="林深推开门走了进来。",
                     content_hash="h", beat_id=bid, role="narration")
    save_volume_outline(conn, vid, beat_contracts=[])
    lock_volume_outline(conn, vid)
    unlock_volume_outline(conn, vid, reason="setup", author="system")
    update_beat_contract(conn, vid, beat_id=bid,
                         new_contract={"purpose": _BEAT_PURPOSE,
                                       "participating_characters": [], "advance_threads": []})
    # 推进 beat 状态：planned → written（clean seed 不能停在 planned）
    update_beat_status(conn, bid, "written")
    return vid, cid, bid


def test_l2report_shape(tmp_project):
    conn = get_connection(tmp_project)
    _, cid, _ = _seed_clean(conn)
    report = run_l2(conn, cid)
    assert isinstance(report, L2Report)
    assert "grep" in report.advisory
    assert "consumption" in report.advisory
    assert "word_count" in report.metrics
    assert isinstance(report.passed_hard_gate, bool)
    assert isinstance(report.drift, dict)
    conn.close()


def test_hard_gate_fails_on_unwritten_beat(tmp_project):
    """planned beat（未推进）→ unwritten_beat violation → passed_hard_gate False。"""
    conn = get_connection(tmp_project)
    _, cid, bid = _seed_clean(conn)
    # 删除段落 + 把 beat 退回 planned，模拟未写
    conn.execute("DELETE FROM paragraph WHERE chapter_id=?", (cid,))
    conn.execute("UPDATE beat SET status='planned' WHERE id=?", (bid,))
    conn.commit()
    report = run_l2(conn, cid)
    assert report.passed_hard_gate is False
    assert any(v.kind == "unwritten_beat" for v in report.beat_violations)
    conn.close()


def test_drift_detection(tmp_project):
    """declared word_count 与重算差超 10% → drift[word_count].drifted True。"""
    conn = get_connection(tmp_project)
    _, cid, _ = _seed_clean(conn)
    from src.bedrock.repositories.telemetry import write_chapter_metrics
    write_chapter_metrics(conn, cid, word_count=9999, declared={"word_count_declared": 9999})
    report = run_l2(conn, cid)
    assert report.drift.get("word_count", {}).get("drifted") is True
    conn.close()


def test_advisory_populated(tmp_project):
    conn = get_connection(tmp_project)
    _, cid, _ = _seed_clean(conn)
    report = run_l2(conn, cid)
    assert "notXisY_per_kchar" in report.advisory["grep"]
    assert "consumed" in report.advisory["consumption"]
    conn.close()
