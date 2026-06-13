# tests/bedrock/test_outline.py
import json
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.outline import (
    save_volume_outline, get_volume_outline, lock_volume_outline,
    save_master_outline, get_master_outline,
    add_inspiration, consume_inspiration,
)
from src.bedrock.repositories.plot_tree import create_volume


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
