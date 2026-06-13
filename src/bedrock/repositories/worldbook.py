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
