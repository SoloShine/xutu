# tests/bedrock/test_paragraph_ops.py
"""段落插入/删除/重排操作（不改 schema，纯 repository 方法）。"""
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_paragraph,
    insert_paragraph_at, delete_paragraph, reorder_paragraphs,
    list_paragraphs_in_chapter,
)


def _seed_chapter(conn, n=3):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    ids = []
    for i in range(1, n + 1):
        pid = create_paragraph(conn, cid, i, f"段{i}。", f"h{i}", None, "narration")
        ids.append(pid)
    return cid, ids


def test_insert_paragraph_at_middle(tmp_project):
    conn = get_connection(tmp_project)
    cid, ids = _seed_chapter(conn, n=2)
    insert_paragraph_at(conn, cid, after_seq=1, text="插入段。",
                        content_hash="hx", beat_id=None, role="narration")
    paras = list_paragraphs_in_chapter(conn, cid)
    assert [p["text"] for p in paras] == ["段1。", "插入段。", "段2。"]
    assert [p["seq"] for p in paras] == [1, 2, 3]
    conn.close()


def test_insert_at_head(tmp_project):
    """after_seq=0 插到章首。"""
    conn = get_connection(tmp_project)
    cid, ids = _seed_chapter(conn, n=2)
    insert_paragraph_at(conn, cid, after_seq=0, text="开头。",
                        content_hash="h0", beat_id=None, role="narration")
    paras = list_paragraphs_in_chapter(conn, cid)
    assert paras[0]["text"] == "开头。"
    assert paras[0]["seq"] == 1
    conn.close()


def test_delete_paragraph_tighten(tmp_project):
    conn = get_connection(tmp_project)
    cid, ids = _seed_chapter(conn, n=3)
    delete_paragraph(conn, ids[1])  # 删 seq=2
    paras = list_paragraphs_in_chapter(conn, cid)
    assert [p["text"] for p in paras] == ["段1。", "段3。"]
    assert [p["seq"] for p in paras] == [1, 2]  # 收紧
    conn.close()


def test_delete_paragraph_no_tighten(tmp_project):
    conn = get_connection(tmp_project)
    cid, ids = _seed_chapter(conn, n=3)
    delete_paragraph(conn, ids[1], tighten=False)
    paras = list_paragraphs_in_chapter(conn, cid)
    assert [p["seq"] for p in paras] == [1, 3]  # 留空洞，ORDER BY 仍正确
    conn.close()


def test_reorder_paragraphs(tmp_project):
    conn = get_connection(tmp_project)
    cid, ids = _seed_chapter(conn, n=3)
    reorder_paragraphs(conn, cid, [ids[2], ids[0], ids[1]])  # 反序重排
    paras = list_paragraphs_in_chapter(conn, cid)
    assert [p["para_id"] for p in paras] == [ids[2], ids[0], ids[1]]
    assert [p["seq"] for p in paras] == [1, 2, 3]
    conn.close()


def test_reorder_rejects_partial(tmp_project):
    conn = get_connection(tmp_project)
    cid, ids = _seed_chapter(conn, n=3)
    with pytest.raises(ValueError):
        reorder_paragraphs(conn, cid, [ids[0], ids[1]])  # 缺 ids[2]，拒绝
    conn.close()


def test_delete_not_found_raises(tmp_project):
    conn = get_connection(tmp_project)
    with pytest.raises(ValueError):
        delete_paragraph(conn, 99999)
    conn.close()
