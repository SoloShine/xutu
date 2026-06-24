# src/bedrock/runner/graph.py
"""建确定性 StateGraph:

  boot→write→commit→[cond_commit]→l2_check→[cond_after_l2]→(write|revise|finalize)
                                                       │
                                       (revise subgraph,同构) revise→commit→l2_check→…

两阶段自纠(write 结构收敛 → revise 文风/二次结构),共享 commit/l2_check 节点,
由 state.phase 区分条件边回写 write 还是 revise,以及前推到下一阶段还是 finalize。
控制流全在 Python(条件边 + cap);LLM 只在 write/revise 出正文。recursion_limit 由双 cap 推。
conn 经 make_nodes 闭包绑定,不入态。MemorySaver checkpoint(可恢复)。
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

from .state import RunnerState
from .nodes import make_nodes
from ..workflow.config_repo import get_workflow_config


def _cond_commit(state):
    """commit 后:被 guard 拒绝→回当前阶段主节点(若未到该阶段 cap,否则 finalize);
    未拒→进 L2 复核。phase 决定回 write 还是 revise。"""
    if not state.get("rejected"):
        return "l2_check"
    if state.get("phase") == "revise":
        return "revise" if state["editor_iter"] < state["editor_cap"] else "finalize"
    return "write" if state["iter"] < state["cap"] else "finalize"


def _cond_after_l2(state):
    """L2 后(共享,phase 区分):
    write 阶段:过→revise(交 editor 做文风+二次复核);未过且 iter<cap→回 write;到 cap→revise(editor 接管结构)。
    revise 阶段:过→finalize;未过且 editor_iter<editor_cap→回 revise;到 cap→finalize(mark-unresolved)。"""
    report = state.get("report") or {}
    phase = state.get("phase", "write")
    if report.get("passed_hard_gate"):
        return "revise" if phase == "write" else "finalize"
    if phase == "revise":
        return "revise" if state["editor_iter"] < state["editor_cap"] else "finalize"
    return "write" if state["iter"] < state["cap"] else "revise"


# 兼容旧测试名(纯路由辅助)——语义已并入 _cond_after_l2
_cond_l2 = _cond_after_l2


def build_graph(conn, project, export_path=None, dry_run=False):
    """建并编译图。返回 (compiled graph, recursion_limit)。每节点闭包绑定 conn。"""
    nodes = make_nodes(conn, project, export_path=export_path, dry_run=dry_run)
    g = StateGraph(RunnerState)
    g.add_node("boot", nodes["boot"])
    g.add_node("write", nodes["write"])
    g.add_node("revise", nodes["revise"])
    g.add_node("commit", nodes["commit"])
    g.add_node("l2_check", nodes["l2_check"])
    g.add_node("finalize", nodes["finalize"])

    g.add_edge(START, "boot")
    g.add_edge("boot", "write")
    g.add_edge("write", "commit")
    g.add_edge("revise", "commit")
    g.add_conditional_edges("commit", _cond_commit,
                            {"write": "write", "revise": "revise", "l2_check": "l2_check", "finalize": "finalize"})
    g.add_conditional_edges("l2_check", _cond_after_l2,
                            {"write": "write", "revise": "revise", "finalize": "finalize"})
    g.add_edge("finalize", END)

    # recursion_limit:write 子图(write/commit/l2 ≈3 节点 * writer cap)+ revise 子图(* editor cap)
    # + boot/finalize + 裕量。从 work-scope config 读双 cap。
    try:
        cfg = get_workflow_config(conn, None)
        wcap = int((cfg.get("caps") or {}).get("writer", 3)) or 3
        ecap = int((cfg.get("caps") or {}).get("editor", 5)) or 5
    except Exception:
        wcap, ecap = 3, 5
    limit = max(25, (wcap + ecap) * 4 + 20)
    return g.compile(checkpointer=InMemorySaver()), limit
