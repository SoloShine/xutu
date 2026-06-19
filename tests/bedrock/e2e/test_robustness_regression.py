"""端到端:验证 prose 防污染三层(extractProse 定界 / commit sanitize / L2 non_prose)协同。

构造 agent 吐 prose+meta 的输入,确认 meta 不入库。

三层防线:
  - A0 workflow extractProse(JS 围栏定界):CLI 层测不到,但在真实工作流中第一道。
  - A1 commit-paragraphs sanitize_prose(Task4):剥残留 meta,清洗后 <500 字拒绝。
  - A2 L2 non_prose 规则(Task2):万一 meta 漏网入库,run-l2 命中。
本测试覆盖 A1 + A2 两个 CLI 可测层。
"""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat
from src.bedrock.repositories.outline import (
    save_volume_outline, lock_volume_outline, unlock_volume_outline,
)


def _make_project(tmp_path: Path) -> Path:
    """建最小 bedrock 项目:1 卷 + 1 章(global 1)+ 1 beat + volume_outline。

    复用 tests/bedrock/test_cli_commit_sanitize.py::_make_project 的成熟模式:
    子进程 CLI 与主进程不同 cwd,不能依赖 conftest 的 in-memory tmp_project,
    故 bedrock init 建库后直灌 volume/chapter/beat。
    volume_outline 是 run-l2 → get_beat_contract 的前置依赖(MEMORY gotcha),
    必须 save+lock+unlock 三步。
    """
    proj = tmp_path / "proj"
    r = subprocess.run(
        [sys.executable, "-m", "src.bedrock", "init", str(proj),
         "--name", "t", "--force"],
        capture_output=True, text=True, encoding="utf-8", cwd="D:/novel_test")
    assert r.returncode == 0, r.stderr
    conn = get_connection(proj)
    vid = create_volume(conn, 1, "v1", 1, 1, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t1")
    create_beat(conn, chapter_id=cid, sequence=1,
                purpose="林昭清晨醒来望向窗外远山轮廓陷入沉思")
    save_volume_outline(conn, vid, beat_contracts=[])
    lock_volume_outline(conn, vid)
    unlock_volume_outline(conn, vid, reason="setup", author="system")
    conn.commit()
    conn.close()
    return proj


def _commit(proj: Path, raw: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "src.bedrock", "commit-paragraphs",
         "--project", str(proj), "--chapter", "1"],
        input=raw, text=True, encoding="utf-8",
        cwd="D:/novel_test", capture_output=True)


def test_pipeline_rejects_or_strips_meta_pollution(tmp_path):
    """A1 层:agent 吐 prose+meta,commit-paragraphs sanitize 剥离 meta,仅干净正文入库。

    "林昭把工牌翻了过去。" = 10 字 ×80 = 800 字 > MIN_PROSE_CHARS(500) ✓
    输入按段落(空行)分段:前言段 / 正文段 / meta 段,sanitize 逐段判定,
    前言与 meta 段被剥,正文段保留入库。
    """
    proj = _make_project(tmp_path)
    clean_prose = "林昭把工牌翻了过去。" * 80   # ~800 字
    raw = (
        "我先想了一下这章怎么写。\n\n"      # 前言段(extractProse 会丢;commit sanitize 也剥)
        + clean_prose + "\n\n"
        "指标：0破折号，对话占比35%。润色版本已完成。"   # meta 段
    )
    r = _commit(proj, raw)
    assert r.returncode == 0, r.stderr
    c = sqlite3.connect(proj / "bedrock.db")
    texts = [row[0] for row in c.execute("SELECT text FROM paragraph")]
    c.close()
    # 干净正文入库
    assert any("林昭把工牌翻了过去" in t for t in texts)
    # meta 未入库(sanitize 剥离)
    assert not any("对话占比" in t or "润色版本" in t or "我先想了一下" in t for t in texts)


def test_l2_non_prose_catches_meta_if_it_reaches_db(tmp_path):
    """A2 层:若 meta 段已入库(A0/A1 都漏网的极端情况),L2 non_prose 兜底命中。"""
    proj = _make_project(tmp_path)
    # 先 commit 干净正文(>500 字)
    clean = "天没亮，林昭就醒了。" + "她数着钟声。" * 100
    r = _commit(proj, clean)
    assert r.returncode == 0, r.stderr
    # 直接往 db 插一段 meta(模拟漏网)
    c = sqlite3.connect(proj / "bedrock.db")
    cid = c.execute("SELECT id FROM chapter WHERE global_number=1").fetchone()[0]
    max_seq = c.execute(
        "SELECT MAX(seq) FROM paragraph WHERE chapter_id=?", (cid,)).fetchone()[0] or 0
    c.execute(
        "INSERT INTO paragraph(chapter_id,seq,beat_id,text,content_hash,role) "
        "VALUES(?,?,NULL,'润色版本已完成，剔除了所有破折号。','x','narration')",
        (cid, max_seq + 1))
    c.commit()
    c.close()
    # run-l2 应报 non_prose 违规
    r = subprocess.run(
        [sys.executable, "-m", "src.bedrock", "run-l2",
         "--project", str(proj), "--chapter", "1"],
        capture_output=True, text=True, encoding="utf-8", cwd="D:/novel_test")
    assert r.returncode == 0, r.stderr
    rep = json.loads(r.stdout)
    assert any(v.get("kind") == "non_prose" for v in rep.get("beat_violations", []))
