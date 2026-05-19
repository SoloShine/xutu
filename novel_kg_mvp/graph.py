"""
Novel Knowledge Graph MVP
知识图谱客户端 - Neo4j连接、Schema初始化、CRUD操作
支持项目级隔离：所有节点带 project 属性，查询自动过滤
"""

from neo4j import GraphDatabase
import yaml


def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class NovelKG:
    def __init__(self, project="default", uri=None, user=None, password=None):
        cfg = load_config()
        self.project = project
        self.uri = uri or cfg["NEO4J_URI"]
        self.user = user or cfg["NEO4J_USER"]
        self.password = password or cfg["NEO4J_PASSWORD"]
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self):
        self.driver.close()

    def clear_all(self):
        """清空整个数据库（所有项目）"""
        with self.driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n")
        print("[DB] 已清空所有数据（含所有项目）")

    def clear_project(self):
        """只清空当前项目的数据"""
        with self.driver.session() as s:
            s.run(
                "MATCH (n) WHERE n.project = $project DETACH DELETE n",
                project=self.project
            )
        print(f"[DB] 已清空项目 '{self.project}' 的所有数据")

    def init_schema(self):
        """创建复合唯一约束（project + 业务键）"""
        with self.driver.session() as s:
            # 查询并删除所有旧的单属性唯一约束
            existing = s.run("SHOW CONSTRAINTS").data()
            for c in existing:
                if (c.get("type") == "UNIQUENESS"
                    and "project" not in str(c.get("properties", []))):
                    name = c.get("name", "")
                    if name:
                        s.run(f"DROP CONSTRAINT {name} IF EXISTS")

            # 新的复合唯一约束
            constraints = [
                "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Character) REQUIRE (c.project, c.name) IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (l:Location) REQUIRE (l.project, l.name) IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (t:TimePeriod) REQUIRE (t.project, t.label) IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Event) REQUIRE (e.project, e.id) IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (th:Theme) REQUIRE (th.project, th.name) IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (sg:StyleGuide) REQUIRE (sg.project, sg.id) IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Motif) REQUIRE (m.project, m.name) IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (ca:ChapterArc) REQUIRE (ca.project, ca.chapter) IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (st:SuspenseThread) REQUIRE (st.project, st.id) IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (oe:OutlineEntry) REQUIRE (oe.project, oe.chapter) IS UNIQUE",
            ]
            for c in constraints:
                s.run(c)
        print("[DB] Schema初始化完成")

    # ========== 节点操作 ==========

    def add_character(self, name, **props):
        props["name"] = name
        props["project"] = self.project
        with self.driver.session() as s:
            s.run(
                "MERGE (c:Character {project: $project, name: $name}) SET c += $props",
                project=self.project, name=name, props=props
            )

    def add_location(self, name, **props):
        props["name"] = name
        props["project"] = self.project
        with self.driver.session() as s:
            s.run(
                "MERGE (l:Location {project: $project, name: $name}) SET l += $props",
                project=self.project, name=name, props=props
            )

    def add_time_period(self, name, **props):
        props["label"] = name
        props["project"] = self.project
        with self.driver.session() as s:
            s.run(
                "MERGE (t:TimePeriod {project: $project, label: $label}) SET t += $props",
                project=self.project, label=name, props=props
            )

    def add_event(self, event_id, **props):
        props["id"] = event_id
        props["project"] = self.project
        with self.driver.session() as s:
            s.run(
                "MERGE (e:Event {project: $project, id: $id}) SET e += $props",
                project=self.project, id=event_id, props=props
            )

    def add_theme(self, name, **props):
        props["name"] = name
        props["project"] = self.project
        with self.driver.session() as s:
            s.run(
                "MERGE (th:Theme {project: $project, name: $name}) SET th += $props",
                project=self.project, name=name, props=props
            )

    def add_style_guide(self, guide_id, **props):
        props["id"] = guide_id
        props["project"] = self.project
        with self.driver.session() as s:
            s.run(
                "MERGE (sg:StyleGuide {project: $project, id: $id}) SET sg += $props",
                project=self.project, id=guide_id, props=props
            )

    def add_motif(self, name, **props):
        props["name"] = name
        props["project"] = self.project
        with self.driver.session() as s:
            s.run(
                "MERGE (m:Motif {project: $project, name: $name}) SET m += $props",
                project=self.project, name=name, props=props
            )

    def add_chapter_arc(self, chapter, **props):
        props["chapter"] = chapter
        props["project"] = self.project
        with self.driver.session() as s:
            s.run(
                "MERGE (ca:ChapterArc {project: $project, chapter: $ch}) SET ca += $props",
                project=self.project, ch=chapter, props=props
            )

    def add_suspense_thread(self, thread_id, **props):
        props["id"] = thread_id
        props["project"] = self.project
        with self.driver.session() as s:
            s.run(
                "MERGE (st:SuspenseThread {project: $project, id: $id}) SET st += $props",
                project=self.project, id=thread_id, props=props
            )

    def update_suspense_thread(self, thread_id, **props):
        """更新悬念线属性（MERGE语义）"""
        self.add_suspense_thread(thread_id, **props)

    def add_outline_entry(self, chapter, **props):
        props["chapter"] = chapter
        props["project"] = self.project
        with self.driver.session() as s:
            s.run(
                "MERGE (oe:OutlineEntry {project: $project, chapter: $ch}) SET oe += $props",
                project=self.project, ch=chapter, props=props
            )

    # ========== 关系操作 ==========

    def add_relation(self, from_label, from_key, from_val, rel_type, to_label, to_key, to_val, **props):
        with self.driver.session() as s:
            s.run(
                f"MATCH (a:{from_label} {{project: $project, {from_key}: $fv}}) "
                f"MATCH (b:{to_label} {{project: $project, {to_key}: $tv}}) "
                f"MERGE (a)-[r:{rel_type}]->(b) SET r += $props",
                project=self.project, fv=from_val, tv=to_val, props=props
            )

    # ========== 查询操作 ==========

    def get_all_character_names(self):
        """获取所有人物名集合"""
        with self.driver.session() as s:
            result = s.run(
                "MATCH (c:Character {project: $p}) RETURN c.name AS name",
                p=self.project
            )
            return {r["name"] for r in result}

    def get_all_location_names(self):
        """获取所有地点名集合"""
        with self.driver.session() as s:
            result = s.run(
                "MATCH (l:Location {project: $p}) RETURN l.name AS name",
                p=self.project
            )
            return {r["name"] for r in result}

    def event_exists(self, event_id):
        """检查事件ID是否已存在"""
        with self.driver.session() as s:
            result = s.run(
                "MATCH (e:Event {project: $p, id: $id}) RETURN e.id",
                p=self.project, id=event_id
            )
            return result.single() is not None

    def get_chapter_time_period(self, chapter):
        """获取章节对应的时间段标签"""
        with self.driver.session() as s:
            result = s.run(
                "MATCH (t:TimePeriod {project: $p}) "
                "WHERE t.chapter_start <= $ch AND t.chapter_end >= $ch "
                "RETURN t.label AS label",
                p=self.project, ch=chapter
            )
            records = [r["label"] for r in result]
            return records[0] if records else None

    def delete_events_by_chapter(self, chapter):
        """删除指定章节的所有事件及其关系"""
        with self.driver.session() as s:
            s.run(
                "MATCH (e:Event {project: $p}) WHERE e.chapter = $ch "
                "DETACH DELETE e",
                p=self.project, ch=chapter
            )

    def get_all_characters(self):
        with self.driver.session() as s:
            result = s.run(
                "MATCH (c:Character {project: $project}) RETURN c",
                project=self.project
            )
            return [dict(r["c"]) for r in result]

    def get_events_by_chapter(self, chapter):
        with self.driver.session() as s:
            result = s.run(
                "MATCH (e:Event {project: $project}) WHERE e.chapter = $ch RETURN e ORDER BY e.id",
                project=self.project, ch=chapter
            )
            return [dict(r["e"]) for r in result]

    def get_unresolved_threads(self, chapter):
        """获取到第N章时仍未解决的悬念线"""
        p = self.project
        with self.driver.session() as s:
            result = s.run(
                "MATCH (st:SuspenseThread {project: $p}) "
                "WHERE st.status <> 'resolved' AND st.status <> 'abandoned' "
                "AND st.planted_chapter < $ch "
                "RETURN st ORDER BY st.importance DESC, st.planted_chapter ASC",
                p=p, ch=chapter
            )
            return [dict(r["st"]) for r in result]

    def get_all_threads(self):
        """获取项目中所有悬念线（用于审计）"""
        p = self.project
        with self.driver.session() as s:
            result = s.run(
                "MATCH (st:SuspenseThread {project: $p}) "
                "RETURN st ORDER BY st.planted_chapter, st.id",
                p=p
            )
            return [dict(r["st"]) for r in result]

    def get_outline_entry(self, chapter):
        """获取第N章的大纲条目"""
        p = self.project
        with self.driver.session() as s:
            result = s.run(
                "MATCH (oe:OutlineEntry {project: $p, chapter: $ch}) RETURN oe",
                p=p, ch=chapter
            )
            entries = [dict(r["oe"]) for r in result]
            return entries[0] if entries else None

    def get_context_for_chapter(self, chapter):
        """获取写第N章时需要的所有图谱上下文"""
        p = self.project
        with self.driver.session() as s:
            # 当前时间段
            time_result = s.run(
                "MATCH (t:TimePeriod {project: $p}) "
                "WHERE t.chapter_start <= $ch AND t.chapter_end >= $ch RETURN t",
                p=p, ch=chapter
            )
            time_periods = [dict(r["t"]) for r in time_result]

            # 前一章的事件
            prev_events_result = s.run(
                "MATCH (e:Event {project: $p}) WHERE e.chapter = $prev_ch RETURN e ORDER BY e.id",
                p=p, prev_ch=chapter - 1
            )
            prev_events = [dict(r["e"]) for r in prev_events_result]

            # 当前章节涉及的人物
            characters_result = s.run(
                "MATCH (e:Event {project: $p})-[:INVOLVES]->(c:Character {project: $p}) "
                "WHERE e.chapter = $ch OR e.chapter = $prev_ch "
                "WITH DISTINCT c ORDER BY c.name RETURN c",
                p=p, ch=chapter, prev_ch=max(chapter - 1, 1)
            )
            characters = [dict(r["c"]) for r in characters_result]

            # 核心地点
            locations_result = s.run(
                "MATCH (e:Event {project: $p})-[:OCCURS_AT]->(l:Location {project: $p}) "
                "WHERE e.chapter = $ch OR e.chapter = $prev_ch "
                "WITH DISTINCT l ORDER BY l.name RETURN l",
                p=p, ch=chapter, prev_ch=max(chapter - 1, 1)
            )
            locations = [dict(r["l"]) for r in locations_result]

            # 主题线
            themes_result = s.run(
                "MATCH (th:Theme {project: $p}) RETURN th",
                p=p
            )
            themes = [dict(r["th"]) for r in themes_result]

            # 风格指南
            style_result = s.run(
                "MATCH (sg:StyleGuide {project: $p}) RETURN sg",
                p=p
            )
            style_guides = [dict(r["sg"]) for r in style_result]

            # 核心意象
            motifs_result = s.run(
                "MATCH (m:Motif {project: $p}) RETURN m",
                p=p
            )
            motifs = [dict(r["m"]) for r in motifs_result]

            # 当前章节情节弧线
            arc_result = s.run(
                "MATCH (ca:ChapterArc {project: $p}) WHERE ca.chapter = $ch RETURN ca",
                p=p, ch=chapter
            )
            chapter_arc = [dict(r["ca"]) for r in arc_result]

            # 悬念线（到本章仍未解决的）
            suspense_threads = self.get_unresolved_threads(chapter)

            # 大纲条目（硬约束）
            outline_entry = self.get_outline_entry(chapter)

            return {
                "time_periods": time_periods,
                "prev_events": prev_events,
                "characters": characters,
                "locations": locations,
                "themes": themes,
                "style_guides": style_guides,
                "motifs": motifs,
                "chapter_arc": chapter_arc,
                "suspense_threads": suspense_threads,
                "outline_entry": outline_entry,
            }

    def get_arc_derivation_context(self, chapter, lookback=3):
        """获取推演新章节ChapterArc所需的上下文"""
        start_ch = max(1, chapter - lookback)
        p = self.project
        with self.driver.session() as s:
            # 近N章的ChapterArc
            arcs_result = s.run(
                "MATCH (ca:ChapterArc {project: $p}) "
                "WHERE ca.chapter >= $start AND ca.chapter < $ch "
                "RETURN ca ORDER BY ca.chapter",
                p=p, start=start_ch, ch=chapter
            )
            arcs = [dict(r["ca"]) for r in arcs_result]

            # 近N章的事件
            events_result = s.run(
                "MATCH (e:Event {project: $p}) "
                "WHERE e.chapter >= $start AND e.chapter < $ch "
                "RETURN e ORDER BY e.chapter, e.id",
                p=p, start=start_ch, ch=chapter
            )
            events = [dict(r["e"]) for r in events_result]

            # 近N章涉及的人物
            chars_result = s.run(
                "MATCH (e:Event {project: $p})-[:INVOLVES]->(c:Character {project: $p}) "
                "WHERE e.chapter >= $start AND e.chapter < $ch "
                "WITH DISTINCT c ORDER BY c.name RETURN c",
                p=p, start=start_ch, ch=chapter
            )
            characters = [dict(r["c"]) for r in chars_result]

            # 主题线
            themes_result = s.run(
                "MATCH (th:Theme {project: $p}) RETURN th",
                p=p
            )
            themes = [dict(r["th"]) for r in themes_result]

            # 核心意象
            motifs_result = s.run(
                "MATCH (m:Motif {project: $p}) RETURN m",
                p=p
            )
            motifs = [dict(r["m"]) for r in motifs_result]

            # 最后一个事件
            last_event_result = s.run(
                "MATCH (e:Event {project: $p}) WHERE e.chapter < $ch "
                "RETURN e ORDER BY e.chapter DESC, e.id DESC LIMIT 1",
                p=p, ch=chapter
            )
            last_event = [dict(r["e"]) for r in last_event_result]

            # 大纲条目（硬约束）
            outline_entry = self.get_outline_entry(chapter)

            # 未解悬念线
            suspense_threads = self.get_unresolved_threads(chapter)

            return {
                "recent_arcs": arcs,
                "recent_events": events,
                "characters": characters,
                "themes": themes,
                "motifs": motifs,
                "last_event": last_event[0] if last_event else None,
                "outline_entry": outline_entry,
                "suspense_threads": suspense_threads,
            }

    def check_consistency(self):
        """运行所有一致性检查，返回问题列表"""
        issues = []
        p = self.project

        with self.driver.session() as s:
            # 检查1: 人物时空矛盾
            result = s.run(
                "MATCH (e:Event {project: $p})-[:INVOLVES]->(c:Character {project: $p}) "
                "MATCH (e)-[:OCCURS_AT]->(l:Location {project: $p}) "
                "MATCH (e)-[:HAPPENS_IN]->(t:TimePeriod {project: $p}) "
                "WHERE c.first_appears > t.chapter_end OR c.last_appears < t.chapter_start "
                "RETURN c.name AS char_name, l.name AS loc_name, t.label AS time_period",
                p=p
            )
            for r in result:
                issues.append({
                    "type": "时空矛盾",
                    "detail": f"{r['char_name']} 在 {r['time_period']} 不应出现在 {r['loc_name']}",
                    "severity": "high"
                })

            # 检查2: 间隙强度递进
            gap_events = s.run(
                "MATCH (e:Event {project: $p}) WHERE e.is_gap = true "
                "RETURN e.chapter AS ch, e.gap_level AS level ORDER BY e.chapter",
                p=p
            )
            gap_sequence = [(r["ch"], r["level"]) for r in gap_events]
            for i in range(1, len(gap_sequence)):
                prev_ch, prev_level = gap_sequence[i - 1]
                curr_ch, curr_level = gap_sequence[i]
                if curr_ch == 9 and curr_level and prev_level and curr_level >= prev_level:
                    issues.append({
                        "type": "间隙强度异常",
                        "detail": f"第{curr_ch}章间隙强度({curr_level})应低于第{prev_ch}章({prev_level})",
                        "severity": "medium"
                    })

            # 检查3: 章节缺失事件（只在有事件存在时检查）
            all_chapters_with_events = s.run(
                "MATCH (e:Event {project: $p}) WHERE e.chapter IS NOT NULL RETURN DISTINCT e.chapter AS ch ORDER BY e.chapter",
                p=p
            )
            chapters_with_events = sorted(r["ch"] for r in all_chapters_with_events)
            if chapters_with_events:
                expected = set(range(chapters_with_events[0], chapters_with_events[-1] + 1))
                actual = set(chapters_with_events)
                for ch in sorted(expected - actual):
                    issues.append({
                        "type": "章节缺失事件",
                        "detail": f"第{ch}章没有提取到任何事件",
                        "severity": "low"
                    })

        return issues

    def check_thread_consistency(self):
        """检查悬念线的一致性：高重要度线程超过3章未解决发出警告"""
        issues = []
        p = self.project
        with self.driver.session() as s:
            max_ch = s.run(
                "MATCH (e:Event {project: $p}) RETURN max(e.chapter) AS m",
                p=p
            ).single()["m"] or 0
            result = s.run(
                "MATCH (st:SuspenseThread {project: $p}) "
                "WHERE st.importance = 'high' AND st.status = 'planted' "
                "RETURN st.id AS id, st.content AS content, st.planted_chapter AS planted",
                p=p
            )
            for r in result:
                gap = max_ch - r["planted"]
                if gap >= 3:
                    issues.append({
                        "type": "悬念线悬而未决",
                        "detail": f"高重要度线程 {r['id']} ('{r['content'][:30]}') 已种植{gap}章未解决",
                        "severity": "medium"
                    })
        return issues

    def stats(self):
        """返回当前项目的图谱统计信息"""
        p = self.project
        with self.driver.session() as s:
            chars = s.run(
                "MATCH (c:Character {project: $p}) RETURN count(c) AS n",
                p=p
            ).single()["n"]
            locs = s.run(
                "MATCH (l:Location {project: $p}) RETURN count(l) AS n",
                p=p
            ).single()["n"]
            events = s.run(
                "MATCH (e:Event {project: $p}) RETURN count(e) AS n",
                p=p
            ).single()["n"]
            themes = s.run(
                "MATCH (th:Theme {project: $p}) RETURN count(th) AS n",
                p=p
            ).single()["n"]
            guides = s.run(
                "MATCH (sg:StyleGuide {project: $p}) RETURN count(sg) AS n",
                p=p
            ).single()["n"]
            motifs_count = s.run(
                "MATCH (m:Motif {project: $p}) RETURN count(m) AS n",
                p=p
            ).single()["n"]
            arcs = s.run(
                "MATCH (ca:ChapterArc {project: $p}) RETURN count(ca) AS n",
                p=p
            ).single()["n"]
            threads = s.run(
                "MATCH (st:SuspenseThread {project: $p}) RETURN count(st) AS n",
                p=p
            ).single()["n"]
            outlines = s.run(
                "MATCH (oe:OutlineEntry {project: $p}) RETURN count(oe) AS n",
                p=p
            ).single()["n"]
            rels = s.run(
                "MATCH (n {project: $p})-[r]->(m {project: $p}) RETURN count(r) AS n",
                p=p
            ).single()["n"]
            return {
                "project": p,
                "characters": chars,
                "locations": locs,
                "events": events,
                "themes": themes,
                "style_guides": guides,
                "motifs": motifs_count,
                "chapter_arcs": arcs,
                "suspense_threads": threads,
                "outline_entries": outlines,
                "relationships": rels,
            }


if __name__ == "__main__":
    kg = NovelKG()
    kg.init_schema()
    print("图谱统计:", kg.stats())
    kg.close()
