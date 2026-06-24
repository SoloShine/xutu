# src/bedrock/runner/author_agent.py
"""作者助手 agent(AI 工作台的"大脑")。

对话式 tool-calling agent(LangGraph ReAct),用于写前创作:起草大纲/beat/角色/世界观、
规划章节、查设定矛盾、解读 review……。agent 用【读工具】直查项目上下文,用【propose_action 工具】
产结构化提案(不直接落库);作者在 UI 审批后才经 repo 函数落库(守铁律)。

模型用 `author` process(可在「工作流配置」绑更大模型,如 Opus 级;未绑→全局默认回退)。
每次调用经 call_llm,token 进 telemetry(author/glm-5.2)。
"""
import json
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool

from .llm import call_llm
from ..workflow.chat_repo import add_message, add_proposal


def _ch_summary(conn, chapter_id):
    r = conn.execute("SELECT c.global_number, c.title, c.status, v.id vid, v.name vname "
                     "FROM chapter c JOIN volume v ON c.volume_id=v.id WHERE c.id=?", (chapter_id,)).fetchone()
    return dict(r) if r else None


def make_author_tools(conn, session_id):
    """构造读工具 + propose_action 工具(闭包绑 conn + session)。写库一律走 propose→审批。"""

    @tool
    def get_work_overview() -> str:
        """作品概况:卷列表(含章数/状态分布)+ 主要角色名 + 最近章节。"""
        from src.bedrock.web.queries import overview_stats
        return json.dumps(overview_stats(conn), ensure_ascii=False)

    @tool
    def list_chapters() -> str:
        """列全部章节(global_number/title/status/volume)。"""
        rows = conn.execute("SELECT c.global_number, c.title, c.status, v.name vname "
                            "FROM chapter c JOIN volume v ON c.volume_id=v.id ORDER BY c.global_number").fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)

    @tool
    def get_chapter_detail(global_number: int) -> str:
        """指定章的 beat 契约(purpose/pov)+ 段落尾(最近 6 段),供起草后续章承接。"""
        ch = conn.execute("SELECT id FROM chapter WHERE global_number=?", (global_number,)).fetchone()
        if not ch:
            return f"章节 {global_number} 不存在"
        cid = ch["id"]
        beats = conn.execute("SELECT id, sequence, purpose, pov_character_id FROM beat WHERE chapter_id=?",
                             (cid,)).fetchall()
        paras = conn.execute("SELECT seq, text FROM paragraph WHERE chapter_id=? ORDER BY seq DESC LIMIT 6",
                             (cid,)).fetchall()
        return json.dumps({"beats": [dict(b) for b in beats],
                           "tail": [dict(p) for p in reversed(paras)]}, ensure_ascii=False)

    @tool
    def get_character_canon() -> str:
        """角色正典(name/pronoun/gender/role/personality/goals),起草 beat pov/出场 + 一致性查用。"""
        rows = conn.execute("SELECT id, name, pronoun, gender, role, personality, goals FROM character").fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)

    @tool
    def get_worldbook() -> str:
        """世界观:constants(world 设定键值)+ locations + factions + themes + motifs。查设定一致性用。"""
        out = {}
        out["constants"] = [dict(r) for r in conn.execute(
            "SELECT key, value, scope, volume_id FROM constants ORDER BY key").fetchall()]
        out["locations"] = [dict(r) for r in conn.execute(
            "SELECT id, name, loc_type, description, state FROM location ORDER BY id").fetchall()]
        out["factions"] = [dict(r) for r in conn.execute(
            "SELECT id, name, ftype, stance, state FROM faction ORDER BY id").fetchall()]
        out["themes"] = [dict(r) for r in conn.execute(
            "SELECT name, description, evolution FROM theme ORDER BY name").fetchall()]
        out["motifs"] = [dict(r) for r in conn.execute(
            "SELECT name, meaning, evolution FROM motif ORDER BY name").fetchall()]
        return json.dumps(out, ensure_ascii=False)

    @tool
    def get_style() -> str:
        """文风:style_template(directive/word_count_target/hygiene/style_examples 范例)+ 实测缓存。"""
        from src.bedrock.style.template_repo import get_style_config
        cfg = get_style_config(conn, None) or {}
        return json.dumps({
            "directive": cfg.get("directive") or "",
            "word_count_target": cfg.get("word_count_target"),
            "style_examples": cfg.get("style_examples") or {},
            "enabled_dims": cfg.get("enabled_dims") or [],
        }, ensure_ascii=False)

    @tool
    def get_master_outline() -> str:
        """master_outline + 各卷 volume_outline,规划新章/新卷定位用。"""
        from src.bedrock.repositories.outline import get_master_outline as _gmo, get_volume_outline
        rows = conn.execute("SELECT id FROM volume ORDER BY number").fetchall()
        mo = _gmo(conn)
        out = {"master": dict(mo) if mo and hasattr(mo, "keys") else (mo or ""),
               "volumes": {}}
        for r in rows:
            vo = get_volume_outline(conn, r["id"])
            out["volumes"][str(r["id"])] = [dict(x) if hasattr(x, "keys") else x for x in vo] if isinstance(vo, list) else (dict(vo) if vo and hasattr(vo, "keys") else vo)
        return json.dumps(out, ensure_ascii=False, default=str)

    @tool
    def get_chapter_full(global_number: int) -> str:
        """指定章的【全部】段落(非仅尾段)。深查设定一致性/代词/前后矛盾时用。"""
        ch = conn.execute("SELECT id FROM chapter WHERE global_number=?", (global_number,)).fetchone()
        if not ch:
            return f"章节 {global_number} 不存在"
        paras = conn.execute("SELECT seq, beat_id, text FROM paragraph WHERE chapter_id=? ORDER BY seq",
                             (ch["id"],)).fetchall()
        return json.dumps({"chapter_global": global_number, "paragraph_count": len(paras),
                           "paragraphs": [dict(p) for p in paras]}, ensure_ascii=False)

    @tool
    def get_review_report(volume_id: int) -> str:
        """读整卷回读报告(review_report_vol<N>.md)+ 各章 review_flag(has_flag/escalate)。
        解读卷审发现、给作者改稿建议时用。"""
        v = conn.execute("SELECT number FROM volume WHERE id=?", (volume_id,)).fetchone()
        rep = ""
        if v:
            from pathlib import Path
            # 报告文件路径需 projects_root,这里只读 DB 里的 flag + 用 volume.number 拼提示
            pass
        flags = [dict(r) for r in conn.execute(
            "SELECT c.global_number, c.title, "
            "  (f.l2_unresolved OR f.likely_rule_or_model_issue OR f.polish_broke_beat OR f.forced_persist_failed) AS has_flag, "
            "  f.l2_unresolved, f.likely_rule_or_model_issue, f.polish_broke_beat, "
            "  f.forced_persist_failed, f.advisory_drift "
            "FROM chapter c LEFT JOIN chapter_review_flag f ON f.chapter_id=c.id "
            "WHERE c.volume_id=? ORDER BY c.global_number", (volume_id,)).fetchall()]
        return json.dumps({"volume_id": volume_id,
                           "note": "完整报告见 projects/<w>/review_report_vol<N>.md(get_chapter_full 查具体章)",
                           "flags": flags}, ensure_ascii=False)

    @tool
    def get_run_status(global_number: int) -> str:
        """指定章最近的 run 状态 + 事件概要(节点序列 + 是否 L2-clean)。看写完没/为何失败用。"""
        from src.bedrock.workflow.run_repo import list_recent_runs, list_events
        runs = list_recent_runs(conn, limit=5, chapter_global=global_number)
        if not runs:
            return f"章节 {global_number} 无 run 记录"
        r = runs[0]
        evs = list_events(conn, r["id"])
        return json.dumps({"run": r, "event_count": len(evs),
                           "nodes": [e["node"] + ":" + e["kind"] for e in evs]}, ensure_ascii=False)

    @tool
    def propose_action(action_type: str, payload: str, summary: str = "") -> str:
        """产一个结构化提案(作者审批后才落库经 repo 函数,守铁律)。payload=JSON 字符串。

        支持 action_type:
        - create_chapter_with_beat: {volume_id, global_number, title, beat:{purpose, pov_character_id?}}
        - batch_create_chapters: {volume_id, chapters:[{global_number, title, beat:{purpose, pov_character_id?}}]}
        - create_volume: {number, name, chapter_start, chapter_end, volume_type}
        - set_beat_contract: {beat_id, purpose, pov_character_id?}
        - create_character: {name, pronoun, role, gender?, personality?, goals?}
        - create_location: {name, loc_type?, description?}
        - create_theme: {name, description?, evolution?}
        - create_motif: {name, meaning?, evolution?}
        - set_worldbook_constant: {key, value}
        - set_master_outline: {theme_evolution?, key_arcs?, key_milestones?}
        - trigger_run: {global_number}
        返回"提案已记录,等待作者审批"。一次只产一个提案;批量建章用 batch_create_chapters。
        """
        try:
            data = json.loads(payload) if isinstance(payload, str) else payload
        except json.JSONDecodeError as e:
            return f"payload 不是合法 JSON: {e}"
        pid = add_proposal(conn, session_id, action_type, data)
        return f"已记录提案 #{pid}({action_type})「{summary or '无摘要'}」,等待作者审批。"

    return [get_work_overview, list_chapters, get_chapter_detail, get_chapter_full,
            get_character_canon, get_worldbook, get_style, get_master_outline,
            get_review_report, get_run_status, propose_action]


SYSTEM_PROMPT = """你是磐石 Bedrock 的作者助手,帮作者做【写前创作 + 一致性守护】:规划卷/章、
起草 beat 契约、补全角色/世界观/主题、查跨章设定矛盾、解读 review、触发写作。输出进对话面板供作者审批。

【工作方式】
- 先用工具读全上下文再答,绝不凭空编。涉及具体角色/设定/前情,先 get_* 查实。
- 分清"读"(你直接做)与"写"(只产 propose_action 提案,作者审批才落库;别谎称已落库)。
- 简洁、给作者可决策的选项(2-3 个),不写长篇大论、不替作者拍板创意。

【读工具选用】
- 续写/规划:list_chapters + get_master_outline + get_work_overview(定位卷/章号)
- 起草 beat / pov / 出场:get_character_canon + get_chapter_detail(前章尾承接)
- 查设定矛盾:get_worldbook(地点/阵营/主题/母题/常量)+ get_character_canon + get_chapter_full(深查某章)
- 文风相关:get_style(directive/范例/字数目标)
- 写完/失败诊断:get_run_status + get_review_report

【写工具(propose_action)要点】
- beat.purpose = 这一拍的叙事目的(≥10 字,具体到"谁做了什么/揭示什么"),不是抽象标签(如"推进情节"❌)。
- 续写新章 global_number = 现有最大 + 1;volume_id 从 list_chapters/get_work_overview 取实值。
- create_character:pronoun 必须符合性别设定;role ∈ {protagonist, antagonist, supporting, ...}。
- 一次规划多章用 batch_create_chapters(一个提案含 chapters 数组),别逐条产。
- trigger_run 只对已有章(有 beat 契约)有效;新章先 create_chapter_with_beat。

【一致性守护】
- 角色代词/性别/称呼严格按 get_character_canon,不得擅改;发现前文矛盾主动指出(给改稿提案)。
- 读者已知信息(reader_disclosed_secrets 类)不在工具范围,别臆造揭示。

【边界】
- 不碰 L2/verify 信任锚(那是 runner 的确定性职责)。
- 不直接写库(铁律);所有写操作走 propose_action。
"""


def run_author(wd, session_id, user_text, workflow_config):
    """跑一轮作者助手:user_text → ReAct agent(读工具 + propose_action)→ 落消息 + 提案。

    wd: 项目目录(Path)——内部开 check_same_thread=False 的 sqlite 连接(LangGraph agent 在
        另一线程跑工具,Flask 请求 conn 不能跨线程用)。
    workflow_config: get_workflow_config 结果(供解析 author process 模型)。
    返回 assistant 回复文本。工具调用经 author process 模型(默认回退)。"""
    import sqlite3
    from .llm import _resolve_endpoint_model, _build_model
    conn = sqlite3.connect(str(wd / "bedrock.db"), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        add_message(conn, session_id, "user", user_text)
        tools = make_author_tools(conn, session_id)
        ep, mid = _resolve_endpoint_model(workflow_config, "author")
        model, _ = _build_model(ep, mid)
        agent = create_react_agent(model, tools, prompt=SYSTEM_PROMPT)
        history = [{"role": m["role"], "content": m["content"]}
                   for m in _recent_history(conn, session_id, limit=8)]
        result = agent.invoke({"messages": history})
        ai = next((m for m in reversed(result["messages"]) if m.type == "ai"), None)
        reply = ai.content if ai else ""
        add_message(conn, session_id, "assistant", reply)
        conn.commit()
        return reply
    finally:
        conn.close()


def _recent_history(conn, session_id, limit=8):
    """最近 limit 条消息(含当前 user_text),供 agent 上下文。"""
    from ..workflow.chat_repo import list_messages
    msgs = list_messages(conn, session_id)
    return msgs[-limit:]
