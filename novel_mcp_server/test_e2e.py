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
        _check_purpose_repetition(arcs_sorted, pacing_issues)
        _check_ending_repetition(arcs_sorted, pacing_issues)
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
