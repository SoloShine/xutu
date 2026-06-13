# tests/bedrock/test_validation.py
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.validation import (
    validate_pronoun_gender_consistency, ValidationError, detect_cycle,
)
from src.bedrock.repositories.character import create_character
from src.bedrock.repositories.worldbook import add_faction


def test_pronoun_gender_mismatch_caught(tmp_project):
    """gender=男 但 pronoun=她 应被应用层校验拦截（CHECK 表达不了跨列语义）。"""
    conn = get_connection(tmp_project)
    conn.execute("INSERT INTO character(name,pronoun,gender,role,state) "
                 "VALUES('X','她','男','minor','active')")
    with pytest.raises(ValidationError):
        validate_pronoun_gender_consistency(conn)
    conn.close()


def test_faction_cycle_detected(tmp_project):
    conn = get_connection(tmp_project)
    a = add_faction(conn, name="A")
    b = add_faction(conn, name="B", parent_faction_id=a)
    conn.execute("UPDATE faction SET parent_faction_id=? WHERE id=?", (b, a))
    conn.commit()
    with pytest.raises(ValidationError):
        detect_cycle(conn, "faction")
    conn.close()
