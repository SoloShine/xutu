# tests/bedrock/test_prompt_gen.py
from src.bedrock.db.connection import get_connection
from src.bedrock.style.prompt_gen import (
    PolishPrompt, RepairPrompt, generate_polish_prompt, generate_repair_prompt,
)
from src.bedrock.checks.beat_fulfillment import BeatViolation
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat, create_paragraph
from src.bedrock.repositories.outline import save_volume_outline, lock_volume_outline, unlock_volume_outline, update_beat_contract
from src.bedrock.style.template_repo import save_fingerprint


def _seed(conn):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="林深发现旧书摊的注记")
    create_paragraph(conn, chapter_id=cid, seq=1, text="他来了。她走了。",
                     content_hash="h", beat_id=bid, role="narrative")
    save_volume_outline(conn, vid, beat_contracts=[])
    lock_volume_outline(conn, vid)
    unlock_volume_outline(conn, vid, reason="setup", author="system")
    update_beat_contract(conn, vid, beat_id=bid,
                         new_contract={"purpose": "林深发现注记", "participating_characters": ["林深"], "advance_threads": []})
    save_fingerprint(conn, scope="work", chapter_ids=[cid])
    return vid, cid, bid


def test_generate_polish_prompt_structure(tmp_project):
    conn = get_connection(tmp_project)
    vid, cid, bid = _seed(conn)
    p = generate_polish_prompt(conn, chapter_id=cid, volume_id=vid)
    assert isinstance(p, PolishPrompt)
    assert "sentence_length" in p.target_distribution
    assert len(p.beat_contracts) >= 1
    assert p.beat_contracts[0]["purpose"] == "林深发现注记"
    s = p.to_string()
    assert "目标分布" in s
    assert "林深发现注记" in s
    conn.close()


def test_generate_repair_prompt_from_violations():
    violations = [
        BeatViolation(beat_id=1, kind="missing_character", detail="角色 林深 未出场", fix_hint="加入林深出场"),
        BeatViolation(beat_id=2, kind="thread_not_advanced", detail="悬链 ST001 未推进", fix_hint="推进 ST001"),
    ]
    p = generate_repair_prompt(violations, chapter_context="第1章")
    assert isinstance(p, RepairPrompt)
    assert len(p.violations) == 2
    assert "加入林深出场" in p.fix_hints
    s = p.to_string()
    assert "林深" in s
    assert "ST001" in s
    assert "只修改违规段落" in s


def test_polish_prompt_no_fingerprint(tmp_project):
    """无指纹时 target_distribution 为空 dict，仍生成 prompt（不抛）。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    save_volume_outline(conn, vid, beat_contracts=[])
    p = generate_polish_prompt(conn, chapter_id=cid, volume_id=vid)
    assert p.target_distribution == {}
    conn.close()
