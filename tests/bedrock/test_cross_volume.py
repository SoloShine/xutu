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


def test_milestone_invalid_thread_ref_flagged(tmp_project):
    """里程碑 resolves_threads 含无效 id（表里没有）→ 报 milestone_unmet。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v1", 1, 3, "opening")
    save_master_outline(conn, key_milestones=[
        {"name": "觉醒", "expected_volume": 1, "resolves_threads": [99999]}])  # 无效 id
    report = check_cross_volume_anchors(conn, 1)
    assert any(a.kind == "milestone_unmet" for a in report.blocking)
    conn.close()


def test_uses_volume_number_not_id(tmp_project):
    """回归（SP2 follow-up）：volume.id != volume.number 时，比较器必须用 number。
    构造 id≠number：先建卷 number=2（id=1），再建 number=1（id=2）。
    在 number=1 的卷（id=2）视角查：一条 planned_resolve_volume=2 的 high 未兑现悬链——
    按 number 比较 2<=1 为假（不 blocking）；若错用 id=2 比较 2<=2 为真（会误 blocking）。"""
    conn = get_connection(tmp_project)
    create_volume(conn, 2, "v2", 4, 6, "opening")            # number=2, id=1
    vid_num1 = create_volume(conn, 1, "v1", 1, 3, "opening")  # number=1, id=2
    assert vid_num1 == 2   # 确认 id≠number（id=2, number=1）
    cid = create_chapter(conn, volume_id=vid_num1, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述")
    plant_thread(conn, content="x", thread_type="mystery", importance="high",
                 planted_at_beat=bid, origin="emergent", planned_resolve_volume=2)
    report = check_cross_volume_anchors(conn, vid_num1)   # 本卷 number=1
    # 2 <= 1（number）为假 → 不 blocking；若错用 id=2：2<=2 真 → 误 blocking（测试会失败）
    assert len(report.blocking) == 0
    conn.close()
