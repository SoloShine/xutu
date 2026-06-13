# tests/bedrock/test_schema_plot_tree.py
import sqlite3
import pytest
from src.bedrock.db.connection import get_connection


def test_volume_number_unique(tmp_project):
    conn = get_connection(tmp_project)
    conn.execute(
        "INSERT INTO volume(number,name,chapter_start,chapter_end,volume_type,status) "
        "VALUES(1,'萌动',1,12,'opening','planned')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO volume(number,name,chapter_start,chapter_end,volume_type,status) "
            "VALUES(1,'重复',1,12,'opening','planned')")
    conn.close()


def test_chapter_global_number_unique(tmp_project):
    conn = get_connection(tmp_project)
    conn.execute("INSERT INTO volume(number,name,chapter_start,chapter_end,volume_type,status) "
                 "VALUES(1,'v',1,12,'opening','planned')")
    vol_id = conn.execute("SELECT id FROM volume WHERE number=1").fetchone()[0]
    conn.execute("INSERT INTO chapter(volume_id,global_number,title,status) VALUES(?,1,'t','planned')", (vol_id,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO chapter(volume_id,global_number,title,status) VALUES(?,1,'t2','planned')", (vol_id,))
    conn.close()


def test_paragraph_narrative_must_have_beat(tmp_project):
    conn = get_connection(tmp_project)
    conn.execute("INSERT INTO volume(number,name,chapter_start,chapter_end,volume_type,status) "
                 "VALUES(1,'v',1,12,'opening','planned')")
    vol_id = conn.execute("SELECT id FROM volume WHERE number=1").fetchone()[0]
    conn.execute("INSERT INTO chapter(volume_id,global_number,title,status) VALUES(?,1,'t','planned')", (vol_id,))
    ch_id = conn.execute("SELECT id FROM chapter WHERE global_number=1").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO paragraph(chapter_id,seq,text,content_hash,beat_id,role) "
            "VALUES(?,1,'x','h',NULL,'narrative')", (ch_id,))
    conn.execute(
        "INSERT INTO paragraph(chapter_id,seq,text,content_hash,beat_id,role) "
        "VALUES(?,1,'x','h',NULL,'transition')", (ch_id,))
    conn.close()
