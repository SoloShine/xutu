"""
Novel Knowledge Graph MVP
提取管线：章节文本 → 结构化数据 → 冲突检测 → 写入图谱

用于闭环流程——写完新章节后，提取新增信息回写图谱。
"""

import json
from .graph import NovelKG
from .config_loader import config_loader
from .prompts import EXTRACTION_PROMPT


def _t2s(text):
    try:
        import opencc
        return opencc.convert(text, config='t2s.json')
    except ImportError:
        pass
    table = str.maketrans(
        '壹貳參肆伍陸柒捌玖拾佰仟萬億趙錢孫李周吳鄭王馮陳褚衛蔣沈韓楊'
        '龍鳳龜鬱體國會對開應關運東長點裡萬與兩個們來時說過現問應該'
        '兒這裡開關運東長點萬與兩個們來時說過現問應該',
        '一二三四五六七八九十百千万亿赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨'
        '龙凤龟郁体国会对开应关运东长点里万与两个们来时说过现问应该'
        '儿这里开关运东长点万与两个们来时说过现问应该'
    )
    return text.translate(table)


def _s2t(text):
    try:
        import opencc
        return opencc.convert(text, config='s2t.json')
    except ImportError:
        return text


def normalize_characters(kg, extracted):
    """将提取结果中的人名规范化为图谱中已有的标准名。

    策略：繁简转换 + 子串匹配。如果图谱中有"王婆"，提取到"老王婆"，
    则将"老王婆"替换为"王婆"。
    """
    existing = kg.get_all_character_names()

    if not existing:
        return extracted, []

    def _match(name):
        if name in existing:
            return name
        s = _t2s(name)
        t = _s2t(name)
        for std in existing:
            if s == _t2s(std) or t == _s2t(std):
                return std
            if std in name or name in std:
                return std
            if _t2s(std) in s or s in _t2s(std):
                return std
        return None

    mapping = {}
    for raw_name in _collect_character_names(extracted):
        if raw_name not in existing:
            std = _match(raw_name)
            if std and std != raw_name:
                mapping[raw_name] = std

    if not mapping:
        return extracted, []

    for rel in extracted.get("event_relations", []):
        if "character" in rel and rel["character"] in mapping:
            rel["character"] = mapping[rel["character"]]

    for cu in extracted.get("character_updates", []):
        if cu["name"] in mapping:
            cu["name"] = mapping[cu["name"]]

    new_chars = []
    for nc in extracted.get("new_characters", []):
        if nc["name"] in mapping:
            pass  # skip, already exists as standard name
        else:
            new_chars.append(nc)
    extracted["new_characters"] = new_chars

    return extracted, [f"{k} -> {v}" for k, v in mapping.items()]


def _collect_character_names(extracted):
    names = set()
    for rel in extracted.get("event_relations", []):
        if "character" in rel:
            names.add(rel["character"])
    for cu in extracted.get("character_updates", []):
        names.add(cu["name"])
    for nc in extracted.get("new_characters", []):
        names.add(nc["name"])
    return names


def get_existing_characters(kg):
    """获取图谱中已有的人物名列表"""
    chars = kg.get_all_characters()
    return "\n".join(f"  - {c['name']}({c.get('role', '')})" for c in chars)


def build_extraction_prompt(kg, chapter, chapter_text, project=None):
    """构建提取prompt"""
    cfg = config_loader.load(project) if project else None
    extraction_cfg = (cfg or {}).get("extraction", {})
    target_events = extraction_cfg.get("target_events", "5-8")
    characters = get_existing_characters(kg)
    # 获取已有悬念线摘要
    threads = kg.get_unresolved_threads(chapter + 1)  # 默认全量，含本章及之前种植的
    if threads:
        threads_str = "\n".join(
            f"  - {t['id']}: {t.get('content', '')} [{t.get('status', '')}]"
            for t in threads
        )
    else:
        threads_str = "  （无）"
    return EXTRACTION_PROMPT.format(
        chapter=chapter,
        characters=characters,
        suspense_threads=threads_str,
        chapter_text=chapter_text,
        target_events=target_events,
    )


def get_chapter_time_period(kg, chapter):
    """获取章节对应的时间段标签"""
    return kg.get_chapter_time_period(chapter)


def detect_conflicts(kg, extracted, project=None):
    """检测提取数据与已有图谱的冲突"""
    cfg = config_loader.load(project) if project else None
    extraction_cfg = (cfg or {}).get("extraction", {})
    max_events = extraction_cfg.get("max_events", 10)
    min_events = extraction_cfg.get("min_events", 3)
    gap_keywords = extraction_cfg.get("gap_keywords", ["尝到", "味道", "活在当下", "觉醒"])
    conflicts = []

    # 1. 检查事件ID是否已存在
    for ev in extracted.get("events", []):
        if kg.event_exists(ev["id"]):
            conflicts.append({
                "type": "事件ID重复",
                "detail": f"{ev['id']} '{ev.get('title', '')}' 已存在于图谱中",
                "severity": "high",
                "resolution": "跳过（已有数据）"
            })

    # 2. 检查地点是否匹配已有地点
    existing_locs = kg.get_all_location_names()

    for rel in extracted.get("event_relations", []):
        loc = rel.get("location")
        if loc and loc not in existing_locs:
            new_locs = {l["name"] for l in extracted.get("new_locations", [])}
            if loc not in new_locs:
                conflicts.append({
                    "type": "地点未注册",
                    "detail": f"事件 {rel['event_id']} 引用了地点 '{loc}'，该地点不在图谱中且未声明为新地点",
                    "severity": "medium",
                    "resolution": "补充为新地点，或映射到已有地点"
                })

    # 3. 检查人物是否在图谱中
    existing_chars = kg.get_all_character_names()

    # new_characters 中声明的人物视为已知
    declared_chars = {c["name"] for c in extracted.get("new_characters", [])}

    for rel in extracted.get("event_relations", []):
        char = rel.get("character")
        if char and char not in existing_chars and char not in declared_chars:
            conflicts.append({
                "type": "人物未注册",
                "detail": f"事件 {rel['event_id']} 引用了人物 '{char}'，该人物不在图谱中且未声明为新人物",
                "severity": "high",
                "resolution": "在 new_characters 中添加该人物，或确认名字拼写"
            })

    for cu in extracted.get("character_updates", []):
        if cu["name"] not in existing_chars:
            conflicts.append({
                "type": "人物更新目标不存在",
                "detail": f"character_updates 中引用了 '{cu['name']}'，该人物不在图谱中",
                "severity": "high",
                "resolution": "确认人物名是否正确"
            })

    # 4. 检查事件粒度（每章建议5-8个）
    event_count = len(extracted.get("events", []))
    if event_count > max_events:
        conflicts.append({
            "type": "事件过多",
            "detail": f"本章提取了{event_count}个事件，建议5-8个。过多会导致图谱臃肿",
            "severity": "low",
            "resolution": "合并同场景的子事件"
        })
    elif event_count < min_events:
        conflicts.append({
            "type": "事件过少",
            "detail": f"本章只提取了{event_count}个事件，可能遗漏了重要场景",
            "severity": "medium",
            "resolution": "检查是否遗漏了关键场景"
        })

    # 5. 检查间隙标记合理性
    gap_events = [e for e in extracted.get("events", []) if e.get("is_gap")]
    for ge in gap_events:
        detail = ge.get("detail", "")
        title = ge.get("title", "")
        if any(kw in detail for kw in gap_keywords) and "滑出" not in detail and "飘" not in detail:
            conflicts.append({
                "type": "间隙误判",
                "detail": f"'{title}' 可能不是间隙体验（意识滑出身体），而是日常觉醒或情感变化",
                "severity": "medium",
                "resolution": "确认is_gap是否应为false"
            })

    return conflicts


def write_extraction_to_graph(kg, chapter, extracted, skip_conflicts=True, project=None):
    """将提取结果写入图谱（冲突项可跳过）"""
    cfg = config_loader.load(project) if project else None
    suspense_cfg = (cfg or {}).get("suspense", {})
    budget_base = suspense_cfg.get("budget_base", 8)
    budget_multiplier = suspense_cfg.get("budget_multiplier", 1.5)
    extracted, name_fixes = normalize_characters(kg, extracted)
    if name_fixes:
        print(f"  人名规范化: {', '.join(name_fixes)}")

    conflicts = detect_conflicts(kg, extracted, project=project)
    stats = {"events": 0, "relations": 0, "locations": 0, "conflicts": len(conflicts)}

    conflict_event_ids = set()
    if skip_conflicts:
        for c in conflicts:
            if c["type"] == "事件ID重复" and "E" in c["detail"]:
                eid = c["detail"].split(" ")[0]
                conflict_event_ids.add(eid)

    time_period = get_chapter_time_period(kg, chapter)

    # 1. 写入事件（跳过冲突的）
    for ev in extracted.get("events", []):
        if ev["id"] in conflict_event_ids:
            continue
        kg.add_event(ev["id"], **{k: v for k, v in ev.items() if k != "id"})
        stats["events"] += 1
        if time_period:
            kg.add_relation("Event", "id", ev["id"], "HAPPENS_IN",
                           "TimePeriod", "label", time_period)

    # 2. 写入事件关系
    for rel in extracted.get("event_relations", []):
        eid = rel["event_id"]
        if eid in conflict_event_ids:
            continue
        if "character" in rel:
            kg.add_relation("Event", "id", eid, "INVOLVES",
                           "Character", "name", rel["character"])
            stats["relations"] += 1
        if "location" in rel:
            kg.add_relation("Event", "id", eid, "OCCURS_AT",
                           "Location", "name", rel["location"])
            stats["relations"] += 1

    # 3. 事件前驱关系
    events = [e for e in extracted.get("events", []) if e["id"] not in conflict_event_ids]
    for i in range(1, len(events)):
        kg.add_relation("Event", "id", events[i-1]["id"], "PRECEDES",
                       "Event", "id", events[i]["id"])

    # 4. 新地点
    for loc in extracted.get("new_locations", []):
        kg.add_location(loc["name"],
                       type=loc.get("type", ""),
                       description=loc.get("description", ""))
        stats["locations"] += 1

    # 5. 新人物
    for char in extracted.get("new_characters", []):
        kg.add_character(char["name"],
                        role=char.get("role", ""),
                        personality=char.get("personality", ""))
        stats.setdefault("characters", 0)
        stats["characters"] += 1

    # 6. 收集不写入图谱的信息（供作者审核）
    char_updates = extracted.get("character_updates", [])
    motif_mentions = extracted.get("motif_mentions", [])
    notes = extracted.get("notes", "")

    # 7. 悬念线状态更新
    for tu in extracted.get("thread_updates", []):
        tid = tu.get("thread_id")
        new_status = tu.get("new_status")
        if tid and new_status:
            update_props = {"status": new_status}
            if new_status == "resolved":
                update_props["resolved_chapter"] = chapter
            kg.update_suspense_thread(tid, **update_props)
            stats.setdefault("thread_updates", 0)
            stats["thread_updates"] += 1

    # 8. 新悬念线（含预算控制）
    current_threads = kg.stats()["suspense_threads"]
    # 动态预算：max(base, chapter * multiplier)
    max_threads = max(budget_base, int(chapter * budget_multiplier))
    thread_idx = 0
    skipped_threads = []
    for nt in extracted.get("new_threads", []):
        importance = nt.get("importance", "medium")
        if current_threads >= max_threads and importance != "high":
            skipped_threads.append(nt.get("content", ""))
            continue
        thread_idx += 1
        tid = f"ST{chapter:02d}_{thread_idx:02d}"
        kg.add_suspense_thread(
            tid,
            content=nt.get("content", ""),
            planted_chapter=chapter,
            importance=nt.get("importance", "medium"),
            thread_type=nt.get("thread_type", "foreshadowing"),
            status="planted"
        )
        if nt.get("planted_event_id"):
            kg.add_relation("SuspenseThread", "id", tid, "PLANTED_IN",
                           "Event", "id", nt["planted_event_id"])
        stats.setdefault("new_threads", 0)
        stats["new_threads"] += 1
        current_threads += 1

    # 9. 因果链
    for cl in extracted.get("causal_links", []):
        from_eid = cl.get("from")
        to_eid = cl.get("to")
        causal_type = cl.get("type", "consequence")
        if from_eid and to_eid and from_eid not in conflict_event_ids and to_eid not in conflict_event_ids:
            kg.add_relation("Event", "id", from_eid, "CAUSES",
                           "Event", "id", to_eid,
                           causal_type=causal_type,
                           detail=cl.get("detail", ""))
            stats.setdefault("causal_links", 0)
            stats["causal_links"] += 1

    # 10. 证据链
    for el in extracted.get("evidence_links", []):
        eid = el.get("event_id")
        tid = el.get("thread_id")
        ev_type = el.get("type", "clue")
        if eid and tid and eid not in conflict_event_ids:
            kg.add_relation("Event", "id", eid, "EVIDENCES",
                           "SuspenseThread", "id", tid,
                           evidence_type=ev_type,
                           detail=el.get("detail", ""))
            stats.setdefault("evidence_links", 0)
            stats["evidence_links"] += 1

    # 11. 角色目标
    for cg in extracted.get("character_goals", []):
        char_name = cg.get("character")
        if char_name and cg.get("goal"):
            kg.add_character_goal(char_name,
                                  goal=cg["goal"],
                                  goal_type=cg.get("type", "pursue"),
                                  status=cg.get("status", "new"),
                                  chapter=chapter)
            stats.setdefault("character_goals", 0)
            stats["character_goals"] += 1

    report = {
        "chapter": chapter,
        "stats": stats,
        "conflicts": conflicts,
        "character_updates": char_updates,
        "motif_mentions": motif_mentions,
        "notes": notes,
        "thread_updates": extracted.get("thread_updates", []),
        "new_threads": extracted.get("new_threads", []),
        "skipped_threads": skipped_threads,
        "causal_links": extracted.get("causal_links", []),
        "evidence_links": extracted.get("evidence_links", []),
        "character_goals": extracted.get("character_goals", []),
    }

    return report


def clear_chapter_data(kg, chapter):
    """清除图谱中指定章节的数据"""
    kg.delete_events_by_chapter(chapter)
    print(f"[DB] 已清除第{chapter}章的事件数据")


if __name__ == "__main__":
    print("提取管线。使用 main.py 中的闭环流程调用，或手动调用 build_extraction_prompt() 获取prompt后粘贴LLM回复。")
