# tests/bedrock/test_relation_governance.py
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.relation import create_relation, append_state_log, state_log_of
from src.bedrock.repositories.governance import add_amendment, add_export_manifest
from src.bedrock.repositories.character import create_character


def test_relation_and_state_log(tmp_project):
    conn = get_connection(tmp_project)
    a = create_character(conn, name="林深", pronoun="他", role="protagonist", gender="男")
    b = create_character(conn, name="韩峥", pronoun="他", role="supporting", gender="男")
    rid = create_relation(conn, from_id=a, to_id=b, rel_type="战友",
                          valid_from_chapter=1, current_state="信任")
    append_state_log(conn, entity_type="relation", entity_id=rid, chapter=10,
                     field="current_state", old="信任", new="决裂", reason="背叛事件")
    log = state_log_of(conn, "relation", rid)
    assert len(log) == 1
    assert log[0]["new"] == "决裂"
    conn.close()


def test_amendment_and_export_manifest(tmp_project):
    conn = get_connection(tmp_project)
    aid = add_amendment(conn, entity_type="character", entity_id=1, chapter=5,
                        field="pronoun", old="它", new="祂", reason="T-1觉醒",
                        author="system")
    assert aid is not None
    eid = add_export_manifest(conn, scope="chapter", target_id=1, format="txt",
                              content_hash="abc", status="final")
    assert eid is not None
    conn.close()
