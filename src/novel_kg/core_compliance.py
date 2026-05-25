"""
核心合规检查模块 — 大纲合规、校验编排、冲突检测。

从 core.py 拆分，V27。
"""

import json
import os

from .core import _kg, config_loader, _llm_enabled
from .core_cache import read_purpose_cache, write_purpose_cache, invalidate_purpose_cache
from .core_errors import SystemError
from .validators import validate_chapter as _run_validation


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
    from .mine import detect_conflicts as _detect
    return _detect(kg, extracted)


# ---- 合规检查核心 ----

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

    from .validators import check_outline_compliance as _check_compliance
    violations = _check_compliance(outline_entry, events, chapter_arc=chapter_arc)

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

    semantic_checks = []
    if pending_semantic:
        if _llm_enabled():
            sem_results = _semantic_compliance_check(
                project, chapter, outline_entry, events, pending_semantic
            )
            for item, matched, reason in sem_results:
                severity = "warning" if matched else "error"
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
        else:
            for v in pending_semantic:
                field_info = v.fix.split(":", 2) if v.fix and ":" in v.fix else ["", "", ""]
                field_name = field_info[1] if len(field_info) > 1 else ""
                semantic_checks.append({
                    "item": v.constraint_type,
                    "status": "pending",
                    "severity": "error" if field_name == "key_events" else "warning",
                    "detail": f"语义判定需Agent审查: {v.detail}",
                    "needs_agent_review": True,
                })

    cfg = config_loader.load(project)
    if cfg.get("collaboration", {}).get("semantic_check", True):
        purpose = outline_entry.get("purpose", "")
        if purpose and events:
            if _llm_enabled():
                purpose_result = _purpose_compliance_check(
                    project, chapter, purpose, events
                )
            else:
                purpose_result = {
                    "item": "purpose_alignment",
                    "status": "pending",
                    "severity": "info",
                    "detail": f"目的合规需Agent审查: '{purpose[:50]}'",
                    "needs_agent_review": True,
                }
            semantic_checks.append(purpose_result)

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


def batch_check_outline_compliance(project: str,
                                   chapters: list = None,
                                   batch_size: int = 8) -> dict:
    """批量化大纲合规检查：程序化逐章执行，purpose检查按batch_size分批合并LLM调用。"""
    kg = _kg(project)

    if batch_size <= 0:
        batch_size = 9999

    if chapters is None:
        all_outlines = kg.get_all_outline_entries()
        chapters = sorted([o.get("chapter", 0) for o in all_outlines
                           if o.get("chapter")])

    results = {}
    chapters_needing_purpose = []

    for ch in chapters:
        result = check_outline_compliance(project, ch)
        results[ch] = result
        oe = result.get("outline_entry") or {}
        if oe.get("purpose"):
            chapters_needing_purpose.append({
                "chapter": ch,
                "purpose": oe["purpose"],
                "events": kg.get_events_by_chapter(ch),
            })

    batch_done = False
    batch_count = 0
    cfg = config_loader.load(project)
    if (cfg.get("collaboration", {}).get("semantic_check", True)
            and len(chapters_needing_purpose) > 1
            and batch_size > 1
            and _llm_enabled()):
        for i in range(0, len(chapters_needing_purpose), batch_size):
            batch = chapters_needing_purpose[i:i + batch_size]
            batch_result = _batch_purpose_check(project, batch)
            if batch_result:
                batch_done = True
                batch_count += 1
                for ch_info in batch_result:
                    ch = ch_info["chapter"]
                    if ch in results:
                        sem = results[ch].get("semantic_checks", [])
                        sem = [s for s in sem if s.get("item") != "purpose_alignment"]
                        sem.append(ch_info["result"])
                        results[ch]["semantic_checks"] = sem
                        all_c = (results[ch].get("programmatic_checks", [])
                                 + sem)
                        errs = [c for c in all_c if c["severity"] == "error"]
                        warns = [c for c in all_c if c["severity"] == "warning"]
                        if errs:
                            results[ch]["overall"] = "diverged"
                        elif warns:
                            results[ch]["overall"] = "partial"
                        else:
                            results[ch]["overall"] = "followed"
                        results[ch]["action_required"] = results[ch]["overall"] != "followed"

    return {
        "results": results,
        "batch_purpose": batch_done,
        "batch_count": batch_count,
        "batch_size": batch_size,
        "stats": {
            "total": len(results),
            "followed": sum(1 for r in results.values()
                           if r.get("overall") == "followed"),
            "partial": sum(1 for r in results.values()
                          if r.get("overall") == "partial"),
            "diverged": sum(1 for r in results.values()
                           if r.get("overall") == "diverged"),
            "no_outline": sum(1 for r in results.values()
                             if r.get("overall") == "no_outline"),
        }
    }


# ---- 内部合规辅助函数 ----

def _batch_purpose_check(project, chapters_info):
    """批量purpose合规检查：一次LLM调用检查多章。"""
    cached_results = {}
    uncached_info = []
    for info in chapters_info:
        ch = info["chapter"]
        cached = read_purpose_cache(project, ch, info["purpose"], info["events"])
        if cached is not None:
            cached_results[ch] = cached
        else:
            uncached_info.append(info)

    if not uncached_info:
        return [{"chapter": ch, "result": cached_results[ch]}
                for ch in sorted(cached_results.keys())]

    sections = []
    for info in uncached_info:
        ch = info["chapter"]
        purpose = info["purpose"]
        events = info["events"]
        ev_lines = []
        for ev in events:
            title = ev.get("title", "")
            detail = ev.get("detail", "")
            if title or detail:
                ev_lines.append(f"  - {title}{'：' + detail if detail else ''}")
        sections.append(
            f"### 第{ch}章\n大纲目的: {purpose}\n实际事件:\n"
            + "\n".join(ev_lines)
        )

    prompt = f"""你是小说大纲合规检查助手。判断以下多章的实际事件是否符合各自大纲的叙事目的。

{chr(10).join(sections)}

## 判定标准
- 不是要求完全一致，而是判断叙事方向是否一致
- 如果大纲目的是"潜入B2层"但实际是"送外卖买早餐"，这是偏离
- 如果大纲目的是"建立悬念"而实际是"发现线索建立悬念"，这是符合的
- 允许细节层面的偏差，但不允许叙事方向的根本性改变

## 输出格式（JSON数组）
```json
[{{"chapter": 章节号, "aligned": true/false, "reason": "简要说明", "confidence": "high/medium/low"}}]
```"""

    try:
        from .llm import call_llm
        result = call_llm(prompt, json_mode=True,
                          stream_label=f"批量目的合规({len(uncached_info)}章)")
        items = result if isinstance(result, list) else [result]
        output = []
        for item in items:
            ch = item.get("chapter")
            aligned = bool(item.get("aligned", False))
            reason = str(item.get("reason", ""))
            confidence = str(item.get("confidence", "medium"))
            purpose = ""
            events = []
            for info in uncached_info:
                if info["chapter"] == ch:
                    purpose = info["purpose"]
                    events = info["events"]
                    break
            res = {
                "item": "purpose_alignment",
                "status": "aligned" if aligned else "diverged",
                "severity": "info" if aligned else "warning",
                "detail": f"批量目的合规: 大纲'{purpose[:30]}...' — "
                          f"{'对齐' if aligned else '偏离'} "
                          f"(confidence={confidence}) — {reason}",
                "confidence": confidence,
            }
            write_purpose_cache(project, ch, purpose, events, res)
            output.append({"chapter": ch, "result": res})

        for ch, res in cached_results.items():
            output.append({"chapter": ch, "result": res})

        return output
    except Exception as e:
        import sys
        print(f"[core_compliance] _batch_purpose_check LLM 调用失败: {e}", file=sys.stderr)
        if cached_results:
            return [{"chapter": ch, "result": cached_results[ch]}
                    for ch in sorted(cached_results.keys())]
        return None


def _semantic_compliance_check(project, chapter, outline_entry, events,
                                pending_items):
    """LLM语义合规判定：对bigram未匹配的大纲项进行语义等价检查。"""
    event_summaries = []
    for ev in events:
        title = ev.get("title", "")
        detail = ev.get("detail", "")
        if title or detail:
            event_summaries.append(f"- {title}{'：' + detail if detail else ''}")

    if not event_summaries:
        return [(v, False, "本章无事件数据") for v in pending_items]

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
        from .llm import call_llm
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
        import sys
        print(f"[core_compliance] _semantic_compliance_check Ch{chapter} LLM 调用失败: {e}",
              file=sys.stderr)

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
    """LLM purpose级别合规检查。"""
    cached = read_purpose_cache(project, chapter, purpose, events)
    if cached is not None:
        return cached

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
        from .llm import call_llm
        result = call_llm(prompt, json_mode=True,
                          stream_label=f"目的合规Ch{chapter}")
        if isinstance(result, dict):
            aligned = bool(result.get("aligned", False))
            reason = str(result.get("reason", ""))
            confidence = str(result.get("confidence", "medium"))
            ret = {
                "item": "purpose_alignment",
                "status": "aligned" if aligned else "diverged",
                "severity": "info" if aligned else "warning",
                "detail": f"目的合规: 大纲'{purpose[:30]}...' — "
                          f"{'对齐' if aligned else '偏离'} (confidence={confidence}) — {reason}",
                "confidence": confidence,
            }
            write_purpose_cache(project, chapter, purpose, events, ret)
            return ret
    except Exception as e:
        import sys
        print(f"[core_compliance] _purpose_compliance_check Ch{chapter} LLM 调用失败: {e}",
              file=sys.stderr)

    return {
        "item": "purpose_alignment",
        "status": "unknown",
        "severity": "info",
        "detail": f"目的合规检查不可用: 大纲'{purpose[:30]}...'",
        "confidence": "unknown",
    }
