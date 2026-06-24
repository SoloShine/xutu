# src/bedrock/runner/nodes.py
"""图节点函数(确定性,返回 state delta)。conn 经 make_nodes(conn) 闭包绑定(不入态)。

每个节点末尾 emit_event(Python 直调,免费)→ Runs 面板节点级实时。
信任锚 run_l2 / verify-persisted Python 直调,零 LLM。writer 用 LLM 单次出整章正文(非 agent runtime)。
"""
import json
import sys
from dataclasses import asdict

from src.bedrock.db.chapter_lookup import chapter_id_by_global
from src.bedrock.orchestration.boot_context import get_chapter_boot_context
from src.bedrock.orchestration.l2_pipeline import run_l2
from src.bedrock.orchestration.persist_gate import verify_chapter_persisted
from src.bedrock.orchestration.review_flag import (
    ensure_flag, mark_unresolved, mark_forced_persist_failed,
)
from src.bedrock.repositories.plot_tree import set_chapter_status
from src.bedrock.workflow.config_repo import get_workflow_config
from src.bedrock.workflow.run_repo import start_run, emit_event, end_run
from src.bedrock.__main__ import _commit_paragraphs, _export_chapter_json   # 复用全套入库 guard

from .llm import get_writer_model
from .prompts import writer_prompt, editor_prompt


def make_nodes(conn, project, export_path=None, dry_run=False):
    """建节点函数字典,闭包绑定 conn + project。runner='langgraph'。

    dry_run=True:mock 掉 LLM/write(run_l2/verify)三处(免 API key),boot/commit/finalize + emit 仍跑真实 DB,
    供免 key 验证 runner 控制流 + 面板可观测。产出的"正文"是占位,不具文学意义。"""

    # dry-run 占位正文(过 commit guard:非 worklog + ≥MIN_PROSE_CHARS;含 @@beat 标记)
    _DRY_PROSE = "@@beat:1@@\n" + "长街尽头起了雾。他停下脚步，听见远处钟声。这是独立 runner 的一次 dry-run 占位正文，不调用任何 LLM。\n" * 40

    def _emit(run_id, node, kind, payload=None):
        if run_id:
            try:
                emit_event(conn, run_id, node, kind, payload)
            except Exception as e:
                print(f"[runner] emit({node}/{kind}) 失败(不阻塞): {e}", file=sys.stderr)

    def boot(state):
        chapter_global = state["chapter_global"]
        volume_id = state["volume_id"]
        chapter_id = chapter_id_by_global(conn, chapter_global)
        ctx = get_chapter_boot_context(conn, chapter_id, volume_id)
        config = get_workflow_config(conn, volume_id)
        cap = int((config.get("caps") or {}).get("writer", 3)) or 3
        editor_cap = int((config.get("caps") or {}).get("editor", 5)) or 5
        run_id = start_run(conn, chapter_global=chapter_global, volume_id=volume_id, runner="langgraph")
        _emit(run_id, "boot", "start", {"beats": len(ctx.get("beat_contracts") or [])})
        return {"chapter_id": chapter_id, "ctx": ctx, "config": config,
                "cap": cap, "editor_cap": editor_cap,
                "run_id": run_id, "iter": 0, "editor_iter": 0, "phase": "write",
                "rejected": False, "violations_feedback": ""}

    def write(state):
        # 控制流保证进入此节点时 iter < cap
        ctx = state["ctx"]
        wt = (ctx.get("constants") or {}).get("word_count_target") or (3000, 5000)
        if dry_run:
            prose = _DRY_PROSE   # 免 key 占位(不调 LLM)
        else:
            prompt = writer_prompt(ctx, state["chapter_global"], state["volume_id"], tuple(wt),
                                   violations_feedback=state.get("violations_feedback", ""))
            model = get_writer_model(state["config"], "writer")
            resp = model.invoke(prompt)
            prose = resp.content if hasattr(resp, "content") else str(resp)
        _emit(state["run_id"], "write", "iteration",
              {"iter": state["iter"] + 1, "chars": len(prose),
               "retry": bool(state.get("violations_feedback")) or state.get("rejected", False)})
        return {"prose": prose, "iter": state["iter"] + 1, "phase": "write",
                "rejected": False, "violations_feedback": ""}

    def revise(state):
        # editor 单次产出修订版整章正文(基于上版 committed prose,累进接受)。控制流保证进入时 editor_iter<editor_cap
        ctx = state["ctx"]
        wt = (ctx.get("constants") or {}).get("word_count_target") or (3000, 5000)
        if dry_run:
            prose = _DRY_PROSE   # 免 key 占位(不调 LLM)
        else:
            prompt = editor_prompt(ctx, state["chapter_global"], state["volume_id"], state["prose"],
                                   tuple(wt), violations_feedback=state.get("violations_feedback", ""))
            model = get_writer_model(state["config"], "editor")
            resp = model.invoke(prompt)
            prose = resp.content if hasattr(resp, "content") else str(resp)
        _emit(state["run_id"], "revise", "iteration",
              {"iter": state["editor_iter"] + 1, "chars": len(prose),
               "retry": bool(state.get("violations_feedback")) or state.get("rejected", False)})
        return {"prose": prose, "editor_iter": state["editor_iter"] + 1, "phase": "revise",
                "rejected": False, "violations_feedback": ""}

    def commit(state):
        if dry_run:
            _emit(state["run_id"], "commit", "enter", {"iter": state["iter"], "dry": True})
            return {"rejected": False}   # 免 key 占位:不动真实段落
        # _commit_paragraphs 用 sys.exit 拒绝垃圾(worklog/污染)→ catch 成重写信号,不当崩溃
        try:
            _commit_paragraphs(conn, state["chapter_id"], state["prose"])
            _emit(state["run_id"], "commit", "enter", {"iter": state["iter"]})
            return {"rejected": False}
        except SystemExit as e:
            # guard 拒绝:prose 像 worklog/重度污染 → 回 write 带反馈重交
            _emit(state["run_id"], "commit", "error", {"rejected": True, "reason": str(e)[:120]})
            return {"rejected": True, "violations_feedback": f"上版正文被入库 guard 拒绝({str(e)[:80]}),请重交纯小说正文。"}

    def l2_check(state):
        if dry_run:
            rdict = {"passed_hard_gate": True, "beat_violations": [], "metrics": {"word_count": 3200}}
            _emit(state["run_id"], "l2", "l2_verdict", {"passed": True, "violations": 0, "words": 3200})
            return {"report": rdict, "violations_feedback": ""}
        report = run_l2(conn, state["chapter_id"])   # 信任锚,Python 直调,零 LLM
        rdict = asdict(report)
        passed = bool(rdict.get("passed_hard_gate"))
        violations = rdict.get("beat_violations") or []
        # 失败时构造违规反馈供回 write 定向修(passed 则不回 write,反馈不被消费)
        fb = ""
        if not passed:
            fb = "; ".join(f"{v.get('beat_id','?')}:{v.get('kind','?')}-{v.get('detail','')[:60]}"
                           for v in violations) or "结构门禁未过(见 run-l2)"
        _emit(state["run_id"], "l2", "l2_verdict",
              {"passed": passed, "violations": len(violations),
               "words": (rdict.get("metrics") or {}).get("word_count")})
        return {"report": rdict, "violations_feedback": fb}

    def finalize(state):
        run_id = state["run_id"]
        chapter_id = state["chapter_id"]
        ensure_flag(conn, chapter_id)
        report = state.get("report") or {}
        passed = bool(report.get("passed_hard_gate"))
        # Finalize 独立 verify-persisted(信任锚终审);通过 → completed
        ok = False
        if dry_run:
            ok = True   # 免 key 占位(跳过真实 verify)
        else:
            try:
                ok = bool(verify_chapter_persisted(conn, chapter_id, export_path=export_path))
            except Exception as e:
                _emit(run_id, "finalize", "error", {"verify_error": str(e)[:120]})
        status = "completed" if (ok and passed) else "failed"
        if not ok:
            mark_forced_persist_failed(conn, chapter_id)
        elif not passed:
            # L2 未过(write 未收敛到 cap)→ mark-unresolved,不阻 status 流转但留旗
            mark_unresolved(conn, chapter_id, json.dumps(report.get("beat_violations") or [], ensure_ascii=False), 0)
        if ok and passed and not dry_run:
            set_chapter_status(conn, chapter_id, "completed")
            try:
                _export_chapter_json(conn, type(project) is str and __import__("pathlib").Path(project) or project,
                                     chapter_id, state["chapter_global"], "draft")
            except Exception as e:
                print(f"[runner] draft 备份失败(不阻塞): {e}", file=sys.stderr)
        _emit(run_id, "finalize", "enter", {"persisted": ok, "passed": passed})
        try:
            end_run(conn, run_id, status, current_node="finalize")
        except Exception as e:
            print(f"[runner] end_run 失败(不阻塞): {e}", file=sys.stderr)
        words = (report.get("metrics") or {}).get("word_count")
        return {"result": {"status": status, "chapter": state["chapter_global"],
                           "passed": passed, "persisted": ok, "words": words,
                           "iterations": state["iter"],
                           "editor_iterations": state.get("editor_iter", 0)}}

    return {"boot": boot, "write": write, "revise": revise, "commit": commit,
            "l2_check": l2_check, "finalize": finalize}
