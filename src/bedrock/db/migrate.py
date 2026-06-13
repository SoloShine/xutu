# src/bedrock/db/migrate.py
import sqlite3
from pathlib import Path
from src.bedrock.db.connection import get_connection

_SCHEMA_FILE = Path(__file__).parent / "schema.sql"


def _current_version(conn):
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return row[0] or 0


def apply_migrations(project_dir: Path) -> int:
    sql = _SCHEMA_FILE.read_text(encoding="utf-8")
    content_hash = _hash_sql(sql)
    conn = get_connection(project_dir)
    try:
        conn.executescript(sql)
        version = _stable_version(content_hash)
        existing = conn.execute(
            "SELECT 1 FROM schema_version WHERE version=?", (version,)).fetchone()
        if not existing:
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
            conn.commit()
        return version
    finally:
        conn.close()


def _hash_sql(sql: str) -> str:
    import hashlib
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()[:12]


def _stable_version(content_hash: str) -> int:
    return int(content_hash[:8], 16) % 1000000
