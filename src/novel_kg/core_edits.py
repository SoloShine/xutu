"""
核心编辑管理模块 — 事后编辑采纳、审核关卡、快照管理、回滚。

从 core.py 拆分，V27。
"""

import json
import os

from .core import _kg, _check_destructive, DESTRUCTIVE_CONFIRM
from .core_cache import invalidate_purpose_cache
from .core_errors import UserError, SystemError, LogicError
from .mine import (
    write_extraction_to_graph,
    clear_chapter_data as _mine_clear_chapter,
)


def accept_edit(project: str, chapter: int, extracted_json: str,
                confirm: str = "") -> dict:
    """采纳事后编辑：快照旧数据 → 清除 → 写入新数据 → 标记后续大纲。"""
    err = _check_destructive(confirm)
    if err:
        return err.to_dict()

    kg = _kg(project)
    snapshot_id = kg.snapshot_chapter(chapter, reason=f"accept_edit ch{chapter}")
    _mine_clear_chapter(kg, chapter)
    invalidate_purpose_cache(project, chapter)

    if isinstance(extracted_json, str):
        extracted = json.loads(extracted_json)
    else:
        extracted = extracted_json
    report = write_extraction_to_graph(kg, chapter, extracted,
                                        skip_conflicts=True, project=project)

    all_outlines = kg.get_all_outline_entries()
    marked = []
    for oe in all_outlines:
        ch = oe.get("chapter", 0)
        if ch > chapter:
            existing = kg.get_outline_entry(ch)
            if existing and existing.get("compliance") != "overridden":
                kg.add_outline_entry(ch, **{
                    k: v for k, v in existing.items()
                    if k != "chapter"
                }, compliance="needs_revision")
                marked.append(ch)

    return {
        "chapter": chapter,
        "stats": report["stats"],
        "conflicts": report["conflicts"],
        "downstream_marked_for_revision": marked,
        "snapshot_id": snapshot_id,
        "message": f"已采纳第{chapter}章编辑。快照: {snapshot_id}。后续章节 {marked} 的大纲标记为 needs_revision。",
    }


def review_chapter(project: str, chapter: int, action: str,
                   edited_text: str = "") -> dict:
    """审核关卡操作。"""
    kg = _kg(project)
    valid_actions = {"accept", "edit", "rewrite", "revise_outline"}
    if action not in valid_actions:
        return UserError(
            f"未知操作 '{action}'，可选: {', '.join(sorted(valid_actions))}",
            code="BAD_PARAM"
        ).to_dict()

    if action == "accept":
        return {
            "action": "accept",
            "chapter": chapter,
            "message": f"第{chapter}章已通过审核。可以继续第{chapter+1}章。",
        }

    if action in ("edit", "rewrite"):
        if not edited_text:
            return UserError(
                f"action='{action}' 需要 edited_text 参数",
                code="MISSING_PARAM"
            ).to_dict()
        output_dir = os.path.join(os.path.dirname(kg._path), "output")
        os.makedirs(output_dir, exist_ok=True)
        edited_path = os.path.join(output_dir, f"ch{chapter}_edited.txt")
        with open(edited_path, "w", encoding="utf-8") as f:
            f.write(edited_text)

        if action == "rewrite":
            return {
                "action": "rewrite",
                "chapter": chapter,
                "message": f"第{chapter}章已保存编辑版本。请重新提取并调用 accept_edit 写入图谱。",
                "edited_path": edited_path,
            }
        else:
            return {
                "action": "edit",
                "chapter": chapter,
                "message": f"第{chapter}章小修已保存。可调用 analyze_edit_impact 检查影响。",
                "edited_path": edited_path,
            }

    if action == "revise_outline":
        return {
            "action": "revise_outline",
            "chapter": chapter,
            "message": f"请调用 revise_outline 修订第{chapter}章大纲，然后继续。",
        }

    return LogicError("unreachable: review_chapter 应在此前返回", code="INTERNAL").to_dict()


def list_edits(project: str, chapter: int = None) -> dict:
    """列出章节编辑快照历史。"""
    kg = _kg(project)
    snapshots = kg.list_snapshots(chapter=chapter)
    return {
        "project": project,
        "filter_chapter": chapter,
        "total": len(snapshots),
        "snapshots": snapshots,
    }


def rollback_edit(project: str, snapshot_id: str,
                  confirm: str = "",
                  clear_revision_marks: bool = True) -> dict:
    """回滚到指定快照版本。"""
    err = _check_destructive(confirm)
    if err:
        return err.to_dict()

    kg = _kg(project)
    snap = kg.get_snapshot(snapshot_id)
    if not snap:
        return UserError(
            f"快照 '{snapshot_id}' 不存在。请用 list_edits 查看可用快照。",
            code="NOT_FOUND"
        ).to_dict()

    chapter = snap["chapter"]
    event_count = len(snap.get("events", {}))
    relation_count = len(snap.get("relations", []))

    new_snap = kg.snapshot_chapter(
        chapter, reason=f"rollback to {snapshot_id}")

    success = kg.restore_snapshot(snapshot_id)
    if not success:
        return SystemError(
            f"恢复快照 '{snapshot_id}' 失败。",
            code="BACKEND_ERROR"
        ).to_dict()

    invalidate_purpose_cache(project, chapter)

    cleared = []
    if clear_revision_marks:
        all_outlines = kg.get_all_outline_entries()
        for oe in all_outlines:
            ch = oe.get("chapter", 0)
            if ch > chapter and oe.get("compliance") == "needs_revision":
                existing = kg.get_outline_entry(ch)
                if existing:
                    kg.add_outline_entry(ch, **{
                        k: v for k, v in existing.items()
                        if k not in ("chapter", "compliance")
                    }, compliance="")
                    cleared.append(ch)

    msg = (f"已回滚第{chapter}章到快照 {snapshot_id} "
           f"({event_count}事件, {relation_count}关系)。"
           f"回滚前快照: {new_snap}")
    if cleared:
        msg += f" 已清除 {len(cleared)} 个下游大纲的needs_revision标记。"

    return {
        "snapshot_id": snapshot_id,
        "chapter": chapter,
        "restored_events": event_count,
        "restored_relations": relation_count,
        "pre_rollback_snapshot": new_snap,
        "revision_marks_cleared": cleared,
        "message": msg,
    }
