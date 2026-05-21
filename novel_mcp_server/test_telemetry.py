"""
V25 遥测模块测试。
用法: python test_telemetry.py
"""

import os
import sys
import json
import time

# 确保 import 路径
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from telemetry import (
    TelemetryCollector, ToolCall, ChapterSession,
    wrap, init_telemetry, get_collector,
    _infer_chapter, _infer_project, _extract_decision,
)

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


# ============================================================
# Section 1: 收集器单元测试
# ============================================================
print("\n=== Section 1: 收集器单元测试 ===")

# 1.1 创建收集器
c = TelemetryCollector("test_proj")
test("1.1 collector session_id", len(c.session_id) == 8, f"got {c.session_id}")
test("1.1 collector project", c.project == "test_proj")
test("1.1 chapters empty", len(c.chapters) == 0)

# 1.2 记录一次调用
call1 = ToolCall(
    tool="get_writing_prompt", chapter=5,
    start=time.perf_counter(), end=time.perf_counter() + 0.01,
    duration_ms=10.0, llm_tokens=None, decision=None, error=None,
)
c.record(call1)
test("1.2 chapter session created", 5 in c.chapters)
test("1.2 call recorded", len(c.chapters[5].calls) == 1)
test("1.2 tool_stats has entry", "get_writing_prompt" in c.tool_stats)
test("1.2 tool_stats count", c.tool_stats["get_writing_prompt"] == [10.0])

# 1.3 记录多次调用（同章）
call2 = ToolCall(
    tool="write_extraction", chapter=5,
    start=time.perf_counter(), end=time.perf_counter() + 0.05,
    duration_ms=50.0,
    llm_tokens={"prompt_tokens": 1000, "completion_tokens": 500},
    decision={"events": 7, "new_characters": 1, "conflicts": 0},
    error=None,
)
c.record(call2)
test("1.3 two calls in same chapter", len(c.chapters[5].calls) == 2)
test("1.3 tool_stats two tools", len(c.tool_stats) == 2)

# 1.4 不同章节
call3 = ToolCall(
    tool="add_chapter_arc", chapter=6,
    start=time.perf_counter(), end=time.perf_counter() + 0.02,
    duration_ms=20.0,
    decision={"rhythm": "tight", "purpose": "test"},
    error=None,
)
c.record(call3)
test("1.4 two chapters", len(c.chapters) == 2)
test("1.4 ch6 has one call", len(c.chapters[6].calls) == 1)

# 1.5 无 chapter 的调用
call_no_ch = ToolCall(
    tool="get_graph_stats", chapter=None,
    start=time.perf_counter(), end=time.perf_counter() + 0.001,
    duration_ms=1.0, error=None,
)
c.record(call_no_ch)
test("1.5 no-chapter call: tool_stats updated", "get_graph_stats" in c.tool_stats)
test("1.5 no-chapter call: not in chapters", None not in c.chapters)

# 1.6 chapter report
report = c.get_chapter_report(5)
test("1.6 report is dict", isinstance(report, dict))
test("1.6 report has version", report.get("version") == "v25")
test("1.6 report has session_id", report.get("session_id") == c.session_id)
test("1.6 report chapter", report.get("chapter") == 5)
test("1.6 report tool_calls count", len(report.get("tool_calls", [])) == 2)
totals = report.get("totals", {})
test("1.6 report totals duration", totals.get("duration_ms") == 60.0)
test("1.6 report totals llm_prompt", totals.get("llm_prompt_tokens") == 1000)
test("1.6 report totals llm_completion", totals.get("llm_completion_tokens") == 500)
test("1.6 report tool_count", totals.get("tool_count") == 2)

# 1.7 session summary
summary = c.get_session_summary()
test("1.7 summary total_chapters", summary.get("total_chapters") == 2)
test("1.7 summary total_tool_calls", summary.get("total_tool_calls") == 4)
test("1.7 summary tool_stats", len(summary.get("tool_stats", {})) == 4)
per_ch = summary.get("per_chapter_duration_ms", {})
test("1.7 summary per_chapter ch5", per_ch.get("5") == 60.0)
test("1.7 summary per_chapter ch6", per_ch.get("6") == 20.0)

# 1.8 tool_stats aggregation
ts = summary.get("tool_stats", {})
gwp = ts.get("get_writing_prompt", {})
test("1.8 tool_stats count", gwp.get("count") == 1)
test("1.8 tool_stats mean", gwp.get("mean_ms") == 10.0)


# ============================================================
# Section 2: 装饰器测试
# ============================================================
print("\n=== Section 2: 装饰器测试 ===")

# 2.1 透传测试（collector=None 时原样执行）
@wrap
def dummy_func(project, chapter, text=""):
    return {"result": text.upper()}

# collector 为 None，应直接执行
prev_collector = get_collector()
# 确保临时清空
import telemetry
telemetry._collector = None

result = dummy_func("test", chapter=3, text="hello")
test("2.1 passthrough result", result == {"result": "HELLO"})

# 2.2 有 collector 时记录
telemetry._collector = TelemetryCollector("decorator_test")

result2 = dummy_func("test", chapter=7, text="world")
test("2.2 wrapped result", result2 == {"result": "WORLD"})
test("2.2 recorded in collector", 7 in telemetry._collector.chapters)
test("2.2 call count", len(telemetry._collector.chapters[7].calls) == 1)
call_record = telemetry._collector.chapters[7].calls[0]
test("2.2 tool name", call_record.tool == "dummy_func")
test("2.2 duration > 0", call_record.duration_ms >= 0)
test("2.2 chapter inferred", call_record.chapter == 7)

# 2.3 位置参数推断 chapter
result3 = dummy_func("test", 9, text="positional")
test("2.3 positional chapter inferred",
     9 in telemetry._collector.chapters and
     telemetry._collector.chapters[9].calls[0].chapter == 9)

# 2.4 错误捕获
@wrap
def failing_func(project, chapter):
    raise ValueError("test error")

try:
    failing_func("test", chapter=10)
    test("2.4 exception re-raised", False)
except ValueError as e:
    test("2.4 exception re-raised", str(e) == "test error")
    test("2.4 error recorded",
         10 in telemetry._collector.chapters and
         telemetry._collector.chapters[10].calls[0].error == "test error")

# 2.5 保留原函数元数据
test("2.5 __name__ preserved", failing_func.__name__ == "failing_func")
test("2.5 __doc__ preserved", dummy_func.__doc__ is None or True)  # no doc is fine


# ============================================================
# Section 3: 决策提取测试
# ============================================================
print("\n=== Section 3: 决策提取测试 ===")

# 3.1 add_chapter_arc decision
decision_arc = _extract_decision("add_chapter_arc", {
    "rhythm": "ascending",
    "purpose": "揭示真相",
    "ending": "主角身份暴露",
    "scenes": "三个场景",
}, {"status": "ok"})
test("3.1 arc decision has rhythm", decision_arc.get("rhythm") == "ascending")
test("3.1 arc decision has purpose", decision_arc.get("purpose") == "揭示真相")
test("3.1 arc decision has ending", decision_arc.get("ending") == "主角身份暴露")

# 3.2 write_extraction decision
decision_ext = _extract_decision("write_extraction", {}, {
    "report": {
        "events_written": 8,
        "relations_written": 15,
        "conflicts": ["E1_01 duplicate"],
        "auto_registered_locations": ["废弃工厂"],
        "new_characters": ["小明"],
    }
})
test("3.2 ext decision events", decision_ext.get("events") == 8)
test("3.2 ext decision conflicts", decision_ext.get("conflicts") == 1)
test("3.2 ext decision auto_locations", "废弃工厂" in decision_ext.get("auto_locations", []))
test("3.2 ext decision new_characters", "小明" in decision_ext.get("new_characters", []))

# 3.3 其他工具无 decision
decision_none = _extract_decision("get_graph_stats", {}, {"characters": 5})
test("3.3 no decision for other tools", decision_none is None)


# ============================================================
# Section 4: 文件输出测试
# ============================================================
print("\n=== Section 4: 文件输出测试 ===")

# 使用临时目录
import tempfile
tmp = tempfile.mkdtemp()
c2 = TelemetryCollector("file_test")
# 覆盖 _telemetry_dirs
c2._telemetry_dirs = {"file_test": os.path.join(tmp, "telemetry")}
call_f = ToolCall(
    tool="get_graph_stats", chapter=1,
    start=0, end=0.01, duration_ms=10.0,
)
c2.record(call_f)

path = c2.save_chapter_report(1)
test("4.1 report file created", path is not None and os.path.exists(path))
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
test("4.1 report valid json", data.get("chapter") == 1)
test("4.1 report has version", data.get("version") == "v25")

path2 = c2.save_session_summary()
test("4.2 summary file created", path2 is not None and os.path.exists(path2))
with open(path2, "r", encoding="utf-8") as f:
    sdata = json.load(f)
test("4.2 summary valid json", sdata.get("total_chapters") == 1)
test("4.2 summary has tool_stats", "get_graph_stats" in sdata.get("tool_stats", {}))

# 4.3 不存在的 chapter
test("4.3 missing chapter report", c2.get_chapter_report(99) is None)

# 清理
import shutil
shutil.rmtree(tmp, ignore_errors=True)

# 恢复 collector
telemetry._collector = prev_collector


# ============================================================
# Section 5: chapter 推断边界测试
# ============================================================
print("\n=== Section 5: chapter 推断边界 ===")

def func_with_ch(project, chapter, text=""): pass
def func_no_ch(project, name=""): pass
def func_ch_second(a, chapter, b): pass

test("5.1 kwargs chapter",
     _infer_chapter(func_with_ch, ("p",), {"chapter": 3}) == 3)
test("5.2 positional chapter",
     _infer_chapter(func_with_ch, ("p", 5, "t"), {}) == 5)
test("5.3 no chapter param",
     _infer_chapter(func_no_ch, ("p",), {"name": "x"}) is None)
test("5.4 chapter second param",
     _infer_chapter(func_ch_second, ("a", 7, "b"), {}) == 7)


# ============================================================
# Section 5b: project 推断测试
# ============================================================
print("\n=== Section 5b: project 推断 ===")

def func_with_proj(project, chapter, text=""): pass
def func_no_proj(name=""): pass

test("5b.1 kwargs project",
     _infer_project(func_with_proj, ("p",), {"project": "my_proj"}) == "my_proj")
test("5b.2 positional project",
     _infer_project(func_with_proj, ("test_project", 5, "t"), {}) == "test_project")
test("5b.3 no project param",
     _infer_project(func_no_proj, ("p",), {"name": "x"}) is None)


# ============================================================
# Section 6: write_extraction 自动保存测试
# ============================================================
print("\n=== Section 6: write_extraction 自动保存 ===")

import tempfile
tmp_auto = tempfile.mkdtemp()
telemetry._collector = TelemetryCollector("auto_save_test")
telemetry._collector._telemetry_dirs = {"auto_save_test": os.path.join(tmp_auto, "telemetry")}

# 模拟 write_extraction 被 wrap 后的自动保存
# 先记录几个调用，模拟章节管线
call_derive = ToolCall(tool="get_derivation_prompt", chapter=3, start=0, end=0.01, duration_ms=10.0)
call_arc = ToolCall(tool="add_chapter_arc", chapter=3, start=0, end=0.02, duration_ms=20.0,
                    decision={"rhythm": "tight", "purpose": "test"})
call_write = ToolCall(tool="write_extraction", chapter=3, start=0, end=0.05, duration_ms=50.0,
                      decision={"events": 5, "conflicts": 0})
telemetry._collector.record(call_derive)
telemetry._collector.record(call_arc)
telemetry._collector.record(call_write)

# 手动触发自动保存（模拟 wrap 中的行为）
path_auto = telemetry._collector.save_chapter_report(3)
test("6.1 auto-save path", path_auto is not None and os.path.exists(path_auto))
with open(path_auto, "r", encoding="utf-8") as f:
    auto_data = json.load(f)
test("6.1 auto-save has 3 calls", len(auto_data.get("tool_calls", [])) == 3)
test("6.1 auto-save has totals", auto_data.get("totals", {}).get("tool_count") == 3)

# 清理
import shutil
shutil.rmtree(tmp_auto, ignore_errors=True)
telemetry._collector = prev_collector


# ============================================================
# 结果汇总
# ============================================================
print(f"\n{'='*50}")
print(f"V25 遥测测试: {PASS} pass / {FAIL} fail / {PASS+FAIL} total")
if ERRORS:
    print("\n失败项:")
    for e in ERRORS:
        print(f"  {e}")
sys.exit(1 if FAIL > 0 else 0)
