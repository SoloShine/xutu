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


class OutlineLockedError(Exception):
    pass


def unlock_volume_outline(conn, volume_id, reason, author="human"):
    """locked → drafted。强制记 amendment。"""
    from src.bedrock.repositories.governance import add_amendment
    row = conn.execute("SELECT status FROM volume_outline WHERE volume_id=?", (volume_id,)).fetchone()
    if row is None:
        raise ValueError(f"volume_outline for volume {volume_id} not found")
    if row["status"] != "locked":
        raise ValueError(f"volume_outline status={row['status']}, expected 'locked'")
    add_amendment(conn, entity_type="volume_outline", entity_id=volume_id,
                  field="status", old="locked", new="drafted", reason=reason, author=author)
    conn.execute("UPDATE volume_outline SET status='drafted', locked_at=NULL WHERE volume_id=?",
                 (volume_id,))
    conn.commit()


def relock_volume_outline(conn, volume_id):
    """drafted → locked。"""
    row = conn.execute("SELECT status FROM volume_outline WHERE volume_id=?", (volume_id,)).fetchone()
    if row is None:
        raise ValueError(f"volume_outline for volume {volume_id} not found")
    if row["status"] != "drafted":
        raise ValueError(f"volume_outline status={row['status']}, expected 'drafted' to relock")
    conn.execute("UPDATE volume_outline SET status='locked', locked_at=datetime('now') WHERE volume_id=?",
                 (volume_id,))
    conn.commit()


def _read_beat_contracts(conn, volume_id):
    row = conn.execute("SELECT beat_contracts FROM volume_outline WHERE volume_id=?",
                       (volume_id,)).fetchone()
    if row is None:
        raise ValueError(f"volume_outline for volume {volume_id} not found")
    return json.loads(row["beat_contracts"])


def _write_beat_contracts(conn, volume_id, contracts):
    conn.execute("UPDATE volume_outline SET beat_contracts=? WHERE volume_id=?",
                 (json.dumps(contracts, ensure_ascii=False), volume_id))
    conn.commit()


def update_beat_contract(conn, volume_id, beat_id, new_contract):
    """修改 beat_contracts JSON 里 beat_id 对应的契约项。locked 下 raise OutlineLockedError。"""
    row = conn.execute("SELECT status FROM volume_outline WHERE volume_id=?", (volume_id,)).fetchone()
    if row is None:
        raise ValueError(f"volume_outline for volume {volume_id} not found")
    if row["status"] == "locked":
        raise OutlineLockedError(f"volume_outline {volume_id} locked；必须先 unlock")
    contracts = _read_beat_contracts(conn, volume_id)
    found = False
    for i, c in enumerate(contracts):
        if c.get("beat_id") == beat_id:
            contracts[i] = {"beat_id": beat_id, **new_contract}
            found = True
            break
    if not found:
        contracts.append({"beat_id": beat_id, **new_contract})
    _write_beat_contracts(conn, volume_id, contracts)


def get_beat_contract(conn, volume_id, beat_id):
    """读 beat_contracts 里 beat_id 的契约项。不存在返回 None。"""
    contracts = _read_beat_contracts(conn, volume_id)
    for c in contracts:
        if c.get("beat_id") == beat_id:
            return c
    return None
