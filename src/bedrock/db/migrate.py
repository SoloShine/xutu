# src/bedrock/db/migrate.py
from pathlib import Path
from src.bedrock.db.connection import get_connection

_SCHEMA_FILE = Path(__file__).parent / "schema.sql"


def apply_migrations(project_dir: Path) -> int:
    sql = _SCHEMA_FILE.read_text(encoding="utf-8")
    content_hash = _hash_sql(sql)
    conn = get_connection(project_dir)
    try:
        conn.executescript(sql)
        _migrate_style_template(conn)   # 旧 DB 补 style_template 新列(CREATE IF NOT EXISTS 不加列)
        version = _stable_version(content_hash)
        existing = conn.execute(
            "SELECT 1 FROM schema_version WHERE version=?", (version,)).fetchone()
        if not existing:
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
            conn.commit()
        return version
    finally:
        conn.close()


# style_template 历次新增列。CREATE TABLE IF NOT EXISTS 不会给已存在的表加列,
# 故对每个缺失列做幂等 ALTER TABLE ADD COLUMN(带默认值,旧行自动填充)。
_STYLE_TEMPLATE_NEW_COLUMNS = {
    "scope": "TEXT NOT NULL DEFAULT 'work'",
    "volume_id": "INTEGER",
    "directive": "TEXT NOT NULL DEFAULT ''",
    "word_count_target": "TEXT NOT NULL DEFAULT '[3000,5000]'",
    "max_edit_rounds": "INTEGER NOT NULL DEFAULT 3",
    "hygiene": "TEXT NOT NULL DEFAULT '{}'",
    "enabled_dims": "TEXT NOT NULL DEFAULT '[]'",
    "scalar_targets": "TEXT NOT NULL DEFAULT '{}'",
    "reference_sample": "TEXT NOT NULL DEFAULT ''",
    "directive_source": "TEXT NOT NULL DEFAULT ''",
}


def _migrate_style_template(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(style_template)")}
    for col, ddl in _STYLE_TEMPLATE_NEW_COLUMNS.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE style_template ADD COLUMN {col} {ddl}")
    conn.commit()


def _hash_sql(sql: str) -> str:
    import hashlib
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()[:12]


def _stable_version(content_hash: str) -> int:
    return int(content_hash[:8], 16) % 1000000
