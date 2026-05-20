"""
Novel KG 工具核心逻辑。

连接池 + 破坏性保护 + 26个业务函数。
server.py（MCP）和 mcp_cli.py（CLI）共享此模块。
"""

import sys
import os
import json
import atexit

# 定位目录
_here = os.path.dirname(os.path.abspath(__file__))
_mvp_dir = os.path.normpath(os.path.join(_here, '..', 'novel_kg_mvp'))
_projects_dir = os.path.join(_mvp_dir, 'projects')

# novel_kg_mvp 需要 chdir（因为 config.yaml 相对路径）
os.chdir(_mvp_dir)
if _mvp_dir not in sys.path:
    sys.path.insert(0, _mvp_dir)

from config_loader import config_loader
from mine import (
    build_extraction_prompt, detect_conflicts,
    write_extraction_to_graph,
    clear_chapter_data as _mine_clear_chapter,
)
from main import build_writing_prompt
from prompts import ARC_DERIVATION_PROMPT
from validators import validate_chapter as _run_validation


def _persist(project: str, subdir: str, filename: str, content: str):
    """将内容落盘到 projects/<project>/<subdir>/<filename>。"""
    from datetime import datetime
    dir_path = os.path.join(_projects_dir, project, subdir)
    os.makedirs(dir_path, exist_ok=True)
    path = os.path.join(dir_path, filename)
    header = f"# Persisted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + content)


def _bigram_overlap_str(s1, s2, min_shared=2):
    """检查两个字符串是否有足够的bigram重叠"""
    if not s1 or not s2:
        return False
    def _bigrams(s):
        if len(s) < 4:
            return {s} if s else set()
        return {s[i:i+2] for i in range(len(s)-1)}
    return len(_bigrams(s1) & _bigrams(s2)) >= min_shared


# ============================================================
# Backend Selection
# ============================================================

_BACKEND = os.environ.get("KG_BACKEND", "json")  # "json"(默认) 或 "neo4j"


def _create_backend(project: str):
    """根据环境变量创建后端实例"""
    cfg = config_loader.load(project)
    if _BACKEND == "neo4j":
        from graph import NovelKG
        return NovelKG(project=project, config=cfg)
    else:
        # 延迟导入，避免 Neo4j 依赖
        if _here not in sys.path:
            sys.path.insert(0, _here)
        from kg_json import JsonKG
        return JsonKG(project=project, data_dir=_projects_dir, config=cfg)


# ============================================================
# Connection Pool
# ============================================================

_pool: dict = {}


def _kg(project: str):
    """获取或创建连接池中的后端实例。"""
    if project not in _pool:
        _pool[project] = _create_backend(project)
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

def get_chapter_context(project: str, chapter: int,
                        prev_text_chars: int = None) -> dict:
    if prev_text_chars is None:
        prev_text_chars = config_loader.get(project, "writing", "prev_text_chars", default=500)
    kg = _kg(project)
    return kg.get_context_for_chapter(chapter, prev_text_chars=prev_text_chars)


def get_derivation_context(project: str, chapter: int, lookback: int = None) -> dict:
    if lookback is None:
        lookback = config_loader.get(project, "derivation", "lookback", default=3)
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
    prompt = build_extraction_prompt(kg, chapter, chapter_text, project=project)
    _persist(project, "prompts", f"extraction_ch{chapter}.txt", prompt)
    return prompt


def get_writing_prompt(project: str, chapter: int,
                       prev_text_chars: int = None) -> str:
    if prev_text_chars is None:
        prev_text_chars = config_loader.get(project, "writing", "prev_text_chars", default=500)
    cfg = config_loader.load(project)
    kg = _kg(project)
    context = kg.get_context_for_chapter(chapter, prev_text_chars=prev_text_chars)
    prompt = build_writing_prompt(context, chapter, config=cfg)
    _persist(project, "prompts", f"writing_ch{chapter}.txt", prompt)
    return prompt


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

    cfg = config_loader.load(project)
    prompt = ARC_DERIVATION_PROMPT.format(
        outline_entry=outline_text, suspense_threads=threads_text,
        recent_arcs=arcs_text, recent_events=events_text,
        characters=chars_text, themes=themes_text, motifs=motifs_text,
        last_event=last_event_text,
        scenes_per_arc=cfg.get("derivation", {}).get("scenes_per_arc", "3-5"))
    _persist(project, "prompts", f"derivation_ch{chapter}.txt", prompt)
    return prompt


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
                    thread_plan: str = "", reasoning: str = "",
                    rhythm: str = "") -> str:
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
    if rhythm:
        props["rhythm"] = rhythm
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
    # 落盘提取结果
    _persist(project, "extractions", f"extraction_ch{chapter}.json",
             json.dumps(extracted, ensure_ascii=False, indent=2))
    report = write_extraction_to_graph(kg, chapter, extracted,
                                       skip_conflicts=True, project=project)
    return {
        "chapter": report["chapter"],
        "stats": report["stats"],
        "conflicts": report["conflicts"],
        "character_updates": report.get("character_updates", []),
        "notes": report.get("notes", ""),
        "skipped_threads": report.get("skipped_threads", []),
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
    cfg = config_loader.load(project)
    context = kg.get_context_for_chapter(chapter)
    arc = context.get("chapter_arc", [None])
    arc = arc[0] if arc else None
    result = _run_validation(text, context, arc=arc, config=cfg)
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


def check_outline_compliance(project: str, chapter: int) -> dict:
    """大纲合规检查（程序化+LLM语义）。"""
    kg = _kg(project)
    outline_entry = kg.get_outline_entry(chapter)
    if not outline_entry:
        return {"chapter": chapter, "overall": "no_outline", "action_required": False}

    events = kg.get_events_by_chapter(chapter)
    arcs = kg.get_all_chapter_arcs()
    chapter_arc = None
    for a in arcs:
        if a.get("chapter") == chapter:
            chapter_arc = a
            break

    from validators import check_outline_compliance as _check_compliance
    violations = _check_compliance(outline_entry, events, chapter_arc=chapter_arc)

    # 分离程序化结果和需要语义检查的项
    programmatic_checks = []
    pending_semantic = []
    for v in violations:
        if v.severity == "pending_semantic":
            pending_semantic.append(v)
        else:
            programmatic_checks.append({
                "item": v.constraint_type,
                "status": "failed",
                "severity": v.severity,
                "detail": v.detail,
            })

    # 第二步：对程序化未匹配的项，调用LLM语义判定
    semantic_checks = []
    if pending_semantic:
        sem_results = _semantic_compliance_check(
            project, chapter, outline_entry, events, pending_semantic
        )
        for item, matched, reason in sem_results:
            severity = "warning" if matched else "error"
            # key_events用error，其余用warning
            field = item.fix.split(":")[1] if item.fix and ":" in item.fix else ""
            if not matched and field == "key_events":
                severity = "error"
            elif not matched:
                severity = "warning"
            semantic_checks.append({
                "item": item.constraint_type,
                "status": "matched" if matched else "failed",
                "severity": severity if not matched else "info",
                "detail": f"语义判定: '{item.detail.split('未在程序化检查中匹配')[0].strip()}' "
                          f"{'已匹配' if matched else '未匹配'} — {reason}",
                "original_outline_item": item.fix.split(":", 2)[-1] if item.fix and ":" in item.fix else "",
            })

    # 第三步：purpose级别的LLM语义检查（始终执行）
    # 判断章节事件是否符合大纲的叙事目的，不受bigram影响
    cfg = config_loader.load(project)
    if cfg.get("collaboration", {}).get("semantic_check", True):
        purpose = outline_entry.get("purpose", "")
        if purpose and events:
            purpose_result = _purpose_compliance_check(
                project, chapter, purpose, events
            )
            semantic_checks.append(purpose_result)

    # 合并所有检查结果
    all_checks = programmatic_checks + semantic_checks

    errors = [c for c in all_checks if c["severity"] == "error"]
    warnings = [c for c in all_checks if c["severity"] == "warning"]

    if errors:
        overall = "diverged"
    elif warnings:
        overall = "partial"
    else:
        overall = "followed"

    return {
        "chapter": chapter,
        "outline_entry": outline_entry,
        "programmatic_checks": programmatic_checks,
        "semantic_checks": semantic_checks,
        "overall": overall,
        "action_required": overall != "followed",
    }


def _semantic_compliance_check(project, chapter, outline_entry, events,
                                pending_items):
    """LLM语义合规判定：对bigram未匹配的大纲项进行语义等价检查。

    返回 list of (Violation, matched: bool, reason: str)
    """
    # 收集事件文本作为"实际发生了什么"
    event_summaries = []
    for ev in events:
        title = ev.get("title", "")
        detail = ev.get("detail", "")
        if title or detail:
            event_summaries.append(f"- {title}{'：' + detail if detail else ''}")

    if not event_summaries:
        # 没有事件，所有未匹配项直接判定为失败
        return [(v, False, "本章无事件数据") for v in pending_items]

    # 构建LLM prompt
    items_text = []
    for v in pending_items:
        field_info = v.fix.split(":", 2) if v.fix and ":" in v.fix else ["", "", ""]
        field_name = field_info[1] if len(field_info) > 1 else "unknown"
        item_value = field_info[2] if len(field_info) > 2 else ""
        items_text.append(f"- [{field_name}] {item_value}")

    prompt = f"""你是小说大纲合规检查助手。判断以下大纲要求是否在章节事件中得到满足（语义等价即可，不需要字面匹配）。

## 第{chapter}章大纲要求（程序化bigram未匹配的项）
{chr(10).join(items_text)}

## 第{chapter}章实际事件
{chr(10).join(event_summaries)}

## 判定规则
- "深夜来访"、"突然出现"、"夜间到访"是语义等价的
- "讲述历史"、"说出真相"、"揭露秘密"可能语义等价
- "发现异常"、"注意到不对劲"、"察觉异样"是语义等价的
- 关键是判断大纲描述的事件是否在章节中以不同措辞发生了

## 输出格式（JSON）
返回一个JSON数组，每个元素对应一个大纲要求：
```json
[
  {{"matched": true/false, "reason": "简要说明为什么匹配/不匹配"}}
]
```
按大纲要求的顺序返回，不要遗漏。"""

    try:
        from llm import call_llm
        result = call_llm(prompt, json_mode=True,
                          stream_label=f"语义合规检查Ch{chapter}")
        if isinstance(result, list) and len(result) == len(pending_items):
            return [
                (pending_items[i],
                 bool(r.get("matched", False)),
                 str(r.get("reason", "")))
                for i, r in enumerate(result)
            ]
    except Exception as e:
        # LLM调用失败时，按保守策略处理：key_events视为error，其余warning
        pass

    # Fallback: 无法判定时按字段类型给severity
    results = []
    for v in pending_items:
        field_info = v.fix.split(":", 2) if v.fix and ":" in v.fix else ["", "", ""]
        field_name = field_info[1] if len(field_info) > 1 else ""
        if field_name == "key_events":
            results.append((v, False, "LLM语义检查不可用，按error处理"))
        else:
            results.append((v, False, "LLM语义检查不可用，按warning处理"))
    return results


def _purpose_compliance_check(project, chapter, purpose, events):
    """LLM purpose级别合规检查：判断章节事件是否符合大纲的叙事目的。

    这是独立于bigram/语义匹配的检查维度——即使key_events都匹配了，
    如果章节事件在叙事目的层面偏离了大纲，也应该被检测出来。
    返回 dict（semantic_check条目格式）。
    """
    event_summaries = []
    for ev in events:
        title = ev.get("title", "")
        detail = ev.get("detail", "")
        if title or detail:
            event_summaries.append(f"- {title}{'：' + detail if detail else ''}")

    prompt = f"""你是小说大纲合规检查助手。判断第{chapter}章的实际事件是否符合大纲的叙事目的。

## 大纲叙事目的
{purpose}

## 第{chapter}章实际事件
{chr(10).join(event_summaries)}

## 判定标准
- 不是要求完全一致，而是判断叙事方向是否一致
- 如果大纲目的是"潜入B2层"但实际是"送外卖买早餐"，这是明显偏离
- 如果大纲目的是"建立悬念"而实际是"发现线索建立悬念"，这是符合的
- 允许细节层面的偏差，但不允许叙事方向的根本性改变

## 输出格式（JSON）
```json
{{"aligned": true/false, "reason": "简要说明为什么对齐/偏离", "confidence": "high/medium/low"}}
```"""

    try:
        from llm import call_llm
        result = call_llm(prompt, json_mode=True,
                          stream_label=f"目的合规Ch{chapter}")
        if isinstance(result, dict):
            aligned = bool(result.get("aligned", False))
            reason = str(result.get("reason", ""))
            confidence = str(result.get("confidence", "medium"))
            return {
                "item": "purpose_alignment",
                "status": "aligned" if aligned else "diverged",
                "severity": "info" if aligned else "warning",
                "detail": f"目的合规: 大纲'{purpose[:30]}...' — "
                          f"{'对齐' if aligned else '偏离'} (confidence={confidence}) — {reason}",
                "confidence": confidence,
            }
    except Exception:
        pass

    # Fallback
    return {
        "item": "purpose_alignment",
        "status": "unknown",
        "severity": "info",
        "detail": f"目的合规检查不可用: 大纲'{purpose[:30]}...'",
        "confidence": "unknown",
    }


def revise_outline(project: str, chapter: int, reason: str,
                   purpose: str = "", key_events: str = "",
                   threads_to_plant: str = "", threads_to_resolve: str = "",
                   structure_hint: str = "") -> str:
    """显式修订大纲条目。只修改传入的字段，并记录修订原因。"""
    kg = _kg(project)
    existing = kg.get_outline_entry(chapter)
    if not existing:
        return f"第{chapter}章无大纲条目，无法修订。请先用 add_outline_entry 创建。"

    all_arcs = kg.get_all_chapter_arcs()
    max_chapter = max((a.get("chapter", 0) for a in all_arcs), default=chapter)

    # Merge with existing entry
    props = existing.copy()
    # Remove chapter from props to avoid duplicate argument
    props.pop("chapter", None)
    props.update({
        "compliance": "overridden",
        "revision_reason": reason,
        "revised_chapter": max_chapter,
    })
    if purpose:
        props["purpose"] = purpose
    if key_events:
        props["key_events"] = key_events
    if threads_to_plant:
        props["threads_to_plant"] = threads_to_plant
    if threads_to_resolve:
        props["threads_to_resolve"] = threads_to_resolve
    if structure_hint:
        props["structure_hint"] = structure_hint

    kg.add_outline_entry(chapter, **props)
    updated_fields = [k for k in props if k not in ("compliance", "revision_reason", "revised_chapter")]
    return f"已修订第{chapter}章大纲。原因: {reason}。更新字段: {', '.join(updated_fields) or '无'}"


# ============================================================
# 后端同步
# ============================================================

def sync_backends(project: str, direction: str = "json_to_neo4j") -> str:
    """同步 JSON 和 Neo4j 后端数据"""
    from kg_sync import sync_json_to_neo4j, sync_neo4j_to_json
    if direction == "json_to_neo4j":
        report = sync_json_to_neo4j(project)
    elif direction == "neo4j_to_json":
        report = sync_neo4j_to_json(project)
    else:
        return f"[ERROR] 未知方向: {direction}，可选: json_to_neo4j, neo4j_to_json"
    return json.dumps(report, ensure_ascii=False, indent=2)


# ============================================================
# 叙事节奏分析
# ============================================================

def analyze_pacing(project: str) -> dict:
    """分析叙事节奏问题"""
    kg = _kg(project)
    arcs = kg.get_all_chapter_arcs()

    if len(arcs) < 3:
        return {"issues": [], "message": "章节弧线不足3个，无法分析节奏",
                "total_arcs": len(arcs)}

    issues = []
    arcs_sorted = sorted(arcs, key=lambda a: a.get("chapter", 0))
    cfg = config_loader.load(project)

    # 1. 目的重复检测
    _check_purpose_repetition(arcs_sorted, issues, cfg)

    # 2. 结尾重复检测
    _check_ending_repetition(arcs_sorted, issues, cfg)

    # 3. 场景密度异常
    _check_scene_density(arcs_sorted, issues)

    # 4. 节奏曲线分析
    _check_pacing_curve(arcs_sorted, issues, kg, cfg)

    return {
        "total_arcs": len(arcs_sorted),
        "issues": issues,
        "chapters": [a.get("chapter", 0) for a in arcs_sorted],
    }


def _shared_keywords(strings, min_shared):
    """检查多个字符串是否共享足够多的关键词（bigram方法）"""
    if not all(strings):
        return False

    def _bigrams(s):
        if len(s) < 4:
            return set()
        return {s[i:i+2] for i in range(len(s)-1)}

    gram_sets = [_bigrams(s) for s in strings]
    common = gram_sets[0]
    for gs in gram_sets[1:]:
        common = common & gs
    return len(common) >= min_shared


def _check_purpose_repetition(arcs, issues, cfg):
    """检测连续3+章目的重复"""
    window = 3
    min_shared = cfg.get("pacing", {}).get("min_shared", 2)
    for i in range(len(arcs) - window + 1):
        window_arcs = arcs[i:i+window]
        purposes = [a.get("purpose", "") for a in window_arcs]
        chapters = [a.get("chapter", 0) for a in window_arcs]
        if len(set(purposes)) == 1 and purposes[0]:
            issues.append({
                "type": "目的重复",
                "detail": f"第{chapters[0]}-{chapters[-1]}章连续{window}章目的相同: '{purposes[0]}'",
                "severity": "medium"
            })
        elif _shared_keywords(purposes, min_shared=min_shared):
            issues.append({
                "type": "目的相似",
                "detail": f"第{chapters[0]}-{chapters[-1]}章目的高度相似",
                "severity": "low"
            })


def _check_ending_repetition(arcs, issues, cfg):
    """检测连续3+章结尾类型重复"""
    window = 3
    min_shared = cfg.get("pacing", {}).get("min_shared", 2)
    for i in range(len(arcs) - window + 1):
        window_arcs = arcs[i:i+window]
        endings = [a.get("ending", "") for a in window_arcs]
        chapters = [a.get("chapter", 0) for a in window_arcs]
        if _shared_keywords(endings, min_shared=min_shared):
            issues.append({
                "type": "结尾重复",
                "detail": f"第{chapters[0]}-{chapters[-1]}章结尾类型相似: '{endings[0][:20]}'...",
                "severity": "medium"
            })


def _check_scene_density(arcs, issues):
    """检测场景密度异常"""
    scene_counts = []
    for arc in arcs:
        scenes_str = arc.get("scenes", "")
        if scenes_str:
            count = len([s.strip() for s in scenes_str.split("->") if s.strip()])
        else:
            count = 0
        scene_counts.append((arc.get("chapter", 0), count))

    if len(scene_counts) < 3:
        return

    counts = [c for _, c in scene_counts]
    avg = sum(counts) / len(counts) if counts else 0

    for ch, count in scene_counts:
        if count > avg * 2 and avg > 0:
            issues.append({
                "type": "场景密度异常",
                "detail": f"第{ch}章有{count}个场景，平均{avg:.1f}个",
                "severity": "low"
            })


def _check_pacing_curve(arcs, issues, kg, cfg):
    """分析节奏曲线"""
    pacing_cfg = cfg.get("pacing", {})
    flat_threshold = pacing_cfg.get("flat_threshold", 4)
    intense_diff = pacing_cfg.get("intense_diff", 5)
    all_events = kg.get_all_events()

    HIGH_TYPES = {"climax", "turning", "revelation", "confrontation"}
    chapter_intensity = {}
    for ev in all_events:
        ch = ev.get("chapter", 0)
        if ch == 0:
            continue
        ev_type = ev.get("type", ev.get("event_type", "daily"))
        score = 3 if ev_type in HIGH_TYPES else 1
        chapter_intensity[ch] = chapter_intensity.get(ch, 0) + score

    if len(chapter_intensity) < 4:
        return

    chapters_sorted = sorted(chapter_intensity.keys())
    intensities = [chapter_intensity[ch] for ch in chapters_sorted]

    # 检测太平缓：连续4+章强度相同
    flat_count = 1
    for i in range(1, len(intensities)):
        if intensities[i] == intensities[i-1]:
            flat_count += 1
            if flat_count >= flat_threshold:
                issues.append({
                    "type": "节奏太平缓",
                    "detail": f"第{chapters_sorted[i-flat_count+1]}-{chapters_sorted[i]}章强度无变化（均为{intensities[i]}）",
                    "severity": "medium"
                })
                break
        else:
            flat_count = 1

    # 检测太剧烈：相邻章节强度差>5
    for i in range(1, len(intensities)):
        diff = abs(intensities[i] - intensities[i-1])
        if diff > intense_diff:
            issues.append({
                "type": "节奏剧烈波动",
                "detail": f"第{chapters_sorted[i-1]}章(强度{intensities[i-1]}) -> 第{chapters_sorted[i]}章(强度{intensities[i]})，变化{diff}",
                "severity": "low"
            })


def analyze_edit_impact(project: str, chapter: int) -> dict:
    """事后影响分析：对比edited文本的提取结果与图谱中该章数据。"""
    kg = _kg(project)

    edited_text = kg.get_edited_chapter_text(chapter)
    if not edited_text:
        return {
            "error": f"未找到第{chapter}章的编辑版本 (ch{chapter}_edited.txt)",
            "edited_chapter": chapter,
        }

    old_events = kg.get_events_by_chapter(chapter)
    old_event_ids = {e["id"] for e in old_events}
    old_event_map = {e["id"]: e for e in old_events}

    all_outlines = kg.get_all_outline_entries()
    downstream_outlines = [
        oe for oe in all_outlines
        if oe.get("chapter", 0) > chapter
    ]

    old_evidence_links = [
        r for r in kg.get_all_relations()
        if r["rt"] == "EVIDENCES"
        and r["fv"] in old_event_ids
    ]
    affected_thread_ids = {r["tv"] for r in old_evidence_links}
    all_threads = kg.get_all_threads()
    affected_threads = [
        {"id": t["id"], "content": t.get("content", ""),
         "status": t.get("status", ""), "importance": t.get("importance", ""),
         "impact": "关联事件可能被删除或修改", "severity": "high"}
        for t in all_threads if t["id"] in affected_thread_ids
    ]

    old_char_names = set()
    for r in kg.get_all_relations():
        if (r["fl"] == "Event" and r["fk"] == "id"
                and r["fv"] in old_event_ids
                and r["rt"] == "INVOLVES"
                and r["tl"] == "Character"):
            old_char_names.add(r["tv"])

    downstream_warnings = []
    outline_revision_suggestions = []
    for oe in downstream_outlines:
        ke = oe.get("key_events", "")
        for eid, ev in old_event_map.items():
            title = ev.get("title", "")
            if title and _bigram_overlap_str(title, ke):
                downstream_warnings.append({
                    "chapter": oe.get("chapter", 0),
                    "outline_key": "key_events",
                    "issue": f"依赖可能被删除/修改的事件'{title}' ({eid})",
                })
                outline_revision_suggestions.append({
                    "chapter": oe.get("chapter", 0),
                    "field": "key_events",
                    "suggestion": f"检查'{title}'是否仍存在，必要时替换",
                })

    return {
        "edited_chapter": chapter,
        "old_events": [{"id": e["id"], "title": e.get("title", "")} for e in old_events],
        "affected_threads": affected_threads,
        "affected_characters": sorted(old_char_names),
        "downstream_warnings": downstream_warnings,
        "outline_revision_suggestions": outline_revision_suggestions,
        "edited_text_length": len(edited_text),
        "message": "Agent需对edited文本重新提取，然后调用 accept_edit 写入图谱",
    }


def accept_edit(project: str, chapter: int, extracted_json: str,
                confirm: str = "") -> dict:
    """采纳事后编辑：快照旧数据 → 清除 → 写入新数据 → 标记后续大纲。"""
    err = _check_destructive(confirm)
    if err:
        return {"error": err}

    kg = _kg(project)

    # 自动快照旧数据（覆盖前可回滚）
    snapshot_id = kg.snapshot_chapter(chapter, reason=f"accept_edit ch{chapter}")

    _mine_clear_chapter(kg, chapter)

    if isinstance(extracted_json, str):
        extracted = json.loads(extracted_json)
    else:
        extracted = extracted_json
    report = write_extraction_to_graph(kg, chapter, extracted,
                                        skip_conflicts=True, project=project)

    all_outlines = kg.get_all_outline_entries()
    marked = []
    for oe in all_outlines:
        ch = oe.get("chapter", 0)
        if ch > chapter:
            existing = kg.get_outline_entry(ch)
            if existing and existing.get("compliance") != "overridden":
                kg.add_outline_entry(ch, **{
                    k: v for k, v in existing.items()
                    if k != "chapter"
                }, compliance="needs_revision")
                marked.append(ch)

    return {
        "chapter": chapter,
        "stats": report["stats"],
        "conflicts": report["conflicts"],
        "downstream_marked_for_revision": marked,
        "snapshot_id": snapshot_id,
        "message": f"已采纳第{chapter}章编辑。快照: {snapshot_id}。后续章节 {marked} 的大纲标记为 needs_revision。",
    }


def review_chapter(project: str, chapter: int, action: str,
                   edited_text: str = "") -> dict:
    """审核关卡操作。"""
    kg = _kg(project)
    valid_actions = {"accept", "edit", "rewrite", "revise_outline"}
    if action not in valid_actions:
        return {"error": f"未知操作 '{action}'，可选: {', '.join(sorted(valid_actions))}"}

    if action == "accept":
        return {
            "action": "accept",
            "chapter": chapter,
            "message": f"第{chapter}章已通过审核。可以继续第{chapter+1}章。",
        }

    if action in ("edit", "rewrite"):
        if not edited_text:
            return {"error": f"action='{action}' 需要 edited_text 参数"}
        output_dir = os.path.join(os.path.dirname(kg._path), "output")
        os.makedirs(output_dir, exist_ok=True)
        edited_path = os.path.join(output_dir, f"ch{chapter}_edited.txt")
        with open(edited_path, "w", encoding="utf-8") as f:
            f.write(edited_text)

        if action == "rewrite":
            return {
                "action": "rewrite",
                "chapter": chapter,
                "message": f"第{chapter}章已保存编辑版本。请重新提取并调用 accept_edit 写入图谱。",
                "edited_path": edited_path,
            }
        else:
            return {
                "action": "edit",
                "chapter": chapter,
                "message": f"第{chapter}章小修已保存。可调用 analyze_edit_impact 检查影响。",
                "edited_path": edited_path,
            }

    if action == "revise_outline":
        return {
            "action": "revise_outline",
            "chapter": chapter,
            "message": f"请调用 revise_outline 修订第{chapter}章大纲，然后继续。",
        }

    return {"error": "unreachable"}


# ============================================================
# 版本管理
# ============================================================

def list_edits(project: str, chapter: int = None) -> dict:
    """列出章节编辑快照历史。"""
    kg = _kg(project)
    snapshots = kg.list_snapshots(chapter=chapter)
    return {
        "project": project,
        "filter_chapter": chapter,
        "total": len(snapshots),
        "snapshots": snapshots,
    }


def rollback_edit(project: str, snapshot_id: str,
                  confirm: str = "") -> dict:
    """回滚到指定快照版本。"""
    err = _check_destructive(confirm)
    if err:
        return {"error": err}

    kg = _kg(project)
    snap = kg.get_snapshot(snapshot_id)
    if not snap:
        return {"error": f"快照 '{snapshot_id}' 不存在。请用 list_edits 查看可用快照。"}

    chapter = snap["chapter"]
    event_count = len(snap.get("events", {}))
    relation_count = len(snap.get("relations", []))

    # 回滚前快照当前状态（以便再次回滚）
    new_snap = kg.snapshot_chapter(
        chapter, reason=f"rollback to {snapshot_id}")

    success = kg.restore_snapshot(snapshot_id)
    if not success:
        return {"error": f"恢复快照 '{snapshot_id}' 失败。"}

    return {
        "snapshot_id": snapshot_id,
        "chapter": chapter,
        "restored_events": event_count,
        "restored_relations": relation_count,
        "pre_rollback_snapshot": new_snap,
        "message": f"已回滚第{chapter}章到快照 {snapshot_id} "
                   f"({event_count}事件, {relation_count}关系)。"
                   f"回滚前快照: {new_snap}",
    }
