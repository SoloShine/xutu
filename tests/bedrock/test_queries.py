# tests/bedrock/test_queries.py
import json
from pathlib import Path
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat, create_paragraph
from src.bedrock.repositories.character import create_character
from src.bedrock.repositories.worldbook import add_constant, add_location, add_theme, add_motif, add_faction
from src.bedrock.repositories.outline import add_inspiration, advance_inspiration
from src.bedrock.web.queries import (
    list_works, overview_stats, chapter_text, outline_tree,
    list_characters, worldbook_overview, list_factions,
)


def _seed(conn):
    add_constant(conn, key="work_name", value="测试书")
    v = create_volume(conn, 1, "第一卷", 1, 3, "opening")
    c1 = create_chapter(conn, volume_id=v, global_number=1, title="甲", status="completed")
    c2 = create_chapter(conn, volume_id=v, global_number=2, title="乙", status="writing")
    hz = create_character(conn, name="韩峥", pronoun="他", role="protagonist", personality="谨慎")
    b1 = create_beat(conn, chapter_id=c1, sequence=1, purpose="一个足够长的场景目的描述文字", pov_character_id=hz)
    create_paragraph(conn, chapter_id=c1, seq=1, text="韩峥站在封锁线前。", content_hash="h11", beat_id=b1, role="narration")
    create_paragraph(conn, chapter_id=c1, seq=2, text="电流声嗡鸣。", content_hash="h12", beat_id=b1, role="narration")
    add_location(conn, name="封锁线", loc_type="border", description="城市边缘的膜")
    add_theme(conn, name="边界", description="人与系统的界线")
    add_motif(conn, name="电流声", meaning="共振象征")
    add_faction(conn, name="守卫者", ftype="org")
    add_inspiration(conn, content="灵一", type="scene")
    i2 = add_inspiration(conn, content="灵二", type="mechanic")
    advance_inspiration(conn, i2, "refined")
    return v, c1, c2, hz


def test_list_works_scans_subdirs(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    from src.bedrock.init_project import init_project
    a = root / "a"
    init_project(a, work_name="书A", force=True)
    # init_project 已写入 work_name，这里确保值正确（INSERT OR REPLACE 避免 UNIQUE 冲突）
    conn = get_connection(a)
    conn.execute("INSERT OR REPLACE INTO constants(key,value,scope,volume_id,source_note) VALUES('work_name','书A','global',NULL,'')")
    conn.commit(); conn.close()
    (root / "b").mkdir()  # 无 db，应忽略
    works = list_works(root)
    assert [w["id"] for w in works] == ["a"]
    assert works[0]["name"] == "书A"


def test_list_works_name_none_fallback(tmp_path):
    root = tmp_path / "projects"; root.mkdir()
    from src.bedrock.init_project import init_project
    init_project(root / "x", work_name="x", force=True)
    conn = get_connection(root / "x"); conn.execute("DELETE FROM constants WHERE key='work_name'"); conn.commit(); conn.close()
    works = list_works(root)
    assert works[0]["name"] == "x"


def test_overview_stats(tmp_project):
    conn = get_connection(tmp_project)
    _seed(conn); conn.commit(); conn.close()
    conn = get_connection(tmp_project)
    st = overview_stats(conn)
    assert st["volumes"] == 1
    assert st["chapters"]["completed"] == 1 and st["chapters"]["writing"] == 1
    assert st["chapters"]["total"] == 2
    assert st["characters"] == 1
    assert st["word_total"] >= 4
    assert st["inspirations"]["raw"] == 1 and st["inspirations"]["refined"] == 1
    assert len(st["volume_list"]) == 1
    conn.close()


def test_chapter_text_orders_by_seq(tmp_project):
    conn = get_connection(tmp_project); _seed(conn); conn.commit(); conn.close()
    conn = get_connection(tmp_project)
    t = chapter_text(conn, 1)
    assert [p["seq"] for p in t["paragraphs"]] == [1, 2]
    assert t["chapter"]["title"] == "甲"
    conn.close()


def test_chapter_text_empty(tmp_project):
    conn = get_connection(tmp_project)
    create_volume(conn, 1, "V", 9, 9, "opening")
    create_chapter(conn, volume_id=1, global_number=9, title="空", status="planned")
    conn.commit(); conn.close()
    conn = get_connection(tmp_project)
    t = chapter_text(conn, 9)
    assert t["paragraphs"] == []
    conn.close()


def test_outline_tree_full(tmp_project):
    conn = get_connection(tmp_project); v, c1, _, hz = _seed(conn)
    conn.execute("INSERT OR IGNORE INTO volume_outline(volume_id,status,beat_contracts) VALUES(?, 'drafted', ?)",
                 (v, json.dumps([{"beat_id": 1, "purpose": "契约"}])))
    conn.commit(); conn.close()
    conn = get_connection(tmp_project)
    tree = outline_tree(conn, v)
    assert tree["master_outline"] is None or isinstance(tree["master_outline"], dict)
    assert len(tree["volumes"]) == 1
    vol = tree["volumes"][0]
    assert vol["volume_outline"]["status"] == "drafted"
    ch = vol["chapters"][0]
    assert ch["beats"][0]["pov_name"] == "韩峥"
    assert ch["beats"][0]["paragraph_count"] == 2
    conn.close()


def test_outline_tree_missing_fields_null(tmp_project):
    conn = get_connection(tmp_project)
    create_volume(conn, 1, "V", 5, 5, "opening")
    create_chapter(conn, volume_id=1, global_number=5, title="裸", status="planned")
    conn.commit(); conn.close()
    conn = get_connection(tmp_project)
    tree = outline_tree(conn, 1)
    vol = tree["volumes"][0]
    assert vol["volume_outline"] is None
    assert vol["chapters"][0]["beats"] == []
    conn.close()


def test_list_characters_with_subcounts(tmp_project):
    conn = get_connection(tmp_project); _, _, _, hz = _seed(conn); conn.commit(); conn.close()
    conn = get_connection(tmp_project)
    cs = list_characters(conn)
    assert cs[0]["name"] == "韩峥"
    assert cs[0]["abilities"] == []
    assert cs[0]["secret_count"] == 0
    conn.close()


def test_worldbook_overview(tmp_project):
    conn = get_connection(tmp_project); _seed(conn); conn.commit(); conn.close()
    conn = get_connection(tmp_project)
    wb = worldbook_overview(conn)
    assert len(wb["locations"]) == 1 and wb["locations"][0]["name"] == "封锁线"
    assert len(wb["themes"]) == 1
    assert len(wb["motifs"]) == 1
    conn.close()


def test_list_factions(tmp_project):
    conn = get_connection(tmp_project); _seed(conn); conn.commit(); conn.close()
    conn = get_connection(tmp_project)
    fs = list_factions(conn)
    assert fs[0]["name"] == "守卫者"
    conn.close()
