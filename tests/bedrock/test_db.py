# tests/bedrock/test_db.py
import sqlite3
from pathlib import Path
from src.bedrock.db.connection import get_connection
from src.bedrock.db.migrate import apply_migrations


def test_get_connection_opens_sqlite_with_wal(tmp_project):
    conn = get_connection(tmp_project)
    assert isinstance(conn, sqlite3.Connection)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"
    conn.close()


def test_apply_migrations_creates_schema_version(tmp_project):
    apply_migrations(tmp_project)
    conn = get_connection(tmp_project)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "schema_version" in tables
    ver = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert ver >= 1
    conn.close()
