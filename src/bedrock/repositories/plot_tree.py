# src/bedrock/repositories/plot_tree.py
import json
import sqlite3
from typing import Optional


def create_volume(conn, number, name, chapter_start, chapter_end, volume_type,
                  theme_seeds=None):
    cur = conn.execute(
        "INSERT INTO volume(number,name,chapter_start,chapter_end,volume_type,theme_seeds) "
        "VALUES(?,?,?,?,?,?)",
        (number, name, chapter_start, chapter_end, volume_type,
         json.dumps(theme_seeds or [], ensure_ascii=False)))
    conn.commit()
    return cur.lastrowid


def get_volume(conn, volume_id):
    return conn.execute("SELECT * FROM volume WHERE id=?", (volume_id,)).fetchone()


def create_chapter(conn, volume_id, global_number, title, status="planned"):
    cur = conn.execute(
        "INSERT INTO chapter(volume_id,global_number,title,status) VALUES(?,?,?,?)",
        (volume_id, global_number, title, status))
    conn.commit()
    return cur.lastrowid


def get_chapter_by_global(conn, global_number):
    return conn.execute("SELECT * FROM chapter WHERE global_number=?",
                        (global_number,)).fetchone()


def create_beat(conn, chapter_id, sequence, purpose, pov_character_id=None,
                scene_setting=None, story_time=None, timeline_id=None, status="planned"):
    cur = conn.execute(
        "INSERT INTO beat(chapter_id,sequence,purpose,pov_character_id,scene_setting,"
        "story_time,timeline_id,status) VALUES(?,?,?,?,?,?,?,?)",
        (chapter_id, sequence, purpose, pov_character_id,
         json.dumps(scene_setting or {}, ensure_ascii=False), story_time, timeline_id, status))
    conn.commit()
    return cur.lastrowid


def get_beat(conn, beat_id):
    return conn.execute("SELECT * FROM beat WHERE id=?", (beat_id,)).fetchone()


def list_beats_in_chapter(conn, chapter_id):
    return conn.execute(
        "SELECT * FROM beat WHERE chapter_id=? ORDER BY sequence", (chapter_id,)).fetchall()


def update_beat_status(conn, beat_id, status, deviation_note=None):
    conn.execute(
        "UPDATE beat SET status=?, deviation_note=COALESCE(?, deviation_note) WHERE id=?",
        (status, deviation_note, beat_id))
    conn.commit()


def create_paragraph(conn, chapter_id, seq, text, content_hash, beat_id, role):
    cur = conn.execute(
        "INSERT INTO paragraph(chapter_id,seq,text,content_hash,beat_id,role) "
        "VALUES(?,?,?,?,?,?)",
        (chapter_id, seq, text, content_hash, beat_id, role))
    conn.commit()
    return cur.lastrowid


def list_paragraphs_in_chapter(conn, chapter_id):
    return conn.execute(
        "SELECT * FROM paragraph WHERE chapter_id=? ORDER BY seq",
        (chapter_id,)).fetchall()


def update_paragraph(conn, para_id, text, content_hash, beat_id, role):
    conn.execute(
        "UPDATE paragraph SET text=?, content_hash=?, beat_id=?, role=? WHERE para_id=?",
        (text, content_hash, beat_id, role, para_id))
    conn.commit()
