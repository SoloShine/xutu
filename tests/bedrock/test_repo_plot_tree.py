# tests/bedrock/test_repo_plot_tree.py
import pytest
from src.bedrock.repositories.plot_tree import (
    create_volume, get_volume, create_chapter, create_beat, create_paragraph,
    list_paragraphs_in_chapter,
)


def test_volume_crud(tmp_project):
    from src.bedrock.db.connection import get_connection
    conn = get_connection(tmp_project)
    vid = create_volume(conn, number=1, name="萌动", chapter_start=1, chapter_end=12,
                        volume_type="opening", theme_seeds=["知识的引力"])
    v = get_volume(conn, vid)
    assert v["name"] == "萌动"
    assert v["chapter_start"] == 1
    conn.close()


def test_chapter_beat_paragraph_roundtrip(tmp_project):
    from src.bedrock.db.connection import get_connection
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="开端")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="林深发现旧书摊的诡异注记")
    create_paragraph(conn, chapter_id=cid, seq=1, text="周末清晨，林深走出公寓。",
                     content_hash="h1", beat_id=bid, role="narrative")
    create_paragraph(conn, chapter_id=cid, seq=2, text="三天后，他回到书摊。",
                     content_hash="h2", beat_id=None, role="transition")
    paras = list_paragraphs_in_chapter(conn, cid)
    assert [p["seq"] for p in paras] == [1, 2]
    assert paras[0]["beat_id"] == bid
    assert paras[1]["beat_id"] is None
    conn.close()


def test_beat_purpose_too_short_rejected(tmp_project):
    from src.bedrock.db.connection import get_connection
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    with pytest.raises(Exception):
        create_beat(conn, chapter_id=cid, sequence=1, purpose="太短")
    conn.close()
