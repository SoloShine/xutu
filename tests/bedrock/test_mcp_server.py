# tests/bedrock/test_mcp_server.py（新建）
import inspect
from pathlib import Path
import pytest

from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_paragraph,
)
from src.bedrock.repositories.worldbook import add_constant
from src.bedrock.mcp_server import (
    export_project, diagnose, show_review_report, list_volumes,
    diff_drift, run_l2_check, get_chapter_flag, list_chapters,
    _project_ok,
)
from src.bedrock.cli.reader_commands import do_export


@pytest.fixture(autouse=True)
def _workspace_env(tmp_project, monkeypatch):
    """让 _project_ok 把 tmp_project 视为合法 workspace。"""
    monkeypatch.setenv("NOVEL_WORKSPACE", str(tmp_project))


def _seed(conn):
    v1 = create_volume(conn, 1, "第一卷", 1, 2, "opening")
    c1 = create_chapter(conn, volume_id=v1, global_number=1, title="甲", status="completed")
    create_paragraph(conn, chapter_id=c1, seq=1, text="正文甲",
                     content_hash="h1", beat_id=None, role="narration")
    add_constant(conn, key="work_name", value="测试书")
    return v1, c1


def test_export_project_chapter(tmp_project):
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    result = export_project(str(tmp_project), scope="chapter", target=1, fmt="md")
    assert "path" in result and "content_hash" in result and "chapter_count" in result
    assert Path(result["path"]).exists()
    assert result["chapter_count"] == 1


def test_export_project_path_uses_posix(tmp_project):
    """path 用 as_posix（正斜杠），即使 Windows。"""
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    result = export_project(str(tmp_project), scope="chapter", target=1)
    assert "\\" not in result["path"]    # POSIX 正斜杠


def test_export_project_out_not_exposed():
    """R2：export_project 签名无 out 参数（path traversal 防御）。"""
    sig = inspect.signature(export_project)
    assert "out" not in sig.parameters


def test_diagnose_tool_volume(tmp_project):
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    report = diagnose(str(tmp_project), scope="volume", volume_id=v1)
    assert "体检模式标记" in report
    assert "flag-only" in report


def test_diagnose_tool_volume_missing_id_returns_error(tmp_project):
    """R3：scope=volume + volume_id=None → 结构化错误，不崩。"""
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    result = diagnose(str(tmp_project), scope="volume", volume_id=None)
    assert isinstance(result, dict) and "error" in result


def test_show_review_report_tool(tmp_project):
    (tmp_project / "review_report_vol1.md").write_text(
        "# VolumeReview 报告 — 卷 1\n\n## 修正结果（三状态）\n- ch1: escalate_human\n",
        encoding="utf-8")
    out = show_review_report(str(tmp_project), volume_id=1, escalate_only=True)
    assert "ch1" in out


def test_list_volumes_tool(tmp_project):
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    vols = list_volumes(str(tmp_project))
    assert len(vols) == 1
    assert vols[0]["number"] == 1
    assert vols[0]["name"] == "第一卷"


def test_diff_drift_tool(tmp_project):
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    do_export(conn, tmp_project, scope="chapter", target=c1, fmt="md", final=False, out=None)
    conn.close()
    out = diff_drift(str(tmp_project), scope="chapter", target=1)
    assert "漂移检测" in out


def test_run_l2_check_returns_compact(tmp_project):
    """R1：beat_violations 含真实四字段 beat_id/kind/detail/fix_hint；无 advisory/metrics/drift。"""
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    result = run_l2_check(str(tmp_project), global_number=1)
    assert "passed_hard_gate" in result
    assert "violations_count" in result
    assert "beat_violations" in result
    assert isinstance(result["beat_violations"], list)
    if result["beat_violations"]:   # 若有 violation，断言四字段
        v0 = result["beat_violations"][0]
        assert {"beat_id", "kind", "detail", "fix_hint"} <= set(v0.keys())
    assert "advisory" not in result   # 精简：不含大字段
    assert "metrics" not in result
    assert "drift" not in result


def test_get_chapter_flag_no_flag(tmp_project):
    """章无旗行 → {has_flag:False, flag:None}。"""
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    result = get_chapter_flag(str(tmp_project), global_number=1)
    assert result["has_flag"] is False
    assert result["flag"] is None


def test_get_chapter_flag_with_flag(tmp_project):
    from src.bedrock.orchestration.review_flag import mark_unresolved
    from src.bedrock.checks.beat_fulfillment import BeatViolation
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    mark_unresolved(conn, c1, [BeatViolation(beat_id=1, kind="unwritten_beat",
                                             detail="d", fix_hint="h")],
                    likely_rule_or_model_issue=False)
    conn.commit()
    conn.close()
    result = get_chapter_flag(str(tmp_project), global_number=1)
    assert result["has_flag"] is True
    assert result["flag"]["l2_unresolved"] == 1


def test_list_chapters_joins_volume_number(tmp_project):
    """Y5：list_chapters 返回含 volume_number/volume_name。"""
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    chs = list_chapters(str(tmp_project))
    assert len(chs) == 1
    assert chs[0]["global_number"] == 1
    assert chs[0]["volume_number"] == 1
    assert chs[0]["volume_name"] == "第一卷"


def test_list_chapters_volume_filter(tmp_project):
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    v2 = create_volume(conn, 2, "第二卷", 3, 4, "climax")
    create_chapter(conn, volume_id=v2, global_number=3, title="乙", status="planned")
    conn.close()
    chs = list_chapters(str(tmp_project), volume_id=v2)
    assert len(chs) == 1
    assert chs[0]["global_number"] == 3


# ---- SP6-B 边界鲁棒性测试（§8 层 2）----

def test_project_path_traversal_rejected(tmp_project, monkeypatch):
    """R2：project 路径越界 workspace → 错误。tmp_project 是合法 workspace，
    一个 workspace 外的路径应被拒。autouse 已设 NOVEL_WORKSPACE=tmp_project，
    这里显式再设一次（monkeypatch 后设的覆盖 autouse 的）。"""
    monkeypatch.setenv("NOVEL_WORKSPACE", str(tmp_project))
    err = _project_ok(str(tmp_project.parent / "other"))
    assert err and "越界" in err


def test_missing_db_returns_structured_error(tmp_project, tmp_path, monkeypatch):
    """目录无 bedrock.db → 错误，且不创建空 db。empty_dir 在 tmp_path 下而非
    tmp_project 下，所以把 workspace 放宽到 tmp_path（覆盖 autouse 的 tmp_project）。"""
    empty_dir = tmp_path / "empty_proj"
    empty_dir.mkdir()
    monkeypatch.setenv("NOVEL_WORKSPACE", str(tmp_path))   # 覆盖 autouse，让 empty_dir 在 workspace 下
    result = export_project(str(empty_dir), scope="book")
    assert isinstance(result, dict) and "error" in result
    assert not (empty_dir / "bedrock.db").exists()   # 不创建空 db


def test_unknown_global_number_returns_structured_error(tmp_project):
    """global_number 不存在 → SystemExit 被 catch → 结构化错误，不崩。"""
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    result = run_l2_check(str(tmp_project), global_number=999)
    assert isinstance(result, dict) and "error" in result


def test_scope_chapter_missing_target_returns_error(tmp_project):
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    result = export_project(str(tmp_project), scope="chapter", target=None)
    assert isinstance(result, dict) and "error" in result
    assert "target" in result["error"]


def test_tool_catches_exception_no_crash(tmp_project, monkeypatch):
    """注入纯函数抛异常 → 结构化错误，函数正常返回（server 存活）。"""
    conn = get_connection(tmp_project)
    v1, c1 = _seed(conn)
    conn.close()
    import src.bedrock.mcp_server as ms

    def boom(*a, **k):
        raise RuntimeError("injected")

    monkeypatch.setattr(ms, "do_export", boom)
    result = export_project(str(tmp_project), scope="chapter", target=1)
    assert isinstance(result, dict) and "error" in result
    assert "injected" in result["error"]
