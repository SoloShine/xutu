# src/bedrock/__main__.py
import argparse
import json
import sys
from pathlib import Path

from src.bedrock.init_project import init_project
from src.bedrock.db.connection import get_connection
from src.bedrock.orchestration.l2_pipeline import run_l2
from src.bedrock.orchestration.boot_context import get_chapter_boot_context
from src.bedrock.orchestration.persist_gate import verify_chapter_persisted
from src.bedrock.orchestration.review_flag import mark_unresolved
from src.bedrock.checks.beat_fulfillment import BeatViolation


def _chapter_id(conn, global_number):
    """global_number → chapter.id。找不到时抛 SystemExit（CLI 边界，友好报错）。"""
    row = conn.execute(
        "SELECT id FROM chapter WHERE global_number=?", (global_number,)).fetchone()
    if row is None:
        sys.exit(f"找不到 global_number={global_number} 的章节")
    return row["id"]


def main():
    parser = argparse.ArgumentParser(prog="bedrock", description="磐石 V3 小说管线 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="初始化新作品项目")
    p_init.add_argument("path", type=Path)
    p_init.add_argument("--name", required=True)
    p_init.add_argument("--force", action="store_true")

    p_runl2 = sub.add_parser("run-l2", help="单章 L2 全量重算（零 LLM）")
    p_runl2.add_argument("--project", type=Path, required=True)
    p_runl2.add_argument("--chapter", type=int, required=True)

    p_boot = sub.add_parser("boot-context", help="装配子代理启动上下文")
    p_boot.add_argument("--project", type=Path, required=True)
    p_boot.add_argument("--chapter", type=int, required=True)
    p_boot.add_argument("--volume", type=int, required=True)

    p_verify = sub.add_parser("verify-persisted", help="强制落盘门禁")
    p_verify.add_argument("--project", type=Path, required=True)
    p_verify.add_argument("--chapter", type=int, required=True)
    p_verify.add_argument("--export-path", type=Path, default=None)

    p_mark = sub.add_parser("mark-unresolved", help="3轮重试耗尽：写 l2_unresolved=1")
    p_mark.add_argument("--project", type=Path, required=True)
    p_mark.add_argument("--chapter", type=int, required=True)
    p_mark.add_argument("--rule-or-model", type=int, required=True,
                        help="1=疑似规则/模型问题，0=否")

    args = parser.parse_args()
    if args.cmd == "init":
        init_project(args.path, work_name=args.name, force=args.force)
        print(f"已初始化作品 '{args.name}' 于 {args.path}")
        return

    # 以下子命令都需要 DB 连接
    conn = get_connection(args.project)
    try:
        if args.cmd == "run-l2":
            cid = _chapter_id(conn, args.chapter)
            report = run_l2(conn, cid)
            print(f"passed_hard_gate: {report.passed_hard_gate}")
            print(f"beat_violations: {len(report.beat_violations)}")
            if report.drift:
                drift_keys = sorted(report.drift.keys())
                print(f"drift_keys: {drift_keys}")
            else:
                print("drift_keys: []")
        elif args.cmd == "boot-context":
            cid = _chapter_id(conn, args.chapter)
            ctx = get_chapter_boot_context(conn, cid, volume_id=args.volume)
            print(json.dumps(ctx, ensure_ascii=False, indent=2))
        elif args.cmd == "verify-persisted":
            cid = _chapter_id(conn, args.chapter)
            ok = verify_chapter_persisted(conn, cid, export_path=args.export_path)
            print("True" if ok else "False")
        elif args.cmd == "mark-unresolved":
            cid = _chapter_id(conn, args.chapter)
            raw = json.load(sys.stdin)
            violations = [BeatViolation(**d) for d in raw]
            mark_unresolved(
                conn, cid, violations,
                likely_rule_or_model_issue=bool(args.rule_or_model))
            print("ok")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
