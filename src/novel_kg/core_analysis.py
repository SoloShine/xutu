"""
核心分析模块 — 叙事节奏分析、编辑影响分析、大纲修订、后端同步。

从 core.py 拆分，V27。
"""

import json

from .core import _kg, config_loader, _bigram_overlap_str
from .core_cache import invalidate_purpose_cache
from .core_errors import UserError


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

    _check_purpose_repetition(arcs_sorted, issues, cfg)
    _check_ending_repetition(arcs_sorted, issues, cfg)
    _check_scene_density(arcs_sorted, issues)
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
    window = 3
    min_shared = cfg.get("pacing", {}).get("min_shared", 2)
    for i in range(len(arcs) - window + 1):
        window_arcs = arcs[i:i+window]
        chapters = [a.get("chapter", 0) for a in window_arcs]
        ending_types = [a.get("ending_type", "") for a in window_arcs]
        if all(ending_types):
            if len(set(ending_types)) == 1:
                issues.append({
                    "type": "结尾类型重复",
                    "detail": f"第{chapters[0]}-{chapters[-1]}章连续{window}章结尾类型相同: '{ending_types[0]}'",
                    "severity": "high"
                })
            continue
        endings = [a.get("ending", "") for a in window_arcs]
        if _shared_keywords(endings, min_shared=min_shared):
            issues.append({
                "type": "结尾重复",
                "detail": f"第{chapters[0]}-{chapters[-1]}章结尾类型相似: '{endings[0][:20]}'...",
                "severity": "medium"
            })


def _check_scene_density(arcs, issues):
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

    for i in range(1, len(intensities)):
        diff = abs(intensities[i] - intensities[i-1])
        if diff > intense_diff:
            issues.append({
                "type": "节奏剧烈波动",
                "detail": f"第{chapters_sorted[i-1]}章(强度{intensities[i-1]}) -> 第{chapters_sorted[i]}章(强度{intensities[i]})，变化{diff}",
                "severity": "low"
            })


# ============================================================
# 编辑影响分析
# ============================================================

def analyze_edit_impact(project: str, chapter: int) -> dict:
    """事后影响分析：对比edited文本的提取结果与图谱中该章数据。"""
    kg = _kg(project)

    edited_text = kg.get_edited_chapter_text(chapter)
    if not edited_text:
        return UserError(
            f"未找到第{chapter}章的编辑版本 (ch{chapter}_edited.txt)",
            code="NOT_FOUND"
        ).to_dict()

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


# ============================================================
# 大纲修订
# ============================================================

def revise_outline(project: str, chapter: int, reason: str,
                   purpose: str = "", key_events: str = "",
                   threads_to_plant: str = "", threads_to_resolve: str = "",
                   structure_hint: str = "") -> str:
    """显式修订大纲条目。只修改传入的字段，并记录修订原因。"""
    kg = _kg(project)
    existing = kg.get_outline_entry(chapter)
    if not existing:
        return UserError(
            f"第{chapter}章无大纲条目，无法修订。请先用 add_outline_entry 创建。",
            code="NOT_FOUND"
        ).to_dict()

    all_arcs = kg.get_all_chapter_arcs()
    max_chapter = max((a.get("chapter", 0) for a in all_arcs), default=chapter)

    props = existing.copy()
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
    from .kg_sync import sync_json_to_neo4j, sync_neo4j_to_json
    if direction == "json_to_neo4j":
        report = sync_json_to_neo4j(project)
    elif direction == "neo4j_to_json":
        report = sync_neo4j_to_json(project)
    else:
        return UserError(
            f"未知方向: {direction}，可选: json_to_neo4j, neo4j_to_json",
            code="BAD_PARAM"
        ).to_dict()
    return json.dumps(report, ensure_ascii=False, indent=2)
