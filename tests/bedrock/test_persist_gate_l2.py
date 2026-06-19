"""verify_chapter_persisted 须 L2 通过(completed 蕴含 L2-clean)。"""
import pytest
from src.bedrock.orchestration.persist_gate import verify_chapter_persisted


@pytest.fixture
def seeded(tmp_path):
    """1 卷 1 章 1 beat + style_template(word_count_target=[3000,5000])。"""
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


def test_verify_true_when_l2_passes(seeded):
    conn, cid, bid = seeded
    from src.bedrock.repositories.plot_tree import create_paragraph, mark_beats_written
    create_paragraph(conn, cid, 1, "正文内容在此。" * 700, "h", bid, "narration")  # 4200 汉字 >=3000
    mark_beats_written(conn, [bid]); conn.commit()
    assert verify_chapter_persisted(conn, cid) is True


def test_verify_false_when_word_count_below_floor(seeded):
    conn, cid, bid = seeded
    from src.bedrock.repositories.plot_tree import create_paragraph, mark_beats_written
    create_paragraph(conn, cid, 1, "短正文。" * 50, "h", bid, "narration")  # ~150 汉字 <3000
    mark_beats_written(conn, [bid]); conn.commit()
    assert verify_chapter_persisted(conn, cid) is False


def test_verify_false_when_no_paragraphs(seeded):
    conn, cid, bid = seeded
    assert verify_chapter_persisted(conn, cid) is False
