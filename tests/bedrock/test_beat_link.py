# tests/bedrock/test_beat_link.py
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.beat_link import link_beat_character, characters_in_beat
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat
from src.bedrock.repositories.character import create_character


def test_beat_character_link(tmp_project):
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述")
    c1 = create_character(conn, name="林深", pronoun="他", role="protagonist", gender="男")
    c2 = create_character(conn, name="拾", pronoun="她", role="supporting", gender="女")
    link_beat_character(conn, bid, c1, role="视角")
    link_beat_character(conn, bid, c2, role="在场")
    chars = characters_in_beat(conn, bid)
    assert {(r["character_id"], r["role"]) for r in chars} == {(c1, "视角"), (c2, "在场")}
    conn.close()
