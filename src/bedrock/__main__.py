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
from src.bedrock.orchestration.review_flag import (
    mark_unresolved,
    mark_polish_broke_beat,
    mark_forced_persist_failed,
    mark_advisory_drift,
)
from src.bedrock.orchestration.runtime_collect import write_runtime
from src.bedrock.orchestration.watchdog import run_watchdog
from src.bedrock.orchestration.cross_volume_gate import check_cross_volume_debt
from src.bedrock.orchestration.review_flag import get_review_flag
from src.bedrock.repositories.governance import add_amendment
from src.bedrock.checks.beat_fulfillment import BeatViolation


def _chapter_id(conn, global_number):
    """global_number → chapter.id。找不到时抛 SystemExit（CLI 边界，友好报错）。"""
    row = conn.execute(
        "SELECT id FROM chapter WHERE global_number=?", (global_number,)).fetchone()
    if row is None:
        sys.exit(f"找不到 global_number={global_number} 的章节")
    return row["id"]


def _write_review_report(report_path, volume, payload):
    """拼装 review_report_vol{N}.md 并落盘（强制，治 Vol15 报告丢失）。

    payload 结构：{findings: {actionable:[...]|{...}}, outcomes: {chN: state},
                   watchdog: {...}, debt: {...}}。
    容错：各段缺失时输出空段而非崩溃（CLI 薄封装，不挡 e2e）。"""
    findings = payload.get("findings") or {}
    outcomes = payload.get("outcomes") or {}
    watchdog = payload.get("watchdog") or {}
    debt = payload.get("debt") or {}

    # findings.actionable 可能是 list 或 dict；统一拍平为 (chapter, f) 行
    actionable = findings.get("actionable") if isinstance(findings, dict) else None
    lines = [f"# VolumeReview 报告 — 卷 {volume}", ""]

    lines.append("## 旗章发现（actionable）")
    if isinstance(actionable, list) and actionable:
        for f in actionable:
            ch = f.get("chapter") if isinstance(f, dict) else "?"
            fi = f.get("fix_instruction", "") if isinstance(f, dict) else str(f)
            ia = f.get("is_actionable", "") if isinstance(f, dict) else ""
            lines.append(f"- ch{ch} [is_actionable={ia}]: {fi}")
    elif isinstance(actionable, dict) and actionable:
        for ch, f in actionable.items():
            fi = f.get("fix_instruction", "") if isinstance(f, dict) else str(f)
            ia = f.get("is_actionable", "") if isinstance(f, dict) else ""
            lines.append(f"- ch{ch} [is_actionable={ia}]: {fi}")
    else:
        lines.append("- （无 actionable 发现）")
    lines.append("")

    lines.append("## 修正结果（三状态）")
    if outcomes:
        for ch, state in outcomes.items():
            lines.append(f"- ch{ch}: {state}")
    else:
        lines.append("- （无编辑章）")
    lines.append("")

    lines.append("## Watchdog（贴边走 / drift 聚合）")
    if isinstance(watchdog, dict) and watchdog:
        lines.append("```json")
        lines.append(json.dumps(watchdog, ensure_ascii=False, indent=2))
        lines.append("```")
    else:
        lines.append("- （无 watchdog 信号）")
    lines.append("")

    lines.append("## 跨卷悬链欠债")
    if isinstance(debt, dict) and debt:
        lines.append("```json")
        lines.append(json.dumps(debt, ensure_ascii=False, indent=2))
        lines.append("```")
    else:
        lines.append("- （无欠债）")
    lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


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

    p_mark_pbb = sub.add_parser("mark-polish-broke-beat")
    p_mark_pbb.add_argument("--project", type=Path, required=True)
    p_mark_pbb.add_argument("--chapter", type=int, required=True)

    p_mark_fpf = sub.add_parser("mark-forced-persist-failed")
    p_mark_fpf.add_argument("--project", type=Path, required=True)
    p_mark_fpf.add_argument("--chapter", type=int, required=True)

    p_mark_drift = sub.add_parser("mark-advisory-drift")
    p_mark_drift.add_argument("--project", type=Path, required=True)
    p_mark_drift.add_argument("--chapter", type=int, required=True)

    p_collect = sub.add_parser("collect-runtime")
    p_collect.add_argument("--project", type=Path, required=True)
    p_collect.add_argument("--chapter", type=int, required=True)
    p_collect.add_argument("--editing-rounds", type=int, default=0)

    # SP5 治理层：卷级 watchdog / 跨卷门禁 / 旗查询 / 报告落盘 / 人工释放
    p_watchdog = sub.add_parser("run-watchdog", help="跨章 statistical watchdog（贴边走+drift）")
    p_watchdog.add_argument("--project", type=Path, required=True)
    p_watchdog.add_argument("--volume", type=int, required=True, help="volume.id")

    p_debt = sub.add_parser("cross-volume-debt", help="跨卷悬链收敛门禁")
    p_debt.add_argument("--project", type=Path, required=True)
    p_debt.add_argument("--volume", type=int, required=True, help="volume.id")

    p_flag = sub.add_parser("get-review-flag", help="读 SP4 chapter_review_flag + 派生 has_flag")
    p_flag.add_argument("--project", type=Path, required=True)
    p_flag.add_argument("--chapter", type=int, required=True)

    p_report = sub.add_parser("write-review-report", help="拼装 review_report_vol{N}.md 强制落盘")
    p_report.add_argument("--project", type=Path, required=True)
    p_report.add_argument("--volume", type=int, required=True, help="volume.id")

    p_unlock = sub.add_parser("unlock-volume", help="人工释放卷间 BLOCKING（写 amendment 留痕）")
    p_unlock.add_argument("--project", type=Path, required=True)
    p_unlock.add_argument("--volume", type=int, required=True, help="volume.id")
    p_unlock.add_argument("--reason", required=True)

    # SP6-A 只读工具集
    p_export = sub.add_parser("export", help="导出正文（paragraph→文件，单向）")
    p_export.add_argument("--project", type=Path, required=True)
    scope_x = p_export.add_mutually_exclusive_group(required=True)
    scope_x.add_argument("--chapter", type=int, help="global_number")
    scope_x.add_argument("--volume", type=int, help="volume.id")
    scope_x.add_argument("--book", action="store_true")
    p_export.add_argument("--format", choices=["md", "txt"], default="md")
    p_export.add_argument("--final", action="store_true")
    p_export.add_argument("--out", type=Path, default=None)

    p_diag = sub.add_parser("diagnose", help="体检报告（聚合留痕旗/状态/欠债，可选live L2）")
    p_diag.add_argument("--project", type=Path, required=True)
    diag_scope = p_diag.add_mutually_exclusive_group(required=True)
    diag_scope.add_argument("--volume", type=int, help="volume.id")
    diag_scope.add_argument("--book", action="store_true")
    p_diag.add_argument("--with-l2", action="store_true",
                        help="现场跑 run_l2（仅 --volume，禁 --book）")
    p_diag.add_argument("--out", type=Path, default=None)

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
            # 输出 JSON（机器可读，Workflow JS 解析 passed_hard_gate / beat_violations[]）
            # asdict 递归转 BeatViolation dataclass；cross_volume 已在 l2_pipeline 转 dict。
            from dataclasses import asdict
            print(json.dumps(asdict(report), ensure_ascii=False))
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
            # 显式按 UTF-8 解 stdin（Windows OEM 码页如 cp936 会把 UTF-8 JSON 解成乱码，
            # 后续 ensure_ascii=False 写回时 UnicodeEncodeError）。读 buffer 原始字节再 decode。
            try:
                raw = json.loads(sys.stdin.buffer.read().decode("utf-8"))
                violations = [BeatViolation(**d) for d in raw]
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                sys.exit(f"invalid violations JSON on stdin: {e}")
            mark_unresolved(
                conn, cid, violations,
                likely_rule_or_model_issue=bool(args.rule_or_model))
            print("ok")
        elif args.cmd == "mark-polish-broke-beat":
            cid = _chapter_id(conn, args.chapter)
            mark_polish_broke_beat(conn, cid)
            print("ok")
        elif args.cmd == "mark-forced-persist-failed":
            cid = _chapter_id(conn, args.chapter)
            mark_forced_persist_failed(conn, cid)
            print("ok")
        elif args.cmd == "mark-advisory-drift":
            cid = _chapter_id(conn, args.chapter)
            try:
                drift = json.loads(sys.stdin.buffer.read().decode("utf-8"))
            except (json.JSONDecodeError, ValueError) as e:
                sys.exit(f"invalid drift JSON on stdin: {e}")
            mark_advisory_drift(conn, cid, drift)
            print("ok")
        elif args.cmd == "collect-runtime":
            cid = _chapter_id(conn, args.chapter)
            try:
                payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
                invocations = payload.get("invocations", [])
                llm_calls = payload.get("llm_calls", [])
            except (json.JSONDecodeError, ValueError) as e:
                sys.exit(f"invalid runtime JSON on stdin: {e}")
            write_runtime(conn, cid, invocations, llm_calls,
                          editing_rounds=args.editing_rounds)
            print("ok")
        elif args.cmd == "run-watchdog":
            # volume 参数语义 = volume.id（run_watchdog/check_cross_volume_debt 都接 id）
            report = run_watchdog(conn, args.volume)
            from dataclasses import asdict
            print(json.dumps(asdict(report), ensure_ascii=False))
        elif args.cmd == "cross-volume-debt":
            report = check_cross_volume_debt(conn, args.volume)
            from dataclasses import asdict
            print(json.dumps(asdict(report), ensure_ascii=False))
        elif args.cmd == "get-review-flag":
            cid = _chapter_id(conn, args.chapter)
            flag = get_review_flag(conn, cid)
            # has_flag：任一硬 flag != 0 或 advisory_drift 非空（'{}' 等价于空）
            # 注意：likely_rule_or_model_issue 不计入 has_flag——它是 l2_unresolved 的诊断
            # 子字段（仅 l2_unresolved 时有意义），单独算会把"仅诊断"行误判为需 VolumeReview 复查。
            has_flag = False
            if flag is not None:
                advisory = flag.get("advisory_drift") or "{}"
                has_flag = (flag.get("l2_unresolved", 0) != 0
                            or flag.get("polish_broke_beat", 0) != 0
                            or flag.get("forced_persist_failed", 0) != 0
                            or advisory not in (None, "{}"))
            print(json.dumps({"has_flag": has_flag, "flag": flag},
                             ensure_ascii=False, default=str))
        elif args.cmd == "write-review-report":
            # 读 stdin JSON（findings/outcomes/watchdog/debt）→ 拼装 markdown → 强制落盘（治 Vol15）
            try:
                payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
            except (json.JSONDecodeError, ValueError) as e:
                sys.exit(f"invalid report JSON on stdin: {e}")
            report_path = args.project / f"review_report_vol{args.volume}.md"
            _write_review_report(report_path, args.volume, payload)
            print(str(report_path))
        elif args.cmd == "unlock-volume":
            # 人工释放卷间 BLOCKING：UPDATE blocking=0 + amendment 留痕（author='human'）
            row = conn.execute(
                "SELECT blocking FROM volume_review WHERE volume_id=?",
                (args.volume,)).fetchone()
            old_blocking = row["blocking"] if row is not None else None
            conn.execute(
                "UPDATE volume_review SET blocking=0 WHERE volume_id=?",
                (args.volume,))
            add_amendment(conn, entity_type="volume_review", entity_id=args.volume,
                          field="blocking", old=str(old_blocking) if old_blocking is not None else None,
                          new="0", reason=args.reason, author="human")
            conn.commit()
            print("ok")
        elif args.cmd == "export":
            from src.bedrock.cli.reader_commands import do_export
            if args.book:
                scope, target = "book", None
            elif args.chapter is not None:
                cid = _chapter_id(conn, args.chapter)   # global_number → id
                scope, target = "chapter", cid
            else:
                scope, target = "volume", args.volume
            result = do_export(conn, args.project, scope, target,
                               args.format, args.final, args.out)
            print(result.path)
        elif args.cmd == "diagnose":
            from src.bedrock.cli.reader_commands import diagnose
            scope = ("book", None) if args.book else ("volume", args.volume)
            report = diagnose(conn, args.project, scope, with_l2=args.with_l2)
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(report, encoding="utf-8")
                print(args.out)
            else:
                print(report)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
