"""
V23 并行章节生成快速测试（无 LLM 调用）。

仅测试 [28]-[31] 四个 section，跳过所有 LLM 相关测试。
用法: python test_parallel.py
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import _create_backend, _kg, close_all, _BACKEND
import core

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
    print(f"  Parallel Test | backend={_BACKEND} | project={PROJECT}")
    print(f"{'='*60}\n")

    try:
        # ---- 28. 并行组分析 ----
        print("[28] 并行组分析")
        close_all()
        kg = _kg(PROJECT)
        kg.clear_project()

        result_empty = core.analyze_parallel_groups(PROJECT)
        test("no outlines returns empty",
             result_empty["max_parallelism"] == 1)

        for ch in range(1, 5):
            kg.add_outline_entry(ch, purpose=f"第{ch}章目的",
                                key_events=f"事件{ch}")
        result_seq = core.analyze_parallel_groups(PROJECT)
        test("sequential has 4 groups",
             len(result_seq["parallel_groups"]) == 4)
        test("sequential max_par is 1",
             result_seq["max_parallelism"] == 1)
        test("sequential has warning",
             len(result_seq["warnings"]) > 0)
        test("sequential dep graph has 4 chapters",
             len(result_seq["dependency_graph"]) == 4)

        # 连续章节双 POV
        close_all()
        kg = _kg(PROJECT)
        kg.clear_project()
        for ch in [1, 3, 5]:
            kg.add_outline_entry(ch, purpose=f"POV-A第{ch}章",
                                parallel_group="A")
        for ch in [2, 4, 6]:
            kg.add_outline_entry(ch, purpose=f"POV-B第{ch}章",
                                parallel_group="B")
        result_par = core.analyze_parallel_groups(PROJECT)
        test("parallel has 6 chapters in dep graph",
             len(result_par["dependency_graph"]) == 6)
        test("consecutive chapters all serial",
             result_par["max_parallelism"] == 1)

        # 跳跃编号 → 真正可并行
        close_all()
        kg = _kg(PROJECT)
        kg.clear_project()
        for ch in [1, 5, 10]:
            kg.add_outline_entry(ch, purpose=f"A线{ch}",
                                parallel_group="A")
        for ch in [3, 7, 12]:
            kg.add_outline_entry(ch, purpose=f"B线{ch}",
                                parallel_group="B")
        result_gap = core.analyze_parallel_groups(PROJECT)
        test("gap chapters has parallelism",
             result_gap["max_parallelism"] > 1)
        pg = kg.get_parallel_groups()
        test("parallel groups stored in graph",
             len(pg) > 0)

        # 显式依赖
        close_all()
        kg = _kg(PROJECT)
        kg.clear_project()
        kg.add_outline_entry(1, purpose="起点", parallel_group="A")
        kg.add_outline_entry(2, purpose="分支A", parallel_group="A",
                            parallel_dependencies=[1])
        kg.add_outline_entry(3, purpose="分支B", parallel_group="B",
                            parallel_dependencies=[1])
        kg.add_outline_entry(4, purpose="汇合", parallel_group="A",
                            parallel_dependencies=[2, 3])
        result_dep = core.analyze_parallel_groups(PROJECT)
        test("explicit deps: ch4 depends on ch2",
             2 in result_dep["dependency_graph"].get(4, {}).get("depends_on", []))
        test("explicit deps: ch4 depends on ch3",
             3 in result_dep["dependency_graph"].get(4, {}).get("depends_on", []))

        # ---- 29. 并行批次：快照+冻结上下文 ----
        print("\n[29] 并行批次：快照+冻结上下文")
        close_all()
        kg = _kg(PROJECT)
        kg.clear_project()
        for ch in [1, 3, 5]:
            kg.add_outline_entry(ch, purpose=f"A线第{ch}章", parallel_group="A",
                                key_events=f"事件A{ch}")
            kg.add_chapter_arc(ch, purpose=f"A线{ch}", scenes="场景",
                              ending=f"A线结尾{ch}")
        for ch in [10, 12, 14]:
            kg.add_outline_entry(ch, purpose=f"B线第{ch}章", parallel_group="B",
                                key_events=f"事件B{ch}")
            kg.add_chapter_arc(ch, purpose=f"B线{ch}", scenes="场景",
                              ending=f"B线结尾{ch}")
        kg.add_character("主角A", role="protagonist")
        kg.add_character("主角B", role="protagonist")
        kg.add_style_guide("sg01", rule="测试风格")
        kg.add_theme("双线叙事", description="两条时间线交织")

        batch_result = core.prepare_parallel_batch(PROJECT, [1, 3, 10])
        test("batch has batch_id",
             "batch_" in batch_result["batch_id"])
        test("batch has snapshot_id",
             "full_" in batch_result["snapshot_id"])
        test("batch frozen 3 chapters",
             len(batch_result["frozen_contexts"]) == 3)
        test("batch each context has keys",
             all("characters" in v for v in batch_result["frozen_contexts"].values()))
        test("batch no conflicts",
             len(batch_result["conflicts_preview"]) == 0)

        # ---- 30. 并行写作 prompt ----
        print("\n[30] 并行写作 prompt")
        batch_id = batch_result["batch_id"]

        prompt1 = core.get_parallel_writing_prompt(PROJECT, 1, batch_id)
        test("parallel prompt ch1 returns string",
             isinstance(prompt1, str) and len(prompt1) > 100)
        test("parallel prompt ch1 has style guides",
             "测试风格" in prompt1)

        prompt10 = core.get_parallel_writing_prompt(PROJECT, 10, batch_id)
        test("parallel prompt ch10 returns string",
             isinstance(prompt10, str) and len(prompt10) > 100)

        prompt_err = core.get_parallel_writing_prompt(PROJECT, 1, "fake_batch")
        test("parallel prompt bad batch returns error",
             "错误" in prompt_err)

        prompt_ch_err = core.get_parallel_writing_prompt(PROJECT, 99, batch_id)
        test("parallel prompt bad chapter returns error",
             "错误" in prompt_ch_err)

        # ---- 31. 并行合并 ----
        print("\n[31] 并行合并")
        mock_results = {
            1: {
                "text": "第一章正文内容，主角A出场。",
                "extraction_json": json.dumps({
                    "events": [
                        {"id": "E1_01", "title": "A出场", "detail": "主角A首次登场",
                         "chapter": 1, "type": "daily"}
                    ],
                    "event_relations": [],
                    "new_characters": [],
                    "new_locations": []
                })
            },
            10: {
                "text": "第十章正文内容，主角B出场。",
                "extraction_json": json.dumps({
                    "events": [
                        {"id": "E10_01", "title": "B出场", "detail": "主角B首次登场",
                         "chapter": 10, "type": "daily"}
                    ],
                    "event_relations": [],
                    "new_characters": [],
                    "new_locations": []
                })
            },
        }
        merge_result = core.merge_parallel_results(PROJECT, batch_id, mock_results)
        test("merge has merged_chapters",
             sorted(merge_result["merged_chapters"]) == [1, 10])
        test("merge has consistency",
             isinstance(merge_result["post_merge_consistency"], list))

        kg_events = kg.get_events_by_chapter(1)
        test("merge ch1 event written",
             len(kg_events) > 0)
        kg_events_10 = kg.get_events_by_chapter(10)
        test("merge ch10 event written",
             len(kg_events_10) > 0)

        ch1_text = kg.get_chapter_text(1)
        test("merge ch1 text saved",
             ch1_text is not None and "主角A" in ch1_text)

        # 再次合并 → batch 已清理
        merge_again = core.merge_parallel_results(PROJECT, batch_id, {})
        test("merge twice returns error",
             "error" in merge_again)

    except Exception as e:
        global FAIL
        print(f"\n  [ERROR] {e}")
        import traceback
        traceback.print_exc()
        FAIL += 1
    finally:
        close_all()

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
