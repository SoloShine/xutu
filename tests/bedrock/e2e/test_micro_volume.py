# tests/bedrock/e2e/test_micro_volume.py
"""SP5 e2e：seed 微型卷真跑全链路。需真 LLM + Workflow runtime，@pytest.mark.e2e 默认 skip。

触发方式：人在 Claude 里跑 bedrock-chapter.js + bedrock-volume-review.js（真 LLM），
本测试做【事后状态断言】（读 DB + 报告文件）。不强求 CI 自动跑（spec §十 已说明手动触发）。

跑法：先人工跑 Workflow，再 `pytest tests/bedrock/e2e/ -m e2e`（需先有跑过的 project）。
"""
import json
from pathlib import Path
import pytest
from src.bedrock.db.migrate import apply_migrations
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat, update_beat_status,
)
from src.bedrock.repositories.outline import (
    save_volume_outline, lock_volume_outline, unlock_volume_outline, update_beat_contract,
)


def _seed_micro_volume(project_dir):
    """seed 1 卷 2 章，每章 1 beat + 契约；2 条悬链（1 本卷 planned_resolve，1 跨卷 high）。"""
    apply_migrations(project_dir)
    conn = get_connection(project_dir)
    vid = create_volume(conn, 1, "micro", 1, 2, "opening")
    chapter_ids = []
    for ch_idx in (1, 2):
        cid = create_chapter(conn, volume_id=vid, global_number=ch_idx, title=f"t{ch_idx}")
        chapter_ids.append(cid)
        bid = create_beat(conn, chapter_id=cid, sequence=1, purpose=f"第{ch_idx}章主beat剧情发展")
        update_beat_status(conn, bid, "planned")  # 待 ChapterWriter 写
    save_volume_outline(conn, vid, beat_contracts=[])
    lock_volume_outline(conn, vid)
    unlock_volume_outline(conn, vid, reason="setup", author="system")
    # 2 条悬链
    conn.execute(
        "INSERT INTO suspense_thread(id,content,thread_type,importance,origin,status,planned_resolve_volume) "
        "VALUES(1,'本卷线','mystery','high','scheduled','planted',1)")
    conn.execute(
        "INSERT INTO suspense_thread(id,content,thread_type,importance,origin,status,planned_resolve_volume) "
        "VALUES(2,'跨卷线','mystery','high','scheduled','planted',2)")
    conn.commit()
    conn.close()
    return vid, chapter_ids


@pytest.mark.e2e
def test_micro_volume_post_state(tmp_path):
    """e2e 事后状态断言：人工跑完 Workflow 后，验证旗/report/gate 状态正确。

    前置：人工在 Claude 里对 tmp_path 项目跑了 bedrock-chapter.js（×2 章）+
    bedrock-volume-review.js。本测试只断言跑完后的 DB + 报告文件状态。
    （若未跑 Workflow，paragraphs 为空 → persist/flag 断言会失败，提示先跑 Workflow。）"""
    project = tmp_path / "e2e_proj"
    project.mkdir()
    vid, chapter_ids = _seed_micro_volume(project)

    # 【人工触发点】在此处人工跑 Workflow（需真 LLM）。自动化触发超出 SP5 范围（spec §十）。
    # 若无 Workflow runtime 桥，本测试主要验证 seed 正确 + 断言语句可执行（跑前会因 paragraphs 空失败）。

    conn = get_connection(project)
    # happy-path 断言（人工跑完后应满足）
    for cid in chapter_ids:
        n_para = conn.execute("SELECT COUNT(*) AS n FROM paragraph WHERE chapter_id=?",
                              (cid,)).fetchone()["n"]
        # 跑完 Workflow 后每章应有段落；若 0 说明 Workflow 未跑（e2e 前置未满足）
        assert n_para > 0, f"章 {cid} 无段落——Workflow 未跑？e2e 需先人工跑 bedrock-chapter.js"
    # watchdog 行（VolumeReview 跑后写）
    vr = conn.execute("SELECT * FROM volume_review WHERE volume_id=?", (vid,)).fetchone()
    assert vr is not None, "volume_review 行缺失——bedrock-volume-review.js 未跑？"
    # review_report 落盘（强制落盘门禁，治 Vol15）
    report_path = project / "review_report_vol1.md"
    assert report_path.exists() and report_path.stat().st_size > 0, "review_report 未落盘（Vol15 bug）"
    conn.close()


@pytest.mark.e2e
def test_seed_correctness(tmp_path):
    """纯 seed 验证（不需 Workflow/LLM）：seed 后 DB 状态正确。这是 e2e 能跑的前提。"""
    project = tmp_path / "e2e_seed"
    project.mkdir()
    vid, chapter_ids = _seed_micro_volume(project)
    conn = get_connection(project)
    assert len(chapter_ids) == 2
    # 2 beat（planned 状态）
    n_beats = conn.execute("SELECT COUNT(*) AS n FROM beat").fetchone()["n"]
    assert n_beats == 2
    # 2 悬链（1 本卷 planned_resolve=1，1 跨卷 planned_resolve=2）
    threads = conn.execute("SELECT planned_resolve_volume FROM suspense_thread ORDER BY id").fetchall()
    assert [t["planned_resolve_volume"] for t in threads] == [1, 2]
    # volume_outline 已解锁（status drafted，可写 beat 契约）
    vo = conn.execute("SELECT status FROM volume_outline WHERE volume_id=?", (vid,)).fetchone()
    assert vo["status"] == "drafted"
    conn.close()
