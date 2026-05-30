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


def inject_agent_phase(project: str, chapter: int, phase: str,
                       duration_ms: float, tool_uses: int = None) -> dict:
    """注入子代理阶段遥测数据（写初稿/编辑/提取等）。"""
    from . import telemetry as _tel
    c = _tel.get_collector()
    if c is None:
        # 懒初始化（与 _kg() 中的逻辑一致）
        _tel.init_telemetry(project)
        c = _tel.get_collector()
    c.inject_agent_phase(chapter, phase, duration_ms, tool_uses=tool_uses)
    # 立即保存到文件
    c.save_chapter_report(chapter, project=project)
    return {"status": "ok", "chapter": chapter, "phase": phase}


def inject_chapter_metrics(project: str, chapter: int,
                           word_count: int = None,
                           editing_corrections: int = None,
                           editing_types: str = None) -> dict:
    """注入章节指标（字数、编辑修正数量/类型等）。"""
    from . import telemetry as _tel
    c = _tel.get_collector()
    if c is None:
        _tel.init_telemetry(project)
        c = _tel.get_collector()
    metrics = {}
    if word_count is not None:
        metrics["word_count"] = word_count
    if editing_corrections is not None:
        metrics["editing_corrections"] = editing_corrections
    if editing_types is not None:
        metrics["editing_types"] = [t.strip() for t in editing_types.split(",")]
    c.inject_chapter_metrics(chapter, metrics)
    c.save_chapter_report(chapter, project=project)
    return {"status": "ok", "chapter": chapter, "metrics": metrics}
