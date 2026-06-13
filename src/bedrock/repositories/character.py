# src/bedrock/repositories/character.py
import json
import sqlite3
from typing import Optional


def create_character(conn, name, pronoun, role, gender=None, aliases=None,
                     faction_id=None, state="active", personality="", goals="",
                     abilities=None):
    cur = conn.execute(
        "INSERT INTO character(name,aliases,pronoun,gender,role,faction_id,state,personality,goals,abilities) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (name, json.dumps(aliases or [], ensure_ascii=False), pronoun, gender, role,
         faction_id, state, personality, goals,
         json.dumps(abilities or [], ensure_ascii=False)))
    conn.commit()
    return cur.lastrowid


def get_character(conn, character_id):
    return conn.execute("SELECT * FROM character WHERE id=?", (character_id,)).fetchone()


def get_character_by_name(conn, name):
    return conn.execute("SELECT * FROM character WHERE name=?", (name,)).fetchone()


def add_secret(conn, character_id, key, value, vis_mode, vis_ref, vis_axis):
    cur = conn.execute(
        "INSERT INTO character_secret(character_id,key,value,vis_mode,vis_ref,vis_axis) "
        "VALUES(?,?,?,?,?,?)",
        (character_id, key, value, vis_mode,
         json.dumps(vis_ref, ensure_ascii=False), vis_axis))
    conn.commit()
    return cur.lastrowid


def visible_secrets_for_context(conn, character_id, chapter, pov_character_id, axis):
    """boot context 注入用：按当前章 + POV + axis 过滤该角色的可见 secrets。"""
    rows = conn.execute(
        "SELECT * FROM character_secret WHERE character_id=? AND vis_axis=?",
        (character_id, axis)).fetchall()
    out = []
    for r in rows:
        ref = json.loads(r["vis_ref"])
        if r["vis_mode"] == "public":
            out.append(r)
        elif r["vis_mode"] == "secret_until":
            if chapter >= ref.get("reveal_chapter", 10**9):
                out.append(r)
        elif r["vis_mode"] == "faction":
            fid = ref.get("faction_id")
            if fid and pov_character_id:
                in_faction = conn.execute(
                    "SELECT 1 FROM character_faction WHERE character_id=? AND faction_id=?",
                    (pov_character_id, fid)).fetchone()
                if in_faction:
                    out.append(r)
        elif r["vis_mode"] == "characters":
            ids = ref.get("character_ids", [])
            if pov_character_id in ids:
                out.append(r)
    return out


def set_pronoun_override(conn, character_id, from_chapter, pronoun, reason):
    cur = conn.execute(
        "INSERT INTO pronoun_override(character_id,from_chapter,pronoun,reason) "
        "VALUES(?,?,?,?)", (character_id, from_chapter, pronoun, reason))
    conn.commit()
    return cur.lastrowid


def effective_pronoun(conn, character_id, chapter):
    row = conn.execute(
        "SELECT pronoun FROM pronoun_override WHERE character_id=? AND from_chapter<=? "
        "ORDER BY from_chapter DESC LIMIT 1", (character_id, chapter)).fetchone()
    if row:
        return row["pronoun"]
    base = get_character(conn, character_id)
    return base["pronoun"] if base else None


def add_knowledge(conn, character_id, fact_id, learned_at_beat=None, confidence=1.0, decay=0.0):
    cur = conn.execute(
        "INSERT OR REPLACE INTO character_knowledge(character_id,fact_id,learned_at_beat,"
        "confidence,decay) VALUES(?,?,?,?,?)",
        (character_id, fact_id, learned_at_beat, confidence, decay))
    conn.commit()
    return cur.lastrowid


def knowledge_of(conn, character_id):
    return conn.execute(
        "SELECT * FROM character_knowledge WHERE character_id=? ORDER BY fact_id",
        (character_id,)).fetchall()
