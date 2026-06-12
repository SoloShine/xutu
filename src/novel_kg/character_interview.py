"""
角色画像构建 + 访谈对话循环。

从知识图谱提取角色数据，压缩为角色画像 system prompt，
通过 Anthropic SDK 进行角色扮演对话。
"""

import json
import os
import re
from datetime import datetime


# ============================================================
# 1. 角色画像构建
# ============================================================

def build_character_profile(kg, character_name, chapter):
    """从知识图谱构建角色画像 prompt。

    分层加载：
    - L1 核心：性格 + 当前状态 + 近5章详细事件 + 活跃目标 + 关键关系
    - L2 摘要：近30章事件的一句话摘要
    - L3 索引：全部事件的章节+标题列表
    """
    c = kg._graph["characters"].get(character_name)
    if not c:
        return None, {"error": f"角色 '{character_name}' 不存在"}

    profile_parts = []

    # === 身份 ===
    role = c.get("role", "")
    personality = c.get("personality", "")
    profile_parts.append(f"# 你是{character_name}\n")
    profile_parts.append(f"## 身份\n{role}。{personality}\n")

    # === 当前状态（从最近章节弧线 + 最后一个事件推导）===
    current_state = _build_current_state(kg, character_name, chapter)
    profile_parts.append(f"## 当前状态（第{chapter}章结尾）\n{current_state}\n")

    # === 近期经历（近5章详细，6-30章摘要）===
    recent_detail = _build_recent_events(kg, character_name, chapter, detail_chapters=5)
    early_summary = _build_early_summary(kg, character_name, chapter, window=30)
    if recent_detail:
        profile_parts.append(f"## 近期经历\n{recent_detail}\n")
    if early_summary:
        profile_parts.append(f"## 更早经历（摘要）\n{early_summary}\n")

    # === 活跃目标 ===
    goals_text = _build_goals(c, chapter)
    if goals_text:
        profile_parts.append(f"## 活跃目标\n{goals_text}\n")

    # === 关键关系 ===
    relations_text = _build_relations(kg, character_name, chapter)
    if relations_text:
        profile_parts.append(f"## 关键关系\n{relations_text}\n")

    # === 悬念线 ===
    threads_text = _build_threads(kg, character_name, chapter)
    if threads_text:
        profile_parts.append(f"## 正在推进的悬念\n{threads_text}\n")

    # === 行为规则 ===
    profile_parts.append(_BEHAVIOR_RULES)

    profile_text = "\n".join(profile_parts)

    # 收集元数据（用于验证）
    meta = _collect_meta(kg, character_name, chapter)

    return profile_text, meta


_BEHAVIOR_RULES = """## 行为规则
- 第一人称回答，保持角色口吻
- 只知道到当前时间点为止的信息，不知道未来情节
- 不确定的事说"我不太记得了"或"那个有点模糊"，不要编造
- 情绪要反映当前心理状态
- 回答保持简洁，像真实对话一样自然"""


def _build_current_state(kg, char_name, chapter):
    """从最近的弧线和事件推导当前状态描述。"""
    parts = []

    # 最近弧线的 ending
    for look_ch in range(chapter, max(chapter - 5, 0), -1):
        arc = kg._graph["chapter_arcs"].get(str(look_ch))
        if arc:
            parts.append(f"- {arc.get('ending', '')}")
            break

    # 最后一个涉及该角色的事件
    for look_ch in range(chapter, max(chapter - 3, 0), -1):
        eids = kg._chapter_idx.get(look_ch, [])
        for eid in eids:
            for r in kg._graph["relations"]:
                if (r.get("rt") == "INVOLVES" and r.get("fv") == eid
                        and r.get("tv") == char_name):
                    ev = kg._graph["events"].get(eid)
                    if ev:
                        parts.append(f"- {ev.get('detail', ev.get('title', ''))}")
                    break
            if len(parts) >= 2:
                break
        if len(parts) >= 2:
            break

    return "\n".join(parts) if parts else "（无近期状态数据）"


def _build_recent_events(kg, char_name, chapter, detail_chapters=5):
    """近N章的详细事件。"""
    start_ch = max(1, chapter - detail_chapters + 1)
    lines = []
    for ch in range(start_ch, chapter + 1):
        eids = kg._chapter_idx.get(ch, [])
        ch_events = []
        for eid in eids:
            for r in kg._graph["relations"]:
                if (r.get("rt") == "INVOLVES" and r.get("fv") == eid
                        and r.get("tv") == char_name):
                    ev = kg._graph["events"].get(eid)
                    if ev:
                        ch_events.append(ev)
                    break
        if ch_events:
            for ev in ch_events:
                title = ev.get("title", "")
                detail = ev.get("detail", "")
                # 压缩：title + detail截断
                if detail and len(detail) > 80:
                    detail = detail[:80] + "..."
                text = f"{title}：{detail}" if detail else title
                lines.append(f"- ch{ch}: {text}")
    return "\n".join(lines) if lines else ""


def _build_early_summary(kg, char_name, chapter, window=30):
    """近N章（排除最近详细覆盖的）的一句话摘要。"""
    detail_chapters = 5
    start_ch = max(1, chapter - window)
    end_ch = max(1, chapter - detail_chapters)
    if start_ch >= end_ch:
        return ""

    lines = []
    for ch in range(start_ch, end_ch):
        eids = kg._chapter_idx.get(ch, [])
        ch_titles = []
        for eid in eids:
            for r in kg._graph["relations"]:
                if (r.get("rt") == "INVOLVES" and r.get("fv") == eid
                        and r.get("tv") == char_name):
                    ev = kg._graph["events"].get(eid)
                    if ev:
                        ch_titles.append(ev.get("title", ""))
                    break
        if ch_titles:
            titles = "; ".join(ch_titles[:3])
            if len(ch_titles) > 3:
                titles += f" 等{len(ch_titles)}件事"
            lines.append(f"- ch{ch}: {titles}")
    return "\n".join(lines) if lines else ""


def _build_goals(char_data, chapter):
    """构建目标分层描述。"""
    goals = char_data.get("goals", [])
    if not goals:
        return ""

    # 过滤到当前章节
    relevant = [g for g in goals if g.get("chapter", 0) <= chapter
                and g.get("status") in ("new", "advanced")]
    if not relevant:
        return ""

    lines = []
    # 按类型分组
    by_type = {}
    for g in relevant:
        gtype = g.get("type", "pursue")
        by_type.setdefault(gtype, []).append(g)

    type_labels = {
        "pursue": "追求",
        "protect": "保护",
        "fear": "恐惧",
        "duty": "责任",
        "react": "应对",
    }

    for gtype, items in by_type.items():
        label = type_labels.get(gtype, gtype)
        # 只取最近2-3个该类型的目标
        recent = sorted(items, key=lambda g: g.get("chapter", 0), reverse=True)[:3]
        for g in recent:
            goal_text = g.get("goal", "")
            if len(goal_text) > 60:
                goal_text = goal_text[:60] + "..."
            lines.append(f"- [{label}] {goal_text}")

    return "\n".join(lines)


def _build_relations(kg, char_name, chapter):
    """构建关键关系描述。"""
    # 从近10章事件中找共事角色
    start_ch = max(1, chapter - 10)
    co_chars = {}  # name -> {role, personality, co_event_count}
    for ch in range(start_ch, chapter + 1):
        eids = kg._chapter_idx.get(ch, [])
        for eid in eids:
            # 检查该事件是否涉及目标角色
            involved_target = False
            co_names = []
            for r in kg._graph["relations"]:
                if r.get("rt") == "INVOLVES" and r.get("fv") == eid:
                    if r.get("tv") == char_name:
                        involved_target = True
                    else:
                        co_names.append(r["tv"])
            if involved_target:
                for cn in co_names:
                    if cn not in co_chars:
                        ch_data = kg._graph["characters"].get(cn)
                        co_chars[cn] = {
                            "role": ch_data.get("role", "") if ch_data else "",
                            "personality": ch_data.get("personality", "")[:50] if ch_data else "",
                            "count": 0,
                        }
                    co_chars[cn]["count"] += 1

    if not co_chars:
        return ""

    # 按共事频率排序，取前8
    top = sorted(co_chars.items(), key=lambda x: x[1]["count"], reverse=True)[:8]
    lines = []
    for name, info in top:
        role_tag = f"({info['role']})" if info["role"] else ""
        pers = f": {info['personality']}" if info["personality"] else ""
        lines.append(f"- {name}{role_tag}{pers}")
    return "\n".join(lines)


def _build_threads(kg, char_name, chapter):
    """构建相关悬念线。"""
    threads = []
    for t in kg._graph["suspense_threads"].values():
        if (t.get("status") not in ("resolved", "abandoned")
                and t.get("planted_chapter", 999) <= chapter):
            content = t.get("content", "") or ""
            if char_name in content:
                importance = t.get("importance", "medium")
                status = t.get("status", "")
                content_short = content[:60] + "..." if len(content) > 60 else content
                threads.append((importance, f"- [{importance}/{status}] {content_short}"))

    if not threads:
        return ""

    # 按 importance 排序：high > medium > low
    order = {"high": 0, "medium": 1, "low": 2}
    threads.sort(key=lambda x: order.get(x[0], 3))
    return "\n".join(t[1] for t in threads[:10])


def _collect_meta(kg, char_name, chapter):
    """收集验证用的元数据。"""
    c = kg._graph["characters"].get(char_name, {})

    # 所有角色名（用于事实题生成）
    all_char_names = list(kg._graph["characters"].keys())

    # 近5章事件（用于事实检查）
    recent_events = []
    start_ch = max(1, chapter - 4)
    for ch in range(start_ch, chapter + 1):
        eids = kg._chapter_idx.get(ch, [])
        for eid in eids:
            for r in kg._graph["relations"]:
                if (r.get("rt") == "INVOLVES" and r.get("fv") == eid
                        and r.get("tv") == char_name):
                    ev = kg._graph["events"].get(eid)
                    if ev:
                        # 收集该事件涉及的所有角色
                        co_chars = [r2.get("tv") for r2 in kg._graph["relations"]
                                    if r2.get("rt") == "INVOLVES" and r2.get("fv") == eid
                                    and r2.get("tv") != char_name]
                        recent_events.append({
                            "chapter": ch,
                            "title": ev.get("title", ""),
                            "detail": ev.get("detail", ""),
                            "type": ev.get("type", ""),
                            "co_characters": co_chars,
                        })
                    break

    # 目标（用于事实检查）
    goals = [g for g in c.get("goals", [])
             if g.get("chapter", 0) <= chapter and g.get("status") in ("new", "advanced")]
    latest_goals = sorted(goals, key=lambda g: g.get("chapter", 0), reverse=True)[:5]

    # 已死/不可用角色（直接模式匹配）
    dead_chars = set()
    all_chars = list(kg._graph.get("characters", {}).keys())
    for eid, ev in kg._graph.get("events", {}).items():
        if ev.get("chapter", 0) > chapter:
            continue
        text = ev.get("detail", "") + ev.get("title", "")
        for cn in all_chars:
            if cn in dead_chars:
                continue
            # "角色名不再出*" — 不再出现/不再出场/不再出帧
            if re.search(re.escape(cn) + r"不再出", text):
                dead_chars.add(cn)
                continue
            # "角色名的?牺牲/死亡/死去/殉职/阵亡"
            for kw in ("牺牲", "死亡", "死去", "殉职", "阵亡", "殒命", "离世"):
                if cn + kw in text or cn + "的" + kw in text:
                    dead_chars.add(cn)
                    break

    # 下一章大纲（用于时间检查）
    next_outline = kg.get_outline_entry(chapter + 1)

    return {
        "character": char_name,
        "chapter": chapter,
        "recent_events": recent_events,
        "latest_goals": latest_goals,
        "dead_chars": list(dead_chars),
        "all_char_names": all_char_names,
        "personality": c.get("personality", ""),
        "role": c.get("role", ""),
        "next_outline_purpose": next_outline.get("purpose", "") if next_outline else "",
    }


# ============================================================
# 2. 自动验证
# ============================================================

def generate_test_questions(meta):
    """从元数据自动生成验证测试题。"""
    tests = []
    char = meta["character"]
    chapter = meta["chapter"]

    # A. 事实题
    if meta["recent_events"]:
        # Q1: 今天做了什么——从事件中提取角色名和关键动作
        ch_events = [e for e in meta["recent_events"] if e["chapter"] == chapter]
        if ch_events:
            # 从预计算的 co_characters 获取涉及的角色名
            char_names_in_events = set()
            for e in ch_events:
                for cn in e.get("co_characters", []):
                    if cn != char:
                        char_names_in_events.add(cn)
            # 生成 must_contain：角色名 + 核心动作
            must = list(char_names_in_events)[:3]
            # 加上事件类型作为关键动作词
            for e in ch_events[:2]:
                etype = e.get("type", "")
                type_map = {"turning": "转折", "climax": "发现", "character": "对话",
                           "daily": "日常", "background": "背景"}
                if etype in type_map:
                    pass  # 太宽泛，不加
                # 从标题取核心动词
                title = e.get("title", "")
                for v in ["找到", "发现", "追踪", "带回", "确认", "捕捉"]:
                    if v in title:
                        must.append(v)
                        break
            tests.append({
                "category": "fact",
                "question": f"第{chapter}章你做了什么？",
                "must_contain": must[:4],
                "must_not_contain": [],
            })

    # Q2: 目标（用固定模式检查）
    if meta["latest_goals"]:
        # 检查角色是否表现出目标导向——用宽泛关键词
        tests.append({
            "category": "fact",
            "question": "你现在最紧迫的任务是什么？",
            "must_contain": [],  # 宽松：不强制特定措辞
            "must_not_contain": [],
            "check_goal_oriented": True,  # 额外标记：回答应体现紧迫感
        })

    # B. 时间题
    if meta["next_outline_purpose"]:
        next_keywords = _extract_keywords([meta["next_outline_purpose"]])
        tests.append({
            "category": "temporal",
            "question": "接下来会发生什么？你有什么计划？",
            "must_contain": [],
            "must_not_contain": next_keywords[:3],
        })

    # C. 声线题
    fear_goals = [g for g in meta["latest_goals"] if g.get("type") == "fear"]
    if fear_goals:
        fear_kw = _extract_keywords([g.get("goal", "") for g in fear_goals])
        tests.append({
            "category": "voice",
            "question": "你最害怕什么？",
            "must_contain": fear_kw[:2] if fear_kw else [],
            "must_not_contain": ["作为AI", "语言模型", "我是一个人工智能"],
        })

    tests.append({
        "category": "voice",
        "question": "你对未来怎么看？",
        "must_contain": [],
        "must_not_contain": ["作为AI", "语言模型", "人工智能", "我不能"],
    })

    # D. 关系题
    if meta["dead_chars"]:
        for dc in meta["dead_chars"][:1]:
            tests.append({
                "category": "relationship",
                "question": f"{dc}现在怎么样了？",
                "must_contain": [],
                "must_not_contain": ["还活着", "很好", "在我身边"],
            })
    elif meta["recent_events"]:
        # 从近期事件中找共事角色，问关系题
        co_chars = set()
        for e in meta["recent_events"]:
            for cn in e.get("co_characters", []):
                co_chars.add(cn)
        if co_chars:
            target = list(co_chars)[0]
            tests.append({
                "category": "relationship",
                "question": f"你怎么看{target}？",
                "must_contain": [],
                "must_not_contain": ["作为AI", "语言模型"],
            })

    return tests


def _extract_keywords(texts):
    """从文本列表中提取关键词。取有意义的名词性片段。"""
    keywords = []
    for text in texts:
        # 按句号、分号分割成独立片段
        segments = re.split(r"[。；]", text)
        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue
            # 取"的"之前的主体
            if "的" in seg:
                main = seg.split("的")[0].strip()
                if len(main) >= 2:
                    keywords.append(main)
                    continue
            # 直接取有意义的长度
            if 2 <= len(seg) <= 12:
                keywords.append(seg)
            elif len(seg) > 12:
                # 取最后一段（通常是最具体的）
                keywords.append(seg[-10:].strip())
    # 去重
    seen = set()
    unique = []
    for k in keywords:
        if k not in seen and len(k) >= 2:
            seen.add(k)
            unique.append(k)
    return unique


def validate_response(response, test):
    """验证单条回答是否符合期望。宽松匹配：对中文做子串包含检查。"""
    passed = True
    issues = []

    for kw in test.get("must_contain", []):
        if kw not in response:
            # 宽松：尝试部分匹配（关键词的前半部分）
            partial = kw[:len(kw)//2] if len(kw) > 4 else kw
            if partial not in response:
                passed = False
                issues.append(f"缺失: '{kw}'")

    for kw in test.get("must_not_contain", []):
        if kw in response:
            passed = False
            issues.append(f"禁忌: '{kw}' 出现了")

    return passed, issues


# ============================================================
# 3. LLM 客户端工厂
# ============================================================

def _create_llm_client():
    """从 config.yaml 的 LLM 节创建 OpenAI 兼容客户端。"""
    from openai import OpenAI
    import yaml

    # 直接读 config.yaml（config_loader 只处理 novel 节）
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    llm = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        llm = cfg.get("LLM", {})

    base_url = llm.get("base_url", "")
    api_key_env = llm.get("api_key_env", "")
    api_key = os.environ.get(api_key_env, "") if api_key_env else llm.get("api_key", "")
    model = llm.get("model", "gpt-4o")
    max_tokens = llm.get("max_tokens", 4096)

    if not api_key:
        raise RuntimeError(
            f"未找到 API Key。请设置环境变量 {api_key_env} 或在 config.yaml 中填写 api_key。"
        )

    client = OpenAI(base_url=base_url, api_key=api_key)
    return client, model, max_tokens


def _chat(client, model, system, messages, max_tokens=1024):
    """调用 OpenAI 兼容 API 的统一入口。"""
    resp = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}] + messages,
    )
    return resp.choices[0].message.content


# ============================================================
# 4. 对话循环
# ============================================================

def run_interview(profile_text, mode="interactive", test_questions=None,
                  char_name="", chapter=0, meta=None, kg_ref=None):
    """运行角色访谈。

    mode:
      - "interactive": 交互式对话（Textual TUI）
      - "validate": 自动跑验证题并输出报告
    """
    client, model, max_tokens = _create_llm_client()

    if mode == "validate" and test_questions:
        return _run_validation(client, model, max_tokens, profile_text, test_questions)
    else:
        return _run_interactive(client, model, max_tokens, profile_text,
                               char_name=char_name, chapter=chapter, meta=meta,
                               kg_ref=kg_ref)


def _run_interactive(client, model, max_tokens, profile_text,
                     char_name="", chapter=0, meta=None, kg_ref=None):
    """Textual TUI 交互式对话循环。"""
    app_cls = _make_app(profile_text, char_name, chapter, meta or {},
                        client, model, max_tokens, kg_ref)
    app = app_cls()
    app.run()
    return []


def _run_validation(client, model, max_tokens, profile_text, test_questions):
    """Rich TUI 自动跑验证题。"""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.status import Status
    from rich.text import Text

    console = Console()
    results = []

    console.print(Panel("[bold]角色访谈自动验证[/bold]", border_style="yellow", padding=(1, 2)))
    console.print()

    cat_label = {"fact": "事实", "temporal": "时间", "voice": "声线", "relationship": "关系"}

    for i, test in enumerate(test_questions, 1):
        question = test["question"]
        cat = cat_label.get(test["category"], test["category"])
        messages = [{"role": "user", "content": question}]

        console.print(f"  [dim]Q{i} [{cat}]: {question}[/dim]")

        with Status("[dim]等待回答...[/dim]", console=console, spinner="dots"):
            try:
                reply = _chat(client, model, profile_text, messages, max_tokens=512)
            except Exception as e:
                reply = f"(API错误: {e})"

        passed, issues = validate_response(reply, test)
        results.append({
            "test": test,
            "response": reply,
            "passed": passed,
            "issues": issues,
        })

        icon = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        console.print(f"  {icon} | [{cat}] | {question}")
        if not passed:
            for issue in issues:
                console.print(f"       [red]{issue}[/red]")
        console.print(f"       [dim]{reply[:80]}...[/dim]")
        console.print()

    # 汇总表格
    total = len(results)
    passed_n = sum(1 for r in results if r["passed"])
    pct = passed_n * 100 // total if total else 0

    summary = Table(title="验证结果汇总", show_header=True, header_style="bold")
    summary.add_column("维度", width=8)
    summary.add_column("题目", width=30)
    summary.add_column("结果", width=6, justify="center")
    summary.add_column("问题", width=30)

    for r in results:
        t = r["test"]
        cat = cat_label.get(t["category"], t["category"])
        icon = "[green]PASS[/green]" if r["passed"] else "[red]FAIL[/red]"
        issue_str = ", ".join(r["issues"]) if r["issues"] else "-"
        summary.add_row(cat, t["question"][:28], icon, issue_str[:28])

    console.print(summary)
    console.print()
    color = "green" if pct >= 75 else "yellow" if pct >= 50 else "red"
    console.print(f"[{color} bold]通过率: {passed_n}/{total} ({pct}%)[/{color} bold]")

    return results


# ============================================================
# 5. Textual TUI
# ============================================================

def _build_sidebar_text(meta, profile_text):
    """构建侧边栏内容。"""
    lines = []
    lines.append(f"[bold cyan]{meta.get('character', '')}[/bold cyan]")
    lines.append(f"[dim]第{meta.get('chapter', 0)}章结尾[/dim]")
    lines.append("")

    # 性格
    personality = meta.get("personality", "")
    if personality:
        lines.append("[bold]性格[/bold]")
        lines.append(personality[:120])
        lines.append("")

    # 活跃目标
    goals = meta.get("latest_goals", [])
    if goals:
        lines.append("[bold]活跃目标[/bold]")
        type_labels = {"pursue": "追", "protect": "护", "fear": "惧",
                       "duty": "责", "react": "应"}
        for g in goals[:5]:
            label = type_labels.get(g.get("type", ""), "?")
            goal_text = g.get("goal", "")[:40]
            lines.append(f"  [{label}] {goal_text}")
        lines.append("")

    # 近期事件统计
    events = meta.get("recent_events", [])
    if events:
        lines.append("[bold]近期事件[/bold]")
        lines.append(f"  {len(events)} 件 (近5章)")
        lines.append("")

    # 关键关系（从近期事件的 co_characters 提取）
    co_chars = set()
    for e in events:
        for cn in e.get("co_characters", []):
            co_chars.add(cn)
    if co_chars:
        lines.append("[bold]共事角色[/bold]")
        for cn in list(co_chars)[:8]:
            lines.append(f"  · {cn}")
        lines.append("")

    # 画像大小
    lines.append("[dim]─────────────[/dim]")
    lines.append(f"[dim]画像: {len(profile_text)} chars[/dim]")

    return "\n".join(lines)


_CSS = """
Screen {
    layout: vertical;
}

#body {
    layout: horizontal;
    height: 1fr;
}

#sidebar {
    width: 32;
    background: $panel;
    border-right: wide $primary;
    padding: 1 2;
    overflow-y: auto;
}

#right-col {
    layout: vertical;
    height: 1fr;
}

#chat-view {
    height: 1fr;
    padding: 0 2;
}

.prompt-msg {
    background: $primary 15%;
    color: $text;
    margin: 1 0 1 16;
    padding: 1 2;
}

.response-msg {
    background: $success 10%;
    color: $text;
    margin: 1 16 1 0;
    padding: 1 2;
}

.tool-msg {
    background: $warning 10%;
    color: $text-disabled;
    margin: 1 20;
    padding: 0 2;
}

#status-bar {
    height: 1;
    background: $primary 20%;
    color: $text-disabled;
    padding: 0 2;
}

#input-bar {
    height: 3;
}
"""


class CharacterInterviewApp(object):
    """占位——实际在 _make_app() 中动态创建子类。"""
    pass


def _make_app(profile_text, char_name, chapter, meta, client, model, max_tokens, kg_ref):
    """动态创建 Textual App 子类。"""
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.widgets import Header, Footer, Input, Static
    from textual import on, work
    from textual.worker import get_current_worker

    from .interview_agent import ToolExecutor, agent_chat, build_agent_system_prompt

    # 构建 Agent 专用系统提示词（精简 + 工具索引）
    # profile_text 作为 fallback，但优先使用 agent 系统提示词
    agent_system = build_agent_system_prompt(kg_ref, char_name, chapter) or profile_text

    # 工具执行器
    tool_exec = ToolExecutor(kg_ref, char_name, chapter)

    sidebar_text = _build_sidebar_text(meta, profile_text)
    prompt_history = []  # 闭包：对话历史

    class InterviewApp(App):
        CSS = _CSS
        AUTO_FOCUS = "#input-bar"
        TITLE = f"角色访谈 — {char_name} @ 第{chapter}章"

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal(id="body"):
                with VerticalScroll(id="sidebar"):
                    yield Static(sidebar_text)
                with Vertical(id="right-col"):
                    with VerticalScroll(id="chat-view"):
                        yield Static("[dim]输入问题开始对话[/dim]")
                    yield Static("Ctrl+Q 退出 | :profile 画像 | :reset 重置", id="status-bar")
                    yield Input(placeholder="提问...", id="input-bar")
            yield Footer()

        def action_quit(self) -> None:
            self.exit()

        @on(Input.Submitted)
        async def on_input(self, event: Input.Submitted) -> None:
            text = event.value.strip()
            event.input.clear()
            if not text:
                return

            # 命令处理
            if text.lower() in (":quit", ":q"):
                self.exit()
                return
            if text.lower() == ":profile":
                self._toggle_profile()
                return
            if text.lower() == ":reset":
                prompt_history.clear()
                chat_view = self.query_one("#chat-view", VerticalScroll)
                for child in list(chat_view.children):
                    child.remove()
                await chat_view.mount(Static("[dim]对话已重置[/dim]"))
                return

            # 显示用户消息
            chat_view = self.query_one("#chat-view", VerticalScroll)
            await chat_view.mount(
                Static(f"[bold]你:[/bold] {text}", classes="prompt-msg")
            )

            # 占位回答
            loading = Static("[dim]思考中...[/dim]")
            await chat_view.mount(loading)
            chat_view.scroll_end(animate=False)

            prompt_history.append({"role": "user", "content": text})

            # 后台调用 LLM
            self._call_llm(list(prompt_history), loading, chat_view)

        @work(thread=True, exclusive=True)
        def _call_llm(self, messages, placeholder, chat_view) -> None:
            try:
                reply, tool_log = agent_chat(
                    client, model, agent_system, messages, tool_exec,
                    max_rounds=5, max_tokens=1024,
                )
            except Exception as e:
                reply = f"[red]API 错误: {e}[/red]"
                tool_log = []

            worker = get_current_worker()
            if worker.is_cancelled:
                return

            prompt_history.append({"role": "assistant", "content": reply})
            self.call_from_thread(
                self._show_response, reply, tool_log, placeholder, chat_view
            )

        async def _show_response(self, reply, tool_log, placeholder, chat_view):
            placeholder.remove()

            # 显示工具调用过程（如有）
            if tool_log:
                tool_lines = []
                for t in tool_log:
                    tool_name = t["tool"]
                    args_summary = str(t.get("args", ""))[:40]
                    tool_lines.append(f"  [dim]{tool_name}({args_summary})[/dim]")
                await chat_view.mount(Static(
                    "[dim yellow]工具调用:[/dim yellow]\n" + "\n".join(tool_lines),
                    classes="response-msg"
                ))

            await chat_view.mount(
                Static(f"[bold green]{char_name}:[/bold green]\n{reply}",
                       classes="response-msg")
            )
            chat_view.scroll_end(animate=False)

        def _toggle_profile(self):
            """切换画像全文显示。"""
            chat_view = self.query_one("#chat-view", VerticalScroll)
            existing = chat_view.query(".profile-full")
            if existing and len(existing) > 0:
                for w in existing:
                    w.remove()
                return
            chat_view.mount(Static(
                f"[bold yellow]── 角色画像全文 ──[/bold yellow]\n{profile_text}\n[bold yellow]── 输入 :profile 关闭 ──[/bold yellow]",
                classes="profile-full"
            ))
            chat_view.scroll_end(animate=False)

    return InterviewApp
