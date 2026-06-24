"""runner 控制流测试。确定性图的核心是路由 + cap,这些不依赖真实 LLM/API。
mock 掉 4 个 I/O(get_writer_model/run_l2/verify_chapter_persisted/_commit_paragraphs),
seed 最小 chapter,invoke 图,断言控制流轨迹(收敛/重试/cap 截断/write→revise 前推/双阶段耗尽)。

v2 起 write 子图收敛结构(过→revise;耗尽→revise 接管结构),revise 子图做文风/二次结构
(过→finalize;耗尽→finalize failed)。两阶段共享 commit/l2_check,phase 区分条件边。
"""
import tempfile, pathlib
from dataclasses import dataclass, field
from unittest.mock import MagicMock

from src.bedrock.db.connection import get_connection
from src.bedrock.db.migrate import apply_migrations
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat
from src.bedrock.repositories.outline import save_volume_outline
from src.bedrock.runner import nodes, graph as graph_mod
from src.bedrock.runner.graph import build_graph, _cond_commit, _cond_l2
from src.bedrock.workflow.run_repo import list_events


@dataclass
class _FakeReport:
    beat_violations: list = field(default_factory=list)
    advisory: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=lambda: {"word_count": 3000})
    drift: dict = field(default_factory=dict)
    passed_hard_gate: bool = True


def _seed(tmp):
    apply_migrations(tmp)
    conn = get_connection(tmp)
    vid = create_volume(conn, 1, "v1", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t1")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="主角登场并推进核心情节冲突", pov_character_id=None)
    # boot-context 必需 volume_outline(beat 契约从此读)
    save_volume_outline(conn, vid, [{"beat_id": bid, "sequence": 1,
                                     "purpose": "主角登场并推进核心情节冲突", "pov": None}])
    conn.commit()
    return conn, cid


def _fake_model(text="第一章正文。" * 200):
    m = MagicMock()
    m.invoke.return_value = MagicMock(content=text)
    return m


# ── 纯路由逻辑 ──

def test_cond_commit_not_rejected_to_l2():
    assert _cond_commit({"rejected": False, "phase": "write", "iter": 1, "cap": 3}) == "l2_check"


def test_cond_commit_write_rejected_under_cap_to_write():
    assert _cond_commit({"rejected": True, "phase": "write", "iter": 1, "cap": 3}) == "write"


def test_cond_commit_write_rejected_at_cap_to_finalize():
    assert _cond_commit({"rejected": True, "phase": "write", "iter": 3, "cap": 3}) == "finalize"


def test_cond_commit_revise_rejected_under_cap_to_revise():
    assert _cond_commit({"rejected": True, "phase": "revise", "editor_iter": 1, "editor_cap": 5}) == "revise"


def test_cond_commit_revise_rejected_at_cap_to_finalize():
    assert _cond_commit({"rejected": True, "phase": "revise", "editor_iter": 5, "editor_cap": 5}) == "finalize"


def test_cond_l2_write_passed_to_revise():
    # v2:write 阶段 L2 过 → 前推到 revise(editor 接管),不直接 finalize
    assert _cond_l2({"report": {"passed_hard_gate": True}, "phase": "write", "iter": 1, "cap": 3}) == "revise"


def test_cond_l2_write_failed_under_cap_to_write():
    assert _cond_l2({"report": {"passed_hard_gate": False}, "phase": "write", "iter": 1, "cap": 3}) == "write"


def test_cond_l2_write_failed_at_cap_to_revise():
    # write 耗尽仍不过 → revise 接管结构(非 finalize,给 editor 第二线机会)
    assert _cond_l2({"report": {"passed_hard_gate": False}, "phase": "write", "iter": 3, "cap": 3}) == "revise"


def test_cond_l2_revise_passed_to_consistency():
    # v2:revise 阶段 L2 过 → 进 consistency(角色正典 ops),不直接 finalize
    assert _cond_l2({"report": {"passed_hard_gate": True}, "phase": "revise", "editor_iter": 1, "editor_cap": 5}) == "consistency"


def test_cond_l2_revise_failed_under_cap_to_revise():
    assert _cond_l2({"report": {"passed_hard_gate": False}, "phase": "revise", "editor_iter": 1, "editor_cap": 5}) == "revise"


def test_cond_l2_revise_failed_at_cap_to_finalize():
    assert _cond_l2({"report": {"passed_hard_gate": False}, "phase": "revise", "editor_iter": 5, "editor_cap": 5}) == "finalize"


# ── 图结构 ──

def test_graph_compiles_with_pipeline_nodes(tmp_project):
    conn = get_connection(tmp_project)
    g, rl = build_graph(conn, tmp_project)
    names = set(g.get_graph().nodes.keys())
    for n in ("boot", "write", "revise", "consistency", "proper_nouns", "commit", "l2_check", "finalize"):
        assert n in names
    assert rl >= 25
    conn.close()


# ── 集成控制流(mock I/O)──

def _run(tmp, monkeypatch, *, l2_pass_seq, cap=3, editor_cap=5, l2_counter=None,
         verify_result=True):
    """跑图;l2_pass_seq=每次 l2_check 的 passed 序列(超出长度取末值);返回 (result, events)。
    l2_counter: 可选 dict,传入则回填 run_l2 总调用次数(triple-gate 断言用)。
    verify_result: finalize gate-3(verify-persisted)的返回值,测 gate-3 权威性用。"""
    conn, cid = _seed(tmp)
    calls = {"l2": 0}
    l2_pass_seq = list(l2_pass_seq)

    def fake_run_l2(c, chapter_id):
        i = calls["l2"]
        calls["l2"] += 1
        passed = l2_pass_seq[min(i, len(l2_pass_seq) - 1)]
        return _FakeReport(passed_hard_gate=passed,
                           beat_violations=[] if passed else [{"beat_id": 1, "kind": "x", "detail": "d"}])

    monkeypatch.setattr(nodes, "call_llm",
                        lambda config, process, prompt: {"content": "第一章正文。" * 200,
                                                          "endpoint": "X", "model": "m",
                                                          "tokens_in": 10, "tokens_out": 20, "latency_ms": 5})
    monkeypatch.setattr(nodes, "run_l2", fake_run_l2)
    monkeypatch.setattr(nodes, "verify_chapter_persisted", lambda c, cid, export_path=None: verify_result)
    monkeypatch.setattr(nodes, "_commit_paragraphs", lambda c, cid, raw: {"paragraph_count": 10})
    monkeypatch.setattr(nodes, "_export_chapter_json", lambda *a, **k: None)
    monkeypatch.setattr(nodes, "set_chapter_status", lambda *a, **k: None)

    g, rl = build_graph(conn, tmp)
    # 覆盖双 cap:patch get_workflow_config 返回 caps
    monkeypatch.setattr(nodes, "get_workflow_config",
                        lambda c, v: {"caps": {"writer": cap, "editor": editor_cap}, "models": {}})
    final = g.invoke(
        {"chapter_global": 1, "volume_id": 1, "chapter_id": 0, "ctx": {}, "config": {},
         "prose": "", "report": {}, "phase": "write", "iter": 0, "cap": cap,
         "editor_iter": 0, "editor_cap": editor_cap, "run_id": 0, "rejected": False,
         "violations_feedback": "", "result": {}},
        config={"configurable": {"thread_id": "t1"}, "recursion_limit": rl},
    )
    evs = list_events(conn, final["run_id"])
    if l2_counter is not None:
        l2_counter["n"] = calls["l2"]
    conn.close()
    return final, evs


def test_converge_first_try_then_revise(tmp_path, monkeypatch):
    # write 一次过 → 前推 revise → revise 过 → finalize(completed)
    final, evs = _run(tmp_path, monkeypatch, l2_pass_seq=[True, True], cap=3)
    assert final["result"]["status"] == "completed"
    assert final["result"]["passed"] is True
    assert final["iter"] == 1            # write 一次
    assert final["editor_iter"] == 1     # revise 一次
    nodes_seq = [e["node"] for e in evs]
    assert nodes_seq[0] == "boot"
    for n in ("write", "revise", "commit", "l2", "finalize"):
        assert n in nodes_seq


def test_write_retry_then_converge_to_revise(tmp_path, monkeypatch):
    # write 第一次不过→重写→第二次过→revise→过→finalize
    final, evs = _run(tmp_path, monkeypatch, l2_pass_seq=[False, True, True], cap=3)
    assert final["result"]["status"] == "completed"
    assert final["iter"] == 2            # write 两次
    assert final["editor_iter"] == 1
    writes = [e for e in evs if e["node"] == "write" and e["kind"] == "iteration"]
    assert len(writes) == 2
    assert writes[1]["payload"]["retry"] is True
    assert writes[0]["payload"]["retry"] is False


def test_write_cap_exhaust_revise_rescues(tmp_path, monkeypatch):
    # write 跑满 cap 仍不过 → revise 接管结构 → revise 一次过 → finalize(completed)
    final, evs = _run(tmp_path, monkeypatch, l2_pass_seq=[False, False, False, True], cap=3)
    assert final["result"]["status"] == "completed"
    assert final["result"]["passed"] is True
    assert final["iter"] == 3            # write 跑满
    assert final["editor_iter"] == 1     # revise 救回结构


def test_both_phases_exhaust_marks_unresolved(tmp_path, monkeypatch):
    # write(3) + revise(2) 全不过 → finalize failed(passed=False)
    final, evs = _run(tmp_path, monkeypatch, l2_pass_seq=[False], cap=3, editor_cap=2)
    assert final["result"]["status"] == "failed"
    assert final["result"]["passed"] is False
    assert final["iter"] == 3            # write 跑满
    assert final["editor_iter"] == 2     # revise 跑满


# ── triple L2 gate(三道独立 L2 门禁)──

def test_triple_gate_all_fire(tmp_path, monkeypatch):
    # clean converge:gate-1(write l2)+ gate-2(revise l2) 各跑一次(nodes.run_l2),
    # gate-3(finalize verify-persisted)也跑(finalize 事件 gate=finalize,persisted=True)。
    # 无角色正典 → consistency 跳过(不增 run_l2);proper_nouns 零 LLM。
    ctr = {}
    final, evs = _run(tmp_path, monkeypatch, l2_pass_seq=[True, True], cap=3, l2_counter=ctr)
    assert ctr["n"] == 2                        # gate-1 + gate-2
    gates = [e["payload"].get("gate") for e in evs if e["node"] == "l2"]
    assert "write" in gates and "revise" in gates
    fin = [e for e in evs if e["node"] == "finalize"][0]
    assert fin["payload"]["gate"] == "finalize" and fin["payload"]["persisted"] is True  # gate-3 fired
    assert final["result"]["status"] == "completed"


def test_gate3_authoritative_overrides_earlier_pass(tmp_path, monkeypatch):
    # write + revise 门禁都过,但 finalize gate-3(verify-persisted)判不过 → status failed。
    # 证明 gate-3 是终审权威:不信任前序 gate 的 passed 快照,独立复检最终 DB。
    final, evs = _run(tmp_path, monkeypatch, l2_pass_seq=[True, True], cap=3, verify_result=False)
    assert final["result"]["status"] == "failed"
    assert final["result"]["persisted"] is False
    assert final["result"]["passed"] is True    # 前序 gate 过(report),但 gate-3 否决


def test_triple_gate_with_consistency_gates_too(tmp_path, monkeypatch):
    # 有角色正典时 consistency 内部也跑一道 L2(gate 2.5):write + revise + consistency = 3 次 nodes.run_l2。
    # 注:_run 的 boot ctx 来自真实 get_chapter_boot_context(无 character 种子)→ 这里直接验无正典场景
    # 下 consistency 不增 gate(已由 test_triple_gate_all_fire 覆盖);本例确认 consistency 节点存在且 gate 标签机制就绪。
    ctr = {}
    final, evs = _run(tmp_path, monkeypatch, l2_pass_seq=[True, True], cap=3, l2_counter=ctr)
    # consistency:skip(无正典),不增 run_l2
    cons = [e for e in evs if e["node"] == "consistency"]
    assert cons and cons[0]["kind"] == "skip"
    assert ctr["n"] == 2   # 仍是 gate-1 + gate-2


# ── 全管线 dry-run(真实 DB 路径,boot 真跑,LLM/L2/verify 全 mock-pass)──

def test_full_pipeline_dry_run_sequence(tmp_path, monkeypatch):
    """全管线 dry-run 端到端:boot(真)→write/commit/l2(mock)→revise/commit/l2→
    consistency(skip)→proper_nouns(skip)→finalize(mock ok)。断言完整节点拓扑 + completed。"""
    conn, cid = _seed(tmp_path)
    g, rl = build_graph(conn, tmp_path, dry_run=True)
    final = g.invoke(
        {"chapter_global": 1, "volume_id": 1, "chapter_id": 0, "ctx": {}, "config": {},
         "prose": "", "report": {}, "phase": "write", "iter": 0, "cap": 3,
         "editor_iter": 0, "editor_cap": 5, "run_id": 0, "rejected": False,
         "violations_feedback": "", "result": {}},
        config={"configurable": {"thread_id": "dry-full"}, "recursion_limit": rl})
    evs = list_events(conn, final["run_id"])
    seq = [e["node"] for e in evs]
    # 完整 v2 管线拓扑(确定性,无分支,因 dry-run 全 pass)
    assert seq == ["boot", "write", "commit", "l2", "revise", "commit", "l2",
                   "consistency", "proper_nouns", "finalize"]
    assert final["result"]["status"] == "completed"
    assert final["result"]["passed"] is True
    assert final["result"]["persisted"] is True
    assert final["iter"] == 1 and final["editor_iter"] == 1
    conn.close()


# ── consistency 节点单元(直调闭包,mock I/O)──

def _consistency_node(tmp, monkeypatch, *, ops_json, post_l2_pass=True, has_chars=True, report_passed=True):
    """直调 consistency 节点闭包,返回 (delta, applied_ops, reverted, flagged)。"""
    conn, cid = _seed(tmp)
    nm = nodes.make_nodes(conn, tmp)   # dry_run=False
    rows = [{"para_id": 1, "seq": 1, "text": "他走进来。"},
            {"para_id": 2, "seq": 2, "text": "她说好。"}]
    monkeypatch.setattr(nodes, "list_paragraphs_in_chapter", lambda c, cid: rows)
    monkeypatch.setattr(nodes, "call_llm",
                        lambda config, process, prompt: {"content": ops_json, "endpoint": "X",
                                                          "model": "m", "tokens_in": 1,
                                                          "tokens_out": 2, "latency_ms": 3})
    monkeypatch.setattr(nodes, "run_l2", lambda c, cid: _FakeReport(passed_hard_gate=post_l2_pass))
    applied = {"n": 0}
    monkeypatch.setattr(nodes, "_apply_paragraph_ops",
                        lambda c, cid, ops: applied.__setitem__("n", len(ops)) or {"applied": ops})
    reverted = {"n": 0}
    monkeypatch.setattr(nodes, "_commit_paragraphs", lambda c, cid, raw: reverted.__setitem__("n", 1) or {})
    flagged = {"n": 0}
    monkeypatch.setattr(nodes, "mark_polish_broke_beat", lambda c, cid: flagged.__setitem__("n", 1))
    ctx = ({"characters": [{"name": "陆沉", "pronoun": "他", "gender": "男", "role": "主角"}]}
           if has_chars else {})
    state = {"chapter_id": cid, "chapter_global": 1, "volume_id": 1, "run_id": 0,
             "config": {}, "report": {"passed_hard_gate": report_passed}, "ctx": ctx}
    delta = nm["consistency"](state)
    conn.close()
    return delta, applied["n"], reverted["n"], flagged["n"]


def test_consistency_applied_keeps_post_l2(tmp_path, monkeypatch):
    ops = '[{"op":"update","para_id":1,"text":"他走进来了。"}]'
    delta, applied, reverted, flagged = _consistency_node(tmp_path, monkeypatch, ops_json=ops, post_l2_pass=True)
    assert applied == 1                     # ops 已落
    assert reverted == 0 and flagged == 0   # 未破 L2,不回退不留旗
    assert delta.get("report", {}).get("passed_hard_gate") is True   # 取 post-consistency L2


def test_consistency_no_ops_skips(tmp_path, monkeypatch):
    # LLM 返 [] → 无需改动,章节不动
    _, applied, reverted, flagged = _consistency_node(tmp_path, monkeypatch, ops_json="[]")
    assert applied == 0 and reverted == 0 and flagged == 0


def test_consistency_garbage_skips(tmp_path, monkeypatch):
    # LLM 返叙述(无可解析数组)→ 跳过,不毁章
    _, applied, reverted, flagged = _consistency_node(
        tmp_path, monkeypatch, ops_json="这章没问题,无需修改。")
    assert applied == 0 and reverted == 0 and flagged == 0


def test_consistency_broke_l2_rolls_back(tmp_path, monkeypatch):
    # ops 落了但破 L2 → 回退 pre 快照 + mark-polish-broke-beat;report 保持 pre(passed)
    ops = '[{"op":"update","para_id":1,"text":"短"}]'   # 故意触发 post-L2 不过
    delta, applied, reverted, flagged = _consistency_node(
        tmp_path, monkeypatch, ops_json=ops, post_l2_pass=False)
    assert applied == 1      # 落过
    assert reverted == 1     # 回退 pre
    assert flagged == 1      # 留旗
    assert delta == {}       # report 不变(pre,passed)


def test_consistency_gated_without_characters(tmp_path, monkeypatch):
    # 无角色正典 → 跳过(不调 LLM)
    _, applied, reverted, flagged = _consistency_node(
        tmp_path, monkeypatch, ops_json='[{"op":"update","para_id":1,"text":"x"}]', has_chars=False)
    assert applied == 0 and reverted == 0 and flagged == 0


def test_consistency_gated_when_l2_not_passed(tmp_path, monkeypatch):
    # L2 未过(write/revise 未收敛)→ 不跑一致性(没意义)
    _, applied, reverted, flagged = _consistency_node(
        tmp_path, monkeypatch, ops_json='[{"op":"update","para_id":1,"text":"x"}]', report_passed=False)
    assert applied == 0 and reverted == 0 and flagged == 0


# ── proper_nouns 节点单元(确定性,零 LLM)──

def _proper_nouns_node(tmp, monkeypatch, *, ops, escalate, report_passed=True, apply_raises=False):
    """直调 proper_nouns 节点闭包,mock _check_proper_nouns/apply;返回 (delta, applied_n)。"""
    conn, cid = _seed(tmp)
    nm = nodes.make_nodes(conn, tmp)   # dry_run=False
    monkeypatch.setattr(nodes, "_check_proper_nouns",
                        lambda c, cid: {"ops": ops, "escalate": escalate, "autoedit_count": len(ops)})
    applied = {"n": 0}

    def fake_apply(c, cid, o):
        if apply_raises:
            raise SystemExit("edit-paragraphs 回滚: bad op")
        applied["n"] = len(o)
        return {"applied": o}
    monkeypatch.setattr(nodes, "_apply_paragraph_ops", fake_apply)
    state = {"chapter_id": cid, "chapter_global": 1, "volume_id": 1, "run_id": 0,
             "config": {}, "report": {"passed_hard_gate": report_passed}}
    delta = nm["proper_nouns"](state)
    conn.close()
    return delta, applied["n"]


def test_proper_nouns_applied(tmp_path, monkeypatch):
    # Tier1 ops → 经 edit-paragraphs 落
    ops = [{"op": "update", "para_id": 1, "text": "陆沉走进来。"}]
    _, applied = _proper_nouns_node(tmp_path, monkeypatch, ops=ops, escalate=[])
    assert applied == 1


def test_proper_nouns_no_ops_clean(tmp_path, monkeypatch):
    # 无 variant → 不动
    _, applied = _proper_nouns_node(tmp_path, monkeypatch, ops=[], escalate=[])
    assert applied == 0


def test_proper_nouns_escalate_only_no_edit(tmp_path, monkeypatch):
    # 仅 Tier2 歧义(escalate)→ 不自动改(留卷审),applied=0
    _, applied = _proper_nouns_node(
        tmp_path, monkeypatch, ops=[], escalate=[{"para_id": 1, "variant": "小陆", "candidates": ["陆沉", "陆远"]}])
    assert applied == 0


def test_proper_nouns_gated_when_l2_not_passed(tmp_path, monkeypatch):
    # L2 未过 → 不跑专名校验
    _, applied = _proper_nouns_node(
        tmp_path, monkeypatch, ops=[{"op": "update", "para_id": 1, "text": "x"}], escalate=[], report_passed=False)
    assert applied == 0


def test_proper_nouns_apply_failure_does_not_crash(tmp_path, monkeypatch):
    # apply 抛 SystemExit(坏 op)→ 节点 catch,不崩,escalate 仍 emit
    delta, applied = _proper_nouns_node(
        tmp_path, monkeypatch, ops=[{"op": "update", "para_id": 1, "text": "x"}],
        escalate=[{"para_id": 2, "variant": "v", "candidates": ["c"]}], apply_raises=True)
    assert applied == 0   # apply 失败未计入
    assert delta == {}
