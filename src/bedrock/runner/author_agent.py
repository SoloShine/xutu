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
        """角色正典(name/pronoun/gender/role/personality),起草 beat pov/出场用。"""
        rows = conn.execute("SELECT name, pronoun, gender, role, personality FROM character").fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)

    @tool
    def get_master_outline() -> str:
        """master_outline + 各卷 volume_outline,规划新章定位用。"""
        from src.bedrock.repositories.outline import get_master_outline, list_volume_outline
        rows = conn.execute("SELECT id FROM volume ORDER BY number").fetchall()
        out = {"master": get_master_outline(conn) or "",
               "volumes": {}}
        for r in rows:
            out["volumes"][str(r["id"])] = list_volume_outline(conn, r["id"])
        return json.dumps(out, ensure_ascii=False)

    @tool
    def propose_action(action_type: str, payload: str, summary: str = "") -> str:
        """产一个结构化提案(作者审批后才落库)。action_type 见下;payload=JSON 字符串。

        支持 action_type:
        - create_chapter_with_beat: payload={volume_id, global_number, title, beat:{purpose, pov_character_id?}}
        - trigger_run: payload={global_number}
        - set_beat_contract: payload={beat_id, purpose, pov_character_id?}
        返回"提案已记录,等待作者审批"。
        """
        try:
            data = json.loads(payload) if isinstance(payload, str) else payload
        except json.JSONDecodeError as e:
            return f"payload 不是合法 JSON: {e}"
        pid = add_proposal(conn, session_id, action_type, data)
        return f"已记录提案 #{pid}({action_type})「{summary or '无摘要'}」,等待作者审批。"

    return [get_work_overview, list_chapters, get_chapter_detail, get_character_canon,
            get_master_outline, propose_action]


SYSTEM_PROMPT = """你是磐石 Bedrock 的作者助手,帮助作者做【写前创作】:规划章节、起草 beat 契约、
查设定一致性、解读 review 报告。你的输出会直接进对话面板供作者审批。

原则:
- 先用工具读作品上下文(角色正典、前章尾、大纲、章节列表)再答,别凭空编。
- 角色代词/性别/设定严格按 get_character_canon,不得擅改。
- 涉及创建章节/beat 或触发写作,调 propose_action 产提案(别谎称已落库;落库要作者审批)。
- beat.purpose 是这一拍的叙事目的(≥10 字,具体到发生什么),不是抽象标签。
- 续写新章:volume_id 从 list_chapters/get_work_overview 取;global_number = 现有最大 +1。
- 简洁,给作者可决策的选项,不写长篇大论。"""


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
