# src/bedrock/repositories/outline.py
import json


def save_volume_outline(conn, volume_id, beat_contracts):
    conn.execute(
        "INSERT OR REPLACE INTO volume_outline(volume_id,status,beat_contracts) "
        "VALUES(?,COALESCE((SELECT status FROM volume_outline WHERE volume_id=?),'drafted'),?)",
        (volume_id, volume_id, json.dumps(beat_contracts, ensure_ascii=False)))
    conn.commit()


def get_volume_outline(conn, volume_id):
    return conn.execute(
        "SELECT * FROM volume_outline WHERE volume_id=?", (volume_id,)).fetchone()


def lock_volume_outline(conn, volume_id):
    conn.execute(
        "UPDATE volume_outline SET status='locked', locked_at=datetime('now') WHERE volume_id=?",
        (volume_id,))
    conn.commit()


def save_master_outline(conn, volumes=None, theme_evolution=None, key_arcs=None,
                        key_milestones=None, rhythm_curve=None):
    fields = {}
    if volumes is not None: fields["volumes"] = json.dumps(volumes, ensure_ascii=False)
    if theme_evolution is not None: fields["theme_evolution"] = theme_evolution
    if key_arcs is not None: fields["key_arcs"] = json.dumps(key_arcs, ensure_ascii=False)
    if key_milestones is not None: fields["key_milestones"] = json.dumps(key_milestones, ensure_ascii=False)
    if rhythm_curve is not None: fields["rhythm_curve"] = rhythm_curve
    if not fields:
        return
    conn.execute("INSERT OR IGNORE INTO master_outline(id) VALUES(1)")
    set_clause = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE master_outline SET {set_clause} WHERE id=1", tuple(fields.values()))
    conn.commit()


def get_master_outline(conn):
    return conn.execute("SELECT * FROM master_outline WHERE id=1").fetchone()


def add_inspiration(conn, content, type, source="", status="raw"):
    cur = conn.execute(
        "INSERT INTO inspiration(content,type,status,source) VALUES(?,?,?,?)",
        (content, type, status, source))
    conn.commit()
    return cur.lastrowid


def consume_inspiration(conn, inspiration_id, target_type, target_id):
    row = conn.execute("SELECT consumed_into FROM inspiration WHERE id=?",
                       (inspiration_id,)).fetchone()
    into = json.loads(row["consumed_into"]) if row and row["consumed_into"] else []
    into.append({"target_type": target_type, "target_id": target_id})
    conn.execute(
        "UPDATE inspiration SET status='consumed', consumed_into=? WHERE id=?",
        (json.dumps(into, ensure_ascii=False), inspiration_id))
    conn.commit()
