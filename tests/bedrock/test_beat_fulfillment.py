# tests/bedrock/test_beat_fulfillment.py
from src.bedrock.db.connection import get_connection
from src.bedrock.checks.beat_fulfillment import check_beat_fulfillment
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat, create_paragraph, update_beat_status,
)
from src.bedrock.repositories.beat_link import link_beat_character
from src.bedrock.repositories.character import create_character
from src.bedrock.repositories.outline import save_volume_outline, lock_volume_outline, unlock_volume_outline, update_beat_contract


def _seed_chapter_with_beat(conn):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="林深发现旧书摊的诡异注记")
    save_volume_outline(conn, vid, beat_contracts=[])
    lock_volume_outline(conn, vid)
    unlock_volume_outline(conn, vid, reason="setup", author="system")
    return vid, cid, bid


def test_unwritten_beat_violation(tmp_project):
    conn = get_connection(tmp_project)
    vid, cid, bid = _seed_chapter_with_beat(conn)
    vs = check_beat_fulfillment(conn, cid)
    assert "unwritten_beat" in [v.kind for v in vs]
    conn.close()


def test_missing_character_violation(tmp_project):
    conn = get_connection(tmp_project)
    vid, cid, bid = _seed_chapter_with_beat(conn)
    cid2 = create_chapter(conn, volume_id=vid, global_number=2, title="t2")
    bid2 = create_beat(conn, chapter_id=cid2, sequence=1, purpose="第二个足够长的场景目的描述")
    update_beat_status(conn, bid2, "written")
    c1 = create_character(conn, name="林深", pronoun="他", role="protagonist", gender="男")
    link_beat_character(conn, bid2, c1)
    create_paragraph(conn, chapter_id=cid2, seq=1, text="风吹过空荡的街道，没有任何人。",
                     content_hash="h", beat_id=bid2, role="narrative")
    vs = check_beat_fulfillment(conn, cid2)
    assert "missing_character" in [v.kind for v in vs]
    conn.close()


def test_thread_not_advanced_violation(tmp_project):
    conn = get_connection(tmp_project)
    vid, cid, bid = _seed_chapter_with_beat(conn)
    cid2 = create_chapter(conn, volume_id=vid, global_number=2, title="t2")
    bid2 = create_beat(conn, chapter_id=cid2, sequence=1, purpose="推进真相线索的场景目的")
    update_beat_status(conn, bid2, "written")
    c1 = create_character(conn, name="林深", pronoun="他", role="protagonist", gender="男")
    link_beat_character(conn, bid2, c1)
    create_paragraph(conn, chapter_id=cid2, seq=1, text="林深看着远方的灯火。",
                     content_hash="h", beat_id=bid2, role="narrative")
    update_beat_contract(conn, vid, beat_id=bid2,
                         new_contract={"purpose": "推进真相线索的场景目的",
                                       "participating_characters": [], "advance_threads": ["ST001"]})
    vs = check_beat_fulfillment(conn, cid2)
    assert "thread_not_advanced" in [v.kind for v in vs]
    conn.close()


def test_all_good_no_violations(tmp_project):
    conn = get_connection(tmp_project)
    vid, cid, bid = _seed_chapter_with_beat(conn)
    cid2 = create_chapter(conn, volume_id=vid, global_number=2, title="t2")
    bid2 = create_beat(conn, chapter_id=cid2, sequence=1, purpose="林深在书摊翻书的场景目的")
    update_beat_status(conn, bid2, "written")
    c1 = create_character(conn, name="林深", pronoun="他", role="protagonist", gender="男")
    link_beat_character(conn, bid2, c1)
    create_paragraph(conn, chapter_id=cid2, seq=1, text="林深蹲下，翻开那本旧书。",
                     content_hash="h", beat_id=bid2, role="narrative")
    vs = check_beat_fulfillment(conn, cid2)
    assert vs == []
    conn.close()


def test_non_prose_violation_for_meta_paragraph(tmp_project):
    conn = get_connection(tmp_project)
    vid, cid, bid = _seed_chapter_with_beat(conn)
    cid2 = create_chapter(conn, volume_id=vid, global_number=2, title="t2")
    bid2 = create_beat(conn, chapter_id=cid2, sequence=1, purpose="林深在书摊翻书的场景目的")
    update_beat_status(conn, bid2, "written")
    c1 = create_character(conn, name="林深", pronoun="他", role="protagonist", gender="男")
    link_beat_character(conn, bid2, c1)
    create_paragraph(conn, chapter_id=cid2, seq=1,
                     text="润色版本已完成，剔除了所有破折号。",
                     content_hash="h", beat_id=bid2, role="narrative")
    vs = check_beat_fulfillment(conn, cid2)
    assert any(v.kind == "non_prose" for v in vs)
    conn.close()
