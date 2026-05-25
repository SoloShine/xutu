"""
核心并行生成模块 — 依赖分析、批次准备、并行 prompt、结果合并。

从 core.py 拆分，V27。
"""

import uuid
from copy import deepcopy

from .core import _kg, config_loader, _persist
from .core_errors import UserError, SystemError
from .main import build_writing_prompt
from .core_crud import write_extraction

# 内存中的冻结上下文缓存
_frozen_batches: dict = {}


def analyze_parallel_groups(project: str) -> dict:
    """分析章节依赖关系，返回可并行分组。"""
    kg = _kg(project)
    outlines = kg.get_all_outline_entries()
    if not outlines:
        return {"dependency_graph": {}, "parallel_groups": [],
                "max_parallelism": 1, "estimated_speedup": "1.0x",
                "warnings": ["无大纲条目"]}

    chapters = sorted([oe.get("chapter", 0) for oe in outlines if oe.get("chapter", 0) > 0])
    if not chapters:
        return {"dependency_graph": {}, "parallel_groups": [],
                "max_parallelism": 1, "estimated_speedup": "1.0x",
                "warnings": ["无有效章节号"]}

    dep_graph = {}
    for ch in chapters:
        dep_graph[ch] = {"depends_on": [], "dependents": []}

    for i in range(len(chapters) - 1):
        a, b = chapters[i], chapters[i + 1]
        if b - a == 1:
            dep_graph[b]["depends_on"].append(a)
            dep_graph[a]["dependents"].append(b)

    thread_map = {}
    all_threads = kg.get_all_threads()
    for t in all_threads:
        tid = t.get("thread_id", "")
        planted = t.get("planted_chapter", 0)
        if tid and planted:
            thread_map[tid] = planted

    for oe in outlines:
        ch = oe.get("chapter", 0)
        deps = oe.get("parallel_dependencies", [])
        if isinstance(deps, list):
            for dep in deps:
                if dep in dep_graph and dep != ch:
                    if dep not in dep_graph[ch]["depends_on"]:
                        dep_graph[ch]["depends_on"].append(dep)
                    if ch not in dep_graph[dep]["dependents"]:
                        dep_graph[dep]["dependents"].append(ch)

    has_groups = any(oe.get("parallel_group") for oe in outlines)
    warnings = []

    if not has_groups:
        groups = []
        for i, ch in enumerate(chapters):
            groups.append({
                "group_id": i,
                "chapters": [ch],
                "can_parallel": False,
                "reason": "无并行标记或相邻章节",
            })
        max_par = 1
        speedup = "1.0x"
        warnings.append("未设置 parallel_group，全部串行。"
                        "在 outline_entry 中设置 parallel_group 可启用并行。")
    else:
        group_map = {}
        for oe in outlines:
            ch = oe.get("chapter", 0)
            grp = oe.get("parallel_group", "")
            if grp:
                group_map.setdefault(grp, []).append(ch)

        for ch in chapters:
            assigned = any(ch in gchs for gchs in group_map.values())
            if not assigned:
                group_map[f"_solo_{ch}"] = [ch]

        for grp_name, gchs in list(group_map.items()):
            sorted_gchs = sorted(gchs)
            for i in range(len(sorted_gchs) - 1):
                if sorted_gchs[i + 1] - sorted_gchs[i] == 1:
                    warnings.append(
                        f"组 '{grp_name}' 包含相邻章节 {sorted_gchs[i]} 和 {sorted_gchs[i+1]}，"
                        f"无法并行，将拆分为串行。")
                    group_map[f"{grp_name}_{sorted_gchs[i]}"] = [sorted_gchs[i]]
                    group_map[f"{grp_name}_{sorted_gchs[i+1]}"] = [sorted_gchs[i+1]]
                    del group_map[grp_name]
                    break

        remaining = set(chapters)
        groups = []
        group_id = 0
        while remaining:
            ready = []
            for ch in sorted(remaining):
                deps = dep_graph[ch]["depends_on"]
                if all(d not in remaining for d in deps):
                    ready.append(ch)

            if not ready:
                warnings.append(f"检测到依赖环路，剩余章节: {sorted(remaining)}")
                break

            can_parallel = len(ready) > 1
            if can_parallel:
                for i in range(len(ready) - 1):
                    if ready[i + 1] - ready[i] == 1:
                        can_parallel = False
                        break

            reason = ""
            if can_parallel:
                ready_groups = set()
                for ch in ready:
                    oe = kg.get_outline_entry(ch)
                    ready_groups.add(oe.get("parallel_group", "") if oe else "")
                if len(ready_groups) <= 1:
                    can_parallel = False
                    reason = "同组章节"
                else:
                    reason = f"不同并行组: {', '.join(str(g) for g in ready_groups)}"
            else:
                reason = "相邻章节或无并行组标记"

            groups.append({
                "group_id": group_id,
                "chapters": ready,
                "can_parallel": can_parallel,
                "reason": reason,
            })
            remaining -= set(ready)
            group_id += 1

        max_par = max((len(g["chapters"]) for g in groups), default=1)
        if max_par <= 1:
            speedup = "1.0x"
        else:
            seq_time = len(chapters)
            par_time = len(groups)
            speedup = f"{seq_time / max(par_time, 1):.1f}x"

    for g in groups:
        if g["can_parallel"] and len(g["chapters"]) > 1:
            gid = f"batch_{g['group_id']}"
            kg.add_parallel_group(gid, g["chapters"],
                                  reason=g.get("reason", ""))

    return {
        "dependency_graph": dep_graph,
        "parallel_groups": groups,
        "max_parallelism": max_par,
        "estimated_speedup": speedup,
        "warnings": warnings,
    }


def prepare_parallel_batch(project: str, chapters: list) -> dict:
    """为并行组创建图谱快照并预冻结每章的上下文。"""
    kg = _kg(project)
    snapshot_id = kg.snapshot_full_graph(reason=f"parallel_batch {chapters}")
    batch_id = f"batch_{uuid.uuid4().hex[:8]}"

    frozen = {}
    conflicts = []
    chapters = [int(c) for c in chapters]
    for ch in chapters:
        ctx = kg.get_context_for_chapter(ch, prev_text_chars=0)
        prev_ch = ch - 1
        if prev_ch > 0 and prev_ch not in chapters:
            prev_text = kg.get_chapter_text(prev_ch)
            cfg = config_loader.load(project)
            ptc = config_loader.get(project, "writing", "prev_text_chars", default=500)
            if prev_text and len(prev_text) > ptc:
                prev_text = prev_text[-ptc:]
            ctx["prev_chapter_text"] = prev_text
        elif prev_ch in chapters:
            arc = kg._graph["chapter_arcs"].get(str(prev_ch))
            if arc:
                ctx["prev_chapter_text"] = (
                    f"[弧线锚点：前章（Ch{prev_ch}）尚未生成，以下为弧线结尾锚点]\n"
                    f"{arc.get('ending', '（无结尾锚点）')}"
                )
                ctx["_parallel_note"] = "prev_text_from_arc_ending"
            else:
                ctx["prev_chapter_text"] = None
                conflicts.append(
                    f"Ch{ch}: 前一章Ch{prev_ch}在并行组中但无弧线ending锚点"
                )
        frozen[ch] = deepcopy(ctx)

    _frozen_batches[batch_id] = {
        "project": project,
        "snapshot_id": snapshot_id,
        "chapters": chapters,
        "contexts": frozen,
    }

    return {
        "batch_id": batch_id,
        "snapshot_id": snapshot_id,
        "frozen_contexts": {ch: list(ctx.keys()) for ch, ctx in frozen.items()},
        "conflicts_preview": conflicts,
    }


def get_parallel_writing_prompt(project: str, chapter: int,
                                batch_id: str) -> str:
    """使用冻结上下文生成写作 prompt（并行模式）。"""
    if batch_id not in _frozen_batches:
        return UserError(
            f"batch_id '{batch_id}' 不存在或已过期。请先调用 prepare_parallel_batch。",
            code="BATCH_EXPIRED"
        ).to_dict()

    batch = _frozen_batches[batch_id]
    if batch["project"] != project:
        return UserError(
            f"batch_id '{batch_id}' 属于项目 '{batch['project']}'，不匹配 '{project}'。",
            code="BATCH_EXPIRED"
        ).to_dict()

    if chapter not in batch["contexts"]:
        return UserError(
            f"章节 {chapter} 不在 batch '{batch_id}' 的冻结上下文中。",
            code="NOT_FOUND"
        ).to_dict()

    ctx = batch["contexts"][chapter]
    cfg = config_loader.load(project)
    prompt = build_writing_prompt(ctx, chapter, config=cfg)
    _persist(project, "prompts", f"parallel_writing_ch{chapter}.txt", prompt)
    return prompt


def merge_parallel_results(project: str, batch_id: str,
                           results: dict) -> dict:
    """合并并行生成结果到图谱（串行写入，冲突检测）。"""
    try:
        if batch_id not in _frozen_batches:
            return UserError(f"batch_id '{batch_id}' 不存在", code="BATCH_EXPIRED").to_dict()

        batch = _frozen_batches[batch_id]
        if batch["project"] != project:
            return UserError(f"batch 项目不匹配", code="BATCH_EXPIRED").to_dict()

        kg = _kg(project)
        merged = []
        conflicts = []

        norm_results = {}
        for k, v in results.items():
            norm_results[int(k)] = v

        for ch in sorted(norm_results.keys()):
            if ch not in batch["contexts"]:
                conflicts.append(f"Ch{ch}: 不在本批中，跳过")
                continue

            ch_result = norm_results[ch]
            text = ch_result.get("text", "")
            if text:
                kg.save_chapter_text(ch, text)

            ext_json = ch_result.get("extraction_json", "")
            if ext_json:
                write_report = write_extraction(project, ch, ext_json)
                if write_report.get("conflicts"):
                    for c in write_report["conflicts"]:
                        conflicts.append(f"Ch{ch}: {c}")
            merged.append(ch)

        from .core_crud import check_consistency
        consistency = check_consistency(project)
        del _frozen_batches[batch_id]

        return {
            "merged_chapters": merged,
            "conflicts_found": conflicts,
            "post_merge_consistency": consistency,
        }
    except Exception as e:
        return SystemError(
            f"merge_parallel_results 异常: {e}",
            code="INTERNAL"
        ).to_dict()
