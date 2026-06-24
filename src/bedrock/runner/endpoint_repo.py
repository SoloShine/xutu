# src/bedrock/runner/endpoint_repo.py
"""全局 LLM 端点目录 repo(操作 ~/.bedrock/global.db)。

每个端点:name(唯一)/provider/base_url/api_key/models[](该端点提供的模型)。
api_key:GET 默认掩码(不回全文),供 runner 的 mask=False 取真值。
"""
import json
from .global_db import get_global_conn


def _row_to_dict(r, mask):
    raw_key = r["api_key"] or ""
    models = json.loads(r["models"]) if r["models"] else []
    d = {"id": r["id"], "name": r["name"], "provider": r["provider"],
         "base_url": r["base_url"], "models": models, "updated_at": r["updated_at"]}
    if mask:
        d["api_key_set"] = bool(raw_key)
        d["api_key_tail"] = raw_key[-4:] if len(raw_key) >= 4 else ""
        d["api_key"] = ""   # 绝不回全文给前端
    else:
        d["api_key"] = raw_key
    return d


def list_endpoints(*, mask=True):
    """列全部端点(按 name 升序)。"""
    conn = get_global_conn()
    try:
        rows = conn.execute("SELECT * FROM llm_endpoint ORDER BY name").fetchall()
        return [_row_to_dict(r, mask) for r in rows]
    finally:
        conn.close()


def get_endpoint(name, *, mask=False):
    """按 name 取单个;不存在→ None。mask=False 时 api_key 含真值(runner 用)。"""
    conn = get_global_conn()
    try:
        r = conn.execute("SELECT * FROM llm_endpoint WHERE name=?", (name,)).fetchone()
        return _row_to_dict(r, mask) if r else None
    finally:
        conn.close()


def upsert_endpoint(name, *, provider=None, base_url=None, api_key=None, models=None):
    """按 name upsert。各字段 None=保留旧值;api_key 显式空串=清空。models=list[str]。
    返回 name。"""
    conn = get_global_conn()
    try:
        existing = conn.execute("SELECT * FROM llm_endpoint WHERE name=?", (name,)).fetchone()
        fields, vals = [], []
        if provider is not None:
            fields.append("provider=?"); vals.append(provider)
        if base_url is not None:
            fields.append("base_url=?"); vals.append(base_url)
        if api_key is not None:
            fields.append("api_key=?"); vals.append(api_key)
        if models is not None:
            fields.append("models=?"); vals.append(json.dumps(list(models), ensure_ascii=False))
        if existing:
            if fields:
                now = conn.execute("SELECT datetime('now')").fetchone()[0]
                fields.append("updated_at=?"); vals.append(now); vals.append(name)
                conn.execute(f"UPDATE llm_endpoint SET {', '.join(fields)} WHERE name=?", vals)
                conn.commit()
            return name
        # 新建(未给字段用列默认)
        now = conn.execute("SELECT datetime('now')").fetchone()[0]
        conn.execute(
            "INSERT INTO llm_endpoint(name, provider, base_url, api_key, models, updated_at) "
            "VALUES(?,?,?,?,?,?)",
            (name, provider or "anthropic", base_url or "", api_key or "",
             json.dumps(list(models) if models else [], ensure_ascii=False), now))
        conn.commit()
        return name
    finally:
        conn.close()


def delete_endpoint(name):
    """按 name 删;返回是否删除了。"""
    conn = get_global_conn()
    try:
        cur = conn.execute("DELETE FROM llm_endpoint WHERE name=?", (name,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
