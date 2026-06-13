# tests/bedrock/test_amendment.py
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.outline import (
    save_volume_outline, lock_volume_outline, unlock_volume_outline,
    relock_volume_outline, update_beat_contract, get_beat_contract,
    OutlineLockedError,
)
from src.bedrock.repositories.plot_tree import create_volume


def _seed_volume(conn):
    return create_volume(conn, 1, "v", 1, 3, "opening")


def _status(conn, vid):
    return conn.execute("SELECT status FROM volume_outline WHERE volume_id=?", (vid,)).fetchone()["status"]


def test_unlock_relock_with_amendment(tmp_project):
    conn = get_connection(tmp_project)
    vid = _seed_volume(conn)
    save_volume_outline(conn, vid, beat_contracts=[])
    lock_volume_outline(conn, vid)
    assert _status(conn, vid) == "locked"
    unlock_volume_outline(conn, vid, reason="修正 beat 契约", author="human")
    assert _status(conn, vid) == "drafted"
    ams = conn.execute("SELECT * FROM amendment WHERE entity_type='volume_outline'").fetchall()
    assert len(ams) == 1
    assert ams[0]["reason"] == "修正 beat 契约"
    relock_volume_outline(conn, vid)
    assert _status(conn, vid) == "locked"
    conn.close()


def test_update_beat_contract_blocked_when_locked(tmp_project):
    conn = get_connection(tmp_project)
    vid = _seed_volume(conn)
    save_volume_outline(conn, vid, beat_contracts=[])
    lock_volume_outline(conn, vid)
    with pytest.raises(OutlineLockedError):
        update_beat_contract(conn, vid, beat_id=1,
                             new_contract={"purpose": "x" * 10, "participating_characters": [], "advance_threads": []})
    conn.close()


def test_update_beat_contract_after_unlock(tmp_project):
    conn = get_connection(tmp_project)
    vid = _seed_volume(conn)
    save_volume_outline(conn, vid, beat_contracts=[])
    lock_volume_outline(conn, vid)
    unlock_volume_outline(conn, vid, reason="加 beat", author="human")
    update_beat_contract(conn, vid, beat_id=1,
                         new_contract={"purpose": "林深发现注记", "participating_characters": ["林深"], "advance_threads": []})
    c = get_beat_contract(conn, vid, beat_id=1)
    assert c["purpose"] == "林深发现注记"
    assert "林深" in c["participating_characters"]
    conn.close()
