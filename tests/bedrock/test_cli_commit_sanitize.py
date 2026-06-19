"""Unit A1: commit-paragraphs 在 split 前跑 sanitize_prose,重度污染(<500字)拒绝入库。"""
import sqlite3
import subprocess
import sys
from pathlib import Path

from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat


def _make_project(tmp_path: Path) -> Path:
    """建最小 bedrock 项目:1 卷 + 1 章(global 1)+ 1 beat(planned→written)。

    复用 conftest.tmp_project 的迁移机制不适用于子进程 CLI(不同进程、不同 cwd),
    故直接调 bedrock init 建库再 sqlite 直灌 volume/chapter/beat。
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
    conn.commit()
    conn.close()
    return proj


def test_commit_strips_meta_and_persists_clean(tmp_path):
    proj = _make_project(tmp_path)
    raw = ("草案符合指标：0破折号。\n\n"
           "天没亮，林昭就醒了。" + "正文内容。" * 200 + "\n\n"
           "D:\\x\\projects\\p\\bedrock.db")
    r = subprocess.run(
        [sys.executable, "-m", "src.bedrock", "commit-paragraphs",
         "--project", str(proj), "--chapter", "1"],
        input=raw, capture_output=True, text=True, encoding="utf-8", cwd="D:/novel_test")
    assert r.returncode == 0, r.stderr
    c = sqlite3.connect(proj / "bedrock.db")
    texts = [row[0] for row in c.execute("SELECT text FROM paragraph")]
    assert any("天没亮" in t for t in texts)
    assert not any("草案符合指标" in t or "bedrock.db" in t for t in texts)


def test_commit_rejects_too_short_after_sanitize(tmp_path):
    proj = _make_project(tmp_path)
    raw = "草案符合指标：0破折号。"   # 全是 meta,清洗后为空 → 拒绝
    r = subprocess.run(
        [sys.executable, "-m", "src.bedrock", "commit-paragraphs",
         "--project", str(proj), "--chapter", "1"],
        input=raw, capture_output=True, text=True, encoding="utf-8", cwd="D:/novel_test")
    assert r.returncode != 0
    assert "拒绝" in r.stderr or "reject" in r.stderr.lower()
