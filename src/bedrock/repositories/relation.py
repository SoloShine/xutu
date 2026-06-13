# src/bedrock/repositories/relation.py
def create_relation(conn, from_id, to_id, rel_type, valid_from_chapter=None,
                    valid_to_chapter=None, current_state=""):
    cur = conn.execute(
        "INSERT INTO relation(from_id,to_id,rel_type,valid_from_chapter,valid_to_chapter,current_state) "
        "VALUES(?,?,?,?,?,?)",
        (from_id, to_id, rel_type, valid_from_chapter, valid_to_chapter, current_state))
    conn.commit()
    return cur.lastrowid


def append_state_log(conn, entity_type, entity_id, chapter, field, old, new, reason=""):
    """追加状态变更（immutable，只 INSERT 不 UPDATE）。"""
    cur = conn.execute(
        "INSERT INTO entity_state_log(entity_type,entity_id,chapter,field,old,new,reason) "
        "VALUES(?,?,?,?,?,?,?)",
        (entity_type, entity_id, chapter, field, old, new, reason))
    conn.commit()
    return cur.lastrowid


def state_log_of(conn, entity_type, entity_id):
    return conn.execute(
        "SELECT * FROM entity_state_log WHERE entity_type=? AND entity_id=? ORDER BY chapter, id",
        (entity_type, entity_id)).fetchall()
