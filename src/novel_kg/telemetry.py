"""
V25 管线遥测模块 — 纯观察者，零侵入。

用法：设置环境变量 NOVEL_TELEMETRY=1 激活。
core.py 底部通过 globals() 替换公共函数为 wrap() 包装版本。

输出：
  projects/<project>/telemetry/ch{N}_report.json   — 按章报告
  projects/<project>/telemetry/session_summary.json — 会话摘要
"""

import time
import json
import uuid
import os
import functools
import inspect
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


# ============================================================
# 数据结构
# ============================================================

@dataclass
class ToolCall:
    tool: str
    chapter: Optional[int]
    start: float
    end: float
    duration_ms: float
    llm_tokens: Optional[dict] = None
    decision: Optional[dict] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "tool": self.tool,
            "duration_ms": round(self.duration_ms, 1),
        }
        if self.llm_tokens:
            d["llm_tokens"] = self.llm_tokens
        if self.decision:
            d["decision"] = self.decision
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class ChapterSession:
    chapter: int
    calls: list = field(default_factory=list)
    wall_clock_ms: Optional[float] = None  # 子代理端到端耗时（含LLM）
    agent_tool_uses: Optional[int] = None  # 子代理MCP调用次数
    agent_phases: list = field(default_factory=list)  # 子代理阶段记录
    chapter_metrics: dict = field(default_factory=dict)  # 章节指标

    def to_dict(self) -> dict:
        total_ms = sum(c.duration_ms for c in self.calls)
        total_prompt = sum(
            (c.llm_tokens or {}).get("prompt_tokens", 0) for c in self.calls
        )
        total_completion = sum(
            (c.llm_tokens or {}).get("completion_tokens", 0) for c in self.calls
        )
        result = {
            "chapter": self.chapter,
            "tool_calls": [c.to_dict() for c in self.calls],
            "totals": {
                "duration_ms": round(total_ms, 1),
                "llm_prompt_tokens": total_prompt,
                "llm_completion_tokens": total_completion,
                "tool_count": len(self.calls),
            },
        }
        # 墙钟时间（子代理端到端，含LLM调用）
        if self.wall_clock_ms is not None:
            result["wall_clock_ms"] = round(self.wall_clock_ms, 1)
        if self.agent_tool_uses is not None:
            result["agent_tool_uses"] = self.agent_tool_uses
        if self.agent_phases:
            result["agent_phases"] = self.agent_phases
        if self.chapter_metrics:
            result["chapter_metrics"] = self.chapter_metrics
        return result


class TelemetryCollector:
    def __init__(self, project: str):
        self.session_id = uuid.uuid4().hex[:8]
        self.project = project
        self.start_time = time.perf_counter()
        self.chapters: dict[int, ChapterSession] = {}
        self.tool_stats: dict[str, list[float]] = {}
        self._telemetry_dirs: dict[str, str] = {}  # project -> dir path

    def _ensure_dir(self, project: str = None):
        proj = project or self.project
        if proj not in self._telemetry_dirs:
            here = os.path.dirname(os.path.abspath(__file__))
            repo_root = os.path.normpath(os.path.join(here, '..', '..'))
            self._telemetry_dirs[proj] = os.path.join(
                repo_root, 'projects', proj, 'telemetry'
            )
        os.makedirs(self._telemetry_dirs[proj], exist_ok=True)
        return self._telemetry_dirs[proj]

    def record(self, call: ToolCall):
        """记录一次工具调用。"""
        # 按 chapter 分组
        ch = call.chapter
        if ch is not None:
            if ch not in self.chapters:
                self.chapters[ch] = ChapterSession(chapter=ch)
            self.chapters[ch].calls.append(call)

        # 按工具名聚合
        name = call.tool
        if name not in self.tool_stats:
            self.tool_stats[name] = []
        self.tool_stats[name].append(call.duration_ms)

    def set_wall_clock(self, chapter: int, wall_clock_ms: float,
                       agent_tool_uses: int = None):
        """注入子代理端到端墙钟时间（主会话在子代理返回后调用）。"""
        if chapter not in self.chapters:
            self.chapters[chapter] = ChapterSession(chapter=chapter)
        self.chapters[chapter].wall_clock_ms = wall_clock_ms
        if agent_tool_uses is not None:
            self.chapters[chapter].agent_tool_uses = agent_tool_uses

    def inject_agent_phase(self, chapter: int, phase: str,
                           duration_ms: float, tool_uses: int = None):
        """注入子代理阶段遥测数据（写初稿/编辑/提取等）。"""
        if chapter not in self.chapters:
            self.chapters[chapter] = ChapterSession(chapter=chapter)
        phase_entry = {
            "phase": phase,
            "duration_ms": round(duration_ms, 1),
        }
        if tool_uses is not None:
            phase_entry["tool_uses"] = tool_uses
        self.chapters[chapter].agent_phases.append(phase_entry)

    def inject_chapter_metrics(self, chapter: int, metrics: dict):
        """注入章节指标（字数、编辑修正、图谱增量等）。"""
        if chapter not in self.chapters:
            self.chapters[chapter] = ChapterSession(chapter=chapter)
        self.chapters[chapter].chapter_metrics.update(metrics)

    def get_chapter_report(self, chapter: int) -> Optional[dict]:
        session = self.chapters.get(chapter)
        if session is None:
            return None
        report = session.to_dict()
        report["version"] = "v25"
        report["session_id"] = self.session_id
        report["timestamp"] = datetime.now().isoformat()
        return report

    def save_chapter_report(self, chapter: int, project: str = None) -> Optional[str]:
        report = self.get_chapter_report(chapter)
        if report is None:
            return None
        d = self._ensure_dir(project)
        path = os.path.join(d, f"ch{chapter}_report.json")

        # 文件累积：合并已有数据
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                existing_calls = existing.get("tool_calls", [])
                new_calls = report.get("tool_calls", [])
                # 去重：同名+同duration视为同一调用
                seen = {(c["tool"], c["duration_ms"]) for c in existing_calls}
                for c in new_calls:
                    if (c["tool"], c["duration_ms"]) not in seen:
                        existing_calls.append(c)
                report["tool_calls"] = existing_calls
                # 重算 totals
                report["totals"]["tool_count"] = len(existing_calls)
                report["totals"]["duration_ms"] = round(
                    sum(c["duration_ms"] for c in existing_calls), 1
                )
                # 合并 wall_clock / agent_tool_uses
                if "wall_clock_ms" in existing and "wall_clock_ms" not in report:
                    report["wall_clock_ms"] = existing["wall_clock_ms"]
                if "agent_tool_uses" in existing and "agent_tool_uses" not in report:
                    report["agent_tool_uses"] = existing["agent_tool_uses"]
                # 合并 agent_phases
                existing_phases = existing.get("agent_phases", [])
                new_phases = report.get("agent_phases", [])
                if existing_phases or new_phases:
                    # 去重：phase+duration_ms+tool_uses 视为同一阶段
                    phase_seen = {
                        (p["phase"], p["duration_ms"], p.get("tool_uses"))
                        for p in existing_phases
                    }
                    merged = list(existing_phases)
                    for p in new_phases:
                        key = (p["phase"], p["duration_ms"], p.get("tool_uses"))
                        if key not in phase_seen:
                            merged.append(p)
                            phase_seen.add(key)
                    report["agent_phases"] = merged
                # 合并 chapter_metrics（增量更新）
                existing_metrics = existing.get("chapter_metrics", {})
                new_metrics = report.get("chapter_metrics", {})
                if existing_metrics or new_metrics:
                    merged_metrics = dict(existing_metrics)
                    merged_metrics.update(new_metrics)
                    report["chapter_metrics"] = merged_metrics
            except (json.JSONDecodeError, KeyError):
                pass  # 文件损坏则覆盖

        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return path

    def get_session_summary(self) -> dict:
        # 统计所有调用（包括无 chapter 的）
        total_calls = sum(len(d) for d in self.tool_stats.values())
        # 从 chapters 中收集 token 和 per-chapter 数据
        chapter_calls = []
        for session in self.chapters.values():
            chapter_calls.extend(session.calls)

        total_prompt = sum(
            (c.llm_tokens or {}).get("prompt_tokens", 0) for c in chapter_calls
        )
        total_completion = sum(
            (c.llm_tokens or {}).get("completion_tokens", 0) for c in chapter_calls
        )

        per_tool = {}
        for name, durations in sorted(self.tool_stats.items()):
            per_tool[name] = {
                "count": len(durations),
                "total_ms": round(sum(durations), 1),
                "mean_ms": round(statistics.mean(durations), 1),
                "min_ms": round(min(durations), 1),
                "max_ms": round(max(durations), 1),
            }

        per_chapter = {}
        for ch_num, session in sorted(self.chapters.items()):
            total_ms = sum(c.duration_ms for c in session.calls)
            per_chapter[str(ch_num)] = round(total_ms, 1)

        return {
            "version": "v25",
            "session_id": self.session_id,
            "project": self.project,
            "started_at": datetime.now().isoformat(),
            "total_chapters": len(self.chapters),
            "total_tool_calls": total_calls,
            "total_duration_s": round(
                time.perf_counter() - self.start_time, 1
            ),
            "total_llm_tokens": {
                "prompt": total_prompt,
                "completion": total_completion,
            },
            "tool_stats": per_tool,
            "per_chapter_duration_ms": per_chapter,
        }

    def save_session_summary(self, project: str = None) -> str:
        summary = self.get_session_summary()
        summary["project"] = project or self.project
        d = self._ensure_dir(project)
        path = os.path.join(d, "session_summary.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        return path


# ============================================================
# 模块级单例
# ============================================================

_collector: Optional[TelemetryCollector] = None


def init_telemetry(project: str):
    """初始化遥测收集器。通常由 core.py 激活时自动调用。"""
    global _collector
    _collector = TelemetryCollector(project)


def get_collector() -> Optional[TelemetryCollector]:
    return _collector


# ============================================================
# 决策提取
# ============================================================

def _extract_decision(tool_name: str, kwargs: dict, result) -> Optional[dict]:
    """从特定工具的参数和返回值中提取决策数据。"""
    if tool_name == "add_chapter_arc" and result is not None:
        return {
            "rhythm": kwargs.get("rhythm", ""),
            "purpose": kwargs.get("purpose", ""),
            "ending": kwargs.get("ending", ""),
            "scenes": kwargs.get("scenes", ""),
        }

    if tool_name == "write_extraction" and isinstance(result, dict):
        report = result.get("report", result)
        stats = result.get("stats", {})
        return {
            "events": report.get("events_written", 0),
            "relations": report.get("relations_written", 0),
            "conflicts": len(report.get("conflicts", [])),
            "auto_locations": report.get("auto_registered_locations", []),
            "new_characters": report.get("new_characters", []),
            # 图谱增量
            "graph_delta": {
                "events_added": stats.get("events", 0),
                "relations_added": stats.get("relations", 0),
                "locations_added": stats.get("locations", 0),
                "characters_added": stats.get("characters", 0),
                "thread_updates": stats.get("thread_updates", 0),
                "new_threads": stats.get("new_threads", 0),
                "causal_links": stats.get("causal_links", 0),
                "evidence_links": stats.get("evidence_links", 0),
                "character_goals": stats.get("character_goals", 0),
            },
        }

    return None


# ============================================================
# 装饰器
# ============================================================

def _bind_args(func, args, kwargs) -> dict:
    """将位置参数绑定到函数签名，返回统一的 kwargs dict。

    server.py 用位置参数调 core.func(project, chapter, ...)，
    原始 kwargs 为空。此函数通过 inspect.Signature.bind()
    把位置参数映射到参数名，供决策提取等使用。
    """
    try:
        sig = inspect.signature(func)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)
    except (TypeError, ValueError):
        return dict(kwargs)


def _infer_chapter(bound_kwargs: dict) -> Optional[int]:
    """从绑定后的参数 dict 推断 chapter 编号。"""
    ch = bound_kwargs.get("chapter")
    if ch is not None:
        return int(ch) if not isinstance(ch, int) else ch
    return None


def _infer_project(bound_kwargs: dict) -> Optional[str]:
    """从绑定后的参数 dict 推断 project 名。"""
    proj = bound_kwargs.get("project")
    if proj is not None:
        return str(proj)
    return None


def _read_llm_usage() -> Optional[dict]:
    """读取 llm._last_usage（如果可访问）。"""
    try:
        # llm 在 novel_kg_mvp/ 目录下，通过 sys.path 可达
        import llm as _llm_mod
        usage = getattr(_llm_mod, '_last_usage', None)
        if usage:
            tokens = dict(usage)
            usage.clear()
            return tokens
    except ImportError:
        pass
    return None


def wrap(func):
    """装饰器工厂：包装 core.py 公共函数，记录遥测数据。

    注意：不在函数调用前检查 _collector is None，因为首次调用会
    通过 _kg() 懒初始化 collector。改为在 finally 中检查，确保
    首次调用也能被记录。
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        bound = _bind_args(func, args, kwargs)
        chapter = _infer_chapter(bound)
        start = time.perf_counter()
        error = None
        result = None
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            error = str(e)
            raise
        finally:
            # 首次调用时 _kg() 会初始化 collector，此处检查即可
            if _collector is not None:
                end = time.perf_counter()
                tokens = _read_llm_usage()
                call = ToolCall(
                    tool=func.__name__,
                    chapter=chapter,
                    start=start,
                    end=end,
                    duration_ms=(end - start) * 1000,
                    llm_tokens=tokens,
                    decision=_extract_decision(func.__name__, bound, result),
                    error=error,
                )
                _collector.record(call)
                # V26: 有 chapter 的命令都自动保存（文件累积模式）
                if chapter is not None:
                    try:
                        project = _infer_project(bound)
                        _collector.save_chapter_report(chapter, project=project)
                    except Exception as _save_err:
                        import sys as _sys
                        _sys.stderr.write(f"[telemetry] auto-save failed: {_save_err}\n")
                        _sys.stderr.flush()

    return wrapper
