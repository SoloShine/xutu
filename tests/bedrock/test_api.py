# tests/bedrock/test_api.py
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.init_project import init_project
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat, create_paragraph,
)
from src.bedrock.repositories.character import create_character
from src.bedrock.repositories.worldbook import add_location, add_theme, add_motif
from src.bedrock.repositories.outline import (
    add_inspiration, consume_inspiration,
)
from src.bedrock.web.app import create_app


def _make_work(root, name="w0", work_name="测试书"):
    """在 root 下建一个 work 子目录（init + 写 work_name）。返回 work 目录 Path。"""
    work = root / name
    init_project(work, work_name=work_name, force=True)
    return work


def _seed(work):
    conn = get_connection(work)
    v = create_volume(conn, 1, "第一卷", 1, 2, "opening")
    c1 = create_chapter(conn, volume_id=v, global_number=1, title="甲", status="completed")
    hz = create_character(conn, name="韩峥", pronoun="他", role="protagonist")
    b = create_beat(conn, chapter_id=c1, sequence=1, purpose="一个足够长的场景目的描述文字", pov_character_id=hz)
    create_paragraph(conn, chapter_id=c1, seq=1, text="正文段落一。", content_hash="h1", beat_id=b, role="narration")
    add_location(conn, name="城", description="d")
    add_theme(conn, name="边界")
    add_motif(conn, name="电")
    add_inspiration(conn, content="灵一", type="scene")
    conn.commit()
    conn.close()


def test_api_works_lists(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    _make_work(root, "demo", "Demo")
    conn = get_connection(root / "demo")
    create_volume(conn, 1, "V", 1, 1, "opening")
    conn.commit()
    conn.close()
    c = create_app(str(root)).test_client()
    resp = c.get("/api/works")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data[0]["id"] == "demo" and data[0]["name"] == "Demo"


def test_api_overview(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    work = _make_work(root)
    _seed(work)
    d = create_app(str(root)).test_client().get("/api/works/w0/overview").get_json()
    assert d["name"] == "测试书" and d["volumes"] == 1


def test_api_matrix(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    work = _make_work(root)
    _seed(work)
    d = create_app(str(root)).test_client().get("/api/works/w0/matrix?volume=1").get_json()
    assert d["characters"][0]["name"] == "韩峥"
    assert isinstance(d["chapters"][0]["povs"], list)  # set→list


def test_api_inspirations_consumed_into_parsed(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    work = _make_work(root)
    conn = get_connection(work)
    iid = add_inspiration(conn, content="x", type="scene")
    hz = create_character(conn, name="韩", pronoun="他", role="protagonist")
    consume_inspiration(conn, iid, target_type="character", target_id=hz)
    conn.commit()
    conn.close()
    item = create_app(str(root)).test_client().get("/api/works/w0/inspirations").get_json()[0]
    assert isinstance(item["consumed_into"], list)  # 解析为 list


def test_api_chapters(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    work = _make_work(root)
    _seed(work)
    d = create_app(str(root)).test_client().get("/api/works/w0/chapters").get_json()
    assert d[0]["title"] == "甲"


def test_api_chapter_text(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    work = _make_work(root)
    _seed(work)
    d = create_app(str(root)).test_client().get("/api/works/w0/chapters/1/text").get_json()
    assert d["paragraphs"][0]["text"] == "正文段落一。"


def test_api_chapter_text_missing(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    work = _make_work(root)
    _seed(work)
    assert create_app(str(root)).test_client().get("/api/works/w0/chapters/999/text").status_code == 404


def test_api_outline(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    work = _make_work(root)
    _seed(work)
    d = create_app(str(root)).test_client().get("/api/works/w0/outline").get_json()
    assert d["volumes"][0]["chapters"][0]["beats"][0]["pov_name"] == "韩峥"


def test_api_characters(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    work = _make_work(root)
    _seed(work)
    d = create_app(str(root)).test_client().get("/api/works/w0/characters").get_json()
    assert d[0]["name"] == "韩峥"


def test_api_reports_scan(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    work = _make_work(root)
    _seed(work)
    (work / "review_report_vol1.md").write_text("# x\n- ch1: escalate_human\n", encoding="utf-8")
    d = create_app(str(root)).test_client().get("/api/works/w0/reports").get_json()
    assert any(r["volume_id"] == 1 and r["exists"] for r in d)


def test_api_report_renders_markdown(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    work = _make_work(root)
    _seed(work)
    (work / "review_report_vol1.md").write_text("# 报告\n## 修正结果\n- ch1: escalate_human\n", encoding="utf-8")
    d = create_app(str(root)).test_client().get("/api/works/w0/report/1").get_json()
    assert "<h1>" in d["html_body"] and 1 in d["escalate_chs"] and d["has_escalate"]


def test_api_report_v2_tolerant(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    work = _make_work(root)
    _seed(work)
    (work / "review_report_vol1.md").write_text("# 手写报告\n无 SP5 格式。\n", encoding="utf-8")
    d = create_app(str(root)).test_client().get("/api/works/w0/report/1").get_json()
    assert d["escalate_chs"] == [] and d["has_escalate"] is False


def test_api_report_missing_404(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    work = _make_work(root)
    _seed(work)
    assert create_app(str(root)).test_client().get("/api/works/w0/report/99").status_code == 404


def test_api_path_traversal_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    work = _make_work(root)
    _seed(work)
    c = create_app(str(root)).test_client()
    for bad in ["..", "a/b", "C:x", "."]:
        assert c.get(f"/api/works/{bad}/overview").status_code == 404, bad


def test_create_app_requires_projects_root(tmp_path):
    with pytest.raises(SystemExit):
        create_app(str(tmp_path / "nope"))  # 不存在的目录


def test_create_app_rejects_file(tmp_path):
    f = tmp_path / "afile"
    f.write_text("x")
    with pytest.raises(SystemExit):
        create_app(str(f))  # 不是目录
