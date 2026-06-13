# tests/bedrock/test_schema_character.py
import sqlite3
import pytest
from src.bedrock.db.connection import get_connection


def test_pronoun_not_null(tmp_project):
    conn = get_connection(tmp_project)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO character(name,gender,role,state) VALUES('林深','男','protagonist','active')")
    conn.close()


def test_character_secret_visibility_mode_check(tmp_project):
    conn = get_connection(tmp_project)
    conn.execute("INSERT INTO character(name,pronoun,gender,role,state) VALUES('林深','他','男','protagonist','active')")
    cid = conn.execute("SELECT id FROM character WHERE name='林深'").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO character_secret(character_id,key,value,vis_mode,vis_axis) "
                     "VALUES(?,'k','v','bogus','character_epistemic')", (cid,))
    conn.close()


def test_pronoun_override_logs_change(tmp_project):
    conn = get_connection(tmp_project)
    conn.execute("INSERT INTO character(name,pronoun,gender,role,state) VALUES('T-1','它','无','supporting','active')")
    cid = conn.execute("SELECT id FROM character WHERE name='T-1'").fetchone()[0]
    conn.execute("INSERT INTO pronoun_override(character_id,from_chapter,pronoun,reason) "
                 "VALUES(?,50,'祂','觉醒后变更')", (cid,))
    rows = conn.execute("SELECT * FROM pronoun_override WHERE character_id=?", (cid,)).fetchall()
    assert len(rows) == 1
    conn.close()
