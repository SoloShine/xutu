from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_paragraph,
)
from src.bedrock.repositories.worldbook import add_constant
from src.bedrock.cli.reader_commands import (
    chapter_filename, render_chapter_body, do_export,
)


def _seed_chapter_with_paragraphs(conn):
    """建 1 卷 1 章 2 段，返回 (chapter_id, global_number, title)。"""
    vid = create_volume(conn, 1, "测试卷", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="破晓")
    create_paragraph(conn, chapter_id=cid, seq=1, text="第一段正文。",
                     content_hash="h1", beat_id=None, role="narration")
    create_paragraph(conn, chapter_id=cid, seq=2, text="第二段正文。",
                     content_hash="h2", beat_id=None, role="narration")
    return cid, 1, "破晓"


def test_chapter_filename_zero_padded(tmp_project):
    assert chapter_filename(1) == "ch01"
    assert chapter_filename(5) == "ch05"
    assert chapter_filename(42) == "ch42"
    assert chapter_filename(239) == "ch239"


def test_render_chapter_body_md(tmp_project):
    conn = get_connection(tmp_project)
    cid, gnum, title = _seed_chapter_with_paragraphs(conn)
    body = render_chapter_body(conn, cid, "md")
    assert body.startswith(f"### 第{gnum}章 {title}")
    assert "第一段正文。" in body
    assert "第二段正文。" in body
    # 段落空行分隔
    assert "第一段正文。\n\n第二段正文。" in body
    conn.close()


def test_render_chapter_body_txt_no_markdown(tmp_project):
    conn = get_connection(tmp_project)
    cid, gnum, title = _seed_chapter_with_paragraphs(conn)
    body = render_chapter_body(conn, cid, "txt")
    assert "###" not in body          # 无 md 标记
    assert body.startswith(f"第{gnum}章 {title}")
    assert "第一段正文。" in body
    conn.close()


def test_render_chapter_body_unknown_chapter_raises(tmp_project):
    import pytest
    conn = get_connection(tmp_project)
    with pytest.raises(ValueError):
        render_chapter_body(conn, 99999, "md")
    conn.close()


# ---- do_export tests (SP6-A Task 2) ----

import hashlib
from pathlib import Path


def _seed_multi_volume_book(conn):
    """2 卷各 2 章（卷1: ch1,ch2 completed；卷2: ch3 completed, ch4 writing）。"""
    v1 = create_volume(conn, 1, "第一卷", 1, 2, "opening")
    v2 = create_volume(conn, 2, "第二卷", 3, 4, "climax")
    c1 = create_chapter(conn, volume_id=v1, global_number=1, title="甲", status="completed")
    c2 = create_chapter(conn, volume_id=v1, global_number=2, title="乙", status="completed")
    c3 = create_chapter(conn, volume_id=v2, global_number=3, title="丙", status="completed")
    create_chapter(conn, volume_id=v2, global_number=4, title="丁", status="writing")
    for cid in (c1, c2, c3):
        create_paragraph(conn, chapter_id=cid, seq=1, text=f"正文{cid}",
                         content_hash=f"h{cid}", beat_id=None, role="narration")
    add_constant(conn, key="work_name", value="绝地天通")
    return v1, v2, c1, c2, c3


def _file_sha256(path):
    return hashlib.sha256(Path(path).read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def test_export_chapter_writes_manifest_and_file(tmp_project):
    conn = get_connection(tmp_project)
    v1, v2, c1, c2, c3 = _seed_multi_volume_book(conn)
    result = do_export(conn, tmp_project, scope="chapter", target=c1,
                       fmt="md", final=False, out=None)
    # 文件存在 + 文件名补零
    out_path = Path(result.path)
    assert out_path.exists()
    assert out_path.name == "ch01.md"
    # manifest 写入：round-trip 不变量
    row = conn.execute(
        "SELECT scope,target_id,format,content_hash,status FROM export_manifest "
        "ORDER BY id DESC LIMIT 1").fetchone()
    assert row["scope"] == "chapter"
    assert row["target_id"] == c1
    assert row["format"] == "md"
    assert row["status"] == "draft"
    assert row["content_hash"] == _file_sha256(out_path)   # round-trip 根基
    assert row["content_hash"] == result.content_hash
    conn.close()


def test_export_volume_skips_non_completed(tmp_project, capsys):
    conn = get_connection(tmp_project)
    v1, v2, c1, c2, c3 = _seed_multi_volume_book(conn)
    result = do_export(conn, tmp_project, scope="volume", target=v2,
                       fmt="md", final=False, out=None)
    # 卷2 只有 ch3 completed（ch4 writing 跳过）
    content = Path(result.path).read_text(encoding="utf-8")
    assert "第3章 丙" in content
    assert "第4章" not in content        # writing 章被跳过
    captured = capsys.readouterr()
    assert "ch4" in captured.err or "跳过" in captured.err   # stderr 跳过清单
    conn.close()


def test_export_empty_volume_exits(tmp_project):
    import pytest
    conn = get_connection(tmp_project)
    v1 = create_volume(conn, 1, "空卷", 1, 3, "opening")
    create_chapter(conn, volume_id=v1, global_number=1, title="x", status="writing")
    with pytest.raises(SystemExit):
        do_export(conn, tmp_project, scope="volume", target=v1,
                  fmt="md", final=False, out=None)
    conn.close()


def test_export_book_orders_by_global_number_across_volumes(tmp_project):
    conn = get_connection(tmp_project)
    v1, v2, c1, c2, c3 = _seed_multi_volume_book(conn)
    result = do_export(conn, tmp_project, scope="book", target=None,
                       fmt="md", final=False, out=None)
    content = Path(result.path).read_text(encoding="utf-8")
    # 全局升序：第1章 在 第3章 之前
    assert content.index("第1章") < content.index("第3章")
    # 书名顶层
    assert content.startswith("# 绝地天通")
    # 卷标题（卷1 在卷2前）
    assert content.index("第一卷") < content.index("第二卷")
    conn.close()


def test_export_final_writes_snapshot_subdir(tmp_project):
    conn = get_connection(tmp_project)
    v1, v2, c1, c2, c3 = _seed_multi_volume_book(conn)
    result = do_export(conn, tmp_project, scope="chapter", target=c1,
                       fmt="md", final=True, out=None)
    final_path = tmp_project / "exports" / "final" / "ch01.md"
    assert final_path.exists()
    row = conn.execute(
        "SELECT status FROM export_manifest ORDER BY id DESC LIMIT 1").fetchone()
    assert row["status"] == "final"
    conn.close()


def test_export_manifest_short_transaction_failure_warns(tmp_project, capsys):
    """manifest 写失败降级警告，不阻断文件导出。用代理包装制造写失败。
    sqlite3.Connection 是 C 扩展，execute 属性只读，无法直接 monkeypatch，
    故用代理包装 conn，仅对 export_manifest INSERT 抛错，其余透传。"""
    conn = get_connection(tmp_project)
    v1, v2, c1, c2, c3 = _seed_multi_volume_book(conn)

    class _FaultyConnProxy:
        def __init__(self, real):
            self._real = real
        def execute(self, sql, *a, **kw):
            if "export_manifest" in sql and "INSERT" in sql:
                raise RuntimeError("simulated manifest write failure")
            return self._real.execute(sql, *a, **kw)
        def __getattr__(self, name):
            return getattr(self._real, name)

    proxy = _FaultyConnProxy(conn)
    result = do_export(proxy, tmp_project, scope="chapter", target=c1,
                       fmt="md", final=False, out=None)
    assert Path(result.path).exists()
    captured = capsys.readouterr()
    assert "manifest" in captured.err.lower() or "留痕" in captured.err
    conn.close()


# ---- export CLI 薄封装 tests (SP6-A Task 3) ----


def test_export_cli_smoke(tmp_project):
    """export CLI 子命令端到端冒烟：建章→CLI export→文件存在。"""
    from src.bedrock.__main__ import main
    conn = get_connection(tmp_project)
    v1, v2, c1, c2, c3 = _seed_multi_volume_book(conn)   # 复用 Task 2 的 seed
    conn.close()
    import sys
    old_argv = sys.argv
    sys.argv = ["bedrock", "export", "--project", str(tmp_project),
                "--chapter", "1", "--format", "md"]
    try:
        main()
    finally:
        sys.argv = old_argv
    # 文件应落在 exports/ch01.md（_seed 里 global_number=1）
    out = tmp_project / "exports" / "ch01.md"
    assert out.exists()


# ---- diagnose tests (SP6-A Task 4) ----

from src.bedrock.cli.reader_commands import diagnose
from src.bedrock.repositories.suspense import plant_thread
from src.bedrock.repositories.plot_tree import create_beat


def _seed_volume_with_flag(conn, vol_number=1, vid=None):
    """建 1 卷 1 completed 章（落盘），返回 vid。"""
    if vid is None:
        vid = create_volume(conn, vol_number, f"卷{vol_number}", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=vol_number,
                         title="x", status="completed")
    create_paragraph(conn, chapter_id=cid, seq=1, text="一段足够长的正文内容用来测试。",
                     content_hash="h", beat_id=None, role="narration")
    return vid, cid


def test_diagnose_requires_scope(tmp_project):
    import pytest
    conn = get_connection(tmp_project)
    with pytest.raises(SystemExit):
        diagnose(conn, tmp_project, scope=None, with_l2=False)
    conn.close()


def test_diagnose_book_with_l2_mutex(tmp_project):
    import pytest
    conn = get_connection(tmp_project)
    with pytest.raises(SystemExit):
        diagnose(conn, tmp_project, scope=("book", None), with_l2=True)
    conn.close()


def test_diagnose_flag_only_has_mode_banner_and_trace(tmp_project):
    conn = get_connection(tmp_project)
    vid, cid = _seed_volume_with_flag(conn, vol_number=1)
    report = diagnose(conn, tmp_project, scope=("volume", vid), with_l2=False)
    assert "体检模式标记" in report
    assert "flag-only" in report
    assert "未对当前正文做 L2 重算" in report          # 可信度声明
    assert "flag（留痕）" in report                    # L2 来源列
    assert "diagnose-trace" in report                  # trace 注释
    conn.close()


def test_diagnose_flag_only_l2_hard_gate_column_na(tmp_project):
    """flag-only 模式 L2 hard_gate 列填 n/a（flag-only），不裸 '-'。"""
    conn = get_connection(tmp_project)
    vid, cid = _seed_volume_with_flag(conn, vol_number=1)
    report = diagnose(conn, tmp_project, scope=("volume", vid), with_l2=False)
    assert "n/a（flag-only）" in report
    conn.close()


def test_diagnose_with_l2_runs_run_l2(tmp_project):
    conn = get_connection(tmp_project)
    vid, cid = _seed_volume_with_flag(conn, vol_number=1)
    report = diagnose(conn, tmp_project, scope=("volume", vid), with_l2=True)
    assert "flag + live-L2" in report
    assert "live（当前正文）" in report               # L2 来源列
    conn.close()


def test_diagnose_does_not_write_volume_review(tmp_project):
    """【核心不变量】diagnose 绝不写 volume_review（不调 check_cross_volume_debt）。"""
    conn = get_connection(tmp_project)
    vid, cid = _seed_volume_with_flag(conn, vol_number=1)
    # 故意种一条本卷 high 未兑现悬链（若 diagnose 调 check_cross_volume_debt 会写 blocking=1）
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述")
    plant_thread(conn, content="未兑现线索", thread_type="mystery", importance="high",
                 planted_at_beat=bid, origin="emergent", planned_resolve_volume=1)
    before = conn.execute(
        "SELECT blocking FROM volume_review WHERE volume_id=?", (vid,)).fetchone()
    report = diagnose(conn, tmp_project, scope=("volume", vid), with_l2=False)
    after = conn.execute(
        "SELECT blocking FROM volume_review WHERE volume_id=?", (vid,)).fetchone()
    assert before == after                              # 状态不变
    assert "未兑现线索" in report                       # 但报告里仍列出欠债（纯读读出来）
    conn.close()


def test_diagnose_book_aggregates_debt(tmp_project):
    """--book 逐卷欠债聚合：任一卷 high 未兑现 → 全书标 BLOCKING。"""
    conn = get_connection(tmp_project)
    v1, _ = _seed_volume_with_flag(conn, vol_number=1)
    v2, c2 = _seed_volume_with_flag(conn, vol_number=2)
    bid = create_beat(conn, chapter_id=c2, sequence=1, purpose="一个足够长的场景目的描述")
    plant_thread(conn, content="卷2欠债", thread_type="mystery", importance="high",
                 planted_at_beat=bid, origin="emergent", planned_resolve_volume=2)
    report = diagnose(conn, tmp_project, scope=("book", None), with_l2=False)
    assert "BLOCKING" in report
    assert "卷2欠债" in report
    conn.close()
