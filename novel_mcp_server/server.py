"""
Novel Knowledge Graph MCP Server

将图谱操作和prompt模板暴露为MCP工具，供Code Agent直接调用。
Agent通过这些工具读取图谱上下文、获取生成指导、写回结构化数据，
自身作为LLM完成生成/提取/推演，无需额外API调用。

用法（Claude Code配置）:
  {
    "mcpServers": {
      "novel-kg": {
        "command": "python",
        "args": ["D:/novel_test/novel_mcp_server/server.py"],
        "cwd": "D:/novel_test/novel_kg_mvp"
      }
    }
  }
"""

import sys
import os
import json

# 定位 novel_kg_mvp 目录（与 novel_mcp_server 同级）
_mvp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'novel_kg_mvp')
_mvp_dir = os.path.normpath(_mvp_dir)

# 切换工作目录（graph.py 的 load_config() 用相对路径读 config.yaml）
os.chdir(_mvp_dir)

# 添加到 sys.path
if _mvp_dir not in sys.path:
    sys.path.insert(0, _mvp_dir)

from mcp.server.fastmcp import FastMCP
from graph import NovelKG
from mine import (
    build_extraction_prompt, detect_conflicts,
    write_extraction_to_graph, clear_chapter_data
)
from main import build_writing_prompt
from prompts import EXTRACTION_PROMPT, ARC_DERIVATION_PROMPT
from validators import validate_chapter as _run_validation

mcp = FastMCP("novel-kg", instructions="小说知识图谱工具集。通过Neo4j存储和查询三层图谱（结构层/风格层/情节层），支持章节续写、结构化提取、弧线推演等操作。")


def _kg(project: str) -> NovelKG:
    return NovelKG(project=project)


# ============================================================
# 1. 图谱查询工具（只读）
# ============================================================

@mcp.tool()
def get_chapter_context(project: str, chapter: int) -> dict:
    """获取写第N章时需要的全部图谱上下文。

    返回：人物状态、前一章事件、地点、主题、风格指南、意象、情节弧线、悬念线、大纲条目。
    这是续写章节的核心输入——Agent据此理解当前故事状态。
    """
    kg = _kg(project)
    try:
        return kg.get_context_for_chapter(chapter)
    finally:
        kg.close()


@mcp.tool()
def get_derivation_context(project: str, chapter: int, lookback: int = 3) -> dict:
    """获取推演第N章ChapterArc所需的上下文。

    返回：近N章弧线、近N章事件、人物、主题、意象、最后事件、大纲条目、悬念线。
    用于在写新章节前推演其叙事结构。
    """
    kg = _kg(project)
    try:
        return kg.get_arc_derivation_context(chapter, lookback=lookback)
    finally:
        kg.close()


@mcp.tool()
def get_graph_stats(project: str) -> dict:
    """获取项目图谱统计信息。返回各类节点和关系的数量。"""
    kg = _kg(project)
    try:
        return kg.stats()
    finally:
        kg.close()


@mcp.tool()
def check_consistency(project: str) -> list:
    """检查图谱一致性。返回时空矛盾、间隙强度异常、章节缺失事件等问题列表。"""
    kg = _kg(project)
    try:
        return kg.check_consistency()
    finally:
        kg.close()


@mcp.tool()
def get_unresolved_threads(project: str, chapter: int) -> list:
    """获取到第N章时仍未解决的悬念线。按重要性降序排列。"""
    kg = _kg(project)
    try:
        return kg.get_unresolved_threads(chapter)
    finally:
        kg.close()


@mcp.tool()
def get_all_threads(project: str) -> list:
    """获取项目中全部悬念线（用于审计）。"""
    kg = _kg(project)
    try:
        return kg.get_all_threads()
    finally:
        kg.close()


# ============================================================
# 2. Prompt模板工具
# ============================================================

@mcp.tool()
def get_extraction_prompt(project: str, chapter: int, chapter_text: str) -> str:
    """获取填充后的提取prompt模板。

    返回精心调校的提取指导文本，包含：已有人物列表、悬念线、粒度控制规则、
    间隙精确定义、JSON schema。Agent按此prompt的schema输出结构化数据，
    然后调用 write_extraction 写回图谱。
    """
    kg = _kg(project)
    try:
        prompt = build_extraction_prompt(kg, chapter, chapter_text)
        return prompt
    finally:
        kg.close()


@mcp.tool()
def get_writing_prompt(project: str, chapter: int) -> str:
    """获取填充后的续写prompt。

    返回包含完整图谱上下文的续写指导：章节弧线、时间段、前一章事件、
    人物状态、地点、主题、风格指南、意象、悬念线、大纲约束、场景展开要求。
    Agent据此生成章节正文。
    """
    kg = _kg(project)
    try:
        context = kg.get_context_for_chapter(chapter)
        prompt = build_writing_prompt(context, chapter)
        return prompt
    finally:
        kg.close()


@mcp.tool()
def get_derivation_prompt(project: str, chapter: int) -> str:
    """获取填充后的章节弧线推演prompt。

    返回推演指导文本，包含：大纲约束、悬念线、近章弧线/事件、人物、
    主题、意象、推演规则。Agent按返回的JSON schema输出arc数据，
    然后调用 add_chapter_arc 写入图谱。
    """
    kg = _kg(project)
    try:
        ctx_data = kg.get_arc_derivation_context(chapter)

        arcs_text = json.dumps(
            [{k: v for k, v in a.items() if k != "chapter"}
             for a in ctx_data["recent_arcs"]], ensure_ascii=False, indent=2
        )
        events_text = json.dumps(
            [{"id": e["id"], "title": e.get("title", ""), "type": e.get("type", ""),
              "detail": e.get("detail", "")}
             for e in ctx_data["recent_events"]], ensure_ascii=False, indent=2
        )
        chars_text = json.dumps(
            [{"name": c["name"], "role": c.get("role", ""),
              "personality": c.get("personality", "")}
             for c in ctx_data["characters"]], ensure_ascii=False, indent=2
        )
        themes_text = json.dumps(
            [{"name": t["name"], "description": t.get("description", ""),
              "chapters": t.get("chapters", "")}
             for t in ctx_data["themes"]], ensure_ascii=False, indent=2
        )
        motifs_text = json.dumps(
            [{"name": m["name"], "meaning": m.get("meaning", ""),
              "evolution": m.get("evolution", "")}
             for m in ctx_data["motifs"]], ensure_ascii=False, indent=2
        )
        last_event_text = json.dumps(
            ctx_data["last_event"], ensure_ascii=False, indent=2
        ) if ctx_data["last_event"] else "无"
        outline_text = json.dumps(
            ctx_data.get("outline_entry"), ensure_ascii=False, indent=2
        ) if ctx_data.get("outline_entry") else "无"
        threads_text = json.dumps(
            [{"id": t.get("id", ""), "content": t.get("content", ""),
              "status": t.get("status", ""), "importance": t.get("importance", "")}
             for t in ctx_data.get("suspense_threads", [])],
            ensure_ascii=False, indent=2
        ) if ctx_data.get("suspense_threads") else "无"

        prompt = ARC_DERIVATION_PROMPT.format(
            outline_entry=outline_text,
            suspense_threads=threads_text,
            recent_arcs=arcs_text,
            recent_events=events_text,
            characters=chars_text,
            themes=themes_text,
            motifs=motifs_text,
            last_event=last_event_text
        )
        return prompt
    finally:
        kg.close()


# ============================================================
# 3. 图谱写入工具
# ============================================================

@mcp.tool()
def init_project(project: str) -> str:
    """清空指定项目的图谱数据（不影响其他项目）。谨慎使用。"""
    kg = _kg(project)
    try:
        kg.clear_project()
        return f"项目 '{project}' 图谱已清空。"
    finally:
        kg.close()


@mcp.tool()
def add_character(project: str, name: str, role: str = "", personality: str = "",
                  gap_relation: str = "") -> str:
    """添加/更新人物节点。"""
    kg = _kg(project)
    try:
        props = {}
        if role:
            props["role"] = role
        if personality:
            props["personality"] = personality
        if gap_relation:
            props["gap_relation"] = gap_relation
        kg.add_character(name, **props)
        return f"已添加人物: {name}"
    finally:
        kg.close()


@mcp.tool()
def add_location(project: str, name: str, loc_type: str = "", description: str = "") -> str:
    """添加/更新地点节点。"""
    kg = _kg(project)
    try:
        props = {}
        if loc_type:
            props["type"] = loc_type
        if description:
            props["description"] = description
        kg.add_location(name, **props)
        return f"已添加地点: {name}"
    finally:
        kg.close()


@mcp.tool()
def add_event(project: str, event_id: str, title: str = "", detail: str = "",
              chapter: int = 0, event_type: str = "daily", is_gap: bool = False,
              gap_level: int = 0) -> str:
    """添加/更新事件节点。event_id格式如 'E5_01'。"""
    kg = _kg(project)
    try:
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
    finally:
        kg.close()


@mcp.tool()
def add_chapter_arc(project: str, chapter: int, purpose: str, scenes: str,
                    ending: str, gap_note: str = "",
                    structure_type: str = "linear", time_jumps: str = "",
                    thread_plan: str = "", reasoning: str = "") -> str:
    """添加/更新章节弧线。time_jumps和thread_plan如果是对象请传JSON字符串。"""
    kg = _kg(project)
    try:
        props = {"purpose": purpose, "scenes": scenes, "ending": ending}
        if gap_note:
            props["gap_note"] = gap_note
        if structure_type and structure_type != "linear":
            props["structure_type"] = structure_type
        if time_jumps:
            # 确保是字符串（Neo4j不存嵌套对象）
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
    finally:
        kg.close()


@mcp.tool()
def add_suspense_thread(project: str, thread_id: str, content: str,
                        planted_chapter: int, importance: str = "medium",
                        thread_type: str = "foreshadowing") -> str:
    """添加悬念线。thread_id格式如 'ST05_01'。"""
    kg = _kg(project)
    try:
        kg.add_suspense_thread(thread_id, content=content,
                               planted_chapter=planted_chapter,
                               importance=importance,
                               thread_type=thread_type, status="planted")
        return f"已添加悬念线: {thread_id} - {content[:40]}"
    finally:
        kg.close()


@mcp.tool()
def add_outline_entry(project: str, chapter: int, purpose: str,
                      key_events: str = "", threads_to_plant: str = "",
                      threads_to_resolve: str = "", structure_hint: str = "") -> str:
    """添加/更新章节大纲条目（硬约束）。"""
    kg = _kg(project)
    try:
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
    finally:
        kg.close()


@mcp.tool()
def add_style_guide(project: str, guide_id: str, rule: str) -> str:
    """添加/更新风格指南规则。"""
    kg = _kg(project)
    try:
        kg.add_style_guide(guide_id, rule=rule)
        return f"已添加风格规则: {guide_id}"
    finally:
        kg.close()


@mcp.tool()
def add_motif(project: str, name: str, meaning: str = "", evolution: str = "") -> str:
    """添加/更新核心意象。"""
    kg = _kg(project)
    try:
        props = {}
        if meaning:
            props["meaning"] = meaning
        if evolution:
            props["evolution"] = evolution
        kg.add_motif(name, **props)
        return f"已添加意象: {name}"
    finally:
        kg.close()


@mcp.tool()
def add_theme(project: str, name: str, description: str = "", chapters: str = "") -> str:
    """添加/更新主题线。"""
    kg = _kg(project)
    try:
        props = {}
        if description:
            props["description"] = description
        if chapters:
            props["chapters"] = chapters
        kg.add_theme(name, **props)
        return f"已添加主题: {name}"
    finally:
        kg.close()


@mcp.tool()
def add_time_period(project: str, label: str, chapter_start: int, chapter_end: int,
                    years: str = "", theme: str = "") -> str:
    """添加/更新时间段。"""
    kg = _kg(project)
    try:
        props = {"chapter_start": chapter_start, "chapter_end": chapter_end}
        if years:
            props["years"] = years
        if theme:
            props["theme"] = theme
        kg.add_time_period(label, **props)
        return f"已添加时间段: {label} (Ch{chapter_start}-{chapter_end})"
    finally:
        kg.close()


@mcp.tool()
def add_relation(project: str, from_label: str, from_key: str, from_val: str,
                 rel_type: str, to_label: str, to_key: str, to_val: str) -> str:
    """添加节点间关系。如 add_relation('Character','name','张三','SPOUSE_OF','Character','name','李四')"""
    kg = _kg(project)
    try:
        kg.add_relation(from_label, from_key, from_val, rel_type,
                        to_label, to_key, to_val)
        return f"已添加关系: {from_val} -{rel_type}-> {to_val}"
    finally:
        kg.close()


@mcp.tool()
def update_suspense_thread(project: str, thread_id: str, status: str = "",
                           importance: str = "") -> str:
    """更新悬念线属性（状态、重要性等）。"""
    kg = _kg(project)
    try:
        props = {}
        if status:
            props["status"] = status
        if importance:
            props["importance"] = importance
        kg.update_suspense_thread(thread_id, **props)
        return f"已更新悬念线: {thread_id}"
    finally:
        kg.close()


@mcp.tool()
def write_extraction(project: str, chapter: int, extracted_json: str) -> dict:
    """将提取的结构化数据写入图谱（含冲突检测+人名规范化）。

    extracted_json: JSON字符串，包含 events/event_relations/new_characters 等。
    返回写入报告：事件数、关系数、冲突列表。
    """
    kg = _kg(project)
    try:
        if isinstance(extracted_json, str):
            extracted = json.loads(extracted_json)
        else:
            extracted = extracted_json

        report = write_extraction_to_graph(kg, chapter, extracted, skip_conflicts=True)
        return {
            "chapter": report["chapter"],
            "stats": report["stats"],
            "conflicts": report["conflicts"],
            "character_updates": report.get("character_updates", []),
            "notes": report.get("notes", ""),
        }
    finally:
        kg.close()


@mcp.tool()
def clear_chapter_data(project: str, chapter: int) -> str:
    """清除图谱中指定章节的事件数据（用于重跑）。"""
    kg = _kg(project)
    try:
        clear_chapter_data(kg, chapter)
        return f"已清除第{chapter}章的事件数据"
    finally:
        kg.close()


# ============================================================
# 4. 校验工具
# ============================================================

@mcp.tool()
def validate_chapter(project: str, text: str, chapter: int) -> dict:
    """对生成的章节文本运行全部后置校验。

    校验项：人名一致性（与图谱对比）、叙事结构（intercut/flashback切换次数）、
    风格指南遵守、篇幅。返回违规列表和自动修复建议。
    """
    kg = _kg(project)
    try:
        context = kg.get_context_for_chapter(chapter)
        arc = context.get("chapter_arc", [None])
        arc = arc[0] if arc else None

        result = _run_validation(text, context, arc=arc)
        return {
            "passed": result.passed,
            "violations": [
                {
                    "type": v.constraint_type,
                    "severity": v.severity,
                    "detail": v.detail,
                    "fix": v.fix,
                }
                for v in result.violations
            ],
        }
    finally:
        kg.close()


@mcp.tool()
def detect_extraction_conflicts(project: str, extracted_json: str) -> list:
    """检测提取数据与已有图谱的冲突（不写入，只检查）。

    检查项：事件ID重复、地点未注册、人物未注册、事件粒度、间隙误判。
    """
    kg = _kg(project)
    try:
        if isinstance(extracted_json, str):
            extracted = json.loads(extracted_json)
        else:
            extracted = extracted_json
        return detect_conflicts(kg, extracted)
    finally:
        kg.close()


if __name__ == "__main__":
    mcp.run()
