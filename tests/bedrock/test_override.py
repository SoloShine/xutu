# tests/bedrock/test_override.py
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat, update_beat_status, mark_override, get_beat,
)


def _seed_beat(conn, status="deviated"):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述")
    update_beat_status(conn, bid, status)
    return bid


def test_override_deviated_with_amendment(tmp_project):
    conn = get_connection(tmp_project)
    bid = _seed_beat(conn, "deviated")
    mark_override(conn, bid, reason="人工兜底，剧情需要", author="human")
    assert get_beat(conn, bid)["status"] == "overridden"
    ams = conn.execute("SELECT * FROM amendment WHERE entity_type='beat' AND entity_id=?", (bid,)).fetchall()
    assert len(ams) == 1
    assert ams[0]["new_value"] == "overridden"
    conn.close()


def test_override_written_also_allowed(tmp_project):
    """放宽：written 状态也可 override（人工兜底）。"""
    conn = get_connection(tmp_project)
    bid = _seed_beat(conn, "written")
    mark_override(conn, bid, reason="跳过校验", author="human")
    assert get_beat(conn, bid)["status"] == "overridden"
    conn.close()


def test_override_rejected_for_verified(tmp_project):
    """verified 状态不能 override（已通过校验，无需逃逸）。"""
    conn = get_connection(tmp_project)
    bid = _seed_beat(conn, "verified")
    with pytest.raises(ValueError):
        mark_override(conn, bid, reason="x", author="human")
    conn.close()
