# tests/bedrock/test_fk.py
"""验证软 FK 列真的挂了 REFERENCES（dangling insert 必须被拒）。"""
import sqlite3
from src.bedrock.db.connection import get_connection


def test_beat_pov_fk_rejects_dangling(tmp_project):
    conn = get_connection(tmp_project)
    conn.execute(
        "INSERT INTO volume(number,name,chapter_start,chapter_end,volume_type,status) "
        "VALUES(1,'v',1,3,'opening','planned')")
    vol = conn.execute("SELECT id FROM volume WHERE number=1").fetchone()[0]
    conn.execute(
        "INSERT INTO chapter(volume_id,global_number,title,status) VALUES(?,1,'t','planned')",
        (vol,))
    # pov 指向不存在的 character 应被拒
    try:
        conn.execute(
            "INSERT INTO beat(chapter_id,sequence,purpose,pov_character_id) "
            "VALUES(1,1,'一个足够长的目的描述',99999)")
        conn.commit()
        raised = False
    except sqlite3.IntegrityError:
        raised = True
    assert raised, "beat.pov_character_id FK 未生效"
    conn.close()


def test_character_faction_fk_rejects_dangling(tmp_project):
    conn = get_connection(tmp_project)
    try:
        conn.execute(
            "INSERT INTO character(name,pronoun,gender,role,faction_id,state) "
            "VALUES('X','他','男','minor',99999,'active')")
        conn.commit()
        raised = False
    except sqlite3.IntegrityError:
        raised = True
    assert raised, "character.faction_id FK 未生效"
    conn.close()


def test_constants_volume_fk_rejects_dangling(tmp_project):
    conn = get_connection(tmp_project)
    try:
        conn.execute(
            "INSERT INTO constants(key,value,scope,volume_id) "
            "VALUES('k','v','volume-specific',99999)")
        conn.commit()
        raised = False
    except sqlite3.IntegrityError:
        raised = True
    assert raised, "constants.volume_id FK 未生效"
    conn.close()
