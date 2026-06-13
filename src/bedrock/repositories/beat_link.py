# src/bedrock/repositories/beat_link.py
def link_beat_character(conn, beat_id, character_id, role=""):
    conn.execute(
        "INSERT OR IGNORE INTO beat_character(beat_id,character_id,role) VALUES(?,?,?)",
        (beat_id, character_id, role))
    conn.commit()


def characters_in_beat(conn, beat_id):
    return conn.execute(
        "SELECT character_id, role FROM beat_character WHERE beat_id=?",
        (beat_id,)).fetchall()
