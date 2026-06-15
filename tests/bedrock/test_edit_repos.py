# tests/bedrock/test_edit_repos.py
import json
import json as _json
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.character import create_character, update_character
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat,
    update_chapter_meta, update_volume_meta, update_beat_meta,
)


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


def test_update_chapter_meta_title(tmp_project):
    conn = get_connection(tmp_project)
    v = create_volume(conn, 1, "V", 1, 1, "opening")
    c = create_chapter(conn, volume_id=v, global_number=1, title="旧", status="completed")
    row = update_chapter_meta(conn, c, title="新标题")
    assert row["title"] == "新标题"
    assert conn.execute("SELECT COUNT(*) n FROM amendment WHERE entity_type='chapter' AND entity_id=?", (c,)).fetchone()["n"] == 1
    conn.close()


def test_update_chapter_meta_empty_rejected(tmp_project):
    conn = get_connection(tmp_project)
    v = create_volume(conn, 1, "V", 1, 1, "opening")
    c = create_chapter(conn, volume_id=v, global_number=1, title="x", status="completed")
    with pytest.raises(ValueError):
        update_chapter_meta(conn, c, title="  ")
    conn.close()


def test_update_volume_meta_theme_seeds(tmp_project):
    conn = get_connection(tmp_project)
    v = create_volume(conn, 1, "旧名", 1, 1, "opening")
    row = update_volume_meta(conn, v, name="新名", theme_seeds=["a", "b"])
    assert row["name"] == "新名"
    assert _json.loads(conn.execute("SELECT theme_seeds FROM volume WHERE id=?", (v,)).fetchone()["theme_seeds"]) == ["a", "b"]
    conn.close()


def test_update_volume_meta_bad_json(tmp_project):
    conn = get_connection(tmp_project)
    v = create_volume(conn, 1, "V", 1, 1, "opening")
    with pytest.raises(ValueError):
        update_volume_meta(conn, v, theme_seeds="不是列表")
    conn.close()


def test_update_beat_meta_purpose_too_short(tmp_project):
    conn = get_connection(tmp_project)
    v = create_volume(conn, 1, "V", 1, 1, "opening")
    c = create_chapter(conn, volume_id=v, global_number=1, title="x", status="completed")
    b = create_beat(conn, chapter_id=c, sequence=1, purpose="一个足够长的初始场景目的描述文字")
    with pytest.raises(ValueError):
        update_beat_meta(conn, b, purpose="短")
    conn.close()


def test_update_beat_meta_ok(tmp_project):
    conn = get_connection(tmp_project)
    v = create_volume(conn, 1, "V", 1, 1, "opening")
    c = create_chapter(conn, volume_id=v, global_number=1, title="x", status="completed")
    b = create_beat(conn, chapter_id=c, sequence=1, purpose="一个足够长的初始场景目的描述文字")
    row = update_beat_meta(conn, b, purpose="这是一个新的足够长的场景目的描述文字", scene_setting={"place": "城门"})
    assert row["purpose"] == "这是一个新的足够长的场景目的描述文字"
    conn.close()
