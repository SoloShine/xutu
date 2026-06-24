# src/bedrock/runner/default_repo.py
"""全局默认缺省模型 repo(操作 ~/.bedrock/global.db llm_default 单行表)。

作品级 workflow_config.models 未绑的流程回退到此默认(endpoint+model)。
作品绑定仅在填写时覆盖;未填 → 用默认。set_default 不校验端点是否存在(允许先设后建端点),
由 llm 解析时 get_endpoint 统一判。
"""
from .global_db import get_global_conn


def get_default():
    """取默认 {endpoint_name, model};未设(空)→ None。"""
    conn = get_global_conn()
    try:
        r = conn.execute("SELECT endpoint_name, model FROM llm_default WHERE id=1").fetchone()
        if r is None or not (r["endpoint_name"] or ""):
            return None
        return {"endpoint_name": r["endpoint_name"], "model": r["model"] or ""}
    finally:
        conn.close()


def set_default(endpoint_name, model=""):
    """upsert 默认(单行 id=1)。endpoint_name 空=清空(等同 clear)。返回当前默认 dict 或 None。"""
    conn = get_global_conn()
    try:
        now = conn.execute("SELECT datetime('now')").fetchone()[0]
        ep = endpoint_name or ""
        conn.execute(
            "INSERT INTO llm_default(id, endpoint_name, model, updated_at) VALUES(1,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET endpoint_name=excluded.endpoint_name, "
            "model=excluded.model, updated_at=excluded.updated_at",
            (ep, model or "", now))
        conn.commit()
        return {"endpoint_name": ep, "model": model or ""} if ep else None
    finally:
        conn.close()


def clear_default():
    """清空默认(endpoint_name 置空)。"""
    conn = get_global_conn()
    try:
        conn.execute("UPDATE llm_default SET endpoint_name='', model='', "
                     "updated_at=datetime('now') WHERE id=1")
        # 若行不存在也插一行空(幂等)
        conn.execute(
            "INSERT OR IGNORE INTO llm_default(id, endpoint_name, model, updated_at) "
            "VALUES(1, '', '', datetime('now'))")
        conn.commit()
    finally:
        conn.close()
