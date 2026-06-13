# src/bedrock/db/connection.py
import sqlite3
from pathlib import Path

DB_FILENAME = "bedrock.db"


def get_connection(project_dir: Path) -> sqlite3.Connection:
    db_path = Path(project_dir) / DB_FILENAME
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
