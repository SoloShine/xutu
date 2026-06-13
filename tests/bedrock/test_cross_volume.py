# tests/bedrock/test_cross_volume.py
from src.bedrock.db.connection import get_connection
from src.bedrock.checks.cross_volume import check_cross_volume_anchors
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat
from src.bedrock.repositories.suspense import plant_thread
from src.bedrock.repositories.outline import save_master_outline


def test_high_overdue_thread_blocks(tmp_project):
    """planned_resolve_volume<=V 且未 resolved 的 high 悬链 → blocking。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v1", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述")
    plant_thread(conn, content="x", thread_type="mystery", importance="high",
                 planted_at_beat=bid, origin="emergent", planned_resolve_volume=1)
    report = check_cross_volume_anchors(conn, 1)
    assert len(report.blocking) == 1
    assert report.blocking[0].kind == "thread_overdue"
    conn.close()


def test_medium_overdue_thread_advisory(tmp_project):
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v1", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述")
    plant_thread(conn, content="x", thread_type="mystery", importance="medium",
                 planted_at_beat=bid, origin="emergent", planned_resolve_volume=1)
    report = check_cross_volume_anchors(conn, 1)
    assert len(report.blocking) == 0
    assert len(report.advisory) == 1
    conn.close()


def test_null_planned_resolve_volume_not_flagged(tmp_project):
    """planned_resolve_volume IS NULL → 无跨卷承诺，不判逾期。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v1", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述")
    plant_thread(conn, content="x", thread_type="mystery", importance="high",
                 planted_at_beat=bid, origin="emergent")  # 无 planned_resolve_volume
    report = check_cross_volume_anchors(conn, 1)
    assert len(report.blocking) == 0
    assert len(report.advisory) == 0
    conn.close()


def test_milestone_unmet_blocks_when_high(tmp_project):
    """里程碑 resolves_threads 含未 resolved 的 high 悬链 → blocking。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v1", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述")
    tid = plant_thread(conn, content="x", thread_type="mystery", importance="high",
                       planted_at_beat=bid, origin="emergent")  # 未 resolved
    save_master_outline(conn, key_milestones=[
        {"name": "觉醒", "expected_volume": 1, "resolves_threads": [tid]}])
    report = check_cross_volume_anchors(conn, 1)
    assert any(a.kind == "milestone_unmet" for a in report.blocking)
    conn.close()
