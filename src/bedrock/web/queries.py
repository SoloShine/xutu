"""SP6-C Web UI 纯查询：POV 矩阵聚合 + 卷列表。新写聚合 SQL（既有 plot_tree 无 distinct-pov 函数）。"""


def list_volumes_simple(conn):
    """卷列表（id/number/name），按 number 升序。卷选择器数据源。"""
    return [dict(r) for r in conn.execute(
        "SELECT id, number, name FROM volume ORDER BY number").fetchall()]


def pov_matrix(conn, volume_id):
    """POV 矩阵数据：{volume_name, characters:[{id,name}], chapters:[{id,global_number,title,povs:set}]}。
    NULL POV beat 不产角色列（H5）。"""
    vrow = conn.execute("SELECT number, name FROM volume WHERE id=?", (volume_id,)).fetchone()
    volume_name = vrow["name"] if vrow else None

    char_rows = conn.execute(
        "SELECT DISTINCT b.pov_character_id AS cid, c.name "
        "FROM beat b JOIN chapter ch ON b.chapter_id=ch.id "
        "JOIN character c ON b.pov_character_id=c.id "
        "WHERE ch.volume_id=? AND b.pov_character_id IS NOT NULL "
        "ORDER BY b.id", (volume_id,)).fetchall()
    characters = [{"id": r["cid"], "name": r["name"]} for r in char_rows]

    chapters = []
    ch_rows = conn.execute(
        "SELECT id, global_number, title FROM chapter WHERE volume_id=? ORDER BY global_number",
        (volume_id,)).fetchall()
    for ch in ch_rows:
        povs = {r["pov_character_id"] for r in conn.execute(
            "SELECT pov_character_id FROM beat WHERE chapter_id=? AND pov_character_id IS NOT NULL",
            (ch["id"],)).fetchall()}
        chapters.append({"id": ch["id"], "global_number": ch["global_number"],
                         "title": ch["title"], "povs": povs})
    return {"volume_name": volume_name, "characters": characters, "chapters": chapters}


# --- P1-T1: read 查询（Web SPA 工作台后端纯函数层）---
import json
from pathlib import Path
from src.bedrock.checks.word_count import compute_word_count
from src.bedrock.repositories.worldbook import get_constant
from src.bedrock.db.connection import get_connection


def list_works(projects_root):
    root = Path(projects_root)
    out = []
    for sub in sorted([p for p in root.iterdir() if p.is_dir()]):
        if not (sub / "bedrock.db").exists():
            continue
        try:
            conn = get_connection(sub)
            try:
                name = _work_name(conn) or sub.name
                nv = conn.execute("SELECT COUNT(*) n FROM volume").fetchone()["n"]
                cc = conn.execute("SELECT SUM(status='completed') c, SUM(status='writing') w FROM chapter").fetchone()
                reports = list(sub.glob("review_report_vol*.md"))
                out.append({"id": sub.name, "name": name, "volumes": nv,
                            "chapters_completed": cc["c"] or 0, "chapters_writing": cc["w"] or 0,
                            "has_any_report": len(reports) > 0})
            finally:
                conn.close()
        except Exception:
            continue
    return out


def _work_name(conn):
    r = get_constant(conn, "work_name")
    if r is None:
        return None
    # get_constant 返回 sqlite3.Row（取 ["value"]）；防御性兼容 str
    try:
        return r["value"]
    except Exception:
        return r


def overview_stats(conn):
    nv = conn.execute("SELECT COUNT(*) n FROM volume").fetchone()["n"]
    row = conn.execute("SELECT SUM(status='completed') c, SUM(status='writing') w, COUNT(*) t FROM chapter").fetchone()
    nchar = conn.execute("SELECT COUNT(*) n FROM character").fetchone()["n"]
    texts = [r["text"] for r in conn.execute("SELECT text FROM paragraph").fetchall()]
    word_total = compute_word_count(texts) if texts else 0
    insp = {r["status"]: r["n"] for r in conn.execute("SELECT status, COUNT(*) n FROM inspiration GROUP BY status").fetchall()}
    vol_list = [dict(r) for r in conn.execute("SELECT id, number, name, volume_type, status FROM volume ORDER BY number").fetchall()]
    for v in vol_list:
        v["chapter_count"] = conn.execute("SELECT COUNT(*) n FROM chapter WHERE volume_id=?", (v["id"],)).fetchone()["n"]
    snap = [dict(r) for r in conn.execute("SELECT id, name, role, state, pronoun, personality FROM character ORDER BY id").fetchall()]
    for s in snap:
        s["personality_excerpt"] = (s["personality"] or "")[:40]
    return {"name": _work_name(conn), "volumes": nv,
            "chapters": {"completed": row["c"] or 0, "writing": row["w"] or 0, "total": row["t"]},
            "characters": nchar, "word_total": word_total,
            "inspirations": {k: insp.get(k, 0) for k in ("raw", "refined", "consumed", "partial", "discarded")},
            "volume_list": vol_list, "character_snapshot": snap, "worldbook": worldbook_overview(conn)}


def chapter_text(conn, global_number):
    ch = conn.execute("SELECT global_number, title FROM chapter WHERE global_number=?", (global_number,)).fetchone()
    if ch is None:
        return None
    paras = [{"seq": r["seq"], "text": r["text"]} for r in conn.execute(
        "SELECT seq, text FROM paragraph WHERE chapter_id IN (SELECT id FROM chapter WHERE global_number=?) ORDER BY seq",
        (global_number,)).fetchall()]
    return {"chapter": {"global_number": ch["global_number"], "title": ch["title"]}, "paragraphs": paras}


def outline_tree(conn, volume_id=None):
    mo_row = conn.execute("SELECT theme_evolution, key_arcs, key_milestones, rhythm_curve FROM master_outline WHERE id=1").fetchone()
    master = None
    if mo_row and any(mo_row[k] for k in ("theme_evolution", "key_arcs", "key_milestones", "rhythm_curve") if mo_row[k]):
        master = {"theme_evolution": mo_row["theme_evolution"], "key_arcs": _jl(mo_row["key_arcs"], []),
                  "key_milestones": _jl(mo_row["key_milestones"], []), "rhythm_curve": mo_row["rhythm_curve"]}
    vsql = ("SELECT id, number, name, volume_type, status, theme_seeds FROM volume"
            + (" WHERE id=?" if volume_id else "") + " ORDER BY number")
    vparams = (volume_id,) if volume_id else ()
    vols = []
    for v in conn.execute(vsql, vparams).fetchall():
        vo = conn.execute("SELECT status, locked_at, beat_contracts FROM volume_outline WHERE volume_id=?", (v["id"],)).fetchone()
        vol_outline = ({"status": vo["status"], "locked_at": vo["locked_at"], "beat_contracts": _jl(vo["beat_contracts"], [])} if vo else None)
        chs = []
        for ch in conn.execute("SELECT id, global_number, title, status FROM chapter WHERE volume_id=? ORDER BY global_number", (v["id"],)).fetchall():
            beats = []
            for b in conn.execute("SELECT id, sequence, purpose, pov_character_id, scene_setting, status, deviation_note FROM beat WHERE chapter_id=? ORDER BY sequence", (ch["id"],)).fetchall():
                pname = None
                if b["pov_character_id"]:
                    pr = conn.execute("SELECT name FROM character WHERE id=?", (b["pov_character_id"],)).fetchone()
                    pname = pr["name"] if pr else None
                pcount = conn.execute("SELECT COUNT(*) n FROM paragraph WHERE beat_id=?", (b["id"],)).fetchone()["n"]
                beats.append({"id": b["id"], "sequence": b["sequence"], "purpose": b["purpose"], "pov_name": pname,
                              "scene_setting": _jl(b["scene_setting"], {}), "status": b["status"],
                              "deviation_note": b["deviation_note"], "paragraph_count": pcount})
            chs.append({"id": ch["id"], "global_number": ch["global_number"], "title": ch["title"], "status": ch["status"], "beats": beats})
        vols.append({"id": v["id"], "number": v["number"], "name": v["name"], "volume_type": v["volume_type"],
                     "status": v["status"], "theme_seeds": _jl(v["theme_seeds"], []), "volume_outline": vol_outline, "chapters": chs})
    return {"master_outline": master, "volumes": vols}


def list_characters(conn):
    rows = conn.execute("SELECT id, name, pronoun, gender, role, faction_id, state, personality, goals, abilities, aliases FROM character ORDER BY id").fetchall()
    out = []
    for r in rows:
        fac = None
        if r["faction_id"]:
            fr = conn.execute("SELECT name FROM faction WHERE id=?", (r["faction_id"],)).fetchone()
            fac = fr["name"] if fr else None
        sc = conn.execute("SELECT COUNT(*) n FROM character_secret WHERE character_id=?", (r["id"],)).fetchone()["n"]
        kc = conn.execute("SELECT COUNT(*) n FROM character_knowledge WHERE character_id=?", (r["id"],)).fetchone()["n"]
        out.append({"id": r["id"], "name": r["name"], "pronoun": r["pronoun"], "gender": r["gender"], "role": r["role"],
                    "faction_id": r["faction_id"], "faction_name": fac, "state": r["state"], "personality": r["personality"],
                    "goals": r["goals"], "abilities": _jl(r["abilities"], []), "aliases": _jl(r["aliases"], []),
                    "secret_count": sc, "knowledge_count": kc})
    return out


def worldbook_overview(conn):
    locs = [dict(r) for r in conn.execute("SELECT id, name, loc_type, description, state FROM location ORDER BY id").fetchall()]
    # theme/motif 用 name 作 PRIMARY KEY，无 id 列
    themes = [dict(r) for r in conn.execute("SELECT name, description, evolution FROM theme ORDER BY name").fetchall()]
    motifs = [dict(r) for r in conn.execute("SELECT name, meaning, evolution FROM motif ORDER BY name").fetchall()]
    return {"locations": locs, "themes": themes, "motifs": motifs}


def list_factions(conn):
    return [dict(r) for r in conn.execute("SELECT id, name, ftype, stance, state FROM faction ORDER BY id").fetchall()]


def _jl(raw, default):
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default
