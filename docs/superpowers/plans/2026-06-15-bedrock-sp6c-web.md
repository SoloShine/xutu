# 磐石 Bedrock SP6-C 实现计划：本地 Web UI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement task-by-task.

**Goal:** 1 个 Flask app + 3 视图（POV 矩阵/灵感池/review_report）+ 1 写点（灵感池状态推进）。

**Architecture:** 先做两处纯函数重构（outline.py inspiration 状态机 + parse_review_outcomes 抽取），再建 web/ 子包（app + queries + templates）。Flask + Jinja + htmx，每请求开/关 conn。

**Tech Stack:** flask + markdown（新依赖）+ Jinja2（Flask 自带）+ htmx（CDN）+ pytest。

**Spec:** `docs/superpowers/specs/2026-06-15-bedrock-sp6c-web-design.md`（两路对抗审核 6🔴+10🟡 全吸收）。

**关键不变量：**
- 唯一写点 = `advance_inspiration`（状态机入口）；`consume_inspiration` 组合它。
- 状态机单向不回退（raw/refined/partial → consumed 合法；consumed → discarded；discarded 终态）。
- advance 端点校验 `HX-Request` 头（弱 CSRF）。
- 每请求开/关 conn，不缓存。
- project 无 bedrock.db → 启动报错。

---

## Task 1: outline.py inspiration 状态机

**Files:** Modify `src/bedrock/repositories/outline.py`、`tests/bedrock/test_outline.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/bedrock/test_outline.py
from src.bedrock.repositories.outline import (
    list_inspirations, advance_inspiration,
)


def test_list_inspirations_all(tmp_project):
    conn = get_connection(tmp_project)
    add_inspiration(conn, content="a", type="scene")
    add_inspiration(conn, content="b", type="twist")
    items = list_inspirations(conn)
    assert len(items) == 2
    # created_at 倒序（b 后建）
    assert items[0]["content"] == "b"


def test_list_inspirations_filter(tmp_project):
    conn = get_connection(tmp_project)
    add_inspiration(conn, content="a", type="scene")
    add_inspiration(conn, content="b", type="twist")
    assert len(list_inspirations(conn, type_filter="scene")) == 1
    assert len(list_inspirations(conn, status_filter="raw")) == 2


def test_advance_raw_to_refined_sets_refined_at(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    row = advance_inspiration(conn, iid, "refined")
    assert row["status"] == "refined"
    assert row["refined_at"] is not None


def test_advance_refined_to_consumed_sets_promoted_at(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    advance_inspiration(conn, iid, "refined")
    row = advance_inspiration(conn, iid, "consumed")
    assert row["status"] == "consumed"
    assert row["promoted_at"] is not None


def test_advance_partial_to_consumed(tmp_project):
    """H1：partial → consumed 合法。"""
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    advance_inspiration(conn, iid, "refined")
    advance_inspiration(conn, iid, "partial")
    row = advance_inspiration(conn, iid, "consumed")
    assert row["status"] == "consumed"


def test_advance_raw_to_consumed_direct(tmp_project):
    """raw → consumed 直接用（兼容既有 consume 语义）。"""
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    row = advance_inspiration(conn, iid, "consumed")
    assert row["status"] == "consumed"


def test_advance_illegal_rejected(tmp_project):
    """非法转移 → ValueError，DB status 不变。"""
    import pytest
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    advance_inspiration(conn, iid, "refined")
    advance_inspiration(conn, iid, "consumed")
    with pytest.raises(ValueError):   # consumed → raw 非法
        advance_inspiration(conn, iid, "raw")
    assert conn.execute("SELECT status FROM inspiration WHERE id=?", (iid,)).fetchone()["status"] == "consumed"
    conn.close()


def test_advance_discarded_terminal(tmp_project):
    """discarded 终态，不能再推进。"""
    import pytest
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    advance_inspiration(conn, iid, "discarded")
    with pytest.raises(ValueError):
        advance_inspiration(conn, iid, "refined")
    conn.close()


def test_advance_unknown_id(tmp_project):
    import pytest
    conn = get_connection(tmp_project)
    with pytest.raises(ValueError):
        advance_inspiration(conn, 999, "refined")
    conn.close()


def test_consume_inspiration_composes_advance_and_multi_target(tmp_project):
    """consume 组合 advance（设 promoted_at）+ 多 target 追加。"""
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")  # raw
    consume_inspiration(conn, iid, target_type="character", target_id=1)
    row1 = conn.execute("SELECT status, promoted_at, consumed_into FROM inspiration WHERE id=?", (iid,)).fetchone()
    assert row1["status"] == "consumed"
    assert row1["promoted_at"] is not None   # 经 advance 设了
    # 再 consume 第二个 target（已 consumed，只追加）
    consume_inspiration(conn, iid, target_type="chapter", target_id=5)
    row2 = conn.execute("SELECT consumed_into FROM inspiration WHERE id=?", (iid,)).fetchone()
    into = json.loads(row2["consumed_into"])
    assert len(into) == 2   # 多 target
    conn.close()


def test_existing_inspiration_lifecycle_still_passes(tmp_project):
    """既有测试：raw → consume → consumed（回归，确保重构不破坏）。"""
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="一个能听到城市电流声的主角", type="character")
    consume_inspiration(conn, iid, target_type="character", target_id=1)
    row = conn.execute("SELECT status FROM inspiration WHERE id=?", (iid,)).fetchone()
    assert row["status"] == "consumed"
    conn.close()
```

- [ ] **Step 2: 跑确认失败**

`python -m pytest tests/bedrock/test_outline.py -k "list_inspirations or advance or compose" -v` → FAIL（函数未定义）

- [ ] **Step 3: 实现状态机（追加到 outline.py）**

```python
# 追加到 src/bedrock/repositories/outline.py（consume_inspiration 之后）
import datetime as _dt

_LEGAL_TRANSITIONS = {
    "raw": {"refined", "consumed", "discarded"},
    "refined": {"consumed", "partial", "discarded"},
    "partial": {"consumed", "discarded"},
    "consumed": {"discarded"},
    "discarded": set(),
}


def list_inspirations(conn, type_filter=None, status_filter=None):
    """灵感池列表，created_at 倒序。type/status 可选筛选（参数化，防注入）。"""
    sql = "SELECT * FROM inspiration"
    clauses, params = [], []
    if type_filter:
        clauses.append("type=?"); params.append(type_filter)
    if status_filter:
        clauses.append("status=?"); params.append(status_filter)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def advance_inspiration(conn, inspiration_id, target):
    """推进状态。校验 (current, target) 合法；非法 raise ValueError。设对应时间戳。
    状态机唯一入口——consume_inspiration 组合本函数。返回更新后 row（dict）。"""
    row = conn.execute("SELECT status FROM inspiration WHERE id=?",
                       (inspiration_id,)).fetchone()
    if row is None:
        raise ValueError(f"inspiration {inspiration_id} 不存在")
    current = row["status"]
    if target not in _LEGAL_TRANSITIONS.get(current, set()):
        raise ValueError(f"非法转移 {current}→{target}")
    now = _dt.datetime.now().isoformat()
    sets = {"status": target}
    if current == "raw" and target == "refined":
        sets["refined_at"] = now
    if target in ("consumed", "partial"):
        sets["promoted_at"] = now
    set_clause = ", ".join(f"{k}=?" for k in sets)
    conn.execute(f"UPDATE inspiration SET {set_clause} WHERE id=?",
                 [*sets.values(), inspiration_id])
    conn.commit()
    return dict(conn.execute("SELECT * FROM inspiration WHERE id=?",
                             (inspiration_id,)).fetchone())
```

- [ ] **Step 4: 重构 consume_inspiration（组合 advance）**

把既有 `consume_inspiration`（outline.py:53-61）替换为：
```python
def consume_inspiration(conn, inspiration_id, target_type, target_id):
    """记录灵感用进某 target。若 status 非 consumed，先 advance 推到 consumed（状态机校验 + 设 promoted_at）；
    若已 consumed，直接追加 consumed_into（允许多 target）。组合 advance 消除双写点。"""
    row = conn.execute("SELECT status FROM inspiration WHERE id=?",
                       (inspiration_id,)).fetchone()
    if row is None:
        raise ValueError(f"inspiration {inspiration_id} 不存在")
    if row["status"] != "consumed":
        advance_inspiration(conn, inspiration_id, "consumed")
    row2 = conn.execute("SELECT consumed_into FROM inspiration WHERE id=?",
                        (inspiration_id,)).fetchone()
    into = json.loads(row2["consumed_into"]) if row2 and row2["consumed_into"] else []
    into.append({"target_type": target_type, "target_id": target_id})
    conn.execute("UPDATE inspiration SET consumed_into=? WHERE id=?",
                 (json.dumps(into, ensure_ascii=False), inspiration_id))
    conn.commit()
```

- [ ] **Step 5: 跑测试 + 全量回归**

`python -m pytest tests/bedrock/ 2>&1 | tail -5` → 191 既有 + 新增测试全过（既有 test_inspiration_lifecycle 不破坏）

- [ ] **Step 6: Commit**

```bash
git add src/bedrock/repositories/outline.py tests/bedrock/test_outline.py
git commit -m "feat(bedrock): SP6-C inspiration 状态机 (list/advance + consume 组合 advance)"
```

---

## Task 2: parse_review_outcomes 抽取

**Files:** Modify `src/bedrock/cli/reader_commands.py`、`tests/bedrock/test_reader_commands.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/bedrock/test_reader_commands.py
from src.bedrock.cli.reader_commands import parse_review_outcomes

SP5_FOR_PARSE = """# VolumeReview 报告 — 卷 3

## 修正结果（三状态）
- ch7: edited_unverified
- ch9: escalate_human
- ch12: escalate_human
"""

V2_FOR_PARSE = """# 卷三 复盘
一、总体评价：本卷节奏偏快。
"""


def test_parse_review_outcomes_sp5():
    outcomes = parse_review_outcomes(SP5_FOR_PARSE)
    assert outcomes == {7: "edited_unverified", 9: "escalate_human", 12: "escalate_human"}


def test_parse_review_outcomes_v2_empty():
    """V2 手写报告 → 空 dict，不抛错。"""
    assert parse_review_outcomes(V2_FOR_PARSE) == {}
```

- [ ] **Step 2: 跑确认失败**

`python -m pytest tests/bedrock/test_reader_commands.py -k parse_review_outcomes -v` → FAIL

- [ ] **Step 3: 抽取 parse_review_outcomes**

在 `reader_commands.py` 把 `_OUTCOME_RE` 附近加公共函数（show_review_report 改用）：
```python
def parse_review_outcomes(text):
    """解析 SP5 review_report 的 outcomes 段，返回 {global_number: state} dict。
    V2 手写报告（无 SP5 格式段）→ 空 dict（不抛错）。CLI/Web 共用。"""
    return {int(m.group(1)): m.group(2) for m in _OUTCOME_RE.finditer(text)}
```
然后 show_review_report 的 escalate-only 分支里，把内联的 `{int(m.group(1)): m.group(2) for m in _OUTCOME_RE.finditer(text)}` 替换为 `parse_review_outcomes(text)`（行为不变，DRY）。

- [ ] **Step 4: 跑测试 + 回归**

`python -m pytest tests/bedrock/test_reader_commands.py -v` → SP6-A 既有 6 个 show_report 测试 + 2 个新 parse 测试全过

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/cli/reader_commands.py tests/bedrock/test_reader_commands.py
git commit -m "refactor(bedrock): 抽 parse_review_outcomes 供 CLI/Web 共用 (SP6-C 前置)"
```

---

## Task 3: queries.py（POV 矩阵 + 卷列表）

**Files:** Create `src/bedrock/web/queries.py`、`tests/bedrock/test_web_queries.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_web_queries.py（新建）
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat,
)
from src.bedrock.web.queries import pov_matrix, list_volumes_simple


def _seed_pov(conn):
    vid = create_volume(conn, 1, "第一卷", 1, 3, "opening")
    cid1 = create_chapter(conn, volume_id=vid, global_number=1, title="甲")
    cid2 = create_chapter(conn, volume_id=vid, global_number=2, title="乙")
    # 角色 1,2（需先建 character）
    from src.bedrock.repositories.worldbook import add_character
    hz = add_character(conn, name="韩峥", pronoun="他", role="protagonist")
    ls = add_character(conn, name="林深", pronoun="她", role="supporting")
    # ch1: 韩峥 POV；ch2: 林深 POV
    create_beat(conn, chapter_id=cid1, sequence=1, purpose="一个足够长的场景目的描述",
                pov_character_id=hz)
    create_beat(conn, chapter_id=cid2, sequence=1, purpose="一个足够长的场景目的描述",
                pov_character_id=ls)
    return vid, hz, ls, cid1, cid2


def test_pov_matrix_basic(tmp_project):
    conn = get_connection(tmp_project)
    vid, hz, ls, cid1, cid2 = _seed_pov(conn)
    matrix = pov_matrix(conn, vid)
    assert matrix["volume_name"] == "第一卷"
    assert len(matrix["chapters"]) == 2
    assert {"id": hz, "name": "韩峥"} in matrix["characters"]
    # ch1 有韩峥 POV
    ch1_row = next(r for r in matrix["chapters"] if r["global_number"] == 1)
    assert ch1_row["povs"] == {hz}   # 该章 POV 角色集合
    conn.close()


def test_pov_matrix_excludes_null_pov(tmp_project):
    """H5：NULL POV beat 不产角色列。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="x")
    create_beat(conn, chapter_id=cid, sequence=1, purpose="一个足够长的场景目的描述",
                pov_character_id=None)   # NULL POV
    matrix = pov_matrix(conn, vid)
    assert matrix["characters"] == []   # 无 POV 角色
    # 但章行仍渲染
    assert len(matrix["chapters"]) == 1
    conn.close()


def test_pov_matrix_empty_volume(tmp_project):
    """整卷无 POV → characters 空。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    matrix = pov_matrix(conn, vid)
    assert matrix["characters"] == []
    assert matrix["chapters"] == []
    conn.close()


def test_list_volumes_simple(tmp_project):
    conn = get_connection(tmp_project)
    create_volume(conn, 2, "乙", 4, 6, "opening")
    create_volume(conn, 1, "甲", 1, 3, "opening")
    vols = list_volumes_simple(conn)
    assert [v["number"] for v in vols] == [1, 2]   # 按 number 升序
    conn.close()
```

**注意**：需确认 `add_character` 的签名（worldbook.py 或 plot_tree）。实现时核对：可能是 `add_character(conn, name, pronoun, role)` 或带更多必填字段。先读 `repositories/worldbook.py`（或 character 所在 repository）确认签名再写测试 seed。

- [ ] **Step 2: 跑确认失败**

`python -m pytest tests/bedrock/test_web_queries.py -v` → FAIL（模块未定义）

- [ ] **Step 3: 实现 queries.py**

```python
# src/bedrock/web/__init__.py（空）
```

```python
# src/bedrock/web/queries.py
"""SP6-C Web UI 纯查询：POV 矩阵聚合 + 卷列表。新写聚合 SQL（既有 plot_tree 无 distinct-pov 函数）。"""


def list_volumes_simple(conn):
    """卷列表（id/number/name），按 number 升序。卷选择器数据源。"""
    return [dict(r) for r in conn.execute(
        "SELECT id, number, name FROM volume ORDER BY number").fetchall()]


def pov_matrix(conn, volume_id):
    """POV 矩阵数据：{volume_name, characters:[{id,name}], chapters:[{id,global_number,title,povs:set(char_id)}]}。
    NULL POV beat 不产角色列（H5）。"""
    vrow = conn.execute("SELECT number, name FROM volume WHERE id=?", (volume_id,)).fetchone()
    volume_name = vrow["name"] if vrow else None

    # 该卷出现过的 POV 角色（NULL 排除），按首次出现排序
    char_rows = conn.execute(
        "SELECT DISTINCT b.pov_character_id AS cid, c.name "
        "FROM beat b JOIN chapter ch ON b.chapter_id=ch.id "
        "JOIN character c ON b.pov_character_id=c.id "
        "WHERE ch.volume_id=? AND b.pov_character_id IS NOT NULL "
        "ORDER BY b.id", (volume_id,)).fetchall()
    characters = [{"id": r["cid"], "name": r["name"]} for r in char_rows]

    # 该卷章节，每章 POV 角色集合
    chapters = []
    ch_rows = conn.execute(
        "SELECT id, global_number, title FROM chapter WHERE volume_id=? ORDER BY global_number",
        (volume_id,)).fetchall()
    for ch in ch_rows:
        povs = {r["pov_character_id"] for r in conn.execute(
            "SELECT pov_character_id FROM beat WHERE chapter_id=? AND pov_character_id IS NOT NULL",
            (ch["id"],)).fetchall()}
        chapters.append({"id": ch["id"], "global_number": ch["global_number"],
                         "title": ch["title"], "povs": povs})
    return {"volume_name": volume_name, "characters": characters, "chapters": chapters}
```

- [ ] **Step 4: 跑测试**

`python -m pytest tests/bedrock/test_web_queries.py -v` → 4 测试过

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/web/__init__.py src/bedrock/web/queries.py tests/bedrock/test_web_queries.py
git commit -m "feat(bedrock): SP6-C queries (pov_matrix 聚合 + list_volumes_simple)"
```

---

## Task 4: web app scaffold + 3 视图路由 + 模板

**Files:** Create `src/bedrock/web/app.py`、`templates/*`、`tests/bedrock/test_web.py`

- [ ] **Step 1: 写失败测试（核心路由）**

```python
# tests/bedrock/test_web.py（新建）
import pytest
from pathlib import Path
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat
from src.bedrock.repositories.worldbook import add_character, add_constant
from src.bedrock.web.app import create_app


def _seed_app(tmp_project):
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "第一卷", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="甲", status="completed")
    hz = add_character(conn, name="韩峥", pronoun="他", role="protagonist")
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
    assert b"第一卷" in resp.data
    assert b"韩峥" in resp.data


def test_matrix_marks_pov_cell(tmp_project):
    vid = _seed_app(tmp_project)
    app = create_app(str(tmp_project))
    client = app.test_client()
    resp = client.get("/matrix", query_string={"volume": vid})
    assert b"\xe2\x97\x8f" in resp.data or "●" in resp.data.decode("utf-8")   # POV 单元格 ●


def test_inspirations_route(tmp_project):
    from src.bedrock.repositories.outline import add_inspiration
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
```

- [ ] **Step 2: 跑确认失败**

`python -m pytest tests/bedrock/test_web.py -v` → FAIL（app 未定义）

- [ ] **Step 3: 实现 app.py + 模板**

```python
# src/bedrock/web/app.py
"""SP6-C Flask app。create_app(project_dir) 工厂。每请求开/关 conn，不缓存。
唯一写点 = advance_inspiration（POST /inspirations/<id>/advance，校验 HX-Request）。"""
from pathlib import Path
from flask import Flask, render_template, request, abort

from src.bedrock.db.connection import get_connection
from src.bedrock.web.queries import pov_matrix, list_volumes_simple
from src.bedrock.repositories.outline import list_inspirations, advance_inspiration
from src.bedrock.cli.reader_commands import parse_review_outcomes


def create_app(project_dir):
    """project_dir 含 bedrock.db。校验存在（不创建空 db）。"""
    if not (Path(project_dir) / "bedrock.db").exists():
        raise SystemExit(f"项目目录无 bedrock.db: {project_dir}")
    app = Flask(__name__)
    app.config["PROJECT_DIR"] = project_dir   # 只存路径，不存 conn
    app.register_blueprint_routes = None      # 占位

    @app.route("/")
    def index():
        conn = get_connection(Path(app.config["PROJECT_DIR"]))
        try:
            volumes = list_volumes_simple(conn)
            return render_template("base.html", volumes=volumes, content="<p>选择一个视图</p>")
        finally:
            conn.close()

    @app.route("/matrix")
    def matrix():
        conn = get_connection(Path(app.config["PROJECT_DIR"]))
        try:
            volumes = list_volumes_simple(conn)
            volume_id = request.args.get("volume", type=int)
            if volume_id is None and volumes:
                volume_id = volumes[0]["id"]
            data = pov_matrix(conn, volume_id) if volume_id else None
            return render_template("matrix.html", volumes=volumes,
                                   volume_id=volume_id, matrix=data)
        finally:
            conn.close()

    @app.route("/inspirations")
    def inspirations():
        conn = get_connection(Path(app.config["PROJECT_DIR"]))
        try:
            type_f = request.args.get("type") or None
            status_f = request.args.get("status") or None
            items = list_inspirations(conn, type_filter=type_f, status_filter=status_f)
            return render_template("inspirations.html", items=items,
                                   type_f=type_f, status_f=status_f)
        finally:
            conn.close()

    @app.route("/report/<int:volume_id>")
    def report(volume_id):
        report_path = Path(app.config["PROJECT_DIR"]) / f"review_report_vol{volume_id}.md"
        if not report_path.exists():
            abort(404)
        text = report_path.read_text(encoding="utf-8")
        import markdown
        html = markdown.markdown(text, extensions=["extra", "sane_lists"])
        outcomes = parse_review_outcomes(text)
        escalate_chs = {ch for ch, st in outcomes.items() if st == "escalate_human"}
        return render_template("report.html", html=html, volume_id=volume_id,
                               escalate_chs=escalate_chs, has_escalate=bool(escalate_chs))

    return app
```

模板（Jinja2）：
- `base.html`：布局 + 导航（首页/矩阵/灵感池）+ htmx CDN `<script src="https://unpkg.com/htmx.org"></script>` + 内联 CSS link（`{{ url_for('static', filename='app.css') }}`）+ `{% block content %}{% endblock %}`。
- `matrix.html`：继承 base；卷选择器（form GET /matrix）+ 矩阵表（行=chapters，列=characters，单元格 `{% if char.id in ch.povs %}●{% endif %}`，● 带 htmx `hx-get="/matrix/beats?chapter=...&character=..."`）；整卷无 POV 提示。
- `inspirations.html`：继承 base；筛选器 + 卡片循环 `{% include "_inspiration_card.html" %}`。
- `_inspiration_card.html`：单卡（status 徽章 + content + 推进按钮，按合法转移显示）。
- `report.html`：继承 base；`{{ html|safe }}` + escalate 切换。

- [ ] **Step 4: 跑测试**

`python -m pytest tests/bedrock/test_web.py -v` → 6 测试过（若 Flask 未装，先 `pip install flask markdown`）

- [ ] **Step 5: 全量回归**

`python -m pytest tests/bedrock/ 2>&1 | tail -5`

- [ ] **Step 6: Commit**

```bash
git add src/bedrock/web/app.py src/bedrock/web/templates/ src/bedrock/web/static/ tests/bedrock/test_web.py
git commit -m "feat(bedrock): SP6-C Flask app + 3视图路由 (matrix/inspirations/report)"
```

**注意**：本步需先确认 flask + markdown 已装（`pip install flask markdown`，并加到 pyproject.toml dependencies）。

---

## Task 5: htmx 交互端点 + HX-Request 校验 + CSS

**Files:** Modify `src/bedrock/web/app.py`、`templates/*`、`static/app.css`、`tests/bedrock/test_web.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/bedrock/test_web.py
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
    assert b"beat" in resp.data.lower() or b"目的" in resp.data   # beat 列表片段


def test_inspirations_advance_htmx(tmp_project):
    from src.bedrock.repositories.outline import add_inspiration
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
    from src.bedrock.repositories.outline import add_inspiration
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    conn.close()
    app = create_app(str(tmp_project))
    client = app.test_client()
    resp = client.post(f"/inspirations/{iid}/advance", data={"target": "refined"})   # 无 HX-Request 头
    assert resp.status_code == 403


def test_inspirations_advance_illegal_returns_error_card(tmp_project):
    from src.bedrock.repositories.outline import add_inspiration, advance_inspiration
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    advance_inspiration(conn, iid, "discarded")   # 终态
    conn.close()
    app = create_app(str(tmp_project))
    client = app.test_client()
    resp = client.post(f"/inspirations/{iid}/advance",
                       data={"target": "refined"}, headers={"HX-Request": "true"})
    assert resp.status_code == 200   # 不崩，返回错误卡
    assert "error" in resp.data.decode("utf-8").lower() or "非法" in resp.data.decode("utf-8")
    # 原 status 不变
    conn = get_connection(tmp_project)
    assert conn.execute("SELECT status FROM inspiration WHERE id=?", (iid,)).fetchone()["status"] == "discarded"
    conn.close()
```

- [ ] **Step 2: 跑确认失败**

`python -m pytest tests/bedrock/test_web.py -k "beat_expand or advance" -v` → FAIL（端点未定义）

- [ ] **Step 3: 加端点到 app.py**

```python
# 追加到 create_app 内（report 路由之后、return app 之前）

    @app.route("/matrix/beats")
    def matrix_beats():
        conn = get_connection(Path(app.config["PROJECT_DIR"]))
        try:
            chapter_id = request.args.get("chapter", type=int)
            character_id = request.args.get("character", type=int)
            beats = conn.execute(
                "SELECT sequence, purpose FROM beat WHERE chapter_id=? AND pov_character_id=? ORDER BY sequence",
                (chapter_id, character_id)).fetchall()
            return render_template("_beats.html", beats=[dict(b) for b in beats])
        finally:
            conn.close()

    @app.route("/inspirations/<int:iid>/advance", methods=["POST"])
    def inspirations_advance(iid):
        if not request.headers.get("HX-Request"):
            abort(403)   # 弱 CSRF
        target = request.form.get("target")
        conn = get_connection(Path(app.config["PROJECT_DIR"]))
        try:
            try:
                row = advance_inspiration(conn, iid, target)
            except ValueError as e:
                return render_template("_inspiration_card.html", item={"status": "error"},
                                       error=str(e))
            return render_template("_inspiration_card.html", item=row)
        finally:
            conn.close()
```

注意 `_inspiration_card.html` 需处理 `item.status == "error"`（错误卡）+ 正常 status（显示对应推进按钮）。

- [ ] **Step 4: CSS（static/app.css）**

```css
.status-raw { background: #ccc; }
.status-refined { background: #6cf; }
.status-consumed { background: #9c9; }
.status-partial { background: #fc9; }
.status-discarded { background: #f99; text-decoration: line-through; }
.matrix-table { overflow-x: auto; }
.escalate-highlight { border-left: 4px solid red; background: #ffc; padding-left: 4px; }
```

- [ ] **Step 5: 跑测试 + 全量回归**

`python -m pytest tests/bedrock/ 2>&1 | tail -5`

- [ ] **Step 6: Commit**

```bash
git add src/bedrock/web/app.py src/bedrock/web/templates/ src/bedrock/web/static/ tests/bedrock/test_web.py
git commit -m "feat(bedrock): SP6-C htmx 交互端点 (beat展开/advance) + HX-Request校验 + CSS"
```

---

## Task 6: __main__ 入口 + 依赖声明 + 全量回归 + 最终复核

**Files:** Create `src/bedrock/web/__main__.py`、Modify `pyproject.toml`（+flask +markdown）

- [ ] **Step 1: __main__.py**

```python
# src/bedrock/web/__main__.py
"""python -m src.bedrock.web --project <dir> [--port 5000]"""
import argparse
from src.bedrock.web.app import create_app


def main():
    parser = argparse.ArgumentParser(prog="bedrock-web")
    parser.add_argument("--project", required=True, help="项目目录（含 bedrock.db）")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    app = create_app(args.project)
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: pyproject.toml 加依赖**

`dependencies` 加 `"flask>=3.0"` 和 `"markdown>=3.5"`（与既有 `mcp[cli]` 等并列）。

- [ ] **Step 3: 冒烟（手动，不进自动化）**

```bash
cd D:/novel_test
# 需一个有 bedrock.db 的项目；若无，用一个 tmp 项目 init
python -m src.bedrock.web --project <有 bedrock.db 的目录> --port 5050
# 浏览器开 http://127.0.0.1:5050 看三视图（手动 Ctrl+C 停）
```

- [ ] **Step 4: 全量回归**

`python -m pytest tests/bedrock/ 2>&1 | tail -5` → 既有 191 + SP6-C 新增全过、2 e2e skip

- [ ] **Step 5: 派最终复核子代理**

用 superpowers:code-reviewer 审整个 `src/bedrock/web/` + outline.py 改动 + reader_commands parse_review_outcomes，对照 spec §9 验收 + 抗博弈（唯一写点 advance / consume 组合 / HX-Request / 每请求 conn / 不创建空 db）。

- [ ] **Step 6: 更新项目记忆**

更新 `bedrock-v3-status.md`：SP6-C ✅ 完成，SP6 工具层（A+B+C）全部完成。

- [ ] **Step 7: Commit**

```bash
git add src/bedrock/web/__main__.py pyproject.toml
git commit -m "feat(bedrock): SP6-C web 入口 + 依赖声明 (flask/markdown)"
```

---

## Self-Review

**Spec 覆盖：**
- §4 三视图 → Task 4（路由）+ Task 5（htmx 交互）
- §5 灵感池状态机 → Task 1
- §6 parse_review_outcomes → Task 2
- §4.1 POV 聚合 → Task 3
- §9 验收 → Task 6

**抗博弈/不变量贯穿：**
- 唯一写点 advance_inspiration + consume 组合 → Task 1 test_consume_inspiration_composes_advance_and_multi_target
- HX-Request 校验 → Task 5 test_inspirations_advance_requires_htmx_header
- 不创建空 db → Task 4 test_create_app_requires_bedrock_db
- POV NULL 排除 → Task 3 test_pov_matrix_excludes_null_pov
- V2 报告容错 → Task 2 test_parse_review_outcomes_v2_empty + Task 4 report 渲染
- partial→consumed → Task 1 test_advance_partial_to_consumed

**已知风险点：**
- Task 3/4 seed 用 `add_character` —— 实现时核对 worldbook.py 的 add_character 签名（必填字段）。
- Task 4/5 需 flask + markdown 已装（`pip install` + pyproject 声明）。
- Task 4 matrix.html 模板的 ● htmx `hx-get` + 整卷无 POV 提示分支，按 spec §4.1 规则。
- `_inspiration_card.html` 按合法转移表（spec §5.1）显示按钮，error 卡分支。
