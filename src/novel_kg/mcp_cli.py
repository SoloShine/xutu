"""
Novel KG 工具 CLI — MCP 的 Bash 替代方案

用于不支持 MCP 的 Agent（如 openclaw），通过命令行调用 core.py 逻辑。

用法:
  python mcp_cli.py <tool_name> [参数...]

示例:
  python mcp_cli.py get_graph_stats --project v11_test
  python mcp_cli.py get_chapter_context --project v11_test --chapter 5
  python mcp_cli.py get_writing_prompt --project v11_test --chapter 5
  python mcp_cli.py init_project --project new_project --confirm I_UNDERSTAND_THIS_IS_DESTRUCTIVE
"""

import sys
import os
import json
import argparse

from . import core


def _out(data):
    """统一输出"""
    if isinstance(data, str):
        try:
            print(data)
        except UnicodeEncodeError:
            sys.stdout.buffer.write(data.encode('utf-8', errors='replace'))
            sys.stdout.buffer.write(b'\n')
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


def _projects_dir():
    """返回 projects/ 目录的绝对路径。"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.environ.get('KG_PROJECTS_DIR') or os.path.normpath(os.path.join(here, '..', '..', 'projects'))


def _std_extraction_path(project, chapter):
    """标准提取JSON路径：projects/<project>/extractions/extraction_ch{NN}.json"""
    return os.path.join(_projects_dir(), project, 'extractions', f'extraction_ch{chapter:02d}.json')


def _std_output_path(project, chapter):
    """标准正文输出路径：projects/<project>/output/ch{NN}_generated.txt"""
    return os.path.join(_projects_dir(), project, 'output', f'ch{chapter:02d}_generated.txt')


# ============================================================
# CLI 参数注册
# ============================================================

def build_parser():
    p = argparse.ArgumentParser(description='Novel KG 工具 CLI')
    sub = p.add_subparsers(dest='command')

    def _proj(sp):
        sp.add_argument('--project', '-p', required=True)

    def _chap(sp):
        sp.add_argument('--chapter', '-ch', type=int, required=True)

    # --- 查询 ---
    for name in ['get_graph_stats', 'get_all_threads', 'check_consistency']:
        sp = sub.add_parser(name)
        _proj(sp)
        sp.set_defaults(func=globals()['cmd_' + name])

    for name in ['get_chapter_context', 'get_unresolved_threads']:
        sp = sub.add_parser(name)
        _proj(sp); _chap(sp)
        sp.set_defaults(func=globals()['cmd_' + name])

    sp = sub.add_parser('get_derivation_context')
    _proj(sp); _chap(sp)
    sp.add_argument('--lookback', type=int, default=3)
    sp.set_defaults(func=cmd_get_derivation_context)

    # --- ChapterAgent 支持 ---
    sp = sub.add_parser('get_boot_context')
    _proj(sp); _chap(sp)
    sp.set_defaults(func=lambda a: _out(core.get_boot_context(a.project, a.chapter)))

    sp = sub.add_parser('get_framework')
    _proj(sp); _chap(sp)
    sp.set_defaults(func=lambda a: _out(core.get_framework(a.project, a.chapter)))

    sp = sub.add_parser('recall_thread')
    _proj(sp)
    sp.add_argument('--thread-id', required=True)
    sp.set_defaults(func=lambda a: _out(core.recall_thread(a.project, a.thread_id)))

    sp = sub.add_parser('recall_arc')
    _proj(sp); _chap(sp)
    sp.set_defaults(func=lambda a: _out(core.recall_arc(a.project, a.chapter)))

    sp = sub.add_parser('generate_context_digest')
    _proj(sp); _chap(sp)
    sp.add_argument('--word-count', type=int, default=0)
    sp.set_defaults(func=lambda a: _out(core.generate_context_digest(
        a.project, a.chapter, word_count=a.word_count)))

    sp = sub.add_parser('verify_pipeline_step')
    _proj(sp); _chap(sp)
    sp.add_argument('--step', required=True, choices=['write', 'edit', 'extract', 'graph', 'telemetry'])
    sp.set_defaults(func=lambda a: _out(core.verify_pipeline_step(a.project, a.chapter, a.step)))

    sp = sub.add_parser('verify_chapter_complete')
    _proj(sp); _chap(sp)
    sp.set_defaults(func=lambda a: _out(core.verify_chapter_complete(a.project, a.chapter)))

    # --- Prompt ---
    sp = sub.add_parser('get_extraction_prompt')
    _proj(sp); _chap(sp)
    sp.add_argument('--text-file', '-f', help='省略则默认 projects/<project>/output/ch{NN}_generated.txt')
    sp.add_argument('--compact', action='store_true', help='精简模式：只列实体名，不展开完整上下文')
    sp.set_defaults(func=cmd_get_extraction_prompt)

    sp = sub.add_parser('get_writing_prompt')
    _proj(sp); _chap(sp)
    sp.add_argument('--focused', action='store_true',
                    help='只注入近期活跃悬念线（节省prompt体积）')
    sp.set_defaults(func=lambda a: _out(core.get_writing_prompt(a.project, a.chapter, focused=a.focused)))

    sp = sub.add_parser('get_derivation_prompt')
    _proj(sp); _chap(sp)
    sp.set_defaults(func=lambda a: _out(core.get_derivation_prompt(a.project, a.chapter)))

    sp = sub.add_parser('get_editing_prompt')
    _proj(sp); _chap(sp)
    sp.add_argument('--draft-file', default='',
                    help='初稿文件路径（省略时自动使用标准路径）')
    sp.set_defaults(func=lambda a: _out(core.get_editing_prompt(
        a.project, a.chapter, draft='',
        draft_file=a.draft_file or _std_output_path(a.project, a.chapter))))

    # --- 校验 ---
    sp = sub.add_parser('validate_chapter')
    _proj(sp); _chap(sp)
    sp.add_argument('--text-file', '-f', help='省略则默认 projects/<project>/output/ch{NN}_generated.txt')
    sp.set_defaults(func=cmd_validate_chapter)

    sp = sub.add_parser('detect_conflicts')
    _proj(sp)
    sp.add_argument('--json-file', '-f', help='省略则默认 projects/<project>/extractions/extraction_ch{NN}.json')
    sp.set_defaults(func=cmd_detect_conflicts)

    # --- 写入 ---
    sp = sub.add_parser('init_project')
    _proj(sp)
    sp.add_argument('--confirm', default='')
    sp.set_defaults(func=lambda a: _out(core.init_project(a.project, a.confirm)))

    sp = sub.add_parser('clear_chapter_data')
    _proj(sp); _chap(sp)
    sp.add_argument('--confirm', default='')
    sp.set_defaults(func=lambda a: _out(core.clear_chapter_data(a.project, a.chapter, a.confirm)))

    sp = sub.add_parser('write_extraction')
    _proj(sp); _chap(sp)
    sp.add_argument('--json-file', '-f', help='省略则默认 projects/<project>/extractions/extraction_ch{NN}.json')
    sp.set_defaults(func=cmd_write_extraction)

    sp = sub.add_parser('sync_backends')
    _proj(sp)
    sp.add_argument('--direction', default='json_to_neo4j',
                    choices=['json_to_neo4j', 'neo4j_to_json'])
    sp.set_defaults(func=lambda a: _out(core.sync_backends(a.project, a.direction)))

    sp = sub.add_parser('analyze_pacing')
    _proj(sp)
    sp.set_defaults(func=lambda a: _out(core.analyze_pacing(a.project)))

    sp = sub.add_parser('add_character')
    _proj(sp)
    sp.add_argument('--name', required=True)
    sp.add_argument('--role', default='')
    sp.add_argument('--personality', default='')
    sp.add_argument('--gap-relation', default='')
    sp.set_defaults(func=lambda a: _out(core.add_character(
        a.project, a.name, a.role, a.personality, a.gap_relation)))

    sp = sub.add_parser('add_location')
    _proj(sp)
    sp.add_argument('--name', required=True)
    sp.add_argument('--loc-type', default='')
    sp.add_argument('--description', default='')
    sp.set_defaults(func=lambda a: _out(core.add_location(
        a.project, a.name, a.loc_type, a.description)))

    sp = sub.add_parser('add_event')
    _proj(sp)
    sp.add_argument('--event-id', required=True)
    sp.add_argument('--chapter', type=int, default=0)
    sp.add_argument('--title', default='')
    sp.add_argument('--detail', default='')
    sp.add_argument('--event-type', default='daily')
    sp.add_argument('--is-gap', action='store_true')
    sp.add_argument('--gap-level', type=int, default=0)
    sp.set_defaults(func=lambda a: _out(core.add_event(
        a.project, a.event_id, a.title, a.detail, a.chapter,
        a.event_type, a.is_gap, a.gap_level)))

    sp = sub.add_parser('add_chapter_arc')
    _proj(sp); _chap(sp)
    sp.add_argument('--purpose', required=True)
    sp.add_argument('--scenes', required=True)
    sp.add_argument('--ending', required=True)
    sp.add_argument('--gap-note', default='')
    sp.add_argument('--structure-type', default='linear')
    sp.add_argument('--time-jumps', default='')
    sp.add_argument('--thread-plan', default='')
    sp.add_argument('--reasoning', default='')
    sp.set_defaults(func=lambda a: _out(core.add_chapter_arc(
        a.project, a.chapter, a.purpose, a.scenes, a.ending,
        a.gap_note, a.structure_type, a.time_jumps, a.thread_plan, a.reasoning)))

    sp = sub.add_parser('add_suspense_thread')
    _proj(sp)
    sp.add_argument('--thread-id', required=True)
    sp.add_argument('--content', required=True)
    sp.add_argument('--planted-chapter', type=int, required=True)
    sp.add_argument('--importance', default='medium')
    sp.add_argument('--thread-type', default='foreshadowing')
    sp.set_defaults(func=lambda a: _out(core.add_suspense_thread(
        a.project, a.thread_id, a.content, a.planted_chapter,
        a.importance, a.thread_type)))

    sp = sub.add_parser('update_suspense_thread')
    _proj(sp)
    sp.add_argument('--thread-id', required=True)
    sp.add_argument('--status', default='')
    sp.add_argument('--importance', default='')
    sp.set_defaults(func=lambda a: _out(core.update_suspense_thread(
        a.project, a.thread_id, a.status, a.importance)))

    sp = sub.add_parser('add_outline_entry')
    _proj(sp); _chap(sp)
    sp.add_argument('--purpose', required=True)
    sp.add_argument('--key-events', default='')
    sp.add_argument('--threads-to-plant', default='')
    sp.add_argument('--threads-to-resolve', default='')
    sp.add_argument('--structure-hint', default='')
    sp.set_defaults(func=lambda a: _out(core.add_outline_entry(
        a.project, a.chapter, a.purpose, a.key_events,
        a.threads_to_plant, a.threads_to_resolve, a.structure_hint)))

    sp = sub.add_parser('add_style_guide')
    _proj(sp)
    sp.add_argument('--guide-id', required=True)
    sp.add_argument('--rule', default='')
    sp.add_argument('--dimension', default='')
    sp.add_argument('--goal', default='')
    sp.add_argument('--good-examples', nargs='+', default=[])
    sp.add_argument('--bad-examples', nargs='+', default=[])
    sp.set_defaults(func=lambda a: _out(core.add_style_guide(
        a.project, a.guide_id, a.rule,
        dimension=a.dimension, goal=a.goal,
        good_examples=a.good_examples or None,
        bad_examples=a.bad_examples or None)))

    sp = sub.add_parser('add_motif')
    _proj(sp)
    sp.add_argument('--name', required=True)
    sp.add_argument('--meaning', default='')
    sp.add_argument('--evolution', default='')
    sp.set_defaults(func=lambda a: _out(core.add_motif(a.project, a.name, a.meaning, a.evolution)))

    sp = sub.add_parser('add_theme')
    _proj(sp)
    sp.add_argument('--name', required=True)
    sp.add_argument('--description', default='')
    sp.add_argument('--chapters', default='')
    sp.set_defaults(func=lambda a: _out(core.add_theme(a.project, a.name, a.description, a.chapters)))

    sp = sub.add_parser('add_time_period')
    _proj(sp)
    sp.add_argument('--label', required=True)
    sp.add_argument('--chapter-start', type=int, required=True)
    sp.add_argument('--chapter-end', type=int, required=True)
    sp.add_argument('--years', default='')
    sp.add_argument('--theme', default='')
    sp.set_defaults(func=lambda a: _out(core.add_time_period(
        a.project, a.label, a.chapter_start, a.chapter_end, a.years, a.theme)))

    sp = sub.add_parser('add_relation')
    _proj(sp)
    sp.add_argument('--from-label', required=True)
    sp.add_argument('--from-key', required=True)
    sp.add_argument('--from-val', required=True)
    sp.add_argument('--rel-type', required=True)
    sp.add_argument('--to-label', required=True)
    sp.add_argument('--to-key', required=True)
    sp.add_argument('--to-val', required=True)
    sp.set_defaults(func=lambda a: _out(core.add_relation(
        a.project, a.from_label, a.from_key, a.from_val,
        a.rel_type, a.to_label, a.to_key, a.to_val)))

    sp = sub.add_parser('inject_agent_phase')
    _proj(sp)
    sp.add_argument('--chapter', type=int, required=True)
    sp.add_argument('--phase', required=True, help='阶段名: writing/editing/extraction')
    sp.add_argument('--duration-ms', type=float, required=True)
    sp.add_argument('--tool-uses', type=int, default=None)
    sp.set_defaults(func=lambda a: _out(core.inject_agent_phase(
        a.project, a.chapter, a.phase, a.duration_ms, tool_uses=a.tool_uses)))

    sp = sub.add_parser('inject_chapter_metrics')
    _proj(sp)
    sp.add_argument('--chapter', type=int, required=True)
    sp.add_argument('--word-count', type=int, default=None)
    sp.add_argument('--editing-corrections', type=int, default=None)
    sp.add_argument('--editing-types', default=None, help='逗号分隔的修正类型')
    sp.set_defaults(func=lambda a: _out(core.inject_chapter_metrics(
        a.project, a.chapter, word_count=a.word_count,
        editing_corrections=a.editing_corrections,
        editing_types=a.editing_types)))

    sp = sub.add_parser('count_chapter_words')
    _proj(sp)
    sp.add_argument('--chapter', type=int, required=True)
    sp.set_defaults(func=lambda a: _out(cmd_count_chapter_words(a)))

    return p


# ============================================================
# 需要文件读取的命令（不能一行 lambda 解决）
# ============================================================

def cmd_get_graph_stats(args):
    _out(core.get_graph_stats(args.project))

def cmd_get_chapter_context(args):
    _out(core.get_chapter_context(args.project, args.chapter))

def cmd_get_derivation_context(args):
    _out(core.get_derivation_context(args.project, args.chapter, args.lookback))

def cmd_get_unresolved_threads(args):
    _out(core.get_unresolved_threads(args.project, args.chapter))

def cmd_get_all_threads(args):
    _out(core.get_all_threads(args.project))

def cmd_check_consistency(args):
    _out(core.check_consistency(args.project))

def cmd_get_extraction_prompt(args):
    path = args.text_file or _std_output_path(args.project, args.chapter)
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    print(core.get_extraction_prompt(args.project, args.chapter, text,
                                     compact=getattr(args, 'compact', False)))

def cmd_validate_chapter(args):
    path = args.text_file or _std_output_path(args.project, args.chapter)
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    _out(core.validate_chapter(args.project, text, args.chapter))

def cmd_detect_conflicts(args):
    path = args.json_file or _std_extraction_path(args.project, args.chapter)
    with open(path, 'r', encoding='utf-8') as f:
        extracted = json.load(f)
    _out(core.detect_extraction_conflicts(args.project, json.dumps(extracted, ensure_ascii=False)))

def cmd_write_extraction(args):
    path = args.json_file or _std_extraction_path(args.project, args.chapter)
    with open(path, 'r', encoding='utf-8') as f:
        extracted = json.load(f)
    _out(core.write_extraction(args.project, args.chapter, json.dumps(extracted, ensure_ascii=False)))

def cmd_count_chapter_words(args):
    """统计章节汉字数并注入遥测。"""
    import re
    path = _std_output_path(args.project, args.chapter)
    if not os.path.exists(path):
        _out({"status": "error", "message": f"文件不存在: {path}"})
        return
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    # 统计汉字数（排除标点、空格、英文）
    chinese_chars = len(re.findall(r'[一-鿿]', text))
    # 注入遥测
    result = core.inject_chapter_metrics(
        args.project, args.chapter, word_count=chinese_chars)
    result["word_count"] = chinese_chars
    _out(result)


# ============================================================
# 入口
# ============================================================

if __name__ == '__main__':
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    try:
        args.func(args)
    finally:
        core.close_all()
