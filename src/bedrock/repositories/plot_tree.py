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


def mark_override(conn, beat_id, reason, author="human"):
    """beat.status ∈ {deviated, written} → overridden。强制记 amendment（逃逸审计）。"""
    from src.bedrock.repositories.governance import add_amendment
    row = conn.execute("SELECT status FROM beat WHERE id=?", (beat_id,)).fetchone()
    if row is None:
        raise ValueError(f"beat {beat_id} not found")
    if row["status"] not in ("deviated", "written"):
        raise ValueError(f"beat {beat_id} status={row['status']}，仅 deviated/written 可 override")
    add_amendment(conn, entity_type="beat", entity_id=beat_id,
                  field="status", old=row["status"], new="overridden", reason=reason, author=author)
    conn.execute("UPDATE beat SET status='overridden' WHERE id=?", (beat_id,))
    conn.commit()


def insert_paragraph_at(conn, chapter_id, after_seq, text, content_hash, beat_id, role):
    """在 seq=after_seq 的段后插入新段；后续段落 seq+1。after_seq=0 表示插到章首。
    两步 UPDATE 避开 UNIQUE(chapter_id,seq) 中间冲突（先移临时大值区，再移回）。"""
    conn.execute(
        "UPDATE paragraph SET seq=seq+1000000 WHERE chapter_id=? AND seq>?",
        (chapter_id, after_seq))
    conn.execute(
        "UPDATE paragraph SET seq=seq-999999 WHERE chapter_id=? AND seq>?",
        (chapter_id, after_seq))
    cur = conn.execute(
        "INSERT INTO paragraph(chapter_id,seq,text,content_hash,beat_id,role) VALUES(?,?,?,?,?,?)",
        (chapter_id, after_seq + 1, text, content_hash, beat_id, role))
    conn.commit()
    return cur.lastrowid


def delete_paragraph(conn, para_id, tighten=True):
    """删除段；tighten=True 时后续 seq-1 收紧连续（默认），False 留空洞（ORDER BY 仍正确）。"""
    row = conn.execute("SELECT chapter_id, seq FROM paragraph WHERE para_id=?", (para_id,)).fetchone()
    if row is None:
        raise ValueError(f"paragraph {para_id} not found")
    chapter_id, seq = row["chapter_id"], row["seq"]
    conn.execute("DELETE FROM paragraph WHERE para_id=?", (para_id,))
    if tighten:
        conn.execute(
            "UPDATE paragraph SET seq=seq-1 WHERE chapter_id=? AND seq>?",
            (chapter_id, seq))
    conn.commit()


def reorder_paragraphs(conn, chapter_id, para_id_list):
    """按 para_id_list 顺序重排该章段落 seq（1..N）。para_id_list 必须是该章全部段落的完整集合。
    先整体移到临时大值区避开 UNIQUE(chapter_id,seq) 冲突，再按新顺序设 seq。"""
    existing = {r["para_id"] for r in conn.execute(
        "SELECT para_id FROM paragraph WHERE chapter_id=?", (chapter_id,)).fetchall()}
    if set(para_id_list) != existing:
        raise ValueError("para_id_list 必须是该章全部段落的完整集合")
    conn.execute("UPDATE paragraph SET seq=seq+1000000 WHERE chapter_id=?", (chapter_id,))
    for i, pid in enumerate(para_id_list, start=1):
        conn.execute("UPDATE paragraph SET seq=? WHERE para_id=?", (i, pid))
    conn.commit()
