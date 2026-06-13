# src/bedrock/init_project.py
from pathlib import Path
from src.bedrock.db.migrate import apply_migrations


def init_project(project_dir, work_name, force=False):
    """初始化新作品项目：建目录 + 空白 DB（全 schema）。不迁移历史数据。

    force=True 时删除既有 DB 文件后重建（覆盖式初始化，得到干净 schema）。
    """
    project_dir = Path(project_dir)
    db_path = project_dir / "bedrock.db"
    if db_path.exists():
        if not force:
            raise FileExistsError(f"{db_path} 已存在；传 force=True 覆盖")
        # 删除主库文件 + WAL 副本（WAL 模式下可能残留 -wal/-shm）
        for suffix in ("", "-wal", "-shm"):
            p = db_path.with_name(db_path.name + suffix)
            if p.exists():
                p.unlink()
    project_dir.mkdir(parents=True, exist_ok=True)
    apply_migrations(project_dir)
    from src.bedrock.db.connection import get_connection
    from src.bedrock.repositories.worldbook import add_constant
    conn = get_connection(project_dir)
    try:
        add_constant(conn, key="work_name", value=work_name, source_note="init_project")
        conn.commit()
    finally:
        conn.close()
