# src/bedrock/repositories/governance.py
import json


def add_amendment(conn, entity_type, entity_id, field, new, old=None,
                  chapter=None, reason="", author="system"):
    cur = conn.execute(
        "INSERT INTO amendment(entity_type,entity_id,chapter,field,old_value,new_value,reason,author) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (entity_type, entity_id, chapter, field, old, new, reason, author))
    conn.commit()
    return cur.lastrowid


def add_export_manifest(conn, scope, format, content_hash, target_id=None,
                        status="draft", source_snapshot=None):
    cur = conn.execute(
        "INSERT INTO export_manifest(scope,target_id,format,content_hash,status,source_snapshot) "
        "VALUES(?,?,?,?,?,?)",
        (scope, target_id, format, content_hash, status,
         json.dumps(source_snapshot or {}, ensure_ascii=False)))
    conn.commit()
    return cur.lastrowid
