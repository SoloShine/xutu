# tests/bedrock/test_boot_context.py
from src.bedrock.db.connection import get_connection
from src.bedrock.orchestration.boot_context import get_chapter_boot_context
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat, create_paragraph
from src.bedrock.repositories.outline import (
    save_volume_outline, lock_volume_outline, unlock_volume_outline, update_beat_contract,
)
from src.bedrock.repositories.character import create_character
from src.bedrock.style.template_repo import save_fingerprint


def _seed(conn):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="林深推门走进房间里面")  # >=10 chars
    create_paragraph(conn, chapter_id=cid, seq=1, text="x。",
                     content_hash="h", beat_id=bid, role="narration")
    save_volume_outline(conn, vid, beat_contracts=[])
    lock_volume_outline(conn, vid)
    unlock_volume_outline(conn, vid, reason="setup", author="system")
    update_beat_contract(conn, vid, beat_id=bid,
                         new_contract={"purpose": "p", "participating_characters": [], "advance_threads": []})
    save_fingerprint(conn, scope="work", chapter_ids=[cid])
    # FK enforced (PRAGMA foreign_keys=ON): create a real character so
    # character_secret(character_id=...) inserts succeed.
    create_character(conn, name="林深", pronoun="他", role="protagonist", gender="男")
    return vid, cid


def test_boot_context_has_required_keys(tmp_project):
    conn = get_connection(tmp_project)
    vid, cid = _seed(conn)
    ctx = get_chapter_boot_context(conn, chapter_id=cid, volume_id=vid)
    assert "beat_contracts" in ctx
    assert "fingerprint" in ctx
    assert "constants" in ctx
    assert isinstance(ctx["beat_contracts"], list)
    conn.close()


def test_boot_context_no_fingerprint_handled(tmp_project):
    """无指纹时不抛（get_effective_fingerprint 返回 None）。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    save_volume_outline(conn, vid, beat_contracts=[])
    ctx = get_chapter_boot_context(conn, chapter_id=cid, volume_id=vid)
    assert ctx["fingerprint"] is None
    conn.close()


def test_boot_context_reader_secrets_filtered(tmp_project):
    """只含 reader_disclosure public 的 secret（visibility 过滤）。"""
    conn = get_connection(tmp_project)
    vid, cid = _seed(conn)
    conn.execute(
        "INSERT INTO character_secret(character_id,key,value,vis_mode,vis_axis,vis_ref) "
        "VALUES(1,'pub','v','public','reader_disclosure','{}')")
    conn.execute(
        "INSERT INTO character_secret(character_id,key,value,vis_mode,vis_axis,vis_ref) "
        "VALUES(1,'sec','v','secret_until','reader_disclosure','{}')")
    conn.commit()
    ctx = get_chapter_boot_context(conn, chapter_id=cid, volume_id=vid)
    keys = [s["key"] for s in ctx["reader_disclosed_secrets"]]
    assert "pub" in keys
    assert "sec" not in keys
    conn.close()
