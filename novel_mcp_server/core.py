"""
Novel KG 工具核心逻辑。

连接池 + 破坏性保护 + 26个业务函数。
server.py（MCP）和 mcp_cli.py（CLI）共享此模块。
"""

import sys
import os
import json
import atexit

# 定位 novel_kg_mvp 目录
_mvp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'novel_kg_mvp')
_mvp_dir = os.path.normpath(_mvp_dir)
os.chdir(_mvp_dir)
if _mvp_dir not in sys.path:
    sys.path.insert(0, _mvp_dir)

from graph import NovelKG
from mine import (
    build_extraction_prompt, detect_conflicts,
    write_extraction_to_graph,
    clear_chapter_data as _mine_clear_chapter,
)
from main import build_writing_prompt
from prompts import ARC_DERIVATION_PROMPT
from validators import validate_chapter as _run_validation


# ============================================================
# Connection Pool
# ============================================================

_pool: dict[str, NovelKG] = {}


def _kg(project: str) -> NovelKG:
    """获取或创建连接池中的 NovelKG 实例。"""
    if project not in _pool:
        _pool[project] = NovelKG(project=project)
    return _pool[project]


def close_all():
    """关闭所有池化连接。"""
    for kg in _pool.values():
        kg.close()
    _pool.clear()


atexit.register(close_all)


# ============================================================
# Destructive Operation Guard
# ============================================================

DESTRUCTIVE_CONFIRM = "I_UNDERSTAND_THIS_IS_DESTRUCTIVE"


def _check_destructive(confirm: str) -> str | None:
    """检查破坏性操作确认。返回 None 表示通过，返回字符串为拒绝原因。"""
    if confirm != DESTRUCTIVE_CONFIRM:
        return f"[BLOCKED] 破坏性操作已拦截。需传入 confirm='{DESTRUCTIVE_CONFIRM}' 以确认执行。"
    return None


# ============================================================
# 1. Query Tools (read-only)
# ============================================================

def get_chapter_context(project: str, chapter: int) -> dict:
    kg = _kg(project)
    return kg.get_context_for_chapter(chapter)


def get_derivation_context(project: str, chapter: int, lookback: int = 3) -> dict:
    kg = _kg(project)
    return kg.get_arc_derivation_context(chapter, lookback=lookback)


def get_graph_stats(project: str) -> dict:
    kg = _kg(project)
    return kg.stats()


def check_consistency(project: str) -> list:
    kg = _kg(project)
    return kg.check_consistency()


def get_unresolved_threads(project: str, chapter: int) -> list:
    kg = _kg(project)
    return kg.get_unresolved_threads(chapter)


def get_all_threads(project: str) -> list:
    kg = _kg(project)
    return kg.get_all_threads()


# ============================================================
# 2. Prompt Template Tools
# ============================================================

def get_extraction_prompt(project: str, chapter: int, chapter_text: str) -> str:
    kg = _kg(project)
    return build_extraction_prompt(kg, chapter, chapter_text)


def get_writing_prompt(project: str, chapter: int) -> str:
    kg = _kg(project)
    context = kg.get_context_for_chapter(chapter)
    return build_writing_prompt(context, chapter)


def get_derivation_prompt(project: str, chapter: int) -> str:
    kg = _kg(project)
    ctx = kg.get_arc_derivation_context(chapter)

    arcs_text = json.dumps(
        [{k: v for k, v in a.items() if k != "chapter"}
         for a in ctx["recent_arcs"]], ensure_ascii=False, indent=2)
    events_text = json.dumps(
        [{"id": e["id"], "title": e.get("title", ""), "type": e.get("type", ""),
          "detail": e.get("detail", "")}
         for e in ctx["recent_events"]], ensure_ascii=False, indent=2)
    chars_text = json.dumps(
        [{"name": c["name"], "role": c.get("role", ""),
          "personality": c.get("personality", "")}
         for c in ctx["characters"]], ensure_ascii=False, indent=2)
    themes_text = json.dumps(
        [{"name": t["name"], "description": t.get("description", ""),
          "chapters": t.get("chapters", "")}
         for t in ctx["themes"]], ensure_ascii=False, indent=2)
    motifs_text = json.dumps(
        [{"name": m["name"], "meaning": m.get("meaning", ""),
          "evolution": m.get("evolution", "")}
         for m in ctx["motifs"]], ensure_ascii=False, indent=2)
    last_event_text = json.dumps(
        ctx["last_event"], ensure_ascii=False, indent=2
    ) if ctx["last_event"] else "无"
    outline_text = json.dumps(
        ctx.get("outline_entry"), ensure_ascii=False, indent=2
    ) if ctx.get("outline_entry") else "无"
    threads_text = json.dumps(
        [{"id": t.get("id", ""), "content": t.get("content", ""),
          "status": t.get("status", ""), "importance": t.get("importance", "")}
         for t in ctx.get("suspense_threads", [])],
        ensure_ascii=False, indent=2
    ) if ctx.get("suspense_threads") else "无"

    return ARC_DERIVATION_PROMPT.format(
        outline_entry=outline_text, suspense_threads=threads_text,
        recent_arcs=arcs_text, recent_events=events_text,
        characters=chars_text, themes=themes_text, motifs=motifs_text,
        last_event=last_event_text)


# ============================================================
# 3. Write Tools
# ============================================================

def init_project(project: str, confirm: str = "") -> str:
    err = _check_destructive(confirm)
    if err:
        return err
    kg = _kg(project)
    kg.clear_project()
    # 清除池中的旧实例，下次访问时重建
    kg.close()
    _pool.pop(project, None)
    return f"项目 '{project}' 图谱已清空。"


def add_character(project: str, name: str, role: str = "",
                  personality: str = "", gap_relation: str = "") -> str:
    kg = _kg(project)
    props = {}
    if role:
        props["role"] = role
    if personality:
        props["personality"] = personality
    if gap_relation:
        props["gap_relation"] = gap_relation
    kg.add_character(name, **props)
    return f"已添加人物: {name}"


def add_location(project: str, name: str, loc_type: str = "",
                 description: str = "") -> str:
    kg = _kg(project)
    props = {}
    if loc_type:
        props["type"] = loc_type
    if description:
        props["description"] = description
    kg.add_location(name, **props)
    return f"已添加地点: {name}"


def add_event(project: str, event_id: str, title: str = "", detail: str = "",
              chapter: int = 0, event_type: str = "daily",
              is_gap: bool = False, gap_level: int = 0) -> str:
    kg = _kg(project)
    props = {}
    if title:
        props["title"] = title
    if detail:
        props["detail"] = detail
    if chapter:
        props["chapter"] = chapter
    props["type"] = event_type
    props["is_gap"] = is_gap
    props["gap_level"] = gap_level
    kg.add_event(event_id, **props)
    return f"已添加事件: {event_id} '{title}'"


def add_chapter_arc(project: str, chapter: int, purpose: str, scenes: str,
                    ending: str, gap_note: str = "",
                    structure_type: str = "linear", time_jumps: str = "",
                    thread_plan: str = "", reasoning: str = "") -> str:
    kg = _kg(project)
    props = {"purpose": purpose, "scenes": scenes, "ending": ending}
    if gap_note:
        props["gap_note"] = gap_note
    if structure_type and structure_type != "linear":
        props["structure_type"] = structure_type
    if time_jumps:
        if not isinstance(time_jumps, str):
            time_jumps = json.dumps(time_jumps, ensure_ascii=False)
        props["time_jumps"] = time_jumps
    if thread_plan:
        if not isinstance(thread_plan, str):
            thread_plan = json.dumps(thread_plan, ensure_ascii=False)
        props["thread_plan"] = thread_plan
    if reasoning:
        props["reasoning"] = reasoning
    kg.add_chapter_arc(chapter, **props)
    return f"已添加第{chapter}章弧线: {purpose}"


def add_suspense_thread(project: str, thread_id: str, content: str,
                        planted_chapter: int, importance: str = "medium",
                        thread_type: str = "foreshadowing") -> str:
    kg = _kg(project)
    kg.add_suspense_thread(thread_id, content=content,
                           planted_chapter=planted_chapter,
                           importance=importance,
                           thread_type=thread_type, status="planted")
    return f"已添加悬念线: {thread_id} - {content[:40]}"


def add_outline_entry(project: str, chapter: int, purpose: str,
                      key_events: str = "", threads_to_plant: str = "",
                      threads_to_resolve: str = "",
                      structure_hint: str = "") -> str:
    kg = _kg(project)
    props = {"purpose": purpose}
    if key_events:
        props["key_events"] = key_events
    if threads_to_plant:
        props["threads_to_plant"] = threads_to_plant
    if threads_to_resolve:
        props["threads_to_resolve"] = threads_to_resolve
    if structure_hint:
        props["structure_hint"] = structure_hint
    kg.add_outline_entry(chapter, **props)
    return f"已添加第{chapter}章大纲: {purpose}"


def add_style_guide(project: str, guide_id: str, rule: str) -> str:
    kg = _kg(project)
    kg.add_style_guide(guide_id, rule=rule)
    return f"已添加风格规则: {guide_id}"


def add_motif(project: str, name: str, meaning: str = "",
              evolution: str = "") -> str:
    kg = _kg(project)
    props = {}
    if meaning:
        props["meaning"] = meaning
    if evolution:
        props["evolution"] = evolution
    kg.add_motif(name, **props)
    return f"已添加意象: {name}"


def add_theme(project: str, name: str, description: str = "",
              chapters: str = "") -> str:
    kg = _kg(project)
    props = {}
    if description:
        props["description"] = description
    if chapters:
        props["chapters"] = chapters
    kg.add_theme(name, **props)
    return f"已添加主题: {name}"


def add_time_period(project: str, label: str, chapter_start: int,
                    chapter_end: int, years: str = "",
                    theme: str = "") -> str:
    kg = _kg(project)
    props = {"chapter_start": chapter_start, "chapter_end": chapter_end}
    if years:
        props["years"] = years
    if theme:
        props["theme"] = theme
    kg.add_time_period(label, **props)
    return f"已添加时间段: {label} (Ch{chapter_start}-{chapter_end})"


def add_relation(project: str, from_label: str, from_key: str,
                 from_val: str, rel_type: str, to_label: str,
                 to_key: str, to_val: str) -> str:
    kg = _kg(project)
    kg.add_relation(from_label, from_key, from_val, rel_type,
                    to_label, to_key, to_val)
    return f"已添加关系: {from_val} -{rel_type}-> {to_val}"


def update_suspense_thread(project: str, thread_id: str, status: str = "",
                           importance: str = "") -> str:
    kg = _kg(project)
    props = {}
    if status:
        props["status"] = status
    if importance:
        props["importance"] = importance
    kg.update_suspense_thread(thread_id, **props)
    return f"已更新悬念线: {thread_id}"


def write_extraction(project: str, chapter: int,
                     extracted_json: str) -> dict:
    kg = _kg(project)
    if isinstance(extracted_json, str):
        extracted = json.loads(extracted_json)
    else:
        extracted = extracted_json
    report = write_extraction_to_graph(kg, chapter, extracted,
                                       skip_conflicts=True)
    return {
        "chapter": report["chapter"],
        "stats": report["stats"],
        "conflicts": report["conflicts"],
        "character_updates": report.get("character_updates", []),
        "notes": report.get("notes", ""),
    }


def clear_chapter_data(project: str, chapter: int,
                       confirm: str = "") -> str:
    err = _check_destructive(confirm)
    if err:
        return err
    kg = _kg(project)
    _mine_clear_chapter(kg, chapter)
    return f"已清除第{chapter}章的事件数据"


# ============================================================
# 4. Validation Tools
# ============================================================

def validate_chapter(project: str, text: str, chapter: int) -> dict:
    kg = _kg(project)
    context = kg.get_context_for_chapter(chapter)
    arc = context.get("chapter_arc", [None])
    arc = arc[0] if arc else None
    result = _run_validation(text, context, arc=arc)
    return {
        "passed": result.passed,
        "violations": [
            {"type": v.constraint_type, "severity": v.severity,
             "detail": v.detail, "fix": v.fix}
            for v in result.violations
        ],
    }


def detect_extraction_conflicts(project: str, extracted_json: str) -> list:
    kg = _kg(project)
    if isinstance(extracted_json, str):
        extracted = json.loads(extracted_json)
    else:
        extracted = extracted_json
    return detect_conflicts(kg, extracted)
