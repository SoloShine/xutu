# src/bedrock/repositories/event.py


def create_event(conn, title, chapter, volume, event_type, detail="",
                 is_gap=False, gap_level=0, timeline_id=None):
    cur = conn.execute(
        "INSERT INTO event(title,detail,chapter,volume,event_type,is_gap,gap_level,timeline_id) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (title, detail, chapter, volume, event_type, int(is_gap), gap_level, timeline_id))
    conn.commit()
    return cur.lastrowid


def add_reveal(conn, event_id, beat_id):
    conn.execute(
        "INSERT OR IGNORE INTO event_reveal(event_id,beat_id) VALUES(?,?)",
        (event_id, beat_id))
    conn.commit()


def reveal_beats_of(conn, event_id):
    return conn.execute(
        "SELECT beat_id FROM event_reveal WHERE event_id=?", (event_id,)).fetchall()


def link_event_character(conn, event_id, character_id):
    conn.execute(
        "INSERT OR IGNORE INTO event_character(event_id,character_id) VALUES(?,?)",
        (event_id, character_id))
    conn.commit()


def characters_in_event(conn, event_id):
    return conn.execute(
        "SELECT character_id FROM event_character WHERE event_id=?", (event_id,)).fetchall()


def add_cause(conn, caused_event, causing_event):
    conn.execute(
        "INSERT OR IGNORE INTO event_cause(caused_event,causing_event) VALUES(?,?)",
        (caused_event, causing_event))
    conn.commit()
