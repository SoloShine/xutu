from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_paragraph,
)
from src.bedrock.cli.reader_commands import chapter_filename, render_chapter_body


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
