"""L2 字数下限硬门禁:实测汉字数 < word_count_target[0] → word_count_below_floor 违规。"""
import pytest
from src.bedrock.orchestration.l2_pipeline import run_l2


@pytest.fixture
def seeded(tmp_path):
    """1 卷 1 章 1 beat(written)+ style_template(word_count_target=[3000,5000])。"""
    import json
    from src.bedrock.db.connection import get_connection
    from src.bedrock.init_project import init_project
    from src.bedrock.repositories.plot_tree import (
        create_volume, create_chapter, create_beat)
    proj = tmp_path / "p"
    init_project(proj, work_name="t", force=True)
    conn = get_connection(proj)
    vid = create_volume(conn, 1, "v", 1, 1, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t", status="writing")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="测试 beat 目的足够长十个字", pov_character_id=None)
    conn.execute("INSERT OR REPLACE INTO volume_outline(volume_id,status,beat_contracts) VALUES(?,'drafted',?)",
                 (vid, json.dumps([{"beat_id": bid, "purpose": "测试 beat 目的足够长十个字"}])))
    conn.execute("INSERT OR REPLACE INTO style_template(scope,volume_id,fingerprint,word_count_target) "
                 "VALUES('work',NULL,'{}','[3000, 5000]')")
    conn.commit()
    return conn, cid, bid


def _set_prose(conn, cid, bid, text):
    from src.bedrock.repositories.plot_tree import create_paragraph, mark_beats_written
    conn.execute("DELETE FROM paragraph WHERE chapter_id=?", (cid,))
    create_paragraph(conn, cid, 1, text, "h", bid, "narration")
    mark_beats_written(conn, [bid])
    conn.commit()


def test_below_floor_flags(seeded):
    conn, cid, bid = seeded
    _set_prose(conn, cid, bid, "短正文。" * 50)   # ~150 汉字 < 3000
    rep = run_l2(conn, cid)
    kinds = [v.kind for v in rep.beat_violations]
    assert "word_count_below_floor" in kinds
    assert rep.passed_hard_gate is False


def test_at_floor_does_not_flag(seeded):
    conn, cid, bid = seeded
    # 每句"正文内容在此。"=6 汉字,*600 = 3600 汉字 ≥ 3000
    _set_prose(conn, cid, bid, "正文内容在此。" * 600)
    rep = run_l2(conn, cid)
    kinds = [v.kind for v in rep.beat_violations]
    assert "word_count_below_floor" not in kinds


def test_empty_draft_not_flagged(seeded):
    """空稿(wc==0)由 unwritten_beat 兜,不重复报 word_count_below_floor。"""
    conn, cid, bid = seeded
    conn.execute("DELETE FROM paragraph WHERE chapter_id=?", (cid,))
    conn.commit()
    rep = run_l2(conn, cid)
    kinds = [v.kind for v in rep.beat_violations]
    assert "word_count_below_floor" not in kinds
    assert "unwritten_beat" in kinds


def test_default_floor_when_no_style_config(tmp_path):
    """无 style_template 行 → 兜底 floor=3000。"""
    import json
    from src.bedrock.db.connection import get_connection
    from src.bedrock.init_project import init_project
    from src.bedrock.repositories.plot_tree import (
        create_volume, create_chapter, create_beat, create_paragraph, mark_beats_written)
    proj = tmp_path / "p2"
    init_project(proj, work_name="t", force=True)
    conn = get_connection(proj)
    vid = create_volume(conn, 1, "v", 1, 1, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t", status="writing")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="测试 beat 目的足够长十个字", pov_character_id=None)
    conn.execute("INSERT OR REPLACE INTO volume_outline(volume_id,status,beat_contracts) VALUES(?,'drafted',?)",
                 (vid, json.dumps([{"beat_id": bid, "purpose": "测试 beat 目的足够长十个字"}])))
    create_paragraph(conn, cid, 1, "短。" * 100, "h", bid, "narration")  # ~100 汉字
    mark_beats_written(conn, [bid])
    conn.commit()  # 不插 style_template → 兜底
    rep = run_l2(conn, cid)
    kinds = [v.kind for v in rep.beat_violations]
    assert "word_count_below_floor" in kinds
