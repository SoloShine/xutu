"""
核心缓存模块 — 目的检查缓存（SHA256）。

从 core.py 拆分，V27。
"""

import os
import json
import hashlib

# 项目目录（与 core.py 共享路径逻辑）
_here = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.normpath(os.path.join(_here, '..', '..'))
_projects_dir = os.environ.get('KG_PROJECTS_DIR') or os.path.join(_repo_root, 'projects')


def purpose_cache_dir(project: str) -> str:
    return os.path.join(_projects_dir, project, "cache", "purpose_checks")


def purpose_cache_path(project: str, chapter: int) -> str:
    return os.path.join(purpose_cache_dir(project), f"purpose_ch{chapter}.json")


def purpose_cache_hash(purpose: str, events: list) -> str:
    """从目的文本和事件数据计算缓存键。"""
    content = purpose
    for ev in events:
        content += ev.get("title", "") + ev.get("detail", "")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def read_purpose_cache(project: str, chapter: int,
                       purpose: str, events: list) -> dict | None:
    """读取缓存的目的检查结果，命中返回 result dict，否则 None。"""
    path = purpose_cache_path(project, chapter)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("hash") == purpose_cache_hash(purpose, events):
            return cached.get("result")
    except Exception as e:
        import sys
        print(f"[core_cache] read_purpose_cache 读取失败: {e}", file=sys.stderr)
    return None


def write_purpose_cache(project: str, chapter: int,
                        purpose: str, events: list, result: dict):
    """写入目的检查结果缓存。"""
    from datetime import datetime
    os.makedirs(purpose_cache_dir(project), exist_ok=True)
    cache_data = {
        "hash": purpose_cache_hash(purpose, events),
        "result": result,
        "timestamp": datetime.now().isoformat(),
    }
    path = purpose_cache_path(project, chapter)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)


def invalidate_purpose_cache(project: str, chapter: int):
    """删除某章的目的检查缓存。"""
    path = purpose_cache_path(project, chapter)
    if os.path.exists(path):
        os.remove(path)
