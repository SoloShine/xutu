"""
Novel Knowledge Graph MCP Server

将图谱操作和prompt模板暴露为MCP工具，供Code Agent直接调用。
Agent通过这些工具读取图谱上下文、获取生成指导、写回结构化数据，
自身作为LLM完成生成/提取/推演，无需额外API调用。

业务逻辑在 core.py，本文件仅做 MCP 装饰。
"""

from . import core
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
def get_chapter_context(project: str, chapter: int,
                        prev_text_chars: int = 500) -> dict:
    """获取写第N章时需要的全部图谱上下文。

    返回:人物状态、前一章事件、地点、主题、风格指南、意象、情节弧线、悬念线、大纲条目。
    这是续写章节的核心输入——Agent据此理解当前故事状态。

    prev_text_chars: 前一章结尾正文的截取字数（首尾帧衔接），默认500。设为0则不注入。
    """
    return core.get_chapter_context(project, chapter, prev_text_chars=prev_text_chars)


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
def get_writing_prompt(project: str, chapter: int,
                       prev_text_chars: int = 500) -> str:
    """获取填充后的续写prompt。

    返回包含完整图谱上下文的续写指导:章节弧线、时间段、前一章事件、
    人物状态、地点、主题、风格指南、意象、悬念线、大纲约束、场景展开要求。
    Agent据此生成章节正文。

    prev_text_chars: 前一章结尾正文的截取字数（首尾帧衔接），默认500。设为0则不注入。
    """
    return core.get_writing_prompt(project, chapter, prev_text_chars=prev_text_chars)


@mcp.tool()
def get_derivation_prompt(project: str, chapter: int) -> str:
    """获取填充后的章节弧线推演prompt。

    返回推演指导文本，包含:大纲约束、悬念线、近章弧线/事件、人物、
    主题、意象、推演规则。Agent按返回的JSON schema输出arc数据，
    然后调用 add_chapter_arc 写入图谱。
    """
    return core.get_derivation_prompt(project, chapter)


@mcp.tool()
def get_editing_prompt(project: str, chapter: int, draft: str = "",
                       draft_file: str = "") -> str:
    """获取填充后的编辑审查prompt。

    返回风格审查指导文本，包含:风格清单（按维度分组）、审查规则。
    Agent对照清单审查初稿，输出修改后的完整正文（纯文本）。
    draft 是初稿文本，draft_file 是初稿文件路径（二选一）。
    """
    return core.get_editing_prompt(project, chapter, draft, draft_file)


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
                    thread_plan: str = "", reasoning: str = "",
                    rhythm: str = "", ending_type: str = "") -> str:
    """添加/更新章节弧线。time_jumps和thread_plan如果是对象请传JSON字符串。
    rhythm可选: tight(紧凑), ascending(递进加速), descending(递减放慢), mixed(混合)
    ending_type可选: cliffhanger(悬念), revelation(揭示), quiet(安静), reversal(反转), open(开放式), daily(日常)"""
    return core.add_chapter_arc(project, chapter, purpose, scenes, ending,
                                gap_note, structure_type, time_jumps,
                                thread_plan, reasoning, rhythm, ending_type)


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
def add_style_guide(project: str, guide_id: str, rule: str = "",
                    dimension: str = "", goal: str = "",
                    good_examples: list = None,
                    bad_examples: list = None) -> str:
    """添加/更新风格指南规则。支持维度、目标、正反例。"""
    return core.add_style_guide(project, guide_id, rule,
                                dimension, goal,
                                good_examples, bad_examples)


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


@mcp.tool()
def check_outline_compliance(project: str, chapter: int) -> dict:
    """大纲合规检查（程序化+LLM）。

    检查项: key_events是否出现、threads_to_plant/resolve是否执行、structure_hint是否匹配。
    返回合规状态(followed/partial/diverged)和详细检查结果。
    无outline_entry的章节返回 no_outline。
    """
    return core.check_outline_compliance(project, chapter)


@mcp.tool()
def batch_check_outline_compliance(project: str,
                                   chapters: list = None,
                                   batch_size: int = 8) -> dict:
    """批量大纲合规检查。程序化逐章执行，purpose检查按batch_size分批合并LLM调用。

    chapters: 可选，指定要检查的章节列表。不传则检查所有有大纲条目的章节。
    batch_size: 每批purpose检查合并的最大章节数，默认8。设为0则全部合并为一次调用。
    返回各章合规结果和统计摘要。
    """
    return core.batch_check_outline_compliance(project, chapters, batch_size)


@mcp.tool()
def sync_backends(project: str, direction: str = "json_to_neo4j") -> str:
    """同步 JSON 和 Neo4j 后端数据。

    direction: 'json_to_neo4j'（从JSON导入到Neo4j）或 'neo4j_to_json'（从Neo4j导出到JSON）。
    读取源后端全部数据，清空目标后端后写入。用于迁移或可视化。
    """
    return core.sync_backends(project, direction)


@mcp.tool()
def analyze_pacing(project: str) -> dict:
    """分析叙事节奏问题。

    检测: 目的重复、结尾重复、场景密度异常、节奏曲线平坦/剧烈波动。
    返回问题列表和章节弧线概览。
    """
    return core.analyze_pacing(project)


@mcp.tool()
def revise_outline(project: str, chapter: int, reason: str,
                   purpose: str = "", key_events: str = "",
                   threads_to_plant: str = "", threads_to_resolve: str = "",
                   structure_hint: str = "") -> str:
    """显式修订大纲条目。只传需要修改的字段。

    修订时自动设置 compliance='overridden'，记录修订原因和修订时最新章节号。
    reason 参数必填，说明为什么修订。
    """
    return core.revise_outline(project, chapter, reason, purpose, key_events,
                                threads_to_plant, threads_to_resolve, structure_hint)


@mcp.tool()
def analyze_edit_impact(project: str, chapter: int) -> dict:
    """事后影响分析。对比edited文本与图谱中该章数据的差异。

    需要 projects/<project>/output/chN_edited.txt 存在。
    返回受影响的事件/悬念线/人物/后续大纲警告。
    Agent需对edited文本重新提取后调用 accept_edit 写入图谱。
    """
    return core.analyze_edit_impact(project, chapter)


@mcp.tool()
def accept_edit(project: str, chapter: int, extracted_json: str,
                confirm: str = "") -> dict:
    """采纳事后编辑。清除旧数据 → 写入新提取数据 → 标记后续大纲。

    confirm需传入 'I_UNDERSTAND_THIS_IS_DESTRUCTIVE'。
    extracted_json 为对edited文本重新提取的JSON结果。
    """
    return core.accept_edit(project, chapter, extracted_json, confirm)


@mcp.tool()
def review_chapter(project: str, chapter: int, action: str,
                   edited_text: str = "") -> dict:
    """审核关卡操作。

    action: 'accept'(通过), 'edit'(小修,需edited_text),
    'rewrite'(重写,需edited_text), 'revise_outline'(修订大纲)。
    accept/revise_outline 不需要 edited_text。
    edit/rewrite 会将 edited_text 保存为 chN_edited.txt。
    """
    return core.review_chapter(project, chapter, action, edited_text)


@mcp.tool()
def list_edits(project: str, chapter: int = None) -> dict:
    """列出章节编辑快照历史。每次 accept_edit 前自动创建快照。

    chapter: 可选，筛选指定章节。不传则列出全部快照。
    返回快照列表（id, chapter, timestamp, reason, event_count）。
    """
    return core.list_edits(project, chapter=chapter)


@mcp.tool()
def rollback_edit(project: str, snapshot_id: str,
                  confirm: str = "",
                  clear_revision_marks: bool = True) -> dict:
    """回滚到指定快照版本（破坏性操作）。

    回滚前自动快照当前状态，支持再次回滚。
    需传入 confirm='I_UNDERSTAND_THIS_IS_DESTRUCTIVE' 确认执行。
    用 list_edits 查看可用的 snapshot_id。
    clear_revision_marks: 回滚时是否清除下游大纲的needs_revision标记（默认True）。
    """
    return core.rollback_edit(project, snapshot_id, confirm=confirm,
                              clear_revision_marks=clear_revision_marks)


@mcp.tool()
def analyze_parallel_groups(project: str) -> dict:
    """分析章节依赖关系，返回可并行分组。

    基于大纲条目的 parallel_group 标记、相邻章节约束和悬念线交叉引用，
    计算哪些章节可以同时生成。返回依赖图、并行分组、预估加速比。
    """
    return core.analyze_parallel_groups(project)


@mcp.tool()
def prepare_parallel_batch(project: str, chapters: list) -> dict:
    """为并行组创建图谱快照并预冻结每章的上下文。

    创建全图谱快照（合并时可回滚），为每章预计算 chapter_context。
    对前一章在同批的章节，用弧线 ending 锚点替代 prev_text。
    返回 batch_id 和冻结上下文概要。
    """
    return core.prepare_parallel_batch(project, chapters)


@mcp.tool()
def get_parallel_writing_prompt(project: str, chapter: int,
                                batch_id: str) -> str:
    """使用冻结上下文生成写作 prompt（并行模式）。

    与 get_writing_prompt 类似但使用预冻结的上下文，不查询活图谱。
    需先调用 prepare_parallel_batch 获取 batch_id。
    """
    return core.get_parallel_writing_prompt(project, chapter, batch_id)


@mcp.tool()
def merge_parallel_results(project: str, batch_id: str,
                           results: dict) -> dict:
    """合并并行生成结果到图谱。

    按章节号顺序串行写入正文和提取数据，含冲突检测。
    results: {chapter: {"text": str, "extraction_json": str}}
    返回合并报告和一致性检查结果。
    """
    return core.merge_parallel_results(project, batch_id, results)


# ============================================================
# 14. 遥测工具
# ============================================================

@mcp.tool()
def save_telemetry_chapter_report(project: str, chapter: int) -> dict:
    """保存指定章节的遥测报告到磁盘（JSON文件）。
    返回保存路径。
    """
    return core.save_telemetry_chapter_report(project, chapter)


@mcp.tool()
def save_telemetry_session_summary(project: str) -> dict:
    """保存会话遥测摘要到磁盘（JSON文件）。
    包含所有章节的工具调用统计、耗时、token消耗等。
    返回保存路径。
    """
    return core.save_telemetry_session_summary(project)


@mcp.tool()
def set_telemetry_wall_clock(project: str, chapter: int,
                             wall_clock_ms: float,
                             agent_tool_uses: int = None) -> dict:
    """注入子代理端到端墙钟时间（主会话在子代理返回后调用）。
    wall_clock_ms: 子代理从启动到完成的总毫秒数。
    agent_tool_uses: 子代理的MCP工具调用次数（可选）。
    """
    return core.set_telemetry_wall_clock(
        project, chapter, wall_clock_ms,
        agent_tool_uses=agent_tool_uses
    )


if __name__ == "__main__":
    mcp.run()
