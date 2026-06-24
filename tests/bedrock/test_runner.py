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


def test_cond_l2_revise_passed_to_finalize():
    assert _cond_l2({"report": {"passed_hard_gate": True}, "phase": "revise", "editor_iter": 1, "editor_cap": 5}) == "finalize"


def test_cond_l2_revise_failed_under_cap_to_revise():
    assert _cond_l2({"report": {"passed_hard_gate": False}, "phase": "revise", "editor_iter": 1, "editor_cap": 5}) == "revise"


def test_cond_l2_revise_failed_at_cap_to_finalize():
    assert _cond_l2({"report": {"passed_hard_gate": False}, "phase": "revise", "editor_iter": 5, "editor_cap": 5}) == "finalize"


# ── 图结构 ──

def test_graph_compiles_with_pipeline_nodes(tmp_project):
    conn = get_connection(tmp_project)
    g, rl = build_graph(conn, tmp_project)
    names = set(g.get_graph().nodes.keys())
    for n in ("boot", "write", "revise", "commit", "l2_check", "finalize"):
        assert n in names
    assert rl >= 25
    conn.close()


# ── 集成控制流(mock I/O)──

def _run(tmp, monkeypatch, *, l2_pass_seq, cap=3, editor_cap=5):
    """跑图;l2_pass_seq=每次 l2_check 的 passed 序列(超出长度取末值);返回 (result, events)。"""
    conn, cid = _seed(tmp)
    calls = {"l2": 0}
    l2_pass_seq = list(l2_pass_seq)

    def fake_run_l2(c, chapter_id):
        i = calls["l2"]
        calls["l2"] += 1
        passed = l2_pass_seq[min(i, len(l2_pass_seq) - 1)]
        return _FakeReport(passed_hard_gate=passed,
                           beat_violations=[] if passed else [{"beat_id": 1, "kind": "x", "detail": "d"}])

    monkeypatch.setattr(nodes, "get_writer_model", lambda config, process="writer": _fake_model())
    monkeypatch.setattr(nodes, "run_l2", fake_run_l2)
    monkeypatch.setattr(nodes, "verify_chapter_persisted", lambda c, cid, export_path=None: True)
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
    writes = [e for e in evs if e["node"] == "write"]
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
