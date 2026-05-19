"""
Novel Knowledge Graph MCP Server

将图谱操作和prompt模板暴露为MCP工具，供Code Agent直接调用。
Agent通过这些工具读取图谱上下文、获取生成指导、写回结构化数据，
自身作为LLM完成生成/提取/推演，无需额外API调用。

业务逻辑在 core.py，本文件仅做 MCP 装饰。
"""

import core
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "novel-kg",
    instructions=(
        "小说知识图谱工具集。通过Neo4j存储和查询三层图谱（结构层/风格层/情节层），"
        "支持章节续写、结构化提取、弧线推演等操作。"
    ),
)


# ============================================================
# 1. 图谱查询工具（只读）
# ============================================================

@mcp.tool()
def get_chapter_context(project: str, chapter: int) -> dict:
    """获取写第N章时需要的全部图谱上下文。

    返回:人物状态、前一章事件、地点、主题、风格指南、意象、情节弧线、悬念线、大纲条目。
    这是续写章节的核心输入——Agent据此理解当前故事状态。
    """
    return core.get_chapter_context(project, chapter)


@mcp.tool()
def get_derivation_context(project: str, chapter: int,
                           lookback: int = 3) -> dict:
    """获取推演第N章ChapterArc所需的上下文。

    返回:近N章弧线、近N章事件、人物、主题、意象、最后事件、大纲条目、悬念线。
    用于在写新章节前推演其叙事结构。
    """
    return core.get_derivation_context(project, chapter, lookback)


@mcp.tool()
def get_graph_stats(project: str) -> dict:
    """获取项目图谱统计信息。返回各类节点和关系的数量。"""
    return core.get_graph_stats(project)


@mcp.tool()
def check_consistency(project: str) -> list:
    """检查图谱一致性。返回时空矛盾、间隙强度异常、章节缺失事件等问题列表。"""
    return core.check_consistency(project)


@mcp.tool()
def get_unresolved_threads(project: str, chapter: int) -> list:
    """获取到第N章时仍未解决的悬念线。按重要性降序排列。"""
    return core.get_unresolved_threads(project, chapter)


@mcp.tool()
def get_all_threads(project: str) -> list:
    """获取项目中全部悬念线（用于审计）。"""
    return core.get_all_threads(project)


# ============================================================
# 2. Prompt模板工具
# ============================================================

@mcp.tool()
def get_extraction_prompt(project: str, chapter: int,
                          chapter_text: str) -> str:
    """获取填充后的提取prompt模板。

    返回精心调校的提取指导文本，包含:已有人物列表、悬念线、粒度控制规则、
    间隙精确定义、JSON schema。Agent按此prompt的schema输出结构化数据，
    然后调用 write_extraction 写回图谱。
    """
    return core.get_extraction_prompt(project, chapter, chapter_text)


@mcp.tool()
def get_writing_prompt(project: str, chapter: int) -> str:
    """获取填充后的续写prompt。

    返回包含完整图谱上下文的续写指导:章节弧线、时间段、前一章事件、
    人物状态、地点、主题、风格指南、意象、悬念线、大纲约束、场景展开要求。
    Agent据此生成章节正文。
    """
    return core.get_writing_prompt(project, chapter)


@mcp.tool()
def get_derivation_prompt(project: str, chapter: int) -> str:
    """获取填充后的章节弧线推演prompt。

    返回推演指导文本，包含:大纲约束、悬念线、近章弧线/事件、人物、
    主题、意象、推演规则。Agent按返回的JSON schema输出arc数据，
    然后调用 add_chapter_arc 写入图谱。
    """
    return core.get_derivation_prompt(project, chapter)


# ============================================================
# 3. 图谱写入工具
# ============================================================

@mcp.tool()
def init_project(project: str, confirm: str = "") -> str:
    """清空指定项目的图谱数据（不影响其他项目）。谨慎使用。"""
    return core.init_project(project, confirm)


@mcp.tool()
def add_character(project: str, name: str, role: str = "",
                  personality: str = "", gap_relation: str = "") -> str:
    """添加/更新人物节点。"""
    return core.add_character(project, name, role, personality, gap_relation)


@mcp.tool()
def add_location(project: str, name: str, loc_type: str = "",
                 description: str = "") -> str:
    """添加/更新地点节点。"""
    return core.add_location(project, name, loc_type, description)


@mcp.tool()
def add_event(project: str, event_id: str, title: str = "",
              detail: str = "", chapter: int = 0,
              event_type: str = "daily", is_gap: bool = False,
              gap_level: int = 0) -> str:
    """添加/更新事件节点。event_id格式如 'E5_01'。"""
    return core.add_event(project, event_id, title, detail, chapter,
                          event_type, is_gap, gap_level)


@mcp.tool()
def add_chapter_arc(project: str, chapter: int, purpose: str, scenes: str,
                    ending: str, gap_note: str = "",
                    structure_type: str = "linear", time_jumps: str = "",
                    thread_plan: str = "", reasoning: str = "") -> str:
    """添加/更新章节弧线。time_jumps和thread_plan如果是对象请传JSON字符串。"""
    return core.add_chapter_arc(project, chapter, purpose, scenes, ending,
                                gap_note, structure_type, time_jumps,
                                thread_plan, reasoning)


@mcp.tool()
def add_suspense_thread(project: str, thread_id: str, content: str,
                        planted_chapter: int, importance: str = "medium",
                        thread_type: str = "foreshadowing") -> str:
    """添加悬念线。thread_id格式如 'ST05_01'。"""
    return core.add_suspense_thread(project, thread_id, content,
                                    planted_chapter, importance, thread_type)


@mcp.tool()
def add_outline_entry(project: str, chapter: int, purpose: str,
                      key_events: str = "", threads_to_plant: str = "",
                      threads_to_resolve: str = "",
                      structure_hint: str = "") -> str:
    """添加/更新章节大纲条目（硬约束）。"""
    return core.add_outline_entry(project, chapter, purpose, key_events,
                                  threads_to_plant, threads_to_resolve,
                                  structure_hint)


@mcp.tool()
def add_style_guide(project: str, guide_id: str, rule: str) -> str:
    """添加/更新风格指南规则。"""
    return core.add_style_guide(project, guide_id, rule)


@mcp.tool()
def add_motif(project: str, name: str, meaning: str = "",
              evolution: str = "") -> str:
    """添加/更新核心意象。"""
    return core.add_motif(project, name, meaning, evolution)


@mcp.tool()
def add_theme(project: str, name: str, description: str = "",
              chapters: str = "") -> str:
    """添加/更新主题线。"""
    return core.add_theme(project, name, description, chapters)


@mcp.tool()
def add_time_period(project: str, label: str, chapter_start: int,
                    chapter_end: int, years: str = "",
                    theme: str = "") -> str:
    """添加/更新时间段。"""
    return core.add_time_period(project, label, chapter_start, chapter_end,
                                years, theme)


@mcp.tool()
def add_relation(project: str, from_label: str, from_key: str,
                 from_val: str, rel_type: str, to_label: str,
                 to_key: str, to_val: str) -> str:
    """添加节点间关系。如 add_relation('Character','name','张三','SPOUSE_OF','Character','name','李四')"""
    return core.add_relation(project, from_label, from_key, from_val,
                             rel_type, to_label, to_key, to_val)


@mcp.tool()
def update_suspense_thread(project: str, thread_id: str, status: str = "",
                           importance: str = "") -> str:
    """更新悬念线属性（状态、重要性等）。"""
    return core.update_suspense_thread(project, thread_id, status, importance)


@mcp.tool()
def write_extraction(project: str, chapter: int,
                     extracted_json: str) -> dict:
    """将提取的结构化数据写入图谱（含冲突检测+人名规范化）。

    extracted_json: JSON字符串，包含 events/event_relations/new_characters 等。
    返回写入报告:事件数、关系数、冲突列表。
    """
    return core.write_extraction(project, chapter, extracted_json)


@mcp.tool()
def clear_chapter_data(project: str, chapter: int,
                       confirm: str = "") -> str:
    """清除图谱中指定章节的事件数据（用于重跑）。"""
    return core.clear_chapter_data(project, chapter, confirm)


# ============================================================
# 4. 校验工具
# ============================================================

@mcp.tool()
def validate_chapter(project: str, text: str, chapter: int) -> dict:
    """对生成的章节文本运行全部后置校验。

    校验项:人名一致性（与图谱对比）、叙事结构（intercut/flashback切换次数）、
    风格指南遵守、篇幅。返回违规列表和自动修复建议。
    """
    return core.validate_chapter(project, text, chapter)


@mcp.tool()
def detect_extraction_conflicts(project: str,
                                extracted_json: str) -> list:
    """检测提取数据与已有图谱的冲突（不写入,只检查）。

    检查项:事件ID重复、地点未注册、人物未注册、事件粒度、间隙误判。
    """
    return core.detect_extraction_conflicts(project, extracted_json)


if __name__ == "__main__":
    mcp.run()
