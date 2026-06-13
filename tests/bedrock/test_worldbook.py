# tests/bedrock/test_worldbook.py
import sqlite3
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.worldbook import (
    add_constant, get_constant, add_location, add_neighbor, neighbors_of,
    add_faction, add_theme,
)


def test_constants_unique_key(tmp_project):
    conn = get_connection(tmp_project)
    add_constant(conn, key="载波频率", value="7.83Hz")
    with pytest.raises(sqlite3.IntegrityError):
        add_constant(conn, key="载波频率", value="9.0Hz")
    assert get_constant(conn, "载波频率")["value"] == "7.83Hz"
    conn.close()


def test_location_neighbors(tmp_project):
    conn = get_connection(tmp_project)
    a = add_location(conn, name="中枢设施", loc_type="设施")
    b = add_location(conn, name="观测站", loc_type="设施")
    add_neighbor(conn, from_id=a, to_id=b, travel_days=3)
    assert [n["to_id"] for n in neighbors_of(conn, a)] == [b]
    conn.close()


def test_faction_self_parent_null_ok(tmp_project):
    conn = get_connection(tmp_project)
    fid = add_faction(conn, name="人族残部", ftype="阵营", stance="防御")
    sub = add_faction(conn, name="中枢守备", ftype="组织", stance="防御", parent_faction_id=fid)
    assert sub is not None
    conn.close()
