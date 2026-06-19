"""Unit B: 章状态生命周期 verify→completed + edit reopen + mark-completed CLI。

- verify-persisted pass → status=completed
- edit-paragraphs → status=writing（已落盘章节被编辑需重 verify）
- mark-completed CLI 作为人工/卷审兜底
"""
import sqlite3
import subprocess
import sys
from pathlib import Path

from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat


def _make_project(tmp_path: Path) -> Path:
    """最小 bedrock 项目:1 卷 + 1 章(global 1)+ 1 beat(written)。"""
    import json
    proj = tmp_path / "proj"
    r = subprocess.run(
        [sys.executable, "-m", "src.bedrock", "init", str(proj),
         "--name", "t", "--force"],
        capture_output=True, text=True, encoding="utf-8", cwd="D:/novel_test")
    assert r.returncode == 0, r.stderr
    conn = get_connection(proj)
    vid = create_volume(conn, 1, "v1", 1, 1, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t1")
    bid = create_beat(conn, chapter_id=cid, sequence=1,
                purpose="林昭清晨醒来望向窗外远山轮廓陷入沉思")
    # verify 现要求 L2 过:check_beat_fulfillment 需 volume_outline 存 beat 契约。
    conn.execute(
        "INSERT OR REPLACE INTO volume_outline(volume_id,status,beat_contracts) VALUES(?,'drafted',?)",
        (vid, json.dumps([{"beat_id": bid, "purpose": "林昭清晨醒来望向窗外远山轮廓陷入沉思"}])))
    conn.commit()
    conn.close()
    return proj


def _commit_prose(proj: Path):
    """提交一段正文,使章成为真正 written 章(verify-persisted 能过)。"""
    raw = ("天没亮，林昭就醒了。" + "窗外的远山轮廓在薄雾中若隐若现。" * 280 + "\n\n"
           "他叹了口气，起身披衣。")  # >=3000 汉字:verify 现要求 L2 过(字数下限)
    r = subprocess.run(
        [sys.executable, "-m", "src.bedrock", "commit-paragraphs",
         "--project", str(proj), "--chapter", "1"],
        input=raw, capture_output=True, text=True, encoding="utf-8",
        cwd="D:/novel_test")
    assert r.returncode == 0, r.stderr


def _status(proj: Path) -> str:
    c = sqlite3.connect(proj / "bedrock.db")
    s = c.execute("SELECT status FROM chapter WHERE global_number=1").fetchone()[0]
    c.close()
    return s


def test_verify_sets_completed(tmp_path):
    proj = _make_project(tmp_path)
    _commit_prose(proj)
    # commit-paragraphs 设 writing;verify 通过应转 completed
    assert _status(proj) == "writing"
    r = subprocess.run(
        [sys.executable, "-m", "src.bedrock", "verify-persisted",
         "--project", str(proj), "--chapter", "1"],
        cwd="D:/novel_test", capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "True"
    assert _status(proj) == "completed"


def test_edit_reopens_to_writing(tmp_path):
    proj = _make_project(tmp_path)
    _commit_prose(proj)
    # 先 verify 到 completed
    subprocess.run(
        [sys.executable, "-m", "src.bedrock", "verify-persisted",
         "--project", str(proj), "--chapter", "1"],
        cwd="D:/novel_test", check=True,
        stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    assert _status(proj) == "completed"
    # 拿一个真实 para_id
    c = sqlite3.connect(proj / "bedrock.db")
    pid = c.execute(
        "SELECT para_id FROM paragraph WHERE chapter_id="
        "(SELECT id FROM chapter WHERE global_number=1) LIMIT 1").fetchone()[0]
    c.close()
    ops = '[{"op":"update","para_id":%d,"text":"改了一字，远山依旧。"}]' % pid
    r = subprocess.run(
        [sys.executable, "-m", "src.bedrock", "edit-paragraphs",
         "--project", str(proj), "--chapter", "1"],
        input=ops, text=True, encoding="utf-8",
        cwd="D:/novel_test", capture_output=True)
    assert r.returncode == 0, r.stderr
    assert _status(proj) == "writing"


def test_mark_completed_cli(tmp_path):
    proj = _make_project(tmp_path)
    assert _status(proj) == "planned"
    r = subprocess.run(
        [sys.executable, "-m", "src.bedrock", "mark-completed",
         "--project", str(proj), "--chapter", "1"],
        cwd="D:/novel_test", capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert _status(proj) == "completed"
