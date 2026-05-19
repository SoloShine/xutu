"""
Novel KG 工具 CLI — MCP 的 Bash 替代方案

用法:
  python mcp_cli.py <tool_name> [参数...]

示例:
  python mcp_cli.py get_graph_stats --project v11_test
  python mcp_cli.py get_chapter_context --project v11_test --chapter 5
  python mcp_cli.py get_writing_prompt --project v11_test --chapter 5
  python mcp_cli.py get_extraction_prompt --project v11_test --chapter 5 --text-file ../projects/v11_test/output/ch4_generated.txt
  python mcp_cli.py get_derivation_prompt --project v11_test --chapter 6
  python mcp_cli.py validate_chapter --project v11_test --chapter 5 --text-file ../projects/v11_test/output/ch5_generated.txt
  python mcp_cli.py write_extraction --project v11_test --chapter 5 --json-file ../projects/v11_test/extractions/extraction_ch5.json
  python mcp_cli.py add_character --project v11_test --name 张三 --role 配角 --personality 沉默寡言
  python mcp_cli.py init_project --project new_project
  python mcp_cli.py get_unresolved_threads --project v11_test --chapter 6
  python mcp_cli.py get_all_threads --project v11_test
  python mcp_cli.py check_consistency --project v11_test
  python mcp_cli.py add_chapter_arc --project v11_test --chapter 6 --purpose "xxx" --scenes "A->B" --ending "xxx"
  python mcp_cli.py add_suspense_thread --project v11_test --thread-id ST06_01 --content "悬念内容" --planted-chapter 6
  python mcp_cli.py update_suspense_thread --project v11_test --thread-id ST01 --status resolved
  python mcp_cli.py clear_chapter_data --project v11_test --chapter 5
"""

import sys
import os
import json
import argparse

# 添加 novel_kg_mvp 到 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'novel_kg_mvp'))

from graph import NovelKG
from mine import (
    build_extraction_prompt, detect_conflicts,
    write_extraction_to_graph, clear_chapter_data as _clear_chapter
)
from main import build_writing_prompt
from prompts import ARC_DERIVATION_PROMPT
from validators import validate_chapter as _run_validation


def _kg(project):
    return NovelKG(project=project)


def _out(data):
    """统一JSON输出"""
    if isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


# ========== 查询工具 ==========

def cmd_get_graph_stats(args):
    kg = _kg(args.project)
    try:
        _out(kg.stats())
    finally:
        kg.close()

def cmd_get_chapter_context(args):
    kg = _kg(args.project)
    try:
        _out(kg.get_context_for_chapter(args.chapter))
    finally:
        kg.close()

def cmd_get_derivation_context(args):
    kg = _kg(args.project)
    try:
        _out(kg.get_arc_derivation_context(args.chapter, lookback=args.lookback))
    finally:
        kg.close()

def cmd_get_unresolved_threads(args):
    kg = _kg(args.project)
    try:
        _out(kg.get_unresolved_threads(args.chapter))
    finally:
        kg.close()

def cmd_get_all_threads(args):
    kg = _kg(args.project)
    try:
        _out(kg.get_all_threads())
    finally:
        kg.close()

def cmd_check_consistency(args):
    kg = _kg(args.project)
    try:
        _out(kg.check_consistency())
    finally:
        kg.close()


# ========== Prompt工具 ==========

def cmd_get_extraction_prompt(args):
    kg = _kg(args.project)
    try:
        with open(args.text_file, 'r', encoding='utf-8') as f:
            text = f.read()
        prompt = build_extraction_prompt(kg, args.chapter, text)
        print(prompt)
    finally:
        kg.close()

def cmd_get_writing_prompt(args):
    kg = _kg(args.project)
    try:
        context = kg.get_context_for_chapter(args.chapter)
        prompt = build_writing_prompt(context, args.chapter)
        print(prompt)
    finally:
        kg.close()

def cmd_get_derivation_prompt(args):
    kg = _kg(args.project)
    try:
        ctx = kg.get_arc_derivation_context(args.chapter)
        arcs_text = json.dumps(
            [{k: v for k, v in a.items() if k != "chapter"} for a in ctx["recent_arcs"]],
            ensure_ascii=False, indent=2)
        events_text = json.dumps(
            [{"id": e["id"], "title": e.get("title", ""), "type": e.get("type", ""),
              "detail": e.get("detail", "")} for e in ctx["recent_events"]],
            ensure_ascii=False, indent=2)
        chars_text = json.dumps(
            [{"name": c["name"], "role": c.get("role", ""), "personality": c.get("personality", "")}
             for c in ctx["characters"]], ensure_ascii=False, indent=2)
        themes_text = json.dumps(
            [{"name": t["name"], "description": t.get("description", ""), "chapters": t.get("chapters", "")}
             for t in ctx["themes"]], ensure_ascii=False, indent=2)
        motifs_text = json.dumps(
            [{"name": m["name"], "meaning": m.get("meaning", ""), "evolution": m.get("evolution", "")}
             for m in ctx["motifs"]], ensure_ascii=False, indent=2)
        last_event_text = json.dumps(ctx["last_event"], ensure_ascii=False, indent=2) if ctx["last_event"] else "无"
        outline_text = json.dumps(ctx.get("outline_entry"), ensure_ascii=False, indent=2) if ctx.get("outline_entry") else "无"
        threads_text = json.dumps(
            [{"id": t.get("id", ""), "content": t.get("content", ""), "status": t.get("status", ""),
              "importance": t.get("importance", "")} for t in ctx.get("suspense_threads", [])],
            ensure_ascii=False, indent=2) if ctx.get("suspense_threads") else "无"

        prompt = ARC_DERIVATION_PROMPT.format(
            outline_entry=outline_text, suspense_threads=threads_text,
            recent_arcs=arcs_text, recent_events=events_text,
            characters=chars_text, themes=themes_text, motifs=motifs_text,
            last_event=last_event_text)
        print(prompt)
    finally:
        kg.close()


# ========== 校验工具 ==========

def cmd_validate_chapter(args):
    kg = _kg(args.project)
    try:
        with open(args.text_file, 'r', encoding='utf-8') as f:
            text = f.read()
        context = kg.get_context_for_chapter(args.chapter)
        arc = context.get("chapter_arc", [None])
        arc = arc[0] if arc else None
        result = _run_validation(text, context, arc=arc)
        _out({
            "passed": result.passed,
            "violations": [
                {"type": v.constraint_type, "severity": v.severity,
                 "detail": v.detail, "fix": v.fix}
                for v in result.violations
            ]
        })
    finally:
        kg.close()

def cmd_detect_conflicts(args):
    kg = _kg(args.project)
    try:
        with open(args.json_file, 'r', encoding='utf-8') as f:
            extracted = json.load(f)
        _out(detect_conflicts(kg, extracted))
    finally:
        kg.close()


# ========== 写入工具 ==========

def cmd_init_project(args):
    kg = _kg(args.project)
    try:
        kg.clear_project()
        print(f"项目 '{args.project}' 图谱已清空")
    finally:
        kg.close()

def cmd_write_extraction(args):
    kg = _kg(args.project)
    try:
        with open(args.json_file, 'r', encoding='utf-8') as f:
            extracted = json.load(f)
        report = write_extraction_to_graph(kg, args.chapter, extracted, skip_conflicts=True)
        _out({
            "chapter": report["chapter"],
            "stats": report["stats"],
            "conflicts": report["conflicts"],
            "character_updates": report.get("character_updates", []),
            "notes": report.get("notes", ""),
        })
    finally:
        kg.close()

def cmd_clear_chapter_data(args):
    kg = _kg(args.project)
    try:
        _clear_chapter(kg, args.chapter)
        print(f"已清除第{args.chapter}章事件数据")
    finally:
        kg.close()

def cmd_add_character(args):
    kg = _kg(args.project)
    try:
        props = {}
        if args.role: props["role"] = args.role
        if args.personality: props["personality"] = args.personality
        kg.add_character(args.name, **props)
        print(f"已添加人物: {args.name}")
    finally:
        kg.close()

def cmd_add_location(args):
    kg = _kg(args.project)
    try:
        props = {}
        if args.loc_type: props["type"] = args.loc_type
        if args.description: props["description"] = args.description
        kg.add_location(args.name, **props)
        print(f"已添加地点: {args.name}")
    finally:
        kg.close()

def cmd_add_event(args):
    kg = _kg(args.project)
    try:
        props = {"type": args.event_type, "is_gap": args.is_gap, "gap_level": args.gap_level}
        if args.title: props["title"] = args.title
        if args.detail: props["detail"] = args.detail
        if args.chapter: props["chapter"] = args.chapter
        kg.add_event(args.event_id, **props)
        print(f"已添加事件: {args.event_id}")
    finally:
        kg.close()

def cmd_add_chapter_arc(args):
    kg = _kg(args.project)
    try:
        props = {"purpose": args.purpose, "scenes": args.scenes, "ending": args.ending}
        if args.gap_note: props["gap_note"] = args.gap_note
        if args.structure_type and args.structure_type != "linear":
            props["structure_type"] = args.structure_type
        kg.add_chapter_arc(args.chapter, **props)
        print(f"已添加第{args.chapter}章弧线: {args.purpose}")
    finally:
        kg.close()

def cmd_add_suspense_thread(args):
    kg = _kg(args.project)
    try:
        kg.add_suspense_thread(args.thread_id, content=args.content,
                               planted_chapter=args.planted_chapter,
                               importance=args.importance,
                               thread_type=args.thread_type, status="planted")
        print(f"已添加悬念线: {args.thread_id}")
    finally:
        kg.close()

def cmd_update_suspense_thread(args):
    kg = _kg(args.project)
    try:
        props = {}
        if args.status: props["status"] = args.status
        if args.importance: props["importance"] = args.importance
        kg.update_suspense_thread(args.thread_id, **props)
        print(f"已更新悬念线: {args.thread_id}")
    finally:
        kg.close()

def cmd_add_outline_entry(args):
    kg = _kg(args.project)
    try:
        props = {"purpose": args.purpose}
        if args.key_events: props["key_events"] = args.key_events
        if args.threads_to_plant: props["threads_to_plant"] = args.threads_to_plant
        if args.threads_to_resolve: props["threads_to_resolve"] = args.threads_to_resolve
        if args.structure_hint: props["structure_hint"] = args.structure_hint
        kg.add_outline_entry(args.chapter, **props)
        print(f"已添加第{args.chapter}章大纲")
    finally:
        kg.close()

def cmd_add_style_guide(args):
    kg = _kg(args.project)
    try:
        kg.add_style_guide(args.guide_id, rule=args.rule)
        print(f"已添加风格规则: {args.guide_id}")
    finally:
        kg.close()

def cmd_add_motif(args):
    kg = _kg(args.project)
    try:
        props = {}
        if args.meaning: props["meaning"] = args.meaning
        if args.evolution: props["evolution"] = args.evolution
        kg.add_motif(args.name, **props)
        print(f"已添加意象: {args.name}")
    finally:
        kg.close()

def cmd_add_theme(args):
    kg = _kg(args.project)
    try:
        props = {}
        if args.description: props["description"] = args.description
        if args.chapters: props["chapters"] = args.chapters
        kg.add_theme(args.name, **props)
        print(f"已添加主题: {args.name}")
    finally:
        kg.close()

def cmd_add_time_period(args):
    kg = _kg(args.project)
    try:
        props = {"chapter_start": args.chapter_start, "chapter_end": args.chapter_end}
        if args.years: props["years"] = args.years
        if args.theme: props["theme"] = args.theme
        kg.add_time_period(args.label, **props)
        print(f"已添加时间段: {args.label}")
    finally:
        kg.close()


# ========== CLI注册 ==========

def build_parser():
    p = argparse.ArgumentParser(description='Novel KG 工具 CLI')
    sub = p.add_subparsers(dest='command')

    # 通用参数
    def _add_project(sp):
        sp.add_argument('--project', '-p', required=True)

    def _add_chapter(sp):
        sp.add_argument('--chapter', '-ch', type=int, required=True)

    # 查询
    for name, fn in [('get_graph_stats', cmd_get_graph_stats),
                     ('get_chapter_context', cmd_get_chapter_context),
                     ('get_derivation_context', cmd_get_derivation_context),
                     ('get_unresolved_threads', cmd_get_unresolved_threads),
                     ('get_all_threads', cmd_get_all_threads),
                     ('check_consistency', cmd_check_consistency)]:
        sp = sub.add_parser(name)
        _add_project(sp)
        sp.set_defaults(func=fn)
        if name in ('get_chapter_context', 'get_derivation_context', 'get_unresolved_threads'):
            _add_chapter(sp)
        if name == 'get_derivation_context':
            sp.add_argument('--lookback', type=int, default=3)

    # Prompt
    for name, fn in [('get_extraction_prompt', cmd_get_extraction_prompt),
                     ('get_writing_prompt', cmd_get_writing_prompt),
                     ('get_derivation_prompt', cmd_get_derivation_prompt)]:
        sp = sub.add_parser(name)
        _add_project(sp)
        _add_chapter(sp)
        sp.set_defaults(func=fn)
        if name == 'get_extraction_prompt':
            sp.add_argument('--text-file', '-f', required=True)

    # 校验
    sp = sub.add_parser('validate_chapter')
    _add_project(sp); _add_chapter(sp)
    sp.add_argument('--text-file', '-f', required=True)
    sp.set_defaults(func=cmd_validate_chapter)

    sp = sub.add_parser('detect_conflicts')
    _add_project(sp)
    sp.add_argument('--json-file', '-f', required=True)
    sp.set_defaults(func=cmd_detect_conflicts)

    # 写入
    sp = sub.add_parser('init_project')
    _add_project(sp)
    sp.set_defaults(func=cmd_init_project)

    sp = sub.add_parser('write_extraction')
    _add_project(sp); _add_chapter(sp)
    sp.add_argument('--json-file', '-f', required=True)
    sp.set_defaults(func=cmd_write_extraction)

    sp = sub.add_parser('clear_chapter_data')
    _add_project(sp); _add_chapter(sp)
    sp.set_defaults(func=cmd_clear_chapter_data)

    sp = sub.add_parser('add_character')
    _add_project(sp)
    sp.add_argument('--name', required=True)
    sp.add_argument('--role', default='')
    sp.add_argument('--personality', default='')
    sp.set_defaults(func=cmd_add_character)

    sp = sub.add_parser('add_location')
    _add_project(sp)
    sp.add_argument('--name', required=True)
    sp.add_argument('--loc-type', default='')
    sp.add_argument('--description', default='')
    sp.set_defaults(func=cmd_add_location)

    sp = sub.add_parser('add_event')
    _add_project(sp)
    sp.add_argument('--event-id', required=True)
    sp.add_argument('--chapter', type=int, default=0)
    sp.add_argument('--title', default='')
    sp.add_argument('--detail', default='')
    sp.add_argument('--event-type', default='daily')
    sp.add_argument('--is-gap', action='store_true')
    sp.add_argument('--gap-level', type=int, default=0)
    sp.set_defaults(func=cmd_add_event)

    sp = sub.add_parser('add_chapter_arc')
    _add_project(sp); _add_chapter(sp)
    sp.add_argument('--purpose', required=True)
    sp.add_argument('--scenes', required=True)
    sp.add_argument('--ending', required=True)
    sp.add_argument('--gap-note', default='')
    sp.add_argument('--structure-type', default='linear')
    sp.set_defaults(func=cmd_add_chapter_arc)

    sp = sub.add_parser('add_suspense_thread')
    _add_project(sp)
    sp.add_argument('--thread-id', required=True)
    sp.add_argument('--content', required=True)
    sp.add_argument('--planted-chapter', type=int, required=True)
    sp.add_argument('--importance', default='medium')
    sp.add_argument('--thread-type', default='foreshadowing')
    sp.set_defaults(func=cmd_add_suspense_thread)

    sp = sub.add_parser('update_suspense_thread')
    _add_project(sp)
    sp.add_argument('--thread-id', required=True)
    sp.add_argument('--status', default='')
    sp.add_argument('--importance', default='')
    sp.set_defaults(func=cmd_update_suspense_thread)

    sp = sub.add_parser('add_outline_entry')
    _add_project(sp); _add_chapter(sp)
    sp.add_argument('--purpose', required=True)
    sp.add_argument('--key-events', default='')
    sp.add_argument('--threads-to-plant', default='')
    sp.add_argument('--threads-to-resolve', default='')
    sp.add_argument('--structure-hint', default='')
    sp.set_defaults(func=cmd_add_outline_entry)

    sp = sub.add_parser('add_style_guide')
    _add_project(sp)
    sp.add_argument('--guide-id', required=True)
    sp.add_argument('--rule', required=True)
    sp.set_defaults(func=cmd_add_style_guide)

    sp = sub.add_parser('add_motif')
    _add_project(sp)
    sp.add_argument('--name', required=True)
    sp.add_argument('--meaning', default='')
    sp.add_argument('--evolution', default='')
    sp.set_defaults(func=cmd_add_motif)

    sp = sub.add_parser('add_theme')
    _add_project(sp)
    sp.add_argument('--name', required=True)
    sp.add_argument('--description', default='')
    sp.add_argument('--chapters', default='')
    sp.set_defaults(func=cmd_add_theme)

    sp = sub.add_parser('add_time_period')
    _add_project(sp)
    sp.add_argument('--label', required=True)
    sp.add_argument('--chapter-start', type=int, required=True)
    sp.add_argument('--chapter-end', type=int, required=True)
    sp.add_argument('--years', default='')
    sp.add_argument('--theme', default='')
    sp.set_defaults(func=cmd_add_time_period)

    return p


if __name__ == '__main__':
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)
