# tests/bedrock/test_consumption.py
from src.bedrock.db.connection import get_connection
from src.bedrock.checks.consumption import compute_consumption
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat, create_paragraph,
)


def _seed(conn):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=5, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="plant-seed")  # purpose >= 10 chars (CHECK)
    create_paragraph(conn, chapter_id=cid, seq=1, text="x。",
                     content_hash="h", beat_id=bid, role="narration")
    return vid, cid, bid


def _record(conn, thread_id, beat_id, new_status, chapter):
    conn.execute(
        "INSERT INTO thread_consumption(thread_id,beat_id,new_status,chapter) VALUES(?,?,?,?)",
        (thread_id, beat_id, new_status, chapter))
    conn.commit()


def _plant_thread(conn, tid, planted_at_beat):
    conn.execute(
        "INSERT INTO suspense_thread(id,content,thread_type,importance,origin,status,planted_at_beat) "
        "VALUES(?,?,?,?,?,?,?)",
        (tid, "c", "mystery", "high", "scheduled", "developing", planted_at_beat))
    conn.commit()


def test_no_consumption_returns_zeros(tmp_project):
    conn = get_connection(tmp_project)
    _, cid, _ = _seed(conn)
    consumed, balance = compute_consumption(conn, cid)
    assert consumed == 0.0
    assert balance == 0.0
    conn.close()


def test_consumed_weights(tmp_project):
    """resolved×1.0 + developing×0.5 + partially_resolved×0.5 + abandoned×0.3 = 2.3"""
    conn = get_connection(tmp_project)
    _, cid, bid = _seed(conn)
    for tid in (1, 2, 3, 4):
        _plant_thread(conn, tid, bid)
    _record(conn, 1, bid, "resolved", 5)
    _record(conn, 2, bid, "developing", 5)
    _record(conn, 3, bid, "partially_resolved", 5)
    _record(conn, 4, bid, "abandoned", 5)
    consumed, balance = compute_consumption(conn, cid)
    assert abs(consumed - 2.3) < 1e-6
    conn.close()


def test_balance_subtracts_new_planted(tmp_project):
    """balance = consumed − 本章新种悬链数。"""
    conn = get_connection(tmp_project)
    _, cid, bid = _seed(conn)
    _plant_thread(conn, 1, bid)   # 本章新种 1 条
    _record(conn, 1, bid, "resolved", 5)  # consumed 1.0
    consumed, balance = compute_consumption(conn, cid)
    assert abs(consumed - 1.0) < 1e-6
    assert abs(balance - 0.0) < 1e-6   # 1.0 − 1 = 0.0
    conn.close()


def test_balance_negative_when_only_planting(tmp_project):
    conn = get_connection(tmp_project)
    _, cid, bid = _seed(conn)
    _plant_thread(conn, 1, bid)
    _plant_thread(conn, 2, bid)   # 新种 2，无消费
    consumed, balance = compute_consumption(conn, cid)
    assert consumed == 0.0
    assert abs(balance - (-2.0)) < 1e-6
    conn.close()
