# tests/bedrock/test_suspense.py
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.suspense import (
    plant_thread, record_consumption, get_thread, consumed_by_thread,
    IllegalTransition,
)


def _seed_beat(conn):
    from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    return create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述")


def test_thread_lifecycle_and_consumption(tmp_project):
    conn = get_connection(tmp_project)
    b1 = _seed_beat(conn)
    tid = plant_thread(conn, content="书的来源", thread_type="mystery",
                       importance="high", planted_at_beat=b1, origin="scheduled",
                       planned_plant_volume=1, planned_resolve_volume=3)
    t = get_thread(conn, tid)
    assert t["status"] == "planted"
    record_consumption(conn, thread_id=tid, beat_id=b1, new_status="developing", chapter=1)
    assert get_thread(conn, tid)["status"] == "developing"
    assert len(consumed_by_thread(conn, tid)) == 1
    conn.close()


def test_illegal_transition_rejected(tmp_project):
    conn = get_connection(tmp_project)
    b1 = _seed_beat(conn)
    tid = plant_thread(conn, content="x", thread_type="mystery", importance="high",
                       planted_at_beat=b1, origin="emergent")
    record_consumption(conn, thread_id=tid, beat_id=b1, new_status="developing", chapter=1)
    with pytest.raises(IllegalTransition):
        record_consumption(conn, thread_id=tid, beat_id=b1, new_status="planted", chapter=2)
    conn.close()


def test_resolved_implies_resolved_at_beat(tmp_project):
    conn = get_connection(tmp_project)
    b1 = _seed_beat(conn)
    tid = plant_thread(conn, content="x", thread_type="mystery", importance="high",
                       planted_at_beat=b1, origin="emergent")
    record_consumption(conn, thread_id=tid, beat_id=b1, new_status="resolved", chapter=1)
    t = get_thread(conn, tid)
    assert t["status"] == "resolved"
    assert t["resolved_at_beat"] == b1
    conn.close()


def test_planted_to_resolved_requires_high_importance(tmp_project):
    """spec §3.3: planted→resolved 禁跳除非 high importance。"""
    conn = get_connection(tmp_project)
    b1 = _seed_beat(conn)
    # medium importance 不能 planted→resolved
    tid = plant_thread(conn, content="x", thread_type="mystery", importance="medium",
                       planted_at_beat=b1, origin="emergent")
    with pytest.raises(IllegalTransition):
        record_consumption(conn, thread_id=tid, beat_id=b1, new_status="resolved", chapter=1)
    # high importance 可以
    tid2 = plant_thread(conn, content="y", thread_type="mystery", importance="high",
                        planted_at_beat=b1, origin="emergent")
    record_consumption(conn, thread_id=tid2, beat_id=b1, new_status="resolved", chapter=1)
    assert get_thread(conn, tid2)["status"] == "resolved"
    conn.close()
