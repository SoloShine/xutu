"""
后端同步工具 — JSON <-> Neo4j 双向同步。

读取源后端全部数据，写入目标后端。
两个后端共享相同接口，同步 = read_all + write_all。
"""

import json


def _read_all(kg) -> dict:
    """从任意后端读取全部数据"""
    return {
        "characters": kg.get_all_characters(),
        "locations": kg.get_all_locations(),
        "events": kg.get_all_events(),
        "themes": kg.get_all_themes(),
        "style_guides": kg.get_all_style_guides(),
        "motifs": kg.get_all_motifs(),
        "chapter_arcs": kg.get_all_chapter_arcs(),
        "suspense_threads": kg.get_all_threads(),
        "outline_entries": kg.get_all_outline_entries(),
        "time_periods": kg.get_all_time_periods(),
        "relations": kg.get_all_relations(),
    }


def _write_all(target_kg, data: dict) -> dict:
    """将全部数据写入目标后端（先清空再写）"""
    target_kg.clear_project()
    stats = {}

    # 1. 人物（goals 需单独处理）
    for char in data["characters"]:
        name = char.get("name", "")
        goals = char.get("goals", [])
        if isinstance(goals, str):
            goals = json.loads(goals)
        props = {k: v for k, v in char.items()
                 if k not in ("name", "goals", "project")}
        target_kg.add_character(name, **props)
        for g in goals:
            target_kg.add_character_goal(
                name,
                goal=g.get("goal", ""),
                goal_type=g.get("type", "pursue"),
                status=g.get("status", "new"),
                chapter=g.get("chapter", 0),
            )
    stats["characters"] = len(data["characters"])

    # 2. 地点
    for loc in data["locations"]:
        name = loc.get("name", "")
        props = {k: v for k, v in loc.items()
                 if k not in ("name", "project")}
        target_kg.add_location(name, **props)
    stats["locations"] = len(data["locations"])

    # 3. 事件
    for ev in data["events"]:
        eid = ev.get("id", "")
        props = {k: v for k, v in ev.items()
                 if k not in ("id", "project")}
        target_kg.add_event(eid, **props)
    stats["events"] = len(data["events"])

    # 4. 主题
    for th in data["themes"]:
        name = th.get("name", "")
        props = {k: v for k, v in th.items()
                 if k not in ("name", "project")}
        target_kg.add_theme(name, **props)
    stats["themes"] = len(data["themes"])

    # 5. 风格指南
    for sg in data["style_guides"]:
        gid = sg.get("id", "")
        props = {k: v for k, v in sg.items()
                 if k not in ("id", "project")}
        target_kg.add_style_guide(gid, **props)
    stats["style_guides"] = len(data["style_guides"])

    # 6. 意象
    for m in data["motifs"]:
        name = m.get("name", "")
        props = {k: v for k, v in m.items()
                 if k not in ("name", "project")}
        target_kg.add_motif(name, **props)
    stats["motifs"] = len(data["motifs"])

    # 7. 章节弧线
    for arc in data["chapter_arcs"]:
        ch = arc.get("chapter", 0)
        props = {k: v for k, v in arc.items()
                 if k not in ("chapter", "project")}
        target_kg.add_chapter_arc(ch, **props)
    stats["chapter_arcs"] = len(data["chapter_arcs"])

    # 8. 悬念线
    for st in data["suspense_threads"]:
        tid = st.get("id", "")
        props = {k: v for k, v in st.items()
                 if k not in ("id", "project")}
        target_kg.add_suspense_thread(tid, **props)
    stats["suspense_threads"] = len(data["suspense_threads"])

    # 9. 大纲条目
    for oe in data["outline_entries"]:
        ch = oe.get("chapter", 0)
        props = {k: v for k, v in oe.items()
                 if k not in ("chapter", "project")}
        target_kg.add_outline_entry(ch, **props)
    stats["outline_entries"] = len(data["outline_entries"])

    # 10. 时间段
    for tp in data["time_periods"]:
        label = tp.get("label", "")
        props = {k: v for k, v in tp.items()
                 if k not in ("label", "project")}
        target_kg.add_time_period(label, **props)
    stats["time_periods"] = len(data["time_periods"])

    # 11. 关系（最后写入，需要端点节点存在）
    for rel in data["relations"]:
        extra = {k: v for k, v in rel.items()
                 if k not in ("fl", "fk", "fv", "rt", "tl", "tk", "tv")}
        target_kg.add_relation(
            rel["fl"], rel["fk"], rel["fv"],
            rel["rt"],
            rel["tl"], rel["tk"], rel["tv"],
            **extra,
        )
    stats["relations"] = len(data["relations"])

    return stats


def sync_json_to_neo4j(project, json_backend=None, neo4j_backend=None):
    """从 JSON 后端导入到 Neo4j 后端"""
    if json_backend is None:
        from .kg_json import JsonKG
        import os
        _here = os.path.dirname(os.path.abspath(__file__))
        _repo_root = os.path.normpath(os.path.join(_here, '..', '..'))
        _projects_dir = os.environ.get('KG_PROJECTS_DIR') or os.path.join(_repo_root, 'projects')
        json_backend = JsonKG(project=project, data_dir=_projects_dir)

    if neo4j_backend is None:
        from .graph import NovelKG
        neo4j_backend = NovelKG(project=project)

    data = _read_all(json_backend)
    stats = _write_all(neo4j_backend, data)

    try:
        neo4j_backend.close()
    except Exception:
        pass

    return {
        "direction": "json_to_neo4j",
        "project": project,
        "stats": stats,
    }


def sync_neo4j_to_json(project, neo4j_backend=None, json_backend=None):
    """从 Neo4j 后端导出到 JSON 后端"""
    if neo4j_backend is None:
        from .graph import NovelKG
        neo4j_backend = NovelKG(project=project)

    if json_backend is None:
        from .kg_json import JsonKG
        import os
        _here = os.path.dirname(os.path.abspath(__file__))
        _repo_root = os.path.normpath(os.path.join(_here, '..', '..'))
        _projects_dir = os.environ.get('KG_PROJECTS_DIR') or os.path.join(_repo_root, 'projects')
        json_backend = JsonKG(project=project, data_dir=_projects_dir)

    data = _read_all(neo4j_backend)
    stats = _write_all(json_backend, data)

    try:
        neo4j_backend.close()
    except Exception:
        pass

    return {
        "direction": "neo4j_to_json",
        "project": project,
        "stats": stats,
    }
