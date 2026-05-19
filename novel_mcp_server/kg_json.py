"""
JSON 文件后端 — NovelKG 接口的纯 Python 实现。

零依赖、零外部服务。数据存储在 novel_kg_mvp/projects/<project>/graph.json。
Neo4j 的独有增强功能（多跳遍历、中心度分析等）在此后端中不可用，
返回空结果或 raise NotImplementedError。
"""

import json
import os
from copy import deepcopy


def _empty_graph():
    """创建空图谱结构"""
    return {
        "characters": {},      # key: name
        "locations": {},       # key: name
        "events": {},          # key: id
        "themes": {},          # key: name
        "style_guides": {},    # key: id
        "motifs": {},          # key: name
        "chapter_arcs": {},    # key: str(chapter)
        "suspense_threads": {},# key: id
        "outline_entries": {}, # key: str(chapter)
        "time_periods": {},    # key: label
        "relations": [],       # list of dicts
    }


class JsonKG:
    """JSON 文件存储的图谱后端。

    接口与 NovelKG (graph.py) 保持一致，使 core.py / mine.py
    可以透明切换后端。
    """

    def __init__(self, project="default", data_dir=None):
        self.project = project
        if data_dir is None:
            # 默认：novel_kg_mvp/projects/
            _here = os.path.dirname(os.path.abspath(__file__))
            data_dir = os.path.normpath(
                os.path.join(_here, '..', 'novel_kg_mvp', 'projects'))
        self.data_dir = data_dir
        self._graph = None
        self._load()

    # ================================================================
    # 内部：文件读写
    # ================================================================

    @property
    def _path(self):
        return os.path.join(self.data_dir, self.project, "graph.json")

    def _load(self):
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                self._graph = json.load(f)
            # 补齐可能缺失的键（向后兼容）
            empty = _empty_graph()
            for k, v in empty.items():
                self._graph.setdefault(k, v if not isinstance(v, dict) else {})
        else:
            self._graph = _empty_graph()
            self._save()

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._graph, f, ensure_ascii=False, indent=2)

    def close(self):
        self._save()

    # ================================================================
    # 内部：关系查询辅助
    # ================================================================

    def _find_related(self, from_label, from_key, from_val, rel_type=None):
        """查找从指定节点出发的关系，返回 (rel_type, to_label, to_key, to_val) 列表"""
        results = []
        for r in self._graph["relations"]:
            if (r["fl"] == from_label and r["fk"] == from_key
                    and r["fv"] == from_val):
                if rel_type is None or r["rt"] == rel_type:
                    results.append(r)
        return results

    def _add_rel_unique(self, rel):
        """添加关系（去重）"""
        for existing in self._graph["relations"]:
            if (existing["fl"] == rel["fl"] and existing["fk"] == rel["fk"]
                    and existing["fv"] == rel["fv"]
                    and existing["rt"] == rel["rt"]
                    and existing["tl"] == rel["tl"]
                    and existing["tk"] == rel["tk"]
                    and existing["tv"] == rel["tv"]):
                return  # 已存在
        self._graph["relations"].append(rel)

    # ================================================================
    # Schema & 清理
    # ================================================================

    def init_schema(self):
        """JSON 后端无需 schema 初始化（兼容接口）"""
        pass

    def clear_all(self):
        """清空所有项目数据"""
        self._graph = _empty_graph()
        self._save()

    def clear_project(self):
        """清空当前项目数据"""
        self._graph = _empty_graph()
        self._save()

    # ================================================================
    # 节点写入
    # ================================================================

    def add_character(self, name, **props):
        props["name"] = name
        self._graph["characters"][name] = props
        self._save()

    def add_location(self, name, **props):
        props["name"] = name
        self._graph["locations"][name] = props
        self._save()

    def add_time_period(self, label, **props):
        props["label"] = label
        self._graph["time_periods"][label] = props
        self._save()

    def add_event(self, event_id, **props):
        props["id"] = event_id
        self._graph["events"][event_id] = props
        self._save()

    def add_theme(self, name, **props):
        props["name"] = name
        self._graph["themes"][name] = props
        self._save()

    def add_style_guide(self, guide_id, **props):
        props["id"] = guide_id
        self._graph["style_guides"][guide_id] = props
        self._save()

    def add_motif(self, name, **props):
        props["name"] = name
        self._graph["motifs"][name] = props
        self._save()

    def add_chapter_arc(self, chapter, **props):
        props["chapter"] = chapter
        self._graph["chapter_arcs"][str(chapter)] = props
        self._save()

    def add_suspense_thread(self, thread_id, **props):
        props["id"] = thread_id
        self._graph["suspense_threads"][thread_id] = props
        self._save()

    def update_suspense_thread(self, thread_id, **props):
        if thread_id in self._graph["suspense_threads"]:
            self._graph["suspense_threads"][thread_id].update(props)
        else:
            props["id"] = thread_id
            self._graph["suspense_threads"][thread_id] = props
        self._save()

    def add_outline_entry(self, chapter, **props):
        props["chapter"] = chapter
        self._graph["outline_entries"][str(chapter)] = props
        self._save()

    def add_character_goal(self, character_name, goal, goal_type="pursue",
                           status="new", chapter=0):
        """为角色追加目标到 goals 列表"""
        char = self._graph["characters"].get(character_name)
        if char is None:
            return
        if "goals" not in char:
            char["goals"] = []
        char["goals"].append({
            "goal": goal, "type": goal_type,
            "status": status, "chapter": chapter
        })
        self._save()

    def add_relation(self, from_label, from_key, from_val,
                     rel_type, to_label, to_key, to_val, **props):
        rel = {
            "fl": from_label, "fk": from_key, "fv": from_val,
            "rt": rel_type,
            "tl": to_label, "tk": to_key, "tv": to_val,
        }
        rel.update(props)
        self._add_rel_unique(rel)
        self._save()

    # ================================================================
    # 查询：简单
    # ================================================================

    def get_all_character_names(self):
        return set(self._graph["characters"].keys())

    def get_all_location_names(self):
        return set(self._graph["locations"].keys())

    def event_exists(self, event_id):
        return event_id in self._graph["events"]

    def get_chapter_time_period(self, chapter):
        for tp in self._graph["time_periods"].values():
            if (tp.get("chapter_start", 0) <= chapter
                    <= tp.get("chapter_end", 0)):
                return tp["label"]
        return None

    def delete_events_by_chapter(self, chapter):
        # 找出要删除的事件ID
        to_delete = [eid for eid, ev in self._graph["events"].items()
                     if ev.get("chapter") == chapter]
        # 删除事件
        for eid in to_delete:
            del self._graph["events"][eid]
        # 删除关联关系
        self._graph["relations"] = [
            r for r in self._graph["relations"]
            if not (r["fl"] == "Event" and r["fk"] == "id"
                    and r["fv"] in to_delete)
            and not (r["tl"] == "Event" and r["tk"] == "id"
                     and r["tv"] in to_delete)
        ]
        self._save()

    def get_all_characters(self):
        return [deepcopy(v) for v in self._graph["characters"].values()]

    def get_events_by_chapter(self, chapter):
        return [deepcopy(v) for v in self._graph["events"].values()
                if v.get("chapter") == chapter]

    def get_unresolved_threads(self, chapter):
        return [
            deepcopy(v) for v in self._graph["suspense_threads"].values()
            if v.get("status") not in ("resolved", "abandoned")
            and v.get("planted_chapter", 999) < chapter
        ]

    def get_all_threads(self):
        return sorted(
            [deepcopy(v) for v in self._graph["suspense_threads"].values()],
            key=lambda t: (t.get("planted_chapter", 0), t.get("id", ""))
        )

    def get_outline_entry(self, chapter):
        entry = self._graph["outline_entries"].get(str(chapter))
        return deepcopy(entry) if entry else None

    # ================================================================
    # 查询：复合
    # ================================================================

    def get_context_for_chapter(self, chapter):
        prev_ch = max(chapter - 1, 1)

        # 前一章事件
        prev_events = self.get_events_by_chapter(prev_ch)

        # 通过关系找当前章和前一章涉及的人物
        event_ids = set()
        for ev in self._graph["events"].values():
            if ev.get("chapter") in (chapter, prev_ch):
                event_ids.add(ev["id"])

        char_names = set()
        loc_names = set()
        for r in self._graph["relations"]:
            if (r["fl"] == "Event" and r["fk"] == "id"
                    and r["fv"] in event_ids):
                if r["rt"] == "INVOLVES" and r["tl"] == "Character":
                    char_names.add(r["tv"])
                if r["rt"] == "OCCURS_AT" and r["tl"] == "Location":
                    loc_names.add(r["tv"])

        characters = [deepcopy(self._graph["characters"][n])
                      for n in sorted(char_names)
                      if n in self._graph["characters"]]
        locations = [deepcopy(self._graph["locations"][n])
                     for n in sorted(loc_names)
                     if n in self._graph["locations"]]

        # 时间段
        time_periods = [deepcopy(v) for v in self._graph["time_periods"].values()
                        if v.get("chapter_start", 0) <= chapter
                        <= v.get("chapter_end", 9999)]

        # 全局数据
        themes = [deepcopy(v) for v in self._graph["themes"].values()]
        style_guides = [deepcopy(v) for v in self._graph["style_guides"].values()]
        motifs = [deepcopy(v) for v in self._graph["motifs"].values()]

        # 章节弧线
        arc = self._graph["chapter_arcs"].get(str(chapter))
        chapter_arc = [deepcopy(arc)] if arc else []

        # 因果链（前一章事件间的CAUSES关系）
        prev_event_ids = {e["id"] for e in prev_events}
        causal_links = [
            {"from": r["fv"], "to": r["tv"],
             "type": r.get("causal_type", ""), "detail": r.get("detail", "")}
            for r in self._graph["relations"]
            if r["rt"] == "CAUSES"
            and r["fv"] in prev_event_ids or r["tv"] in prev_event_ids
        ]

        # 证据链（未解决悬念线的已有证据）
        unresolved_ids = {t["id"] for t in self.get_unresolved_threads(chapter)}
        evidence_links = [
            {"event_id": r["fv"], "thread_id": r["tv"],
             "type": r.get("evidence_type", ""), "detail": r.get("detail", "")}
            for r in self._graph["relations"]
            if r["rt"] == "EVIDENCES" and r["tv"] in unresolved_ids
        ]

        return {
            "time_periods": time_periods,
            "prev_events": prev_events,
            "characters": characters,
            "locations": locations,
            "themes": themes,
            "style_guides": style_guides,
            "motifs": motifs,
            "chapter_arc": chapter_arc,
            "suspense_threads": self.get_unresolved_threads(chapter),
            "outline_entry": self.get_outline_entry(chapter),
            "causal_links": causal_links,
            "evidence_links": evidence_links,
        }

    def get_arc_derivation_context(self, chapter, lookback=3):
        start_ch = max(1, chapter - lookback)

        # 近N章弧线
        arcs = sorted(
            [deepcopy(v) for v in self._graph["chapter_arcs"].values()
             if start_ch <= v.get("chapter", 0) < chapter],
            key=lambda a: a.get("chapter", 0)
        )

        # 近N章事件
        events = sorted(
            [deepcopy(v) for v in self._graph["events"].values()
             if start_ch <= v.get("chapter", 0) < chapter],
            key=lambda e: (e.get("chapter", 0), e.get("id", ""))
        )

        # 近N章涉及的人物
        event_ids = {e["id"] for e in events}
        char_names = set()
        for r in self._graph["relations"]:
            if (r["fl"] == "Event" and r["fk"] == "id"
                    and r["fv"] in event_ids
                    and r["rt"] == "INVOLVES"
                    and r["tl"] == "Character"):
                char_names.add(r["tv"])
        characters = [deepcopy(self._graph["characters"][n])
                      for n in sorted(char_names)
                      if n in self._graph["characters"]]

        # 最后一个事件
        all_prev = sorted(
            [v for v in self._graph["events"].values()
             if v.get("chapter", 0) < chapter],
            key=lambda e: (e.get("chapter", 0), e.get("id", ""))
        )
        last_event = deepcopy(all_prev[-1]) if all_prev else None

        return {
            "recent_arcs": arcs,
            "recent_events": events,
            "characters": characters,
            "themes": [deepcopy(v) for v in self._graph["themes"].values()],
            "motifs": [deepcopy(v) for v in self._graph["motifs"].values()],
            "last_event": last_event,
            "outline_entry": self.get_outline_entry(chapter),
            "suspense_threads": self.get_unresolved_threads(chapter),
        }

    # ================================================================
    # 一致性检查
    # ================================================================

    def check_consistency(self):
        issues = []

        # 1. 人物时空矛盾
        events = self._graph["events"]
        for eid, ev in events.items():
            locs_for_event = set()
            for r in self._graph["relations"]:
                if (r["fl"] == "Event" and r["fk"] == "id"
                        and r["fv"] == eid and r["rt"] == "OCCURS_AT"):
                    locs_for_event.add(r["tv"])
            if len(locs_for_event) > 1:
                issues.append({
                    "type": "事件多处",
                    "detail": f"事件 {eid} 关联了多个地点: {locs_for_event}",
                    "severity": "low"
                })

        # 2. 悬念线悬而未决
        max_ch = max(
            (ev.get("chapter", 0) for ev in events.values()), default=0)
        for tid, t in self._graph["suspense_threads"].items():
            if t.get("status") not in ("resolved", "abandoned"):
                gap = max_ch - t.get("planted_chapter", 0)
                if gap >= 3 and t.get("importance") == "high":
                    issues.append({
                        "type": "悬念线悬而未决",
                        "detail": f"高重要度线程 {tid} ('{t.get('content', '')[:30]}') 已种植{gap}章未解决",
                        "severity": "medium"
                    })

        # 3. 因果断裂检测：事件没有因果入边（除了每章第一个事件）
        events_by_ch = {}
        for eid, ev in events.items():
            ch = ev.get("chapter", 0)
            events_by_ch.setdefault(ch, []).append(eid)
        causal_targets = {r["tv"] for r in self._graph["relations"] if r["rt"] == "CAUSES"}
        for ch in sorted(events_by_ch.keys()):
            ch_events = sorted(events_by_ch[ch])
            for eid in ch_events[1:]:  # 跳过每章第一个事件
                if eid not in causal_targets:
                    issues.append({
                        "type": "因果断裂",
                        "detail": f"事件 {eid} 没有因果前置（第{ch}章非首事件），情节可能缺乏驱动力",
                        "severity": "medium"
                    })

        # 4. 证据缺失检测：已解决的悬念线没有EVIDENCES关系
        for tid, t in self._graph["suspense_threads"].items():
            if t.get("status") == "resolved":
                has_evidence = any(
                    r["rt"] == "EVIDENCES" and r["tv"] == tid
                    for r in self._graph["relations"]
                )
                if not has_evidence:
                    issues.append({
                        "type": "证据缺失",
                        "detail": f"悬念线 {tid} ('{t.get('content', '')[:30]}') 已解决但无证据链支撑，解决方案可能缺乏说服力",
                        "severity": "high"
                    })

        return issues

    # ================================================================
    # 统计
    # ================================================================

    def stats(self):
        p = self.project
        # 统计同项目内的关系数
        node_keys = {
            "Character": set(self._graph["characters"].keys()),
            "Location": set(self._graph["locations"].keys()),
            "Event": set(self._graph["events"].keys()),
            "Theme": set(self._graph["themes"].keys()),
            "StyleGuide": set(self._graph["style_guides"].keys()),
            "Motif": set(self._graph["motifs"].keys()),
            "ChapterArc": set(self._graph["chapter_arcs"].keys()),
            "SuspenseThread": set(self._graph["suspense_threads"].keys()),
            "OutlineEntry": set(self._graph["outline_entries"].keys()),
            "TimePeriod": set(self._graph["time_periods"].keys()),
        }
        rel_count = len(self._graph["relations"])

        return {
            "project": p,
            "characters": len(self._graph["characters"]),
            "locations": len(self._graph["locations"]),
            "events": len(self._graph["events"]),
            "themes": len(self._graph["themes"]),
            "style_guides": len(self._graph["style_guides"]),
            "motifs": len(self._graph["motifs"]),
            "chapter_arcs": len(self._graph["chapter_arcs"]),
            "suspense_threads": len(self._graph["suspense_threads"]),
            "outline_entries": len(self._graph["outline_entries"]),
            "relationships": rel_count,
            "backend": "json",
        }
