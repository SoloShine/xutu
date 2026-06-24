# src/bedrock/runner/__main__.py
"""runner CLI:python -m src.bedrock.runner --project <p> --chapter N --volume V

跑确定性 LangGraph 图(Boot→Write 自纠→L2→Finalize),打印结果 JSON。
独立 Python runner,脱离 Claude Workflow 引擎。信任锚 run_l2/verify-persisted 经 Python 直调。
"""
import argparse
import json
import sys
from pathlib import Path

from src.bedrock.db.connection import get_connection
from src.bedrock.db.migrate import apply_migrations
from .graph import build_graph


def main():
    ap = argparse.ArgumentParser(prog="src.bedrock.runner", description="LangGraph 章节管线 runner(脱离 Claude)")
    ap.add_argument("--project", type=Path, required=True, help="项目目录(含 bedrock.db)")
    ap.add_argument("--chapter", type=int, required=True, help="global_number")
    ap.add_argument("--volume", type=int, required=True, help="volume.id")
    ap.add_argument("--export-path", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="mock LLM/run_l2/verify(免 API key),跑通真实 DB 路径+emit,验证控制流/可观测")
    args = ap.parse_args()

    apply_migrations(args.project)   # 自愈:老库补 workflow_config/run 表
    conn = get_connection(args.project)
    try:
        graph, recursion_limit = build_graph(conn, args.project, export_path=args.export_path, dry_run=args.dry_run)
        init_state = {
            "chapter_global": args.chapter,
            "volume_id": args.volume,
            "chapter_id": 0, "ctx": {}, "config": {}, "prose": "", "report": {},
            "phase": "write", "iter": 0, "cap": 3, "editor_iter": 0, "editor_cap": 5,
            "run_id": 0, "rejected": False, "violations_feedback": "", "result": {},
        }
        final = graph.invoke(
            init_state,
            config={"configurable": {"thread_id": f"ch{args.chapter}"}, "recursion_limit": recursion_limit},
        )
        print(json.dumps(final.get("result", {"status": "unknown"}), ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
