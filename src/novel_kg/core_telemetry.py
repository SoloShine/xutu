"""
核心遥测模块 — 遥测数据保存 + 工具函数装饰器注入。

从 core.py 拆分，V27。
"""


def save_telemetry_chapter_report(project: str, chapter: int) -> dict:
    """保存指定章节的遥测报告到磁盘。"""
    from . import telemetry as _tel
    c = _tel.get_collector()
    if c is None:
        return {"status": "no_collector", "message": "遥测未激活"}
    path = c.save_chapter_report(chapter, project=project)
    if path is None:
        return {"status": "no_data", "message": f"第{chapter}章无遥测数据"}
    return {"status": "ok", "path": path}


def set_telemetry_wall_clock(project: str, chapter: int,
                             wall_clock_ms: float,
                             agent_tool_uses: int = None) -> dict:
    """注入子代理端到端墙钟时间（主会话在子代理返回后调用）。"""
    from . import telemetry as _tel
    c = _tel.get_collector()
    if c is None:
        return {"status": "no_collector", "message": "遥测未激活"}
    c.set_wall_clock(chapter, wall_clock_ms, agent_tool_uses=agent_tool_uses)
    return {"status": "ok", "chapter": chapter, "wall_clock_ms": wall_clock_ms}


def save_telemetry_session_summary(project: str) -> dict:
    """保存会话遥测摘要到磁盘。"""
    from . import telemetry as _tel
    c = _tel.get_collector()
    if c is None:
        return {"status": "no_collector", "message": "遥测未激活"}
    path = c.save_session_summary(project=project)
    return {"status": "ok", "path": path}
