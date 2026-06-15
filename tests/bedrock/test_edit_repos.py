# tests/bedrock/test_edit_repos.py
import json
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.character import create_character, update_character


def test_update_character_fields(tmp_project):
    conn = get_connection(tmp_project)
    cid = create_character(conn, name="韩峥", pronoun="他", role="protagonist", personality="旧")
    row = update_character(conn, cid, personality="谨慎执拗", goals="守住边界")
    assert row["personality"] == "谨慎执拗" and row["goals"] == "守住边界"
    am = conn.execute("SELECT COUNT(*) n FROM amendment WHERE entity_type='character' AND entity_id=?", (cid,)).fetchone()["n"]
    assert am >= 2
    conn.close()


def test_update_character_name_unique_conflict(tmp_project):
    conn = get_connection(tmp_project)
    create_character(conn, name="韩峥", pronoun="他", role="protagonist")
    cid2 = create_character(conn, name="林深", pronoun="她", role="supporting")
    with pytest.raises(ValueError):
        update_character(conn, cid2, name="韩峥")
    assert conn.execute("SELECT name FROM character WHERE id=?", (cid2,)).fetchone()["name"] == "林深"
    conn.close()


def test_update_character_enum_invalid(tmp_project):
    conn = get_connection(tmp_project)
    cid = create_character(conn, name="韩", pronoun="他", role="protagonist")
    with pytest.raises(ValueError):
        update_character(conn, cid, pronoun="某某")
    with pytest.raises(ValueError):
        update_character(conn, cid, state="不存在")
    conn.close()


def test_update_character_abilities_aliases_json(tmp_project):
    conn = get_connection(tmp_project)
    cid = create_character(conn, name="韩", pronoun="他", role="protagonist")
    update_character(conn, cid, abilities=["速攻", "洞察"], aliases=["老韩"])
    assert json.loads(conn.execute("SELECT abilities FROM character WHERE id=?", (cid,)).fetchone()["abilities"]) == ["速攻", "洞察"]
    conn.close()


def test_update_character_unknown_id(tmp_project):
    conn = get_connection(tmp_project)
    with pytest.raises(ValueError):
        update_character(conn, 9999, personality="x")
    conn.close()
