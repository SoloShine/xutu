from src.bedrock.db.connection import get_connection
from src.bedrock.orchestration.persist_gate import verify_chapter_persisted
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat, create_paragraph,
    mark_beats_written,
)


def _seed(conn, write_paragraph=True):
    import json
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    if write_paragraph:
        bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="林深推门走进房间里面")  # >=10 chars
        # verify 现要求 L2 过:字数下限(默认 3000 汉字)+ beat 兑现(需 volume_outline 契约)。
        create_paragraph(conn, chapter_id=cid, seq=1, text="正文内容在此。" * 500,  # 3000 汉字
                         content_hash="h", beat_id=bid, role="narration")
        mark_beats_written(conn, [bid])
        conn.execute(
            "INSERT OR REPLACE INTO volume_outline(volume_id,status,beat_contracts) VALUES(?,'drafted',?)",
            (vid, json.dumps([{"beat_id": bid, "purpose": "林深推门走进房间里面"}])))
        conn.commit()
    return vid, cid


def test_persisted_when_paragraphs_exist(tmp_project):
    conn = get_connection(tmp_project)
    _, cid = _seed(conn, write_paragraph=True)
    assert verify_chapter_persisted(conn, cid) is True
    conn.close()


def test_not_persisted_when_no_paragraphs(tmp_project):
    conn = get_connection(tmp_project)
    _, cid = _seed(conn, write_paragraph=False)
    assert verify_chapter_persisted(conn, cid) is False
    conn.close()


def test_export_file_check_optional(tmp_project):
    """传 export_path：文件存在才 True；不传则只查 DB。"""
    import os
    conn = get_connection(tmp_project)
    _, cid = _seed(conn, write_paragraph=True)
    # 文件不存在 → False
    assert verify_chapter_persisted(conn, cid, export_path=str(tmp_project / "nope.txt")) is False
    # 文件存在 → True
    p = tmp_project / "ch.txt"; p.write_text("正文", encoding="utf-8")
    assert verify_chapter_persisted(conn, cid, export_path=str(p)) is True
    conn.close()
