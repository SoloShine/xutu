# src/bedrock/repositories/outline.py
import datetime as _dt
import json

from src.bedrock.repositories._amendment import record_amendment


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
    """记录灵感用进某 target。若 status 非 consumed，先 advance 推到 consumed（状态机校验 + 设 promoted_at）；
    若已 consumed，直接追加 consumed_into（允许多 target）。组合 advance 消除双写点。"""
    row = conn.execute("SELECT status FROM inspiration WHERE id=?",
                       (inspiration_id,)).fetchone()
    if row is None:
        raise ValueError(f"inspiration {inspiration_id} 不存在")
    if row["status"] != "consumed":
        advance_inspiration(conn, inspiration_id, "consumed")
    row2 = conn.execute("SELECT consumed_into FROM inspiration WHERE id=?",
                        (inspiration_id,)).fetchone()
    into = json.loads(row2["consumed_into"]) if row2 and row2["consumed_into"] else []
    into.append({"target_type": target_type, "target_id": target_id})
    conn.execute("UPDATE inspiration SET consumed_into=? WHERE id=?",
                 (json.dumps(into, ensure_ascii=False), inspiration_id))
    conn.commit()


_LEGAL_TRANSITIONS = {
    "raw": {"refined", "consumed", "discarded"},
    "refined": {"consumed", "partial", "discarded"},
    "partial": {"consumed", "discarded"},
    "consumed": {"discarded"},
    "discarded": set(),
}


def list_inspirations(conn, type_filter=None, status_filter=None):
    """灵感池列表，created_at 倒序。type/status 可选筛选（参数化，防注入）。"""
    sql = "SELECT * FROM inspiration"
    clauses, params = [], []
    if type_filter:
        clauses.append("type=?"); params.append(type_filter)
    if status_filter:
        clauses.append("status=?"); params.append(status_filter)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC, id DESC"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def advance_inspiration(conn, inspiration_id, target):
    """推进状态。校验 (current, target) 合法；非法 raise ValueError。设对应时间戳。
    状态机唯一入口——consume_inspiration 组合本函数。返回更新后 row（dict）。"""
    row = conn.execute("SELECT status FROM inspiration WHERE id=?",
                       (inspiration_id,)).fetchone()
    if row is None:
        raise ValueError(f"inspiration {inspiration_id} 不存在")
    current = row["status"]
    if target not in _LEGAL_TRANSITIONS.get(current, set()):
        raise ValueError(f"非法转移 {current}→{target}")
    now = _dt.datetime.now().isoformat()
    sets = {"status": target}
    if current == "raw" and target == "refined":
        sets["refined_at"] = now
    if target in ("consumed", "partial"):
        sets["promoted_at"] = now
    set_clause = ", ".join(f"{k}=?" for k in sets)
    conn.execute(f"UPDATE inspiration SET {set_clause} WHERE id=?",
                 [*sets.values(), inspiration_id])
    conn.commit()
    return dict(conn.execute("SELECT * FROM inspiration WHERE id=?",
                             (inspiration_id,)).fetchone())


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


def update_inspiration_content(conn, inspiration_id, content, source=None):
    """编辑灵感内容（仅未消费时）。guard：status IN (raw,refined,partial) 且 consumed_into 为空。
    content 去空后非空。source 非 None 一并更新。UPDATE 前 raise。返回更新后整行 dict。"""
    row = conn.execute("SELECT status, consumed_into, content, source FROM inspiration WHERE id=?",
                      (inspiration_id,)).fetchone()
    if row is None:
        raise ValueError(f"inspiration {inspiration_id} 不存在")
    into = json.loads(row["consumed_into"]) if row["consumed_into"] else []
    if row["status"] not in ("raw", "refined", "partial") or into:
        raise ValueError(f"inspiration {inspiration_id} 已消费/已弃用，内容冻结")
    content = (content or "").strip()
    if not content:
        raise ValueError("content 不能为空")
    sets = {"content": content}
    if source is not None:
        sets["source"] = source
    set_clause = ", ".join(f"{k}=?" for k in sets)
    conn.execute(f"UPDATE inspiration SET {set_clause} WHERE id=?", [*sets.values(), inspiration_id])
    if "content" in sets:
        record_amendment(conn, "inspiration", inspiration_id, "content", row["content"], content)
    if source is not None:
        record_amendment(conn, "inspiration", inspiration_id, "source", row["source"], source)
    conn.commit()
    return dict(conn.execute("SELECT * FROM inspiration WHERE id=?", (inspiration_id,)).fetchone())
