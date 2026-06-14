# tests/bedrock/test_web.py
import pytest
from pathlib import Path
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat
from src.bedrock.repositories.character import create_character
from src.bedrock.repositories.worldbook import add_constant
from src.bedrock.repositories.outline import add_inspiration
from src.bedrock.web.app import create_app


def _seed_app(tmp_project):
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "第一卷", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="甲", status="completed")
    hz = create_character(conn, name="韩峥", pronoun="他", role="protagonist")
    create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述",
                pov_character_id=hz)
    add_constant(conn, key="work_name", value="测试书")
    conn.close()
    return vid


def test_create_app_requires_bedrock_db(tmp_path):
    empty = tmp_path / "nodb"
    empty.mkdir()
    with pytest.raises(SystemExit):
        create_app(str(empty))


def test_matrix_route(tmp_project):
    vid = _seed_app(tmp_project)
    app = create_app(str(tmp_project))
    client = app.test_client()
    resp = client.get("/matrix", query_string={"volume": vid})
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "第一卷" in body
    assert "韩峥" in body


def test_matrix_marks_pov_cell(tmp_project):
    vid = _seed_app(tmp_project)
    app = create_app(str(tmp_project))
    client = app.test_client()
    resp = client.get("/matrix", query_string={"volume": vid})
    assert "●" in resp.data.decode("utf-8")   # POV 单元格 ●


def test_inspirations_route(tmp_project):
    conn = get_connection(tmp_project)
    add_inspiration(conn, content="一个灵感", type="scene")
    conn.close()
    app = create_app(str(tmp_project))
    client = app.test_client()
    resp = client.get("/inspirations")
    assert resp.status_code == 200
    assert "一个灵感" in resp.data.decode("utf-8")


def test_report_route_renders_markdown(tmp_project):
    (tmp_project / "review_report_vol1.md").write_text(
        "# VolumeReview 报告 — 卷 1\n\n## 修正结果（三状态）\n- ch1: escalate_human\n",
        encoding="utf-8")
    _seed_app(tmp_project)
    app = create_app(str(tmp_project))
    client = app.test_client()
    resp = client.get("/report/1")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "<h1>" in body   # markdown 转 HTML
    assert "escalate" in body.lower() or "ch1" in body


def test_report_missing_404(tmp_project):
    _seed_app(tmp_project)
    app = create_app(str(tmp_project))
    client = app.test_client()
    resp = client.get("/report/99")
    assert resp.status_code == 404


def test_matrix_beat_expand_endpoint(tmp_project):
    vid = _seed_app(tmp_project)
    conn = get_connection(tmp_project)
    cid = conn.execute("SELECT id FROM chapter WHERE global_number=1").fetchone()["id"]
    hz = conn.execute("SELECT id FROM character WHERE name='韩峥'").fetchone()["id"]
    conn.close()
    app = create_app(str(tmp_project))
    client = app.test_client()
    resp = client.get("/matrix/beats", query_string={"chapter": cid, "character": hz})
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "场景目的" in body   # beat purpose 出现


def test_inspirations_advance_htmx(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    conn.close()
    app = create_app(str(tmp_project))
    client = app.test_client()
    resp = client.post(f"/inspirations/{iid}/advance",
                       data={"target": "refined"}, headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "refined" in resp.data.decode("utf-8")   # 卡片 status 变


def test_inspirations_advance_requires_htmx_header(tmp_project):
    """H6：无 HX-Request 头 → 403（弱 CSRF）。"""
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    conn.close()
    app = create_app(str(tmp_project))
    client = app.test_client()
    resp = client.post(f"/inspirations/{iid}/advance", data={"target": "refined"})   # 无 HX-Request 头
    assert resp.status_code == 403


def test_inspirations_advance_illegal_returns_error_card(tmp_project):
    from src.bedrock.repositories.outline import advance_inspiration
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    advance_inspiration(conn, iid, "discarded")   # 终态
    conn.close()
    app = create_app(str(tmp_project))
    client = app.test_client()
    resp = client.post(f"/inspirations/{iid}/advance",
                       data={"target": "refined"}, headers={"HX-Request": "true"})
    assert resp.status_code == 200   # 不崩，返回错误卡
    body = resp.data.decode("utf-8")
    assert "非法" in body or "error" in body.lower()
    # 原 status 不变
    conn = get_connection(tmp_project)
    assert conn.execute("SELECT status FROM inspiration WHERE id=?", (iid,)).fetchone()["status"] == "discarded"
    conn.close()


def test_report_escalate_per_item_highlight(tmp_project):
    """spec §4.3：含 escalate_human 的 outcome 行（<li>）加 escalate-highlight class。"""
    (tmp_project / "review_report_vol1.md").write_text(
        "# VolumeReview 报告 — 卷 1\n\n## 修正结果（三状态）\n- ch1: escalate_human\n- ch2: verified_fixed\n",
        encoding="utf-8")
    _seed_app(tmp_project)
    app = create_app(str(tmp_project))
    client = app.test_client()
    resp = client.get("/report/1")
    body = resp.data.decode("utf-8")
    assert 'class="escalate-highlight"' in body
    assert "ch1: escalate_human" in body   # escalate 行被高亮
    # ch2 (verified_fixed) 不被高亮
    assert body.count('class="escalate-highlight"') == 1
