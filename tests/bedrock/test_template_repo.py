import json
from src.bedrock.db.connection import get_connection
from src.bedrock.style.template_repo import (
    save_fingerprint, get_effective_fingerprint, list_fingerprints,
    delete_volume_fingerprint,
)
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_paragraph


def _seed_paragraphs(conn, texts):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    for i, t in enumerate(texts):
        create_paragraph(conn, chapter_id=cid, seq=i + 1, text=t,
                         content_hash=f"h{i}", beat_id=None, role="narration")
    return vid, cid


def test_save_and_get_work_fingerprint(tmp_project):
    conn = get_connection(tmp_project)
    vid, cid = _seed_paragraphs(conn, ["他来了。她走了。", "看见远处的光。"])
    save_fingerprint(conn, scope="work", chapter_ids=[cid])
    fp = get_effective_fingerprint(conn, volume_id=vid)
    assert fp is not None
    assert "sentence_length" in fp
    assert fp["_scope"] == "work"
    conn.close()


def test_volume_fallback_to_work(tmp_project):
    """无卷级指纹时 fallback 作品级。"""
    conn = get_connection(tmp_project)
    vid, cid = _seed_paragraphs(conn, ["他来了。"])
    save_fingerprint(conn, scope="work", chapter_ids=[cid])
    # 无卷级指纹 → fallback work
    fp = get_effective_fingerprint(conn, volume_id=vid)
    assert fp["_scope"] == "work"
    conn.close()


def test_volume_overrides_work(tmp_project):
    """有卷级指纹时用卷级。"""
    conn = get_connection(tmp_project)
    vid, cid = _seed_paragraphs(conn, ["他来了。", "她走了。"])
    save_fingerprint(conn, scope="work", chapter_ids=[cid])
    save_fingerprint(conn, scope="volume", chapter_ids=[cid], volume_id=vid)
    fp = get_effective_fingerprint(conn, volume_id=vid)
    assert fp["_scope"] == "volume"
    assert fp["_volume_id"] == vid
    conn.close()


def test_no_fingerprint_returns_none(tmp_project):
    conn = get_connection(tmp_project)
    vid, _ = _seed_paragraphs(conn, ["x"])
    assert get_effective_fingerprint(conn, volume_id=vid) is None
    conn.close()


def test_list_fingerprints(tmp_project):
    conn = get_connection(tmp_project)
    vid, cid = _seed_paragraphs(conn, ["他来了。"])
    save_fingerprint(conn, scope="work", chapter_ids=[cid])
    fps = list_fingerprints(conn)
    assert len(fps) >= 1
    conn.close()


def test_delete_volume_fingerprint_clears_then_reinsert(tmp_project):
    """I1: save_fingerprint 卷级无 upsert。delete_volume_fingerprint 先清旧行再 save，保证一卷一行。"""
    from src.bedrock.style.template_repo import (
        save_fingerprint, delete_volume_fingerprint, get_effective_fingerprint,
    )
    conn = get_connection(tmp_project)
    vid, cid = _seed_paragraphs(conn, ["他来了。", "她走了。"])
    save_fingerprint(conn, scope="volume", chapter_ids=[cid], volume_id=vid)
    # 再 save 一次（无 upsert → 插第二行）
    save_fingerprint(conn, scope="volume", chapter_ids=[cid], volume_id=vid)
    # delete 后卷级行清空
    delete_volume_fingerprint(conn, volume_id=vid)
    rows = conn.execute("SELECT fingerprint FROM style_template").fetchall()
    vol_rows = [r for r in rows if json.loads(r["fingerprint"]).get("_scope") == "volume"
                and json.loads(r["fingerprint"]).get("_volume_id") == vid]
    assert len(vol_rows) == 0
    # 重新 save → 恰好一行
    save_fingerprint(conn, scope="volume", chapter_ids=[cid], volume_id=vid)
    vol_rows = [r for r in conn.execute("SELECT fingerprint FROM style_template").fetchall()
                if json.loads(r["fingerprint"]).get("_scope") == "volume"
                and json.loads(r["fingerprint"]).get("_volume_id") == vid]
    assert len(vol_rows) == 1
    conn.close()
