"""
角色访谈 Agent 层。

独立于 UI 的智能体核心：工具定义 + function calling 循环。
可被 TUI、CLI、或编程方式调用。
"""

import json
import os

from . import kg_json


# ============================================================
# 工具定义（OpenAI function calling 格式）
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "recall_thread",
            "description": "回忆某条悬念线/伏笔的完整内容。当你需要回忆某条线索的来龙去脉时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "thread_id": {
                        "type": "string",
                        "description": "悬念线ID（如 T_ch5_01）或关键词（如'第三穿越者'、'晶体化'）",
                    }
                },
                "required": ["thread_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_arc",
            "description": "回忆某一章发生了什么。返回该章的弧线、事件和涉及的角色。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter": {
                        "type": "integer",
                        "description": "章节编号（如 74）",
                    }
                },
                "required": ["chapter"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": "搜索与你相关的事件。按关键词搜索你参与过的事件列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词（如'信号'、'穿越者'、'晶体'）",
                    },
                    "start_chapter": {
                        "type": "integer",
                        "description": "起始章节（可选，默认从头搜）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回几条（默认10）",
                    },
                },
                "required": ["keyword"],
            },
        },
    },
]


# ============================================================
# 工具执行
# ============================================================

class ToolExecutor:
    """执行角色访谈工具调用，返回结果字符串。"""

    def __init__(self, kg, character_name, chapter):
        self.kg = kg
        self.char_name = character_name
        self.chapter = chapter

    def execute(self, tool_name, arguments):
        """执行工具调用，返回结果字符串。"""
        handler = {
            "recall_thread": self._recall_thread,
            "recall_arc": self._recall_arc,
            "search_events": self._search_events,
        }.get(tool_name)

        if not handler:
            return f"未知工具: {tool_name}"

        try:
            return handler(**arguments)
        except Exception as e:
            return f"工具执行错误: {e}"

    def _recall_thread(self, thread_id="", **_):
        """回忆悬念线。支持 ID 或关键词搜索。"""
        threads = self.kg._graph.get("suspense_threads", {})

        # 精确 ID 匹配
        if thread_id in threads:
            t = threads[thread_id]
            return self._format_thread(thread_id, t)

        # 关键词模糊匹配
        matches = []
        for tid, t in threads.items():
            content = t.get("content", "") or ""
            if thread_id in content or thread_id in tid:
                matches.append((tid, t))

        if not matches:
            return f"未找到与 '{thread_id}' 相关的悬念线。"

        if len(matches) == 1:
            return self._format_thread(matches[0][0], matches[0][1])

        # 多条匹配，返回列表
        lines = [f"找到 {len(matches)} 条相关悬念线："]
        for tid, t in matches[:10]:
            status = t.get("status", "")
            content = (t.get("content", "") or "")[:80]
            lines.append(f"  [{status}] {tid}: {content}...")
        return "\n".join(lines)

    def _format_thread(self, tid, t):
        content = t.get("content", "") or ""
        status = t.get("status", "")
        importance = t.get("importance", "")
        planted = t.get("planted_chapter", "")
        resolved = t.get("resolved_chapter", "")

        lines = [
            f"悬念线: {tid}",
            f"状态: {status} | 重要度: {importance} | 种植于第{planted}章",
        ]
        if resolved:
            lines.append(f"解决于第{resolved}章")
        lines.append(f"内容: {content}")
        return "\n".join(lines)

    def _recall_arc(self, chapter, **_):
        """回忆某章弧线。"""
        arcs = self.kg._graph.get("chapter_arcs", {})
        arc = arcs.get(str(chapter))
        if not arc:
            return f"第{chapter}章没有弧线数据。"

        lines = [f"第{chapter}章弧线:"]
        for key in ("purpose", "scenes", "ending", "structure_type"):
            val = arc.get(key, "")
            if val:
                label = {"purpose": "目的", "scenes": "场景", "ending": "结尾",
                         "structure_type": "结构"}.get(key, key)
                lines.append(f"  {label}: {val}")

        # 该章涉及该角色的事件
        eids = self.kg._chapter_idx.get(chapter, [])
        char_events = []
        for eid in eids:
            for r in self.kg._graph["relations"]:
                if (r.get("rt") == "INVOLVES" and r.get("fv") == eid
                        and r.get("tv") == self.char_name):
                    ev = self.kg._graph["events"].get(eid)
                    if ev:
                        char_events.append(ev)
                    break

        if char_events:
            lines.append(f"  你的事件({len(char_events)}件):")
            for ev in char_events[:5]:
                title = ev.get("title", "")
                detail = ev.get("detail", "")[:100]
                lines.append(f"    - {title}: {detail}")

        return "\n".join(lines)

    def _search_events(self, keyword, start_chapter=1, limit=10, **_):
        """搜索角色参与的含关键词的事件。"""
        results = []
        for ch in range(start_chapter, self.chapter + 1):
            eids = self.kg._chapter_idx.get(ch, [])
            for eid in eids:
                for r in self.kg._graph["relations"]:
                    if (r.get("rt") == "INVOLVES" and r.get("fv") == eid
                            and r.get("tv") == self.char_name):
                        ev = self.kg._graph["events"].get(eid)
                        if ev:
                            text = ev.get("title", "") + ev.get("detail", "")
                            if keyword in text:
                                results.append((ch, ev))
                        break

        if not results:
            return f"未找到与 '{keyword}' 相关的事件。"

        lines = [f"找到 {len(results)} 件相关事件（显示前{min(len(results), limit)}件）："]
        for ch, ev in results[:limit]:
            title = ev.get("title", "")
            detail = ev.get("detail", "")[:80]
            lines.append(f"  ch{ch}: {title} — {detail}...")

        return "\n".join(lines)


# ============================================================
# Agent 循环
# ============================================================

def build_agent_system_prompt(kg, character_name, chapter):
    """构建 Agent 系统提示词。精简版：核心信息 + 工具索引。"""
    c = kg._graph["characters"].get(character_name)
    if not c:
        return None

    parts = []

    # 身份
    parts.append(f"# 你是{character_name}\n")
    parts.append(f"## 身份\n{c.get('role', '')}。{c.get('personality', '')}\n")

    # 当前状态（最近弧线结尾 + 最后一个事件）
    for look_ch in range(chapter, max(chapter - 5, 0), -1):
        arc = kg._graph["chapter_arcs"].get(str(look_ch))
        if arc:
            parts.append(f"## 当前状态（第{chapter}章结尾）\n- {arc.get('ending', '')}\n")
            break

    # 近3章事件摘要（比画像更精简）
    lines = []
    for ch in range(max(1, chapter - 2), chapter + 1):
        eids = kg._chapter_idx.get(ch, [])
        for eid in eids:
            for r in kg._graph["relations"]:
                if (r.get("rt") == "INVOLVES" and r.get("fv") == eid
                        and r.get("tv") == character_name):
                    ev = kg._graph["events"].get(eid)
                    if ev:
                        lines.append(f"- ch{ch}: {ev.get('title', '')}")
                    break
    if lines:
        parts.append("## 近期经历\n" + "\n".join(lines) + "\n")

    # 工具索引——列出可按需回忆的线索（只列标题，不展开）
    threads_index = []
    for tid, t in kg._graph["suspense_threads"].items():
        if (t.get("status") not in ("resolved", "abandoned")
                and t.get("planted_chapter", 999) <= chapter):
            content = (t.get("content", "") or "")[:50]
            threads_index.append(f"  - {tid}: {content}...")
    if threads_index:
        parts.append("## 可回忆的线索（用 recall_thread 展开详情）\n"
                      + "\n".join(threads_index[:15]) + "\n")

    # 行为规则
    parts.append("""## 行为规则
- 第一人称回答，保持角色口吻
- 只知道到当前时间点为止的信息，不知道未来情节
- 如果记不清细节，使用工具回忆（recall_thread / recall_arc / search_events）
- 不确定的事说"我不太记得了"，不要编造
- 情绪要反映当前心理状态
- 回答保持简洁，像真实对话一样自然""")

    return "\n".join(parts)


def _estimate_tokens(messages):
    """粗略估算 messages 的 token 数（中文约 1.5 字/token）。"""
    total = 0
    for m in messages:
        content = m.get("content", "") or ""
        total += len(content) // 1.5
    return int(total)


def _trim_messages(messages, max_chars=30000):
    """裁剪消息历史，保持最近对话不超过 max_chars。

    策略：保留最后 6 轮对话（user+assistant），中间的早期消息用摘要替代。
    """
    if _estimate_tokens(messages) * 1.5 < max_chars:
        return messages

    # 保留最近 6 条（3 轮对话），其余丢弃
    keep_count = min(6, len(messages))
    trimmed = messages[-keep_count:]

    # 如果裁剪了内容，插入一条提示
    if len(messages) > keep_count:
        trimmed.insert(0, {
            "role": "system",
            "content": "[对话历史已自动裁剪，只保留最近几轮。如果需要回忆更早的对话，使用工具查询。]",
        })

    return trimmed


def agent_chat(client, model, system_prompt, messages, tool_executor,
               max_rounds=8, max_tokens=1024):
    """带工具调用的 Agent 对话循环。

    返回 (final_reply, tool_calls_log)
    - final_reply: 最终文本回答
    - tool_calls_log: 工具调用记录列表 [{tool, args, result}]
    """
    tool_log = []
    working_messages = list(messages)

    for _ in range(max_rounds):
        # 自动裁剪上下文
        working_messages = _trim_messages(working_messages)

        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system_prompt}] + working_messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        choice = resp.choices[0]
        msg = choice.message

        # 没有工具调用——直接返回内容
        if not msg.tool_calls:
            return msg.content or "", tool_log

        # 处理工具调用
        working_messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        })

        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            result = tool_executor.execute(tool_name, args)
            tool_log.append({"tool": tool_name, "args": args, "result": result[:200]})

            working_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    # 达到最大轮次，返回最后一条消息
    return working_messages[-1].get("content", ""), tool_log
