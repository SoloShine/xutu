# src/bedrock/repositories/worldbook.py
def add_constant(conn, key, value, scope="global", volume_id=None, source_note=""):
    conn.execute(
        "INSERT INTO constants(key,value,scope,volume_id,source_note) VALUES(?,?,?,?,?)",
        (key, value, scope, volume_id, source_note))
    conn.commit()


def get_constant(conn, key):
    return conn.execute("SELECT * FROM constants WHERE key=?", (key,)).fetchone()


def list_constants(conn):
    return conn.execute("SELECT * FROM constants ORDER BY key").fetchall()


def add_location(conn, name, loc_type="", description="", state="", parent_location_id=None):
    cur = conn.execute(
        "INSERT INTO location(name,loc_type,description,state,parent_location_id) VALUES(?,?,?,?,?)",
        (name, loc_type, description, state, parent_location_id))
    conn.commit()
    return cur.lastrowid


def add_neighbor(conn, from_id, to_id, travel_days=None):
    conn.execute(
        "INSERT OR IGNORE INTO location_neighbor(from_id,to_id,travel_days) VALUES(?,?,?)",
        (from_id, to_id, travel_days))
    conn.commit()


def neighbors_of(conn, location_id):
    return conn.execute(
        "SELECT * FROM location_neighbor WHERE from_id=?", (location_id,)).fetchall()


def add_faction(conn, name, ftype="", stance="", state="", parent_faction_id=None):
    cur = conn.execute(
        "INSERT INTO faction(name,ftype,stance,state,parent_faction_id) VALUES(?,?,?,?,?)",
        (name, ftype, stance, state, parent_faction_id))
    conn.commit()
    return cur.lastrowid


def add_time_period(conn, label, chapter_start, chapter_end, description=""):
    conn.execute(
        "INSERT OR REPLACE INTO time_period(label,chapter_start,chapter_end,description) "
        "VALUES(?,?,?,?)", (label, chapter_start, chapter_end, description))
    conn.commit()


def add_theme(conn, name, description="", evolution=""):
    conn.execute(
        "INSERT OR REPLACE INTO theme(name,description,evolution) VALUES(?,?,?)",
        (name, description, evolution))
    conn.commit()


def add_motif(conn, name, meaning="", evolution=""):
    conn.execute(
        "INSERT OR REPLACE INTO motif(name,meaning,evolution) VALUES(?,?,?)",
        (name, meaning, evolution))
    conn.commit()


from src.bedrock.repositories._amendment import record_amendment


def _update_by_col(conn, table, entity_type, key_col, key_val, allowed, **fields):
    """通用 update：按 key_col(id 或 name) 定位行。非法字段/未知行/空字段 → raise。记 amendment。"""
    illegal = set(fields) - allowed
    if illegal:
        raise ValueError(f"非法字段: {illegal}")
    row = conn.execute(f"SELECT * FROM {table} WHERE {key_col}=?", (key_val,)).fetchone()
    if row is None:
        raise ValueError(f"{entity_type} {key_val} 不存在")
    if not fields:
        raise ValueError("无字段可更新")
    sets, params = [], []
    for k, v in fields.items():
        sets.append(f"{k}=?"); params.append(v if v is not None else "")
    params.append(key_val)
    conn.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE {key_col}=?", params)
    for k in fields:
        record_amendment(conn, entity_type, key_val, k, row[k], fields[k])
    conn.commit()
    return dict(conn.execute(f"SELECT * FROM {table} WHERE {key_col}=?", (key_val,)).fetchone())


def update_location(conn, location_id, description=None, state=None, loc_type=None):
    fields = {}
    if description is not None: fields["description"] = description
    if state is not None: fields["state"] = state
    if loc_type is not None: fields["loc_type"] = loc_type
    return _update_by_col(conn, "location", "location", "id", location_id,
                          {"description", "state", "loc_type"}, **fields)


def update_theme(conn, name, description=None, evolution=None):
    # theme 无 id，name 是 PK
    fields = {}
    if description is not None: fields["description"] = description
    if evolution is not None: fields["evolution"] = evolution
    return _update_by_col(conn, "theme", "theme", "name", name,
                          {"description", "evolution"}, **fields)


def update_motif(conn, name, meaning=None, evolution=None):
    # motif 无 id，name 是 PK
    fields = {}
    if meaning is not None: fields["meaning"] = meaning
    if evolution is not None: fields["evolution"] = evolution
    return _update_by_col(conn, "motif", "motif", "name", name,
                          {"meaning", "evolution"}, **fields)
