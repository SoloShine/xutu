# tests/bedrock/test_outline.py
import json
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.outline import (
    save_volume_outline, get_volume_outline, lock_volume_outline,
    save_master_outline, get_master_outline,
    add_inspiration, consume_inspiration,
)
from src.bedrock.repositories.plot_tree import create_volume
import pytest
from src.bedrock.repositories.character import create_character
from src.bedrock.repositories.outline import update_inspiration_content


def test_volume_outline_lock(tmp_project):
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    save_volume_outline(conn, vid, beat_contracts=[{"chapter": 1, "beats": []}])
    assert get_volume_outline(conn, vid)["status"] == "drafted"
    lock_volume_outline(conn, vid)
    assert get_volume_outline(conn, vid)["status"] == "locked"
    conn.close()


def test_master_outline_single_row(tmp_project):
    conn = get_connection(tmp_project)
    save_master_outline(conn, key_milestones=[{"name": "觉醒", "expected_volume": 2}])
    mo = get_master_outline(conn)
    assert json.loads(mo["key_milestones"])[0]["name"] == "觉醒"
    save_master_outline(conn, key_milestones=[{"name": "觉醒", "expected_volume": 3}])
    assert len(conn.execute("SELECT * FROM master_outline").fetchall()) == 1
    conn.close()


def test_inspiration_lifecycle(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="一个能听到城市电流声的主角", type="character")
    consume_inspiration(conn, iid, target_type="character", target_id=1)
    row = conn.execute("SELECT status FROM inspiration WHERE id=?", (iid,)).fetchone()
    assert row["status"] == "consumed"
    conn.close()


from src.bedrock.repositories.outline import (
    list_inspirations, advance_inspiration,
)


def test_list_inspirations_all(tmp_project):
    conn = get_connection(tmp_project)
    add_inspiration(conn, content="a", type="scene")
    add_inspiration(conn, content="b", type="twist")
    items = list_inspirations(conn)
    assert len(items) == 2
    assert items[0]["content"] == "b"   # created_at 倒序


def test_list_inspirations_filter(tmp_project):
    conn = get_connection(tmp_project)
    add_inspiration(conn, content="a", type="scene")
    add_inspiration(conn, content="b", type="twist")
    assert len(list_inspirations(conn, type_filter="scene")) == 1
    assert len(list_inspirations(conn, status_filter="raw")) == 2


def test_advance_raw_to_refined_sets_refined_at(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    row = advance_inspiration(conn, iid, "refined")
    assert row["status"] == "refined"
    assert row["refined_at"] is not None


def test_advance_refined_to_consumed_sets_promoted_at(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    advance_inspiration(conn, iid, "refined")
    row = advance_inspiration(conn, iid, "consumed")
    assert row["status"] == "consumed"
    assert row["promoted_at"] is not None


def test_advance_partial_to_consumed(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    advance_inspiration(conn, iid, "refined")
    advance_inspiration(conn, iid, "partial")
    row = advance_inspiration(conn, iid, "consumed")
    assert row["status"] == "consumed"


def test_advance_raw_to_consumed_direct(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    row = advance_inspiration(conn, iid, "consumed")
    assert row["status"] == "consumed"


def test_advance_illegal_rejected(tmp_project):
    import pytest
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    advance_inspiration(conn, iid, "refined")
    advance_inspiration(conn, iid, "consumed")
    with pytest.raises(ValueError):   # consumed → raw 非法
        advance_inspiration(conn, iid, "raw")
    assert conn.execute("SELECT status FROM inspiration WHERE id=?", (iid,)).fetchone()["status"] == "consumed"
    conn.close()


def test_advance_discarded_terminal(tmp_project):
    import pytest
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    advance_inspiration(conn, iid, "discarded")
    with pytest.raises(ValueError):
        advance_inspiration(conn, iid, "refined")
    conn.close()


def test_advance_unknown_id(tmp_project):
    import pytest
    conn = get_connection(tmp_project)
    with pytest.raises(ValueError):
        advance_inspiration(conn, 999, "refined")
    conn.close()


def test_consume_inspiration_composes_advance_and_multi_target(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")  # raw
    consume_inspiration(conn, iid, target_type="character", target_id=1)
    row1 = conn.execute("SELECT status, promoted_at, consumed_into FROM inspiration WHERE id=?", (iid,)).fetchone()
    assert row1["status"] == "consumed"
    assert row1["promoted_at"] is not None   # 经 advance 设了
    consume_inspiration(conn, iid, target_type="chapter", target_id=5)
    row2 = conn.execute("SELECT consumed_into FROM inspiration WHERE id=?", (iid,)).fetchone()
    into = json.loads(row2["consumed_into"])
    assert len(into) == 2   # 多 target
    conn.close()


def test_update_content_raw_ok(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="原", type="scene")
    row = update_inspiration_content(conn, iid, content="新内容")
    assert row["content"] == "新内容"
    conn.close()


def test_update_content_refined_partial_ok(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    advance_inspiration(conn, iid, "refined")
    update_inspiration_content(conn, iid, content="改")
    iid2 = add_inspiration(conn, content="y", type="scene")
    advance_inspiration(conn, iid2, "refined"); advance_inspiration(conn, iid2, "partial")
    update_inspiration_content(conn, iid2, content="改2")
    conn.close()


def test_update_content_frozen_consumed(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    hz = create_character(conn, name="韩", pronoun="他", role="protagonist")
    consume_inspiration(conn, iid, target_type="character", target_id=hz)
    with pytest.raises(ValueError):
        update_inspiration_content(conn, iid, content="改")
    assert conn.execute("SELECT content FROM inspiration WHERE id=?", (iid,)).fetchone()["content"] == "x"
    conn.close()


def test_update_content_frozen_discarded(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    advance_inspiration(conn, iid, "discarded")
    with pytest.raises(ValueError):
        update_inspiration_content(conn, iid, content="改")
    conn.close()


def test_update_content_unknown_id(tmp_project):
    conn = get_connection(tmp_project)
    with pytest.raises(ValueError):
        update_inspiration_content(conn, 9999, content="x")
    conn.close()


def test_update_content_empty_rejected(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    with pytest.raises(ValueError):
        update_inspiration_content(conn, iid, content="   ")
    conn.close()


def test_update_content_with_source(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    row = update_inspiration_content(conn, iid, content="改", source="新来源")
    assert row["source"] == "新来源"
    conn.close()
