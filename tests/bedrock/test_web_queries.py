# tests/bedrock/test_web_queries.py
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat,
)
from src.bedrock.repositories.character import create_character
from src.bedrock.web.queries import pov_matrix, list_volumes_simple


def _seed_pov(conn):
    vid = create_volume(conn, 1, "第一卷", 1, 3, "opening")
    cid1 = create_chapter(conn, volume_id=vid, global_number=1, title="甲")
    cid2 = create_chapter(conn, volume_id=vid, global_number=2, title="乙")
    hz = create_character(conn, name="韩峥", pronoun="他", role="protagonist")
    ls = create_character(conn, name="林深", pronoun="她", role="supporting")
    create_beat(conn, chapter_id=cid1, sequence=1, purpose="一个足够长的场景目的描述",
                pov_character_id=hz)
    create_beat(conn, chapter_id=cid2, sequence=1, purpose="一个足够长的场景目的描述",
                pov_character_id=ls)
    return vid, hz, ls, cid1, cid2


def test_pov_matrix_basic(tmp_project):
    conn = get_connection(tmp_project)
    vid, hz, ls, cid1, cid2 = _seed_pov(conn)
    matrix = pov_matrix(conn, vid)
    assert matrix["volume_name"] == "第一卷"
    assert len(matrix["chapters"]) == 2
    assert {"id": hz, "name": "韩峥"} in matrix["characters"]
    ch1_row = next(r for r in matrix["chapters"] if r["global_number"] == 1)
    assert ch1_row["povs"] == {hz}
    conn.close()


def test_pov_matrix_excludes_null_pov(tmp_project):
    """H5：NULL POV beat 不产角色列。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="x")
    create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述",
                pov_character_id=None)
    matrix = pov_matrix(conn, vid)
    assert matrix["characters"] == []
    assert len(matrix["chapters"]) == 1   # 章行仍渲染
    assert matrix["chapters"][0]["povs"] == set()
    conn.close()


def test_pov_matrix_empty_volume(tmp_project):
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    matrix = pov_matrix(conn, vid)
    assert matrix["characters"] == []
    assert matrix["chapters"] == []
    conn.close()


def test_list_volumes_simple(tmp_project):
    conn = get_connection(tmp_project)
    create_volume(conn, 2, "乙", 4, 6, "opening")
    create_volume(conn, 1, "甲", 1, 3, "opening")
    vols = list_volumes_simple(conn)
    assert [v["number"] for v in vols] == [1, 2]
    conn.close()
