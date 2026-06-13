# tests/bedrock/test_event.py
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.event import (
    create_event, add_reveal, reveal_beats_of, link_event_character,
    characters_in_event, add_cause,
)
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat


def _two_beats(conn):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    b1 = create_beat(conn, chapter_id=cid, sequence=1, purpose="第一个场景目的足够长")
    b2 = create_beat(conn, chapter_id=cid, sequence=2, purpose="第二个场景目的足够长")
    return b1, b2


def test_event_multiple_reveals(tmp_project):
    """Event 支持多次揭示（revealed_at_beats[]，避免 bitemporal 单区间丢失）。"""
    conn = get_connection(tmp_project)
    b1, b2 = _two_beats(conn)
    eid = create_event(conn, title="制造者真相", detail="代谢系统的本质",
                       chapter=1, volume=1, event_type="revelation")
    add_reveal(conn, event_id=eid, beat_id=b1)
    add_reveal(conn, event_id=eid, beat_id=b2)
    assert {r["beat_id"] for r in reveal_beats_of(conn, eid)} == {b1, b2}
    conn.close()


def test_event_characters_and_cause(tmp_project):
    conn = get_connection(tmp_project)
    from src.bedrock.repositories.character import create_character
    b1, b2 = _two_beats(conn)
    c1 = create_character(conn, name="林深", pronoun="他", role="protagonist", gender="男")
    e_cause = create_event(conn, title="起因", detail="d", chapter=1, volume=1, event_type="plot")
    e_eff = create_event(conn, title="结果", detail="d", chapter=2, volume=1, event_type="turning")
    link_event_character(conn, e_eff, c1)
    add_cause(conn, caused_event=e_eff, causing_event=e_cause)
    assert c1 in [r["character_id"] for r in characters_in_event(conn, e_eff)]
    conn.close()
