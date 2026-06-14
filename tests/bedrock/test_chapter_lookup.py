# tests/bedrock/test_chapter_lookup.py
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.db.chapter_lookup import chapter_id_by_global
from src.bedrock.repositories.plot_tree import create_volume, create_chapter


def test_chapter_id_by_global_found(tmp_project):
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=5, title="t")
    assert chapter_id_by_global(conn, 5) == cid
    conn.close()


def test_chapter_id_by_global_not_found_raises(tmp_project):
    conn = get_connection(tmp_project)
    with pytest.raises(SystemExit):
        chapter_id_by_global(conn, 999)
    conn.close()
