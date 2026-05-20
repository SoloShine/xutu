"""
Novel KG 端到端测试脚本。

验证 JSON/Neo4j 双后端的完整写作循环：
  初始化 → 写入世界观 → 大纲 → 弧线推演 → 续写 → 提取 → 校验 → 统计

用法:
  python test_e2e.py                    # JSON 后端（默认）
  KG_BACKEND=neo4j python test_e2e.py   # Neo4j 后端
"""

import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import _create_backend, close_all, _BACKEND

PROJECT = f"e2e_test_{_BACKEND}"
PASS = 0
FAIL = 0
ERRORS = []


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        msg = f"  [FAIL] {name}" + (f" — {detail}" if detail else "")
        ERRORS.append(msg)
        print(msg)


def main():
    print(f"\n{'='*60}")
    print(f"  E2E Test | backend={_BACKEND} | project={PROJECT}")
    print(f"{'='*60}\n")

    kg = _create_backend(PROJECT)

    try:
        # ---- 1. 初始化 ----
        print("[1] 初始化")
        kg.clear_project()
        test("clear_project", True)

        stats = kg.stats()
        test("空图谱 events=0", stats["events"] == 0)

        # ---- 2. 写入节点 ----
        print("\n[2] 写入节点")
        kg.add_character("老孟", role="主角", personality="沉默")
        kg.add_character("孙洁", role="调查者", personality="敏锐")
        kg.add_character("赵所", role="反派", personality="狡猾")
        test("add_character x3", len(kg.get_all_characters()) == 3)
        test("get_all_character_names",
             kg.get_all_character_names() == {"老孟", "孙洁", "赵所"})

        kg.add_location("东华澡堂", loc_type="废墟", description="铁东区")
        kg.add_location("管道层", loc_type="地下")
        test("add_location x2", kg.get_all_location_names() == {"东华澡堂", "管道层"})

        kg.add_style_guide("style_01", rule="零形容词叙事")
        kg.add_style_guide("style_02", rule="感官驱动")
        s = kg.stats()
        test("style_guides=2", s["style_guides"] == 2)

        kg.add_theme("废墟与记忆", description="工业废墟中的历史")
        test("add_theme", s["themes"] == 1 or kg.stats()["themes"] >= 1)

        kg.add_time_period("拆迁期", chapter_start=1, chapter_end=6, years="2024冬")
        test("add_time_period", kg.get_chapter_time_period(3) == "拆迁期")
        test("time_period out of range", kg.get_chapter_time_period(99) is None)

        # ---- 3. 大纲 & 弧线 ----
        print("\n[3] 大纲 & 弧线")
        kg.add_outline_entry(1, purpose="建立悬念",
                             key_events="发现焊疤",
                             threads_to_plant="ST01_01")
        kg.add_outline_entry(2, purpose="推进调查",
                             threads_to_resolve="ST01_01")
        test("add_outline_entry",
             kg.get_outline_entry(1) is not None)
        test("outline_entry purpose",
             kg.get_outline_entry(1)["purpose"] == "建立悬念")

        kg.add_chapter_arc(1, purpose="建立悬念", scenes="澡堂->管道层",
                           ending="发现纸片")
        kg.add_chapter_arc(2, purpose="推进调查", scenes="面馆->澡堂",
                           ending="墙壁差值12cm")
        test("add_chapter_arc", kg.stats()["chapter_arcs"] == 2)

        # ---- 4. 事件 & 关系 ----
        print("\n[4] 事件 & 关系")
        kg.add_event("E1_01", title="发现焊疤", chapter=1, event_type="discovery")
        kg.add_event("E1_02", title="看到纸片", chapter=1, event_type="discovery")
        kg.add_event("E2_01", title="测量墙壁", chapter=2, event_type="investigation")
        test("add_event x3", kg.stats()["events"] == 3)
        test("event_exists(E1_01)", kg.event_exists("E1_01"))
        test("event_exists(FAKE)", not kg.event_exists("FAKE"))

        kg.add_relation("Event", "id", "E1_01", "INVOLVES", "Character", "name", "老孟")
        kg.add_relation("Event", "id", "E1_01", "OCCURS_AT", "Location", "name", "东华澡堂")
        kg.add_relation("Event", "id", "E1_02", "INVOLVES", "Character", "name", "老孟")
        kg.add_relation("Event", "id", "E2_01", "INVOLVES", "Character", "name", "孙洁")
        kg.add_relation("Event", "id", "E2_01", "OCCURS_AT", "Location", "name", "东华澡堂")
        kg.add_relation("Event", "id", "E1_01", "PRECEDES", "Event", "id", "E1_02")
        test("add_relation", kg.stats()["relationships"] == 6)

        # 关系去重
        kg.add_relation("Event", "id", "E1_01", "INVOLVES", "Character", "name", "老孟")
        test("relation dedup", kg.stats()["relationships"] == 6)

        # ---- 5. 悬念线 ----
        print("\n[5] 悬念线")
        kg.add_suspense_thread("ST01_01", content="117号柜为何焊死",
                               planted_chapter=1, importance="high",
                               status="planted")
        kg.add_suspense_thread("ST02_01", content="墙壁多出12cm",
                               planted_chapter=2, importance="medium",
                               status="planted")
        test("add_suspense_thread", kg.stats()["suspense_threads"] == 2)

        unresolved = kg.get_unresolved_threads(2)
        test("unresolved at ch2", len(unresolved) == 1)  # ST01_01(planted=1)
        test("unresolved at ch3", len(kg.get_unresolved_threads(3)) == 2)  # + ST02_01(planted=2)

        kg.update_suspense_thread("ST01_01", status="resolved", resolved_chapter=2)
        unresolved_after = kg.get_unresolved_threads(3)
        test("resolved ST01_01", len(unresolved_after) == 1)
        test("resolved thread detail",
             unresolved_after[0]["id"] == "ST02_01")

        all_threads = kg.get_all_threads()
        test("get_all_threads", len(all_threads) == 2)

        # ---- 6. 复合查询 ----
        print("\n[6] 复合查询")
        ctx = kg.get_context_for_chapter(2)
        test("context has characters", len(ctx["characters"]) > 0)
        test("context has prev_events", len(ctx["prev_events"]) == 2)
        test("context has style_guides", len(ctx["style_guides"]) == 2)
        test("context has chapter_arc", len(ctx["chapter_arc"]) == 1)
        test("context has time_periods", len(ctx["time_periods"]) == 1)
        test("context has outline_entry", ctx["outline_entry"] is not None)

        drv_ctx = kg.get_arc_derivation_context(3, lookback=2)
        test("derivation has recent_arcs", len(drv_ctx["recent_arcs"]) == 2)
        test("derivation has recent_events", len(drv_ctx["recent_events"]) == 3)
        test("derivation has last_event", drv_ctx["last_event"] is not None)

        # ---- 7. 因果链 & 证据链 & 角色目标 ----
        print("\n[7] 因果链 & 证据链 & 角色目标")

        # 因果链：E1_01 → E1_02 → E2_01
        kg.add_relation("Event", "id", "E1_01", "CAUSES", "Event", "id", "E1_02",
                        causal_type="consequence", detail="发现焊疤后注意到纸片")
        kg.add_relation("Event", "id", "E1_02", "CAUSES", "Event", "id", "E2_01",
                        causal_type="investigation", detail="纸片线索引发调查")
        test("causal relations added", kg.stats()["relationships"] == 8)

        # 证据链：E2_01 为 ST02_01 提供线索
        kg.add_relation("Event", "id", "E2_01", "EVIDENCES",
                        "SuspenseThread", "id", "ST02_01",
                        evidence_type="clue", detail="测量发现墙壁异常")
        test("evidence relation added", kg.stats()["relationships"] == 9)

        # 角色目标
        kg.add_character_goal("老孟", goal="查明焊疤真相",
                              goal_type="pursue", status="new", chapter=1)
        kg.add_character_goal("孙洁", goal="保护老孟",
                              goal_type="protect", status="new", chapter=2)
        chars_with_goals = kg.get_all_characters()
        meng = [c for c in chars_with_goals if c["name"] == "老孟"][0]
        # Neo4j stores goals as JSON string, JSON backend stores as list
        goals_raw = meng.get("goals", [])
        if isinstance(goals_raw, str):
            import json as _json
            goals_raw = _json.loads(goals_raw)
        test("character goal added", len(goals_raw) == 1)
        test("character goal content", goals_raw[0]["goal"] == "查明焊疤真相")

        # ---- 8. 一致性检查（含因果断裂+证据缺失） ----
        print("\n[8] 一致性检查")
        issues = kg.check_consistency()
        test("check_consistency runs", isinstance(issues, list))

        # 验证因果断裂检测：给第2章加一个孤立事件（非首事件，无因果入边）
        kg.add_event("E2_02", title="孙洁遇到路人", chapter=2, event_type="daily")
        issues_with_gap = kg.check_consistency()
        causal_gaps = [i for i in issues_with_gap if i["type"] == "因果断裂"]
        test("causal gap detected", len(causal_gaps) >= 1,
             f"found {len(causal_gaps)} causal gaps")

        # 验证证据缺失检测：ST01_01 已解决但没有 EVIDENCES 关系
        evidence_missing = [i for i in issues_with_gap if i["type"] == "证据缺失"]
        test("evidence missing detected", len(evidence_missing) >= 1,
             f"found {len(evidence_missing)} evidence missing issues")

        # 清理：删除测试用孤立事件
        kg.delete_events_by_chapter(2)
        # 重新添加 E2_01 和必要关系（因为 delete_events_by_chapter 删除了所有关系）
        kg.add_event("E2_01", title="测量墙壁", chapter=2, event_type="investigation")
        kg.add_relation("Event", "id", "E2_01", "INVOLVES", "Character", "name", "孙洁")
        kg.add_relation("Event", "id", "E2_01", "OCCURS_AT", "Location", "name", "东华澡堂")

        # ---- 9. 删除操作 ----
        print("\n[9] 删除操作")
        kg.delete_events_by_chapter(1)
        test("delete_events_by_chapter",
             kg.stats()["events"] == 1)  # 只剩 E2_01
        test("event E1_01 gone", not kg.event_exists("E1_01"))

        # ---- 10. 最终统计 ----
        print("\n[10] 最终统计")
        final = kg.stats()
        test("final backend tag", final.get("backend") == _BACKEND or "backend" not in final)
        print(f"\n  最终图谱: {json.dumps(final, ensure_ascii=False, indent=4)}")

        # ---- 11. 批量查询方法 ----
        print("\n[11] 批量查询方法")
        test("get_all_events", len(kg.get_all_events()) >= 1)
        test("get_all_locations", len(kg.get_all_locations()) >= 1)
        test("get_all_themes", len(kg.get_all_themes()) >= 1)
        test("get_all_style_guides", len(kg.get_all_style_guides()) >= 1)
        test("get_all_motifs", isinstance(kg.get_all_motifs(), list))
        test("get_all_chapter_arcs", len(kg.get_all_chapter_arcs()) >= 1)
        test("get_all_outline_entries", len(kg.get_all_outline_entries()) >= 1)
        test("get_all_time_periods", len(kg.get_all_time_periods()) >= 1)
        test("get_all_relations", len(kg.get_all_relations()) >= 1)

        # ---- 12. 增强一致性检查 ----
        print("\n[12] 增强一致性检查")

        # 人物空间矛盾测试：孙洁在第2章同时出现在两个地点
        kg.add_event("E2_03", title="孙洁在管道层", chapter=2, event_type="daily")
        kg.add_relation("Event", "id", "E2_03", "INVOLVES", "Character", "name", "孙洁")
        kg.add_location("管道层地下室", loc_type="地下")
        kg.add_relation("Event", "id", "E2_03", "OCCURS_AT", "Location", "name", "管道层地下室")

        issues_enhanced = kg.check_consistency()
        coloc_issues = [i for i in issues_enhanced if i["type"] == "人物空间矛盾"]
        test("character co-location conflict", len(coloc_issues) >= 1,
             f"found {len(coloc_issues)} co-location issues")

        # 主角缺席检测运行正常
        protagonist_absent = [i for i in issues_enhanced if i["type"] == "主角缺席"]
        test("protagonist absence check runs", isinstance(protagonist_absent, list))

        # 清理 E2_03
        kg.delete_events_by_chapter(2)

        # ---- 13. 叙事节奏分析 ----
        print("\n[13] 叙事节奏分析")
        from core import analyze_pacing

        # 先测试不足3章弧线的情况
        pacing = analyze_pacing(PROJECT)
        test("analyze_pacing returns dict", isinstance(pacing, dict))
        test("pacing has issues key", "issues" in pacing)

        # 添加重复弧线触发检测
        kg.add_chapter_arc(3, purpose="推进调查", scenes="A->B", ending="发现新线索")
        kg.add_chapter_arc(4, purpose="推进调查", scenes="C->D", ending="发现新线索")
        kg.add_chapter_arc(5, purpose="推进调查", scenes="E->F", ending="发现新线索")
        kg.add_chapter_arc(6, purpose="高潮冲突",
                           scenes="A->B->C->D->E->F->G->H", ending="真相大白")

        # 直接用 kg 对象读取弧线（避免连接池缓存不一致）
        from core import _check_purpose_repetition, _check_ending_repetition, _check_scene_density
        all_arcs = kg.get_all_chapter_arcs()
        arcs_sorted = sorted(all_arcs, key=lambda a: a.get("chapter", 0))
        pacing_issues = []
        _check_purpose_repetition(arcs_sorted, pacing_issues, {})
        _check_ending_repetition(arcs_sorted, pacing_issues, {})
        _check_scene_density(arcs_sorted, pacing_issues)

        test("purpose repetition detected",
             any(i["type"] == "目的重复" for i in pacing_issues),
             f"issues: {[i['type'] for i in pacing_issues]}")
        test("ending repetition detected",
             any(i["type"] == "结尾重复" for i in pacing_issues),
             f"issues: {[i['type'] for i in pacing_issues]}")
        test("scene density anomaly",
             any(i["type"] == "场景密度异常" for i in pacing_issues),
             f"issues: {[i['type'] for i in pacing_issues]}")

        # ---- 14. 大纲合规检查 ----
        print("\n[14] 大纲合规检查")
        from validators import check_outline_compliance

        # 合规场景（bigram匹配）
        kg.clear_project()
        kg.add_outline_entry(1, purpose="建立悬念", key_events="发现焊疤")
        compliant_events = [{"id": "E1_01", "title": "发现焊疤", "detail": "老孟看到焊疤"}]
        result = check_outline_compliance(kg.get_outline_entry(1), compliant_events)
        test("outline compliance passed",
             len(result) == 0,
             f"violations: {[v.detail for v in result]}")

        # bigram不匹配场景 → pending_semantic
        divergent_events = [{"id": "E1_01", "title": "遇到孙洁", "detail": "走廊偶遇"}]
        result2 = check_outline_compliance(kg.get_outline_entry(1), divergent_events)
        test("outline compliance pending_semantic on bigram miss",
             any(v.severity == "pending_semantic" for v in result2),
             f"violations: {[v.detail for v in result2]}")

        # 无大纲
        result3 = check_outline_compliance(None, compliant_events)
        test("outline compliance no outline", len(result3) == 0)

        # threads_to_resolve 检查
        kg.add_outline_entry(2, purpose="推进", threads_to_resolve="ST01_01")
        result4 = check_outline_compliance(
            kg.get_outline_entry(2), [],
            thread_updates=[{"thread_id": "ST01_01", "new_status": "resolved"}]
        )
        test("outline threads_to_resolve passed",
             not any("ST01_01" in v.detail for v in result4))

        result5 = check_outline_compliance(
            kg.get_outline_entry(2), [],
            thread_updates=[]
        )
        test("outline threads_to_resolve pending_semantic",
             any(v.severity == "pending_semantic" and "ST01_01" in v.detail for v in result5))

        # ---- 15. check_outline_compliance MCP工具 ----
        print("\n[15] check_outline_compliance MCP工具")
        from core import check_outline_compliance as _coc

        # Clear the connection pool to avoid stale data
        from core import _pool, close_all
        close_all()

        kg.clear_project()
        kg.add_outline_entry(1, purpose="建立悬念", key_events="发现焊疤,看到纸片")
        kg.add_event("E1_01", title="发现焊疤", chapter=1)
        kg.add_event("E1_02", title="看到纸片", chapter=1)

        result_coc = _coc(PROJECT, 1)
        test("check_outline_compliance followed",
             result_coc["overall"] == "followed",
             f"got {result_coc['overall']}")
        test("check_outline_compliance action_required false",
             result_coc["action_required"] == False)
        test("check_outline_compliance has semantic_checks field",
             "semantic_checks" in result_coc)

        # bigram miss → LLM语义检查（fallback时key_events→error→diverged）
        close_all()
        kg.clear_project()
        kg.add_outline_entry(1, purpose="建立悬念", key_events="发现焊疤")
        kg.add_event("E1_01", title="遇到孙洁", chapter=1)
        result_div = _coc(PROJECT, 1)
        test("check_outline_compliance diverged on semantic miss",
             result_div["overall"] == "diverged",
             f"got {result_div['overall']}")
        test("check_outline_compliance has semantic_checks results",
             len(result_div.get("semantic_checks", [])) > 0,
             f"semantic_checks: {result_div.get('semantic_checks', [])}")

        # 无大纲测试
        close_all()
        result_none = _coc(PROJECT, 99)
        test("check_outline_compliance no outline",
             result_none["overall"] == "no_outline")

        # ---- 16. revise_outline MCP工具 ----
        print("\n[16] revise_outline MCP工具")
        from core import revise_outline as _ro

        close_all()
        kg = _create_backend(PROJECT)
        kg.clear_project()
        kg.add_chapter_arc(1, purpose="test", scenes="A->B", ending="end")
        kg.add_chapter_arc(2, purpose="test", scenes="C->D", ending="end")
        kg.add_outline_entry(1, purpose="原始目的", key_events="事件A")
        kg.add_chapter_arc(3, purpose="latest", scenes="E->F", ending="end")

        result_ro = _ro(PROJECT, 1, reason="作者修改了ch1", purpose="新目的",
                         key_events="事件B,事件C")
        test("revise_outline returns success",
             "已修订" in result_ro)

        # Close pool to get fresh instance with updated data
        close_all()
        kg = _create_backend(PROJECT)
        updated = kg.get_outline_entry(1)
        test("revise_outline updated purpose",
             updated["purpose"] == "新目的")
        test("revise_outline updated key_events",
             updated["key_events"] == "事件B,事件C")
        test("revise_outline set compliance",
             updated["compliance"] == "overridden")
        test("revise_outline set reason",
             updated["revision_reason"] == "作者修改了ch1")
        test("revise_outline set revised_chapter",
             updated["revised_chapter"] == 3)

        # 修订不存在的章节
        result_missing = _ro(PROJECT, 99, reason="test")
        test("revise_outline missing entry",
             "无大纲条目" in result_missing)

        # ---- 17. 事后编辑工具 ----
        print("\n[17] 事后编辑工具 (analyze_edit_impact + accept_edit)")
        from core import analyze_edit_impact as _aei, accept_edit as _ae, close_all

        kg.clear_project()
        close_all()  # clear pool
        kg.add_character("老孟", role="主角")
        kg.add_location("澡堂", loc_type="废墟")
        kg.add_chapter_arc(1, purpose="ch1", scenes="A", ending="end")
        kg.add_chapter_arc(2, purpose="ch2", scenes="B", ending="end")
        kg.add_chapter_arc(3, purpose="ch3", scenes="C", ending="end")

        # 创建 edited 文件
        output_dir = os.path.join(os.path.dirname(kg._path), "output")
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "ch1_edited.txt"), "w", encoding="utf-8") as f:
            f.write("这是编辑后的ch1文本")

        # 添加旧数据
        kg.add_event("E1_01", title="发现焊疤", chapter=1)
        kg.add_event("E1_02", title="看到纸片", chapter=1)
        kg.add_relation("Event", "id", "E1_01", "INVOLVES", "Character", "name", "老孟")
        kg.add_suspense_thread("ST01_01", content="焊疤之谜", planted_chapter=1,
                                importance="high", status="planted")
        kg.add_relation("Event", "id", "E1_01", "EVIDENCES",
                         "SuspenseThread", "id", "ST01_01")
        kg.add_outline_entry(2, purpose="调查焊疤", key_events="发现焊疤")
        kg.add_outline_entry(3, purpose="深入", key_events="发现纸片")

        close_all()  # clear pool before using core functions
        result_aei = _aei(PROJECT, 1)
        test("analyze_edit_impact returns dict", isinstance(result_aei, dict))
        test("analyze_edit_impact has old_events",
             len(result_aei.get("old_events", [])) == 2,
             f"old_events: {result_aei.get('old_events', [])}")
        test("analyze_edit_impact affected threads",
             len(result_aei.get("affected_threads", [])) >= 1,
             f"threads: {result_aei.get('affected_threads', [])}")
        test("analyze_edit_impact downstream warnings",
             len(result_aei.get("downstream_warnings", [])) >= 1,
             f"warnings: {result_aei.get('downstream_warnings', [])}")

        # 无edited文件时应报错
        result_no_edit = _aei(PROJECT, 99)
        test("analyze_edit_impact missing file",
             "error" in result_no_edit)

        # accept_edit
        new_extraction = json.dumps({
            "events": [
                {"id": "E1_01", "title": "重写事件", "chapter": 1, "type": "daily"},
            ],
            "event_relations": [
                {"event_id": "E1_01", "character": "老孟", "location": "澡堂"},
            ],
            "new_characters": [],
            "new_locations": [],
            "thread_updates": [],
            "new_threads": [],
            "causal_links": [],
            "evidence_links": [],
        })
        result_ae = _ae(PROJECT, 1, new_extraction,
                         confirm="I_UNDERSTAND_THIS_IS_DESTRUCTIVE")
        test("accept_edit returns stats",
             "stats" in result_ae)
        test("accept_edit marked downstream",
             len(result_ae.get("downstream_marked_for_revision", [])) >= 1,
             f"marked: {result_ae.get('downstream_marked_for_revision', [])}")

        # accept_edit without confirm should fail
        result_blocked = _ae(PROJECT, 1, "{}", confirm="")
        test("accept_edit blocked without confirm",
             "error" in result_blocked or "BLOCKED" in str(result_blocked))

        # 验证后续大纲被标记（需要重新创建kg实例）
        close_all()
        kg = _create_backend(PROJECT)
        oe2 = kg.get_outline_entry(2)
        test("downstream outline marked needs_revision",
             oe2 is not None and oe2.get("compliance") == "needs_revision",
             f"compliance: {oe2.get('compliance') if oe2 else 'None'}")

        # ---- 18. review_chapter MCP工具 ----
        print("\n[18] review_chapter MCP工具")
        from core import review_chapter as _rc, close_all

        close_all()  # clear pool
        kg.clear_project()

        # accept
        result_accept = _rc(PROJECT, 1, "accept")
        test("review_chapter accept",
             result_accept["action"] == "accept")
        test("review_chapter accept message",
             "通过审核" in result_accept["message"])

        # edit (with text)
        result_edit = _rc(PROJECT, 1, "edit", edited_text="修改后的文本内容")
        test("review_chapter edit saved",
             result_edit["action"] == "edit")
        test("review_chapter edit has path",
             "edited_path" in result_edit)

        # rewrite (with text)
        result_rewrite = _rc(PROJECT, 2, "rewrite", edited_text="完全重写的文本")
        test("review_chapter rewrite",
             result_rewrite["action"] == "rewrite")

        # revise_outline
        result_revise = _rc(PROJECT, 1, "revise_outline")
        test("review_chapter revise_outline",
             result_revise["action"] == "revise_outline")

        # invalid action
        result_invalid = _rc(PROJECT, 1, "invalid_action")
        test("review_chapter invalid action",
             "error" in result_invalid)

        # edit without text
        result_no_text = _rc(PROJECT, 1, "edit")
        test("review_chapter edit no text error",
             "error" in result_no_text)

        # ---- 19. 协作配置 ----
        print("\n[19] 协作配置")
        from config_loader import config_loader
        cfg = config_loader.load(PROJECT)
        collab = cfg.get("collaboration", {})
        test("collaboration config exists",
             "collaboration" in cfg,
             f"keys: {list(cfg.keys())}")
        test("review_checkpoint default False",
             collab.get("review_checkpoint") == False)
        test("outline_compliance default True",
             collab.get("outline_compliance") == True)
        test("auto_revise_outline default False",
             collab.get("auto_revise_outline") == False)
        test("semantic_check default True",
             collab.get("semantic_check") == True)

        from config_loader import config_loader as cl2
        test("config_loader.get collaboration",
             cl2.get(PROJECT, "collaboration", "review_checkpoint", default=False) == False)

        # ---- 20. LLM语义合规检查 ----
        print("\n[20] LLM语义合规检查")
        from core import _semantic_compliance_check

        # 测试1: 无事件数据时fallback
        close_all()
        kg.clear_project()
        kg.add_outline_entry(1, purpose="测试", key_events="宋姐出现")
        from validators import check_outline_compliance as _coc_val
        outline_e = kg.get_outline_entry(1)
        violations_e = _coc_val(outline_e, [])  # 空事件列表
        sem_no_events = _semantic_compliance_check(PROJECT, 1, outline_e, [], violations_e)
        test("semantic check no events fallback",
             len(sem_no_events) > 0 and not sem_no_events[0][1],
             f"got {sem_no_events}")

        # 测试2: mock LLM语义匹配（"深夜来访" = "突然出现"）
        close_all()
        kg.clear_project()
        kg.add_outline_entry(1, purpose="测试", key_events="宋姐突然出现")
        kg.add_event("E1_01", title="宋姐深夜来访", detail="半夜敲门", chapter=1)
        outline_sem = kg.get_outline_entry(1)
        events_sem = kg.get_events_by_chapter(1)
        violations_sem = _coc_val(outline_sem, events_sem)

        # violations_sem应该有pending_semantic项（bigram不匹配）
        test("semantic pending items exist after bigram miss",
             any(v.severity == "pending_semantic" for v in violations_sem),
             f"violations: {[v.detail for v in violations_sem]}")

        # 测试3: semantic_check配置项
        test("semantic_check config True",
             cl2.get(PROJECT, "collaboration", "semantic_check", default=True) == True)

        # 测试4: 返回结构完整性
        from core import check_outline_compliance as _coc_core
        close_all()
        result_struct = _coc_core(PROJECT, 1)
        test("semantic result has required fields",
             all(k in result_struct for k in ["programmatic_checks", "semantic_checks", "overall"]),
             f"keys: {list(result_struct.keys())}")

        # ---- 21. 版本管理 ----
        print("\n[21] 版本管理 (snapshot + list_edits + rollback_edit)")
        from core import list_edits as _le, rollback_edit as _re
        from core import accept_edit as _ae

        close_all()
        kg.clear_project()
        kg.add_character("老陈", role="protagonist")
        kg.add_event("E1_01", title="初始事件A", detail="原始内容", chapter=1)
        kg.add_event("E1_02", title="初始事件B", detail="更多内容", chapter=1)

        # list_edits 初始为空
        result_le = _le(PROJECT)
        test("list_edits empty initially",
             result_le["total"] == 0,
             f"got {result_le['total']}")

        # accept_edit 应自动创建快照
        close_all()
        extracted = json.dumps({
            "events": [
                {"id": "E1_01", "title": "修改后事件", "detail": "新内容", "chapter": 1, "type": "daily"}
            ],
            "event_relations": [],
            "new_characters": [],
            "character_updates": [],
            "thread_updates": [],
            "new_threads": []
        })
        result_ae = _ae(PROJECT, 1, extracted,
                        confirm="I_UNDERSTAND_THIS_IS_DESTRUCTIVE")
        test("accept_edit has snapshot_id",
             result_ae.get("snapshot_id") is not None,
             f"got {result_ae.get('snapshot_id')}")

        # list_edits 现在有1个快照
        close_all()
        result_le2 = _le(PROJECT, chapter=1)
        test("list_edits has 1 snapshot",
             result_le2["total"] == 1,
             f"got {result_le2['total']}")
        test("list_edits snapshot has chapter",
             result_le2["snapshots"][0]["chapter"] == 1)
        test("list_edits snapshot has event_count",
             result_le2["snapshots"][0]["event_count"] == 2,
             f"got {result_le2['snapshots'][0]['event_count']}")

        # rollback_edit 需要确认
        snap_id = result_le2["snapshots"][0]["id"]
        result_rb_fail = _re(PROJECT, snap_id)
        test("rollback_edit blocked without confirm",
             "error" in result_rb_fail)

        # rollback_edit 成功
        close_all()
        result_rb = _re(PROJECT, snap_id,
                        confirm="I_UNDERSTAND_THIS_IS_DESTRUCTIVE")
        test("rollback_edit success",
             "restored_events" in result_rb,
             f"got {result_rb}")
        test("rollback_edit restored 2 events",
             result_rb["restored_events"] == 2)
        test("rollback_edit has pre_rollback_snapshot",
             result_rb.get("pre_rollback_snapshot") is not None)

        # 验证回滚后数据正确
        close_all()
        events_after = kg.get_events_by_chapter(1)
        test("rollback events restored",
             len(events_after) == 2,
             f"got {len(events_after)} events")
        titles = {e.get("title", "") for e in events_after}
        test("rollback correct events",
             "初始事件A" in titles,
             f"titles: {titles}")

        # list_edits 现在有2个快照（原始 + rollback前的自动快照）
        close_all()
        result_le3 = _le(PROJECT)
        test("list_edits has 2 snapshots after rollback",
             result_le3["total"] == 2,
             f"got {result_le3['total']}")

        # rollback 不存在的快照
        close_all()
        result_rb_fake = _re(PROJECT, "fake_snapshot_999",
                             confirm="I_UNDERSTAND_THIS_IS_DESTRUCTIVE")
        test("rollback_edit fake snapshot error",
             "error" in result_rb_fake)

        # ---- 22. Prompt/Extraction 落盘 ----
        print("\n[22] Prompt/Extraction 落盘")
        import glob as _glob

        close_all()
        kg.clear_project()
        kg.add_character("测试角色", role="protagonist")
        kg.add_event("E1_01", title="测试事件", detail="用于落盘测试", chapter=1)
        kg.add_chapter_arc(1, purpose="落盘测试", scenes="场景A", ending="结束")

        # 测试 prompts 目录不存在（clean start）
        prompts_dir = os.path.join(os.path.dirname(kg._path), "prompts")
        extractions_dir = os.path.join(os.path.dirname(kg._path), "extractions")

        # get_extraction_prompt 落盘
        from core import get_extraction_prompt as _gep
        close_all()
        prompt_e = _gep(PROJECT, 1, "这是章节正文用于测试提取。")
        test("extraction prompt returns string",
             isinstance(prompt_e, str) and len(prompt_e) > 50)
        epath = os.path.join(prompts_dir, "extraction_ch1.txt")
        test("extraction prompt file exists",
             os.path.isfile(epath))
        with open(epath, encoding="utf-8") as f:
            content = f.read()
        test("extraction prompt has persisted header",
             "# Persisted:" in content)
        test("extraction prompt has content",
             "这是章节正文用于测试提取" in content)

        # get_writing_prompt 落盘
        from core import get_writing_prompt as _gwp
        close_all()
        prompt_w = _gwp(PROJECT, 1)
        test("writing prompt returns string",
             isinstance(prompt_w, str) and len(prompt_w) > 50)
        wpath = os.path.join(prompts_dir, "writing_ch1.txt")
        test("writing prompt file exists",
             os.path.isfile(wpath))

        # get_derivation_prompt 落盘
        from core import get_derivation_prompt as _gdp
        close_all()
        prompt_d = _gdp(PROJECT, 2)
        test("derivation prompt returns string",
             isinstance(prompt_d, str) and len(prompt_d) > 50)
        dpath = os.path.join(prompts_dir, "derivation_ch2.txt")
        test("derivation prompt file exists",
             os.path.isfile(dpath))

        # write_extraction 落盘
        from core import write_extraction as _we
        close_all()
        extracted_data = {
            "events": [{"id": "E1_02", "title": "提取事件", "detail": "测试", "chapter": 1, "type": "daily"}],
            "event_relations": [],
            "new_characters": [],
            "character_updates": [],
            "thread_updates": [],
            "new_threads": []
        }
        _we(PROJECT, 1, json.dumps(extracted_data))
        xpath = os.path.join(extractions_dir, "extraction_ch1.json")
        test("extraction json file exists",
             os.path.isfile(xpath))
        with open(xpath, encoding="utf-8") as f:
            xcontent = f.read()
        test("extraction json has persisted header",
             "# Persisted:" in xcontent)
        test("extraction json has event data",
             "E1_02" in xcontent)

        # ---- 23. 地点自动注册 ----
        print("\n[23] 地点自动注册")
        close_all()
        kg.clear_project()
        kg.add_character("李四", role="protagonist")
        # 图谱中没有"废弃工厂"这个地点
        existing_locs = kg.get_all_location_names()
        test("no locations initially",
             "废弃工厂" not in existing_locs)

        from core import write_extraction as _we2
        close_all()
        extracted_auto = {
            "events": [
                {"id": "E2_01", "title": "到达", "detail": "到达废弃工厂", "chapter": 2, "type": "daily"}
            ],
            "event_relations": [
                {"event_id": "E2_01", "character": "李四", "location": "废弃工厂"}
            ],
            "new_characters": [],
            "character_updates": [],
            "thread_updates": [],
            "new_threads": [],
            "new_locations": []
        }
        result_we = _we2(PROJECT, 2, json.dumps(extracted_auto))
        test("write_extraction with auto location returns stats",
             "stats" in result_we)
        test("auto_registered_locations has 废弃工厂",
             "废弃工厂" in result_we.get("auto_registered_locations", []),
             f"got {result_we.get('auto_registered_locations')}")

        # 验证地点已写入图谱
        close_all()
        kg = _create_backend(PROJECT)
        locs_after = kg.get_all_location_names()
        test("废弃工厂 now in locations",
             "废弃工厂" in locs_after,
             f"got {locs_after}")

        # 测试：已在new_locations中声明的地点不应被重复自动注册
        close_all()
        extracted_declared = {
            "events": [
                {"id": "E3_01", "title": "访问", "detail": "访问旧仓库", "chapter": 3, "type": "daily"}
            ],
            "event_relations": [
                {"event_id": "E3_01", "character": "李四", "location": "旧仓库"}
            ],
            "new_characters": [],
            "character_updates": [],
            "thread_updates": [],
            "new_threads": [],
            "new_locations": [{"name": "旧仓库", "type": "仓库", "description": "废弃仓库"}]
        }
        result_we2 = _we2(PROJECT, 3, json.dumps(extracted_declared))
        test("declared location not auto-registered",
             "auto_registered_locations" not in result_we2 or
             "旧仓库" not in result_we2.get("auto_registered_locations", []))

        # 测试：已存在的地点不应被自动注册
        close_all()
        kg.add_location("医院", type="建筑", description="市中心医院")
        extracted_existing = {
            "events": [
                {"id": "E4_01", "title": "就医", "detail": "去医院", "chapter": 4, "type": "daily"}
            ],
            "event_relations": [
                {"event_id": "E4_01", "character": "李四", "location": "医院"}
            ],
            "new_characters": [],
            "character_updates": [],
            "thread_updates": [],
            "new_threads": [],
            "new_locations": []
        }
        result_we3 = _we2(PROJECT, 4, json.dumps(extracted_existing))
        test("existing location not auto-registered",
             "auto_registered_locations" not in result_we3 or
             "医院" not in result_we3.get("auto_registered_locations", []))

        # ---- 24. 批量大纲合规检查 ----
        print("\n[24] 批量大纲合规检查")
        close_all()
        kg.clear_project()
        # 设置3章大纲+事件
        kg.add_outline_entry(1, purpose="发现线索",
                            key_events="找到日记", structure_hint="linear")
        kg.add_outline_entry(2, purpose="调查深入",
                            key_events="审问嫌疑人", structure_hint="linear")
        kg.add_outline_entry(3, purpose="真相大白",
                            key_events="揭露真相", structure_hint="linear")
        kg.add_event("E1_01", title="找到日记", detail="在阁楼发现旧日记", chapter=1)
        kg.add_event("E2_01", title="审问嫌疑人", detail="在审讯室问话", chapter=2)
        kg.add_event("E3_01", title="揭露真相", detail="公布调查结果", chapter=3)

        from core import batch_check_outline_compliance as _bcoc
        close_all()
        result_batch = _bcoc(PROJECT, chapters=[1, 2, 3])
        test("batch returns results dict",
             isinstance(result_batch.get("results"), dict))
        test("batch has stats",
             "stats" in result_batch and "total" in result_batch["stats"])
        test("batch total is 3",
             result_batch["stats"]["total"] == 3,
             f"got {result_batch['stats']['total']}")
        test("batch each chapter has overall",
             all(ch in result_batch["results"] for ch in [1, 2, 3]))
        # 程序化检查应该全部通过（bigram匹配）
        test("batch all followed",
             all(result_batch["results"][ch].get("overall") == "followed"
                 for ch in [1, 2, 3]),
             f"got {[result_batch['results'][ch].get('overall') for ch in [1,2,3]]}")

        # 测试不传chapters参数（自动检测所有大纲章节）
        close_all()
        result_auto = _bcoc(PROJECT)
        test("batch auto-detect chapters",
             result_auto["stats"]["total"] == 3,
             f"got {result_auto['stats']['total']}")

        # 测试空列表
        close_all()
        result_empty = _bcoc(PROJECT, chapters=[])
        test("batch empty chapters",
             result_empty["stats"]["total"] == 0)

        # 测试 batch_size 参数
        # 设置6章大纲+事件（用于分批测试）
        close_all()
        kg.clear_project()
        for ch in range(1, 7):
            kg.add_outline_entry(ch, purpose=f"第{ch}章目的",
                                key_events=f"事件{ch}", structure_hint="linear")
            kg.add_event(f"E{ch}_01", title=f"事件{ch}", detail=f"第{ch}章事件", chapter=ch)

        # batch_size=2 → 3批
        close_all()
        result_bs2 = _bcoc(PROJECT, batch_size=2)
        test("batch_size=2 has batch_count",
             result_bs2.get("batch_count", 0) >= 1,
             f"got batch_count={result_bs2.get('batch_count')}")
        test("batch_size=2 total is 6",
             result_bs2["stats"]["total"] == 6,
             f"got {result_bs2['stats']['total']}")
        test("batch_size=2 returns batch_size field",
             result_bs2.get("batch_size") == 2,
             f"got {result_bs2.get('batch_size')}")

        # batch_size=0 → 全部合并（1批）
        close_all()
        result_bs0 = _bcoc(PROJECT, batch_size=0)
        test("batch_size=0 total is 6",
             result_bs0["stats"]["total"] == 6)

        # batch_size=1 → 逐章检查（无批量）
        close_all()
        result_bs1 = _bcoc(PROJECT, batch_size=1)
        test("batch_size=1 no batch",
             result_bs1.get("batch_purpose") == False,
             f"got batch_purpose={result_bs1.get('batch_purpose')}")

    except Exception as e:
        global FAIL
        print(f"\n  [ERROR] {e}")
        import traceback
        traceback.print_exc()
        FAIL += 1
    finally:
        close_all()

    # ---- 结果 ----
    print(f"\n{'='*60}")
    print(f"  Results: {PASS} passed, {FAIL} failed")
    if ERRORS:
        print(f"\n  Failures:")
        for e in ERRORS:
            print(e)
    print(f"{'='*60}\n")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
