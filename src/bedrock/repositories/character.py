# src/bedrock/repositories/character.py
import json
import sqlite3
from typing import Optional

from src.bedrock.repositories._amendment import record_amendment

_PRONOUNS = {"他", "她", "它", "祂", "TA"}
_GENDERS = {None, "男", "女", "无", "未知", "其他"}
_ROLES = {"protagonist", "supporting", "antagonist", "minor"}
_STATES = {"active", "dormant", "deceased", "ascended", "merged"}
_TEXT_FIELDS = {"name", "personality", "goals"}
_JSON_FIELDS = {"abilities", "aliases"}


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


def update_character(conn, character_id, **fields):
    """白名单字段更新。枚举/UNIQUE/JSON 校验。UPDATE 前 raise。记 amendment。返回更新后 dict。"""
    if not fields:
        raise ValueError("无字段可更新")
    illegal = set(fields) - (_TEXT_FIELDS | _JSON_FIELDS | {"pronoun", "gender", "role", "state", "faction_id"})
    if illegal:
        raise ValueError(f"非法字段: {illegal}")
    row = conn.execute("SELECT * FROM character WHERE id=?", (character_id,)).fetchone()
    if row is None:
        raise ValueError(f"character {character_id} 不存在")
    if "pronoun" in fields and fields["pronoun"] not in _PRONOUNS:
        raise ValueError(f"非法 pronoun: {fields['pronoun']}")
    if "gender" in fields and fields["gender"] not in _GENDERS:
        raise ValueError(f"非法 gender: {fields['gender']}")
    if "role" in fields and fields["role"] not in _ROLES:
        raise ValueError(f"非法 role: {fields['role']}")
    if "state" in fields and fields["state"] not in _STATES:
        raise ValueError(f"非法 state: {fields['state']}")
    if "name" in fields:
        nm = (fields["name"] or "").strip()
        if not nm:
            raise ValueError("name 不能为空")
        dup = conn.execute("SELECT id FROM character WHERE name=? AND id!=?", (nm, character_id)).fetchone()
        if dup:
            raise ValueError(f"name 冲突: {nm}")
        fields["name"] = nm
    sets, params = [], []
    for k, v in fields.items():
        if k in _JSON_FIELDS:
            v = json.dumps(v, ensure_ascii=False)
        sets.append(f"{k}=?"); params.append(v)
    params.append(character_id)
    conn.execute(f"UPDATE character SET {', '.join(sets)} WHERE id=?", params)
    for k in fields:
        record_amendment(conn, "character", character_id, k, row[k], fields[k])
    conn.commit()
    return dict(conn.execute("SELECT * FROM character WHERE id=?", (character_id,)).fetchone())
