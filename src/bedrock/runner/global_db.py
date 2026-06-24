# src/bedrock/runner/global_db.py
"""全局配置 DB(跨项目共享)。默认 ~/.bedrock/global.db;BEDROCK_GLOBAL_CONFIG env 可覆盖路径。

存全局 LLM 端点目录(llm_endpoint 表)。web 控制台 + runner 都经此读写。
与项目 bedrock.db 分离:全局=有哪些 LLM;项目=每个流程用哪个 LLM(作品级绑定)。
"""
import os
import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_endpoint (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL DEFAULT 'anthropic',
    base_url TEXT NOT NULL DEFAULT '',
    api_key TEXT NOT NULL DEFAULT '',
    models TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 全局默认缺省模型(单行,id 锁=1)。workflow_config 未绑的流程回退到此(endpoint+model)。
-- 作品级绑定仅在填写时覆盖;未填 → 用此默认。
CREATE TABLE IF NOT EXISTS llm_default (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    endpoint_name TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def global_db_path() -> Path:
    """全局 DB 路径(env 覆盖 > ~/.bedrock/global.db)。"""
    env = os.environ.get("BEDROCK_GLOBAL_CONFIG")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".bedrock" / "global.db"


def get_global_conn() -> sqlite3.Connection:
    """连接全局 DB(建父目录 + 建表,幂等)。"""
    p = global_db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn
