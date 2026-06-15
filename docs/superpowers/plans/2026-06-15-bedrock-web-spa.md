# 磁石 Bedrock Web SPA 工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前 Flask+Jinja+htmx 的只读 Web UI 重做成 Vue3+Naive UI 的 SPA 工作台：7 视图（总览/角色/POV矩阵/灵感池/Review报告/正文阅读/正文大纲）+ 多作品工作区切换 + 灵感推进/编辑 + 层1元数据编辑 + 层2大纲编辑，全部走 `add_amendment` 审计骨架，单进程一键启动。

**Architecture:** Flask 退成纯 JSON API（`/api` 蓝图，按 work_id 作用域），Vue3 SPA 经 Vite 构建后由 Flask 同进程托管。纯函数层（repositories/queries）零破坏复用，新增 read/edit 查询函数 pytest 锁死；API 层 Flask test client 测；前端手动冒烟。3 期推进：①后端纯函数+API ②SPA骨架+7只读视图+灵感写 ③元数据+大纲编辑。

**Tech Stack:** Python/Flask（既有）/ Vue3 + Vite + Naive UI + vue-router + pinia + marked + TypeScript（新增 frontend/ 工程）/ SQLite（既有 bedrock.db）。

**Spec:** `docs/superpowers/specs/2026-06-15-bedrock-web-spa-redesign.md`

**前端约定：** 逻辑关键代码（vite/package/router/pinia store/api client/App 外壳/提交处理/guard）给完整代码；展示型 Vue SFC 给精确 spec（用哪些 Naive 组件、布局、数据绑定、验收），由实现者据此写出组件。这是本计划对 writing-plans「complete code」的务实诠释——前端组件的"代码"= spec+绑定+验收，足够执行。

---

## File Structure

**后端（src/bedrock/）：**
- `web/queries.py` — **扩**：read 查询（list_works/overview_stats/chapter_text/outline_tree/list_characters/worldbook_overview/list_factions）。纯函数，pytest 锁。
- `repositories/outline.py` — **扩**：update_inspiration_content（已在 spec）+ update_master_outline。
- `repositories/character.py` — **扩**：update_character + amendment 助手。
- `repositories/plot_tree.py` — **扩**：update_chapter_meta/update_volume_meta/update_beat_meta。
- `repositories/worldbook.py` — **扩**：update_location/update_theme/update_motif。
- `repositories/_amendment.py` — **新**：私有 `record_amendment` 助手（包 governance.add_amendment，best-effort）。
- `web/api.py` — **新**：/api 蓝图，read + write 端点，路径穿越/CSRF/失败语义。
- `web/app.py` — **改**：create_app(projects_root) + 挂 api 蓝图 + SPA 静态托管；删 Jinja 路由/context_processor。
- `web/__main__.py` — **改**：--projects-root。
- `web/templates/`、`web/static/app.css` — **删**。
- `web/static/.gitkeep` — **新**（占位，static/ 其余 gitignored）。

**前端（frontend/，新工程）：**
- `package.json` / `vite.config.ts` / `tsconfig.json` / `index.html` / `.gitignore`
- `src/main.ts` / `src/App.vue` / `src/router.ts`
- `src/api/client.ts` / `src/stores/workspace.ts`
- `src/components/{WorkSwitcher,SideNav,BeatDrawer}.vue`
- `src/views/{Overview,Characters,Matrix,Inspirations,Report,Reader,Outline}.vue`
- `src/components/edit/{CharacterForm,WorldbookInline,BeatEdit,MasterOutlineEdit}.vue`

**测试（tests/bedrock/）：**
- `test_queries.py` — **新**（read 查询）。
- `test_edit_repos.py` — **新**（层1+层2 edit repo）。
- `test_api.py` — **新**（API 层，取代 test_web.py）。
- `test_outline.py` — **扩**（update_inspiration_content）。
- `test_web.py` — **删**。
- `test_web_queries.py` — **保留**（pov_matrix/list_volumes_simple 零改动）。

**其他：**
- `.gitignore` — **扩**（frontend/node_modules、frontend/dist、src/bedrock/web/static/ 除 .gitkeep）。
- `.claude/launch.json` — **改**（bedrock-web → --projects-root projects）。
- `scripts/start_webui.bat` — **新**（一键启动）。
- `scripts/seed_bedrock_demo.py` — **扩**（补 master_outline/volume_outline/世界观数据，供冒烟）。

---

# Phase 1：后端纯函数 + API（无前端，pytest 锁）

## Task 1: amendment 助手 + read 查询（queries.py）

**Files:**
- Create: `src/bedrock/repositories/_amendment.py`
- Modify: `src/bedrock/web/queries.py`
- Test: `tests/bedrock/test_queries.py`

- [ ] **Step 1: 写失败测试 `tests/bedrock/test_queries.py`**

```python
# tests/bedrock/test_queries.py
import json
from pathlib import Path
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat, create_paragraph
from src.bedrock.repositories.character import create_character
from src.bedrock.repositories.worldbook import add_constant, add_location, add_theme, add_motif, add_faction
from src.bedrock.repositories.outline import add_inspiration, advance_inspiration
from src.bedrock.web.queries import (
    list_works, overview_stats, chapter_text, outline_tree,
    list_characters, worldbook_overview, list_factions,
)


def _seed(conn):
    add_constant(conn, key="work_name", value="测试书")
    v = create_volume(conn, 1, "第一卷", 1, 3, "opening")
    c1 = create_chapter(conn, volume_id=v, global_number=1, title="甲", status="completed")
    c2 = create_chapter(conn, volume_id=v, global_number=2, title="乙", status="writing")
    hz = create_character(conn, name="韩峥", pronoun="他", role="protagonist", personality="谨慎")
    b1 = create_beat(conn, chapter_id=c1, sequence=1, purpose="一个足够长的场景目的描述文字", pov_character_id=hz)
    create_paragraph(conn, chapter_id=c1, seq=1, text="韩峥站在封锁线前。", content_hash="h11", beat_id=b1, role="narration")
    create_paragraph(conn, chapter_id=c1, seq=2, text="电流声嗡鸣。", content_hash="h12", beat_id=b1, role="narration")
    add_location(conn, name="封锁线", loc_type="border", description="城市边缘的膜")
    add_theme(conn, name="边界", description="人与系统的界线")
    add_motif(conn, name="电流声", meaning="共振象征")
    add_faction(conn, name="守卫者", ftype="org")
    add_inspiration(conn, content="灵一", type="scene")
    i2 = add_inspiration(conn, content="灵二", type="mechanic")
    advance_inspiration(conn, i2, "refined")
    return v, c1, c2, hz


def test_list_works_scans_subdirs(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    # 子目录 a 含 bedrock.db
    from src.bedrock.init_project import init_project
    a = root / "a"
    init_project(a, work_name="书A", force=True)
    conn = get_connection(a); add_constant(conn, "work_name", "书A"); conn.close()
    # 子目录 b 无 db（应被忽略）
    (root / "b").mkdir()
    works = list_works(root)
    assert [w["id"] for w in works] == ["a"]
    assert works[0]["name"] == "书A"


def test_list_works_name_none_fallback(tmp_path):
    root = tmp_path / "projects"; root.mkdir()
    from src.bedrock.init_project import init_project
    init_project(root / "x", work_name="x", force=True)  # work_name 会被 init_project 写入
    # 模拟无 work_name：删除 constant
    conn = get_connection(root / "x"); conn.execute("DELETE FROM constants WHERE key='work_name'"); conn.commit(); conn.close()
    works = list_works(root)
    assert works[0]["name"] == "x"  # 降级目录名


def test_overview_stats(tmp_project):
    conn = get_connection(tmp_project)
    _seed(conn); conn.commit(); conn.close()
    conn = get_connection(tmp_project)
    st = overview_stats(conn)
    assert st["volumes"] == 1
    assert st["chapters"]["completed"] == 1 and st["chapters"]["writing"] == 1
    assert st["chapters"]["total"] == 2
    assert st["characters"] == 1
    assert st["word_total"] >= 4  # 至少 4 汉字
    assert st["inspirations"]["raw"] == 1 and st["inspirations"]["refined"] == 1
    assert len(st["volume_list"]) == 1
    conn.close()


def test_chapter_text_orders_by_seq(tmp_project):
    conn = get_connection(tmp_project); _seed(conn); conn.commit(); conn.close()
    conn = get_connection(tmp_project)
    t = chapter_text(conn, 1)
    assert [p["seq"] for p in t["paragraphs"]] == [1, 2]
    assert t["chapter"]["title"] == "甲"
    conn.close()


def test_chapter_text_empty(tmp_project):
    conn = get_connection(tmp_project)
    create_volume(conn, 1, "V", 9, 9, "opening")
    create_chapter(conn, volume_id=1, global_number=9, title="空", status="planned")
    conn.commit(); conn.close()
    conn = get_connection(tmp_project)
    t = chapter_text(conn, 9)
    assert t["paragraphs"] == []
    conn.close()


def test_outline_tree_full(tmp_project):
    conn = get_connection(tmp_project); v, c1, _, hz = _seed(conn)
    # volume_outline 行
    conn.execute("INSERT OR IGNORE INTO volume_outline(volume_id,status,beat_contracts) VALUES(?, 'drafted', ?)",
                 (v, json.dumps([{"beat_id": 1, "purpose": "契约"}])))
    conn.commit(); conn.close()
    conn = get_connection(tmp_project)
    tree = outline_tree(conn, v)
    assert tree["master_outline"] is None or isinstance(tree["master_outline"], dict)
    assert len(tree["volumes"]) == 1
    vol = tree["volumes"][0]
    assert vol["volume_outline"]["status"] == "drafted"
    ch = vol["chapters"][0]
    assert ch["beats"][0]["pov_name"] == "韩峥"
    assert ch["beats"][0]["paragraph_count"] == 2
    conn.close()


def test_outline_tree_missing_fields_null(tmp_project):
    conn = get_connection(tmp_project)
    create_volume(conn, 1, "V", 5, 5, "opening")
    create_chapter(conn, volume_id=1, global_number=5, title="裸", status="planned")
    conn.commit(); conn.close()
    conn = get_connection(tmp_project)
    tree = outline_tree(conn, 1)
    vol = tree["volumes"][0]
    assert vol["volume_outline"] is None  # 无 volume_outline 行
    assert vol["chapters"][0]["beats"] == []
    conn.close()


def test_list_characters_with_subcounts(tmp_project):
    conn = get_connection(tmp_project); _, _, _, hz = _seed(conn); conn.commit(); conn.close()
    conn = get_connection(tmp_project)
    cs = list_characters(conn)
    assert cs[0]["name"] == "韩峥"
    assert cs[0]["abilities"] == []  # JSON 解析为 list
    assert cs[0]["secret_count"] == 0
    conn.close()


def test_worldbook_overview(tmp_project):
    conn = get_connection(tmp_project); _seed(conn); conn.commit(); conn.close()
    conn = get_connection(tmp_project)
    wb = worldbook_overview(conn)
    assert len(wb["locations"]) == 1 and wb["locations"][0]["name"] == "封锁线"
    assert len(wb["themes"]) == 1
    assert len(wb["motifs"]) == 1
    conn.close()


def test_list_factions(tmp_project):
    conn = get_connection(tmp_project); _seed(conn); conn.commit(); conn.close()
    conn = get_connection(tmp_project)
    fs = list_factions(conn)
    assert fs[0]["name"] == "守卫者"
    conn.close()
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/bedrock/test_queries.py -q`
Expected: FAIL（ImportError / 函数未定义）。

- [ ] **Step 3: 实现 `src/bedrock/repositories/_amendment.py`**

```python
# src/bedrock/repositories/_amendment.py
"""amendment 记录助手：包 governance.add_amendment，best-effort（写失败仅记日志，不阻断主写）。"""
import logging
from src.bedrock.repositories.governance import add_amendment

_log = logging.getLogger(__name__)


def record_amendment(conn, entity_type, entity_id, field, old, new):
    """记一条修正。失败 best-effort（本地单用户，审计完整性不阻断可用性）。"""
    try:
        add_amendment(conn, entity_type=entity_type, entity_id=entity_id,
                      field=field, new=str(new), old=(None if old is None else str(old)))
    except Exception as e:  # best-effort
        _log.warning("amendment 记录失败 %s/%s/%s: %s", entity_type, entity_id, field, e)
```

> 核对 `governance.add_amendment` 实际签名：实现第一步 `Read src/bedrock/repositories/governance.py` 确认参数名（entity_type/entity_id/field/new/old），按真实签名调整。spec §7.1 已记。

- [ ] **Step 4: 实现 read 查询 `src/bedrock/web/queries.py`（在文件末尾追加；保留既有 pov_matrix/list_volumes_simple）**

```python
# src/bedrock/web/queries.py —— 文件顶部既有 pov_matrix/list_volumes_simple 保留，下面追加
import json
from pathlib import Path
from src.bedrock.checks.word_count import compute_word_count
from src.bedrock.repositories.worldbook import get_constant
from src.bedrock.db.connection import get_connection


def list_works(projects_root):
    """扫描 projects_root 子目录，找含 bedrock.db 的。每个开 conn 读 work_name + 计数。"""
    root = Path(projects_root)
    out = []
    for sub in sorted([p for p in root.iterdir() if p.is_dir()]):
        if not (sub / "bedrock.db").exists():
            continue
        try:
            conn = get_connection(sub)
            try:
                name_row = get_constant(conn, "work_name")
                name = name_row["value"] if (name_row and "value" in name_row.keys()) else (name_row if isinstance(name_row, str) else None)
                if not name:
                    name = sub.name  # 降级目录名
                nv = conn.execute("SELECT COUNT(*) n FROM volume").fetchone()["n"]
                cc = conn.execute(
                    "SELECT SUM(status='completed') c, SUM(status='writing') w FROM chapter").fetchone()
                reports = list((sub).glob("review_report_vol*.md"))
                out.append({
                    "id": sub.name, "name": name, "volumes": nv,
                    "chapters_completed": cc["c"] or 0, "chapters_writing": cc["w"] or 0,
                    "has_any_report": len(reports) > 0,
                })
            finally:
                conn.close()
        except Exception:
            continue  # 跳过打不开的 db
    return out


def overview_stats(conn):
    nv = conn.execute("SELECT COUNT(*) n FROM volume").fetchone()["n"]
    row = conn.execute(
        "SELECT SUM(status='completed') c, SUM(status='writing') w, COUNT(*) t FROM chapter").fetchone()
    nchar = conn.execute("SELECT COUNT(*) n FROM character").fetchone()["n"]
    texts = [r["text"] for r in conn.execute("SELECT text FROM paragraph").fetchall()]
    word_total = compute_word_count(texts) if texts else 0
    insp = {r["status"]: r["n"] for r in conn.execute(
        "SELECT status, COUNT(*) n FROM inspiration GROUP BY status").fetchall()}
    vol_list = [dict(r) for r in conn.execute(
        "SELECT id, number, name, volume_type, status FROM volume ORDER BY number").fetchall()]
    for v in vol_list:
        v["chapter_count"] = conn.execute(
            "SELECT COUNT(*) n FROM chapter WHERE volume_id=?", (v["id"],)).fetchone()["n"]
    snap = [dict(r) for r in conn.execute(
        "SELECT id, name, role, state, pronoun, personality FROM character ORDER BY id").fetchall()]
    for s in snap:
        s["personality_excerpt"] = (s["personality"] or "")[:40]
    wb = worldbook_overview(conn)
    return {
        "name": _work_name(conn), "volumes": nv,
        "chapters": {"completed": row["c"] or 0, "writing": row["w"] or 0, "total": row["t"]},
        "characters": nchar, "word_total": word_total,
        "inspirations": {k: insp.get(k, 0) for k in
                         ("raw", "refined", "consumed", "partial", "discarded")},
        "volume_list": vol_list,
        "character_snapshot": snap,
        "worldbook": wb,
    }


def _work_name(conn):
    r = get_constant(conn, "work_name")
    if r is None:
        return None
    return r["value"] if "value" in r.keys() else r


def chapter_text(conn, global_number):
    ch = conn.execute(
        "SELECT global_number, title FROM chapter WHERE global_number=?", (global_number,)).fetchone()
    if ch is None:
        return None
    paras = [{"seq": r["seq"], "text": r["text"]} for r in conn.execute(
        "SELECT seq, text FROM paragraph WHERE chapter_id IN (SELECT id FROM chapter WHERE global_number=?) "
        "ORDER BY seq", (global_number,)).fetchall()]
    return {"chapter": {"global_number": ch["global_number"], "title": ch["title"]},
            "paragraphs": paras}


def outline_tree(conn, volume_id=None):
    # master_outline
    mo_row = conn.execute(
        "SELECT theme_evolution, key_arcs, key_milestones, rhythm_curve FROM master_outline WHERE id=1").fetchone()
    master = None
    if mo_row and any(mo_row[k] for k in mo_row.keys() if mo_row[k] not in ("", None)):
        master = {
            "theme_evolution": mo_row["theme_evolution"],
            "key_arcs": _json_loads(mo_row["key_arcs"], []),
            "key_milestones": _json_loads(mo_row["key_milestones"], []),
            "rhythm_curve": mo_row["rhythm_curve"],
        }
    vsql = ("SELECT id, number, name, volume_type, status, theme_seeds FROM volume"
            + (" WHERE id=?" if volume_id else "") + " ORDER BY number")
    vparams = (volume_id,) if volume_id else ()
    vols = []
    for v in conn.execute(vsql, vparams).fetchall():
        vo = conn.execute(
            "SELECT status, locked_at, beat_contracts FROM volume_outline WHERE volume_id=?",
            (v["id"],)).fetchone()
        vol_outline = ({"status": vo["status"], "locked_at": vo["locked_at"],
                        "beat_contracts": _json_loads(vo["beat_contracts"], [])} if vo else None)
        chs = []
        for ch in conn.execute(
                "SELECT id, global_number, title, status FROM chapter WHERE volume_id=? ORDER BY global_number",
                (v["id"],)).fetchall():
            beats = []
            for b in conn.execute(
                    "SELECT id, sequence, purpose, pov_character_id, scene_setting, status, deviation_note "
                    "FROM beat WHERE chapter_id=? ORDER BY sequence", (ch["id"],)).fetchall():
                pname = None
                if b["pov_character_id"]:
                    pr = conn.execute("SELECT name FROM character WHERE id=?", (b["pov_character_id"],)).fetchone()
                    pname = pr["name"] if pr else None
                pcount = conn.execute("SELECT COUNT(*) n FROM paragraph WHERE beat_id=?", (b["id"],)).fetchone()["n"]
                beats.append({
                    "id": b["id"], "sequence": b["sequence"], "purpose": b["purpose"],
                    "pov_name": pname, "scene_setting": _json_loads(b["scene_setting"], {}),
                    "status": b["status"], "deviation_note": b["deviation_note"],
                    "paragraph_count": pcount,
                })
            chs.append({"id": ch["id"], "global_number": ch["global_number"],
                        "title": ch["title"], "status": ch["status"], "beats": beats})
        vols.append({"id": v["id"], "number": v["number"], "name": v["name"],
                     "volume_type": v["volume_type"], "status": v["status"],
                     "theme_seeds": _json_loads(v["theme_seeds"], []),
                     "volume_outline": vol_outline, "chapters": chs})
    return {"master_outline": master, "volumes": vols}


def list_characters(conn):
    rows = conn.execute(
        "SELECT id, name, pronoun, gender, role, faction_id, state, personality, goals, abilities, aliases "
        "FROM character ORDER BY id").fetchall()
    out = []
    for r in rows:
        fac = None
        if r["faction_id"]:
            fr = conn.execute("SELECT name FROM faction WHERE id=?", (r["faction_id"],)).fetchone()
            fac = fr["name"] if fr else None
        sc = conn.execute("SELECT COUNT(*) n FROM character_secret WHERE character_id=?", (r["id"],)).fetchone()["n"]
        kc = conn.execute("SELECT COUNT(*) n FROM character_knowledge WHERE character_id=?", (r["id"],)).fetchone()["n"]
        out.append({
            "id": r["id"], "name": r["name"], "pronoun": r["pronoun"], "gender": r["gender"],
            "role": r["role"], "faction_id": r["faction_id"], "faction_name": fac, "state": r["state"],
            "personality": r["personality"], "goals": r["goals"],
            "abilities": _json_loads(r["abilities"], []), "aliases": _json_loads(r["aliases"], []),
            "secret_count": sc, "knowledge_count": kc,
        })
    return out


def worldbook_overview(conn):
    locs = [dict(r) for r in conn.execute("SELECT id, name, loc_type, description, state FROM location ORDER BY id").fetchall()]
    themes = [dict(r) for r in conn.execute("SELECT id, name, description, evolution FROM theme ORDER BY id").fetchall()]
    motifs = [dict(r) for r in conn.execute("SELECT id, name, meaning, evolution FROM motif ORDER BY id").fetchall()]
    return {"locations": locs, "themes": themes, "motifs": motifs}


def list_factions(conn):
    return [dict(r) for r in conn.execute("SELECT id, name, ftype, stance, state FROM faction ORDER BY id").fetchall()]


def _json_loads(raw, default):
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default
```

> 实现第一步核对：`get_constant` 返回 `sqlite3.Row` 或 None（row_factory 已设）。`"value" in r.keys()` 适配 Row。若 `get_constant` 实际返回 str/None，按真实调整（test_list_works_name_none_fallback 已覆盖 None 分支）。

- [ ] **Step 5: 运行确认通过**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/bedrock/test_queries.py -q`
Expected: 10 passed。

- [ ] **Step 6: 提交**

```bash
git add src/bedrock/repositories/_amendment.py src/bedrock/web/queries.py tests/bedrock/test_queries.py
git commit -m "feat(web): read 查询 (list_works/overview/chapter_text/outline_tree/characters/worldbook/factions) + amendment 助手"
```

---

## Task 2: update_inspiration_content（outline.py）

**Files:**
- Modify: `src/bedrock/repositories/outline.py`
- Test: `tests/bedrock/test_outline.py`

- [ ] **Step 1: 写失败测试（追加到 `tests/bedrock/test_outline.py`）**

```python
# 追加到 tests/bedrock/test_outline.py
import json
from src.bedrock.repositories.outline import (
    add_inspiration, advance_inspiration, consume_inspiration, update_inspiration_content,
)


def test_update_content_raw_ok(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="原", type="scene")
    row = update_inspiration_content(conn, iid, content="新内容")
    assert row["content"] == "新内容"
    conn.close()


def test_update_content_refined_partial_ok(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    advance_inspiration(conn, iid, "refined")
    update_inspiration_content(conn, iid, content="改")
    iid2 = add_inspiration(conn, content="y", type="scene")
    advance_inspiration(conn, iid2, "refined"); advance_inspiration(conn, iid2, "partial")
    update_inspiration_content(conn, iid2, content="改2")
    conn.close()  # 不抛即过


def test_update_content_frozen_consumed(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    hz = create_character(conn, name="韩", pronoun="他", role="protagonist")  # 复用既有 import
    consume_inspiration(conn, iid, target_type="character", target_id=hz)
    with pytest.raises(ValueError):
        update_inspiration_content(conn, iid, content="改")
    assert conn.execute("SELECT content FROM inspiration WHERE id=?", (iid,)).fetchone()["content"] == "x"
    conn.close()


def test_update_content_frozen_discarded(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    advance_inspiration(conn, iid, "discarded")
    with pytest.raises(ValueError):
        update_inspiration_content(conn, iid, content="改")
    conn.close()


def test_update_content_unknown_id(tmp_project):
    conn = get_connection(tmp_project)
    with pytest.raises(ValueError):
        update_inspiration_content(conn, 9999, content="x")
    conn.close()


def test_update_content_empty_rejected(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    with pytest.raises(ValueError):
        update_inspiration_content(conn, iid, content="   ")
    conn.close()


def test_update_content_with_source(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    row = update_inspiration_content(conn, iid, content="改", source="新来源")
    assert row["source"] == "新来源"
    conn.close()
```

> 文件顶部需 `import pytest` + `from src.bedrock.repositories.character import create_character` + `get_connection`（若已 import 则跳过）。

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/bedrock/test_outline.py -q -k update_content`
Expected: FAIL（update_inspiration_content 未定义）。

- [ ] **Step 3: 实现（追加到 `src/bedrock/repositories/outline.py`）**

```python
# 追加到 src/bedrock/repositories/outline.py
from src.bedrock.repositories._amendment import record_amendment


def update_inspiration_content(conn, inspiration_id, content, source=None):
    """编辑灵感内容（仅未消费时）。guard：status IN (raw,refined,partial) 且 consumed_into 为空。
    content 去空后非空。source 非 None 一并更新。UPDATE 前 raise。返回更新后整行 dict。"""
    row = conn.execute("SELECT status, consumed_into, content, source FROM inspiration WHERE id=?",
                      (inspiration_id,)).fetchone()
    if row is None:
        raise ValueError(f"inspiration {inspiration_id} 不存在")
    into = json.loads(row["consumed_into"]) if row["consumed_into"] else []
    if row["status"] not in ("raw", "refined", "partial") or into:
        raise ValueError(f"inspiration {inspiration_id} 已消费/已弃用，内容冻结")
    content = (content or "").strip()
    if not content:
        raise ValueError("content 不能为空")
    sets = {"content": content}
    if source is not None:
        sets["source"] = source
    set_clause = ", ".join(f"{k}=?" for k in sets)
    conn.execute(f"UPDATE inspiration SET {set_clause} WHERE id=?",
                 [*sets.values(), inspiration_id])
    if "content" in sets:
        record_amendment(conn, "inspiration", inspiration_id, "content", row["content"], content)
    if source is not None:
        record_amendment(conn, "inspiration", inspiration_id, "source", row["source"], source)
    conn.commit()
    return dict(conn.execute("SELECT * FROM inspiration WHERE id=?", (inspiration_id,)).fetchone())
```

> `json` 已在 outline.py 顶部 import（consume_inspiration 用过）。`record_amendment` import 放文件顶部。

- [ ] **Step 4: 运行确认通过**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/bedrock/test_outline.py -q`
Expected: 全部通过（既有 + 7 新）。

- [ ] **Step 5: 提交**

```bash
git add src/bedrock/repositories/outline.py tests/bedrock/test_outline.py
git commit -m "feat(outline): update_inspiration_content (未消费可编辑, consumed/discarded 冻结)"
```

---

## Task 3: update_character（character.py）

**Files:**
- Modify: `src/bedrock/repositories/character.py`
- Test: `tests/bedrock/test_edit_repos.py`（新文件）

- [ ] **Step 1: 写失败测试 `tests/bedrock/test_edit_repos.py`**

```python
# tests/bedrock/test_edit_repos.py
import pytest
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.character import create_character, update_character


def test_update_character_fields(tmp_project):
    conn = get_connection(tmp_project)
    cid = create_character(conn, name="韩峥", pronoun="他", role="protagonist", personality="旧")
    row = update_character(conn, cid, personality="谨慎执拗", goals="守住边界")
    assert row["personality"] == "谨慎执拗" and row["goals"] == "守住边界"
    # 记了 amendment
    am = conn.execute("SELECT COUNT(*) n FROM amendment WHERE entity_type='character' AND entity_id=?", (cid,)).fetchone()["n"]
    assert am >= 2
    conn.close()


def test_update_character_name_unique_conflict(tmp_project):
    conn = get_connection(tmp_project)
    create_character(conn, name="韩峥", pronoun="他", role="protagonist")
    cid2 = create_character(conn, name="林深", pronoun="她", role="supporting")
    with pytest.raises(ValueError):
        update_character(conn, cid2, name="韩峥")
    assert conn.execute("SELECT name FROM character WHERE id=?", (cid2,)).fetchone()["name"] == "林深"
    conn.close()


def test_update_character_enum_invalid(tmp_project):
    conn = get_connection(tmp_project)
    cid = create_character(conn, name="韩", pronoun="他", role="protagonist")
    with pytest.raises(ValueError):
        update_character(conn, cid, pronoun="某某")  # 非法枚举
    with pytest.raises(ValueError):
        update_character(conn, cid, state="不存在")
    conn.close()


def test_update_character_abilities_aliases_json(tmp_project):
    conn = get_connection(tmp_project)
    cid = create_character(conn, name="韩", pronoun="他", role="protagonist")
    row = update_character(conn, cid, abilities=["速攻", "洞察"], aliases=["老韩"])
    import json
    assert json.loads(conn.execute("SELECT abilities FROM character WHERE id=?", (cid,)).fetchone()["abilities"]) == ["速攻", "洞察"]
    conn.close()


def test_update_character_unknown_id(tmp_project):
    conn = get_connection(tmp_project)
    with pytest.raises(ValueError):
        update_character(conn, 9999, personality="x")
    conn.close()
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/bedrock/test_edit_repos.py -q`
Expected: FAIL（update_character 未定义）。

- [ ] **Step 3: 实现（追加到 `src/bedrock/repositories/character.py`）**

```python
# 追加到 src/bedrock/repositories/character.py
import json
from src.bedrock.repositories._amendment import record_amendment

_PRONOUNS = {"他", "她", "它", "祂", "TA"}
_GENDERS = {None, "男", "女", "无", "未知", "其他"}
_ROLES = {"protagonist", "supporting", "antagonist", "minor"}
_STATES = {"active", "dormant", "deceased", "ascended", "merged"}
_TEXT_FIELDS = {"name", "personality", "goals"}
_JSON_FIELDS = {"abilities", "aliases"}


def update_character(conn, character_id, **fields):
    """白名单字段更新。枚举/UNIQUE/JSON 校验。UPDATE 前 raise。记 amendment。返回更新后 dict。"""
    if not fields:
        raise ValueError("无字段可更新")
    illegal = set(fields) - (_TEXT_FIELDS | _JSON_FIELDS | {"pronoun", "gender", "role", "state", "faction_id"})
    if illegal:
        raise ValueError(f"非法字段: {illegal}")
    row = conn.execute("SELECT * FROM character WHERE id=?", (character_id,)).fetchone()
    if row is None:
        raise ValueError(f"character {character_id} 不存在")
    # 校验
    if "pronoun" in fields and fields["pronoun"] not in _PRONOUNS:
        raise ValueError(f"非法 pronoun: {fields['pronoun']}")
    if "gender" in fields and fields["gender"] not in _GENDERS:
        raise ValueError(f"非法 gender: {fields['gender']}")
    if "role" in fields and fields["role"] not in _ROLES:
        raise ValueError(f"非法 role: {fields['role']}")
    if "state" in fields and fields["state"] not in _STATES:
        raise ValueError(f"非法 state: {fields['state']}")
    if "name" in fields:
        nm = (fields["name"] or "").strip()
        if not nm:
            raise ValueError("name 不能为空")
        dup = conn.execute("SELECT id FROM character WHERE name=? AND id!=?", (nm, character_id)).fetchone()
        if dup:
            raise ValueError(f"name 冲突: {nm}")
        fields["name"] = nm
    sets, params = [], []
    for k, v in fields.items():
        if k in _JSON_FIELDS:
            v = json.dumps(v, ensure_ascii=False)
        sets.append(f"{k}=?"); params.append(v)
    params.append(character_id)
    conn.execute(f"UPDATE character SET {', '.join(sets)} WHERE id=?", params)
    for k in fields:
        old_v = row[k]
        record_amendment(conn, "character", character_id, k, old_v, fields[k])
    conn.commit()
    return dict(conn.execute("SELECT * FROM character WHERE id=?", (character_id,)).fetchone())
```

- [ ] **Step 4: 运行确认通过**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/bedrock/test_edit_repos.py -q`
Expected: 5 passed。

- [ ] **Step 5: 提交**

```bash
git add src/bedrock/repositories/character.py tests/bedrock/test_edit_repos.py
git commit -m "feat(character): update_character (枚举/UNIQUE/JSON 校验 + amendment)"
```

---

## Task 4: update_chapter_meta / update_volume_meta / update_beat_meta（plot_tree.py）

**Files:**
- Modify: `src/bedrock/repositories/plot_tree.py`
- Test: `tests/bedrock/test_edit_repos.py`（追加）

- [ ] **Step 1: 写失败测试（追加到 `tests/bedrock/test_edit_repos.py`）**

```python
# 追加
import json as _json
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat,
    update_chapter_meta, update_volume_meta, update_beat_meta,
)


def test_update_chapter_meta_title(tmp_project):
    conn = get_connection(tmp_project)
    v = create_volume(conn, 1, "V", 1, 1, "opening")
    c = create_chapter(conn, volume_id=v, global_number=1, title="旧", status="completed")
    row = update_chapter_meta(conn, c, title="新标题")
    assert row["title"] == "新标题"
    assert conn.execute("SELECT COUNT(*) n FROM amendment WHERE entity_type='chapter' AND entity_id=?", (c,)).fetchone()["n"] == 1
    conn.close()


def test_update_chapter_meta_empty_rejected(tmp_project):
    conn = get_connection(tmp_project)
    v = create_volume(conn, 1, "V", 1, 1, "opening")
    c = create_chapter(conn, volume_id=v, global_number=1, title="x", status="completed")
    with pytest.raises(ValueError):
        update_chapter_meta(conn, c, title="  ")
    conn.close()


def test_update_volume_meta_theme_seeds(tmp_project):
    conn = get_connection(tmp_project)
    v = create_volume(conn, 1, "旧名", 1, 1, "opening")
    row = update_volume_meta(conn, v, name="新名", theme_seeds=["a", "b"])
    assert row["name"] == "新名"
    assert _json.loads(conn.execute("SELECT theme_seeds FROM volume WHERE id=?", (v,)).fetchone()["theme_seeds"]) == ["a", "b"]
    conn.close()


def test_update_volume_meta_bad_json(tmp_project):
    conn = get_connection(tmp_project)
    v = create_volume(conn, 1, "V", 1, 1, "opening")
    with pytest.raises(ValueError):
        update_volume_meta(conn, v, theme_seeds="不是列表")
    conn.close()


def test_update_beat_meta_purpose_too_short(tmp_project):
    conn = get_connection(tmp_project)
    v = create_volume(conn, 1, "V", 1, 1, "opening")
    c = create_chapter(conn, volume_id=v, global_number=1, title="x", status="completed")
    b = create_beat(conn, chapter_id=c, sequence=1, purpose="一个足够长的初始场景目的描述文字")
    with pytest.raises(ValueError):
        update_beat_meta(conn, b, purpose="短")
    conn.close()


def test_update_beat_meta_ok(tmp_project):
    conn = get_connection(tmp_project)
    v = create_volume(conn, 1, "V", 1, 1, "opening")
    c = create_chapter(conn, volume_id=v, global_number=1, title="x", status="completed")
    b = create_beat(conn, chapter_id=c, sequence=1, purpose="一个足够长的初始场景目的描述文字")
    row = update_beat_meta(conn, b, purpose="这是一个新的足够长的场景目的描述文字", scene_setting={"place": "城门"})
    assert row["purpose"] == "这是一个新的足够长的场景目的描述文字"
    conn.close()
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/bedrock/test_edit_repos.py -q -k "chapter_meta or volume_meta or beat_meta"`
Expected: FAIL。

- [ ] **Step 3: 实现（追加到 `src/bedrock/repositories/plot_tree.py`）**

```python
# 追加到 src/bedrock/repositories/plot_tree.py
import json
from src.bedrock.repositories._amendment import record_amendment


def update_chapter_meta(conn, chapter_id, title):
    title = (title or "").strip()
    if not title:
        raise ValueError("title 不能为空")
    row = conn.execute("SELECT title FROM chapter WHERE id=?", (chapter_id,)).fetchone()
    if row is None:
        raise ValueError(f"chapter {chapter_id} 不存在")
    conn.execute("UPDATE chapter SET title=? WHERE id=?", (title, chapter_id))
    record_amendment(conn, "chapter", chapter_id, "title", row["title"], title)
    conn.commit()
    return dict(conn.execute("SELECT * FROM chapter WHERE id=?", (chapter_id,)).fetchone())


def update_volume_meta(conn, volume_id, name=None, theme_seeds=None):
    sets, params = [], []
    row = conn.execute("SELECT name, theme_seeds FROM volume WHERE id=?", (volume_id,)).fetchone()
    if row is None:
        raise ValueError(f"volume {volume_id} 不存在")
    if name is not None:
        nm = name.strip()
        if not nm:
            raise ValueError("name 不能为空")
        sets.append("name=?"); params.append(nm)
    if theme_seeds is not None:
        if not isinstance(theme_seeds, list):
            raise ValueError("theme_seeds 须为列表")
        sets.append("theme_seeds=?"); params.append(json.dumps(theme_seeds, ensure_ascii=False))
    if not sets:
        raise ValueError("无字段可更新")
    params.append(volume_id)
    conn.execute(f"UPDATE volume SET {', '.join(sets)} WHERE id=?", params)
    if name is not None:
        record_amendment(conn, "volume", volume_id, "name", row["name"], name)
    if theme_seeds is not None:
        record_amendment(conn, "volume", volume_id, "theme_seeds", row["theme_seeds"], theme_seeds)
    conn.commit()
    return dict(conn.execute("SELECT * FROM volume WHERE id=?", (volume_id,)).fetchone())


def update_beat_meta(conn, beat_id, purpose=None, scene_setting=None):
    sets, params = [], []
    row = conn.execute("SELECT purpose, scene_setting FROM beat WHERE id=?", (beat_id,)).fetchone()
    if row is None:
        raise ValueError(f"beat {beat_id} 不存在")
    if purpose is not None:
        if len(purpose) < 10:
            raise ValueError("purpose 至少 10 字")
        sets.append("purpose=?"); params.append(purpose)
    if scene_setting is not None:
        if not isinstance(scene_setting, dict):
            raise ValueError("scene_setting 须为 dict")
        sets.append("scene_setting=?"); params.append(json.dumps(scene_setting, ensure_ascii=False))
    if not sets:
        raise ValueError("无字段可更新")
    params.append(beat_id)
    conn.execute(f"UPDATE beat SET {', '.join(sets)} WHERE id=?", params)
    if purpose is not None:
        record_amendment(conn, "beat", beat_id, "purpose", row["purpose"], purpose)
    if scene_setting is not None:
        record_amendment(conn, "beat", beat_id, "scene_setting", row["scene_setting"], scene_setting)
    conn.commit()
    return dict(conn.execute("SELECT * FROM beat WHERE id=?", (beat_id,)).fetchone())
```

- [ ] **Step 4: 运行确认通过**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/bedrock/test_edit_repos.py -q`
Expected: 全部通过（Task3 + Task4）。

- [ ] **Step 5: 提交**

```bash
git add src/bedrock/repositories/plot_tree.py tests/bedrock/test_edit_repos.py
git commit -m "feat(plot_tree): update_chapter_meta/update_volume_meta/update_beat_meta"
```

---

## Task 5: update_location/theme/motif（worldbook.py）+ update_master_outline（outline.py）

**Files:**
- Modify: `src/bedrock/repositories/worldbook.py`
- Modify: `src/bedrock/repositories/outline.py`
- Test: `tests/bedrock/test_edit_repos.py`（追加）

- [ ] **Step 1: 写失败测试（追加到 `tests/bedrock/test_edit_repos.py`）**

```python
# 追加
from src.bedrock.repositories.worldbook import (
    add_location, add_theme, add_motif,
    update_location, update_theme, update_motif,
)
from src.bedrock.repositories.outline import update_master_outline


def test_update_location(tmp_project):
    conn = get_connection(tmp_project)
    lid = add_location(conn, name="城", loc_type="city", description="旧")
    row = update_location(conn, lid, description="新城", state="废弃")
    assert row["description"] == "新城" and row["state"] == "废弃"
    conn.close()


def test_update_theme_by_name(tmp_project):
    # theme 表无 id 列（name 是 PK）—— 按 name 键
    conn = get_connection(tmp_project)
    add_theme(conn, name="边界", description="旧", evolution="初")
    row = update_theme(conn, name="边界", description="新", evolution="进")
    assert row["evolution"] == "进" and row["description"] == "新"
    conn.close()


def test_update_motif_by_name(tmp_project):
    # motif 表无 id 列（name 是 PK）—— 按 name 键
    conn = get_connection(tmp_project)
    add_motif(conn, name="电流", meaning="旧")
    row = update_motif(conn, name="电流", meaning="新意", evolution="深")
    assert row["meaning"] == "新意"
    conn.close()


def test_update_master_outline(tmp_project):
    conn = get_connection(tmp_project)
    row = update_master_outline(conn, theme_evolution="从对抗到共生", key_arcs=["韩峥线", "林深线"])
    assert row["theme_evolution"] == "从对抗到共生"
    import json as _j
    assert _j.loads(conn.execute("SELECT key_arcs FROM master_outline WHERE id=1").fetchone()["key_arcs"]) == ["韩峥线", "林深线"]
    conn.close()


def test_update_master_outline_bad_json(tmp_project):
    conn = get_connection(tmp_project)
    with pytest.raises(ValueError):
        update_master_outline(conn, key_milestones="不是列表")
    conn.close()


def test_update_worldbook_unknown(tmp_project):
    conn = get_connection(tmp_project)
    with pytest.raises(ValueError):
        update_location(conn, 9999, description="x")
    with pytest.raises(ValueError):
        update_theme(conn, name="不存在", description="x")
    conn.close()
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/bedrock/test_edit_repos.py -q -k "location or theme or motif or master"`
Expected: FAIL。

- [ ] **Step 3: 实现 worldbook（追加到 `src/bedrock/repositories/worldbook.py`）**

```python
# 追加到 src/bedrock/repositories/worldbook.py
from src.bedrock.repositories._amendment import record_amendment


def _update_by_col(conn, table, entity_type, key_col, key_val, allowed, **fields):
    """通用 update：按 key_col(如 id/name) 定位行。非法字段/未知行/空字段 → raise。记 amendment。"""
    illegal = set(fields) - allowed
    if illegal:
        raise ValueError(f"非法字段: {illegal}")
    row = conn.execute(f"SELECT * FROM {table} WHERE {key_col}=?", (key_val,)).fetchone()
    if row is None:
        raise ValueError(f"{entity_type} {key_val} 不存在")
    if not fields:
        raise ValueError("无字段可更新")
    sets, params = [], []
    for k, v in fields.items():
        sets.append(f"{k}=?"); params.append(v if v is not None else "")
    params.append(key_val)
    conn.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE {key_col}=?", params)
    for k in fields:
        record_amendment(conn, entity_type, key_val, k, row[k], fields[k])
    conn.commit()
    return dict(conn.execute(f"SELECT * FROM {table} WHERE {key_col}=?", (key_val,)).fetchone())


def update_location(conn, location_id, description=None, state=None, loc_type=None):
    # location 表有 id 列
    fields = {}
    if description is not None: fields["description"] = description
    if state is not None: fields["state"] = state
    if loc_type is not None: fields["loc_type"] = loc_type
    return _update_by_col(conn, "location", "location", "id", location_id,
                          {"description", "state", "loc_type"}, **fields)


def update_theme(conn, name, description=None, evolution=None):
    # theme 表无 id 列（name 是 PK）—— 按 name 键
    fields = {}
    if description is not None: fields["description"] = description
    if evolution is not None: fields["evolution"] = evolution
    return _update_by_col(conn, "theme", "theme", "name", name,
                          {"description", "evolution"}, **fields)


def update_motif(conn, name, meaning=None, evolution=None):
    # motif 表无 id 列（name 是 PK）—— 按 name 键
    fields = {}
    if meaning is not None: fields["meaning"] = meaning
    if evolution is not None: fields["evolution"] = evolution
    return _update_by_col(conn, "motif", "motif", "name", name,
                          {"meaning", "evolution"}, **fields)
```

- [ ] **Step 4: 实现 master_outline（追加到 `src/bedrock/repositories/outline.py`）**

```python
# 追加到 src/bedrock/repositories/outline.py
def update_master_outline(conn, theme_evolution=None, key_arcs=None, key_milestones=None, rhythm_curve=None):
    """更新 master_outline(id=1)。JSON 字段须为 list。记 amendment。返回更新后 dict。"""
    sets, params = [], []
    row = conn.execute("SELECT * FROM master_outline WHERE id=1").fetchone()
    if row is None:
        raise ValueError("master_outline 不存在")
    spec = {"theme_evolution": (theme_evolution, False), "rhythm_curve": (rhythm_curve, False),
            "key_arcs": (key_arcs, True), "key_milestones": (key_milestones, True)}
    for k, (v, is_list) in spec.items():
        if v is None:
            continue
        if is_list and not isinstance(v, list):
            raise ValueError(f"{k} 须为列表")
        sets.append(f"{k}=?"); params.append(json.dumps(v, ensure_ascii=False) if is_list else v)
    if not sets:
        raise ValueError("无字段可更新")
    params.append(1)
    conn.execute(f"UPDATE master_outline SET {', '.join(sets)} WHERE id=1", params)
    for k, (v, is_list) in spec.items():
        if v is not None:
            record_amendment(conn, "master_outline", 1, k, row[k], v)
    conn.commit()
    return dict(conn.execute("SELECT * FROM master_outline WHERE id=1").fetchone())
```

- [ ] **Step 5: 运行确认通过**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/bedrock/test_edit_repos.py -q`
Expected: 全部通过。

- [ ] **Step 6: 提交**

```bash
git add src/bedrock/repositories/worldbook.py src/bedrock/repositories/outline.py tests/bedrock/test_edit_repos.py
git commit -m "feat(worldbook,outline): update_location/theme/motif + update_master_outline"
```

---

## Task 6: api.py 蓝图 — read 端点

**Files:**
- Create: `src/bedrock/web/api.py`
- Test: `tests/bedrock/test_api.py`（新）

- [ ] **Step 1: 写失败测试 `tests/bedrock/test_api.py`**

```python
# tests/bedrock/test_api.py
import pytest
from pathlib import Path
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat, create_paragraph
from src.bedrock.repositories.character import create_character
from src.bedrock.repositories.worldbook import add_constant, add_location, add_theme, add_motif
from src.bedrock.repositories.outline import add_inspiration, advance_inspiration
from src.bedrock.web.app import create_app


def _seed(tmp_project):
    conn = get_connection(tmp_project)
    add_constant(conn, key="work_name", value="测试书")
    v = create_volume(conn, 1, "第一卷", 1, 2, "opening")
    c1 = create_chapter(conn, volume_id=v, global_number=1, title="甲", status="completed")
    hz = create_character(conn, name="韩峥", pronoun="他", role="protagonist")
    b = create_beat(conn, chapter_id=c1, sequence=1, purpose="一个足够长的场景目的描述文字", pov_character_id=hz)
    create_paragraph(conn, chapter_id=c1, seq=1, text="正文段落一。", content_hash="h1", beat_id=b, role="narration")
    add_location(conn, name="城", description="d"); add_theme(conn, name="边界"); add_motif(conn, name="电")
    add_inspiration(conn, content="灵一", type="scene")
    conn.commit(); conn.close()


def _client(tmp_project, monkeypatch):
    # tmp_project 是 projects root 的一个子目录；建 root
    root = tmp_project.parent
    app = create_app(str(root))
    app.config["TESTING"] = True
    return app.test_client()


def test_api_works_lists(tmp_path):
    root = tmp_path / "root"; root.mkdir()
    sub = root / "demo"; 
    from src.bedrock.init_project import init_project
    init_project(sub, work_name="Demo", force=True)
    conn = get_connection(sub); add_constant(conn, "work_name", "Demo")
    create_volume(conn, 1, "V", 1, 1, "opening"); conn.commit(); conn.close()
    app = create_app(str(root)); c = app.test_client()
    resp = c.get("/api/works")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data[0]["id"] == "demo" and data[0]["name"] == "Demo"


def test_api_overview(tmp_project):
    _seed(tmp_project); root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    resp = c.get(f"/api/works/{tmp_project.name}/overview")
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["name"] == "测试书" and d["volumes"] == 1


def test_api_matrix(tmp_project):
    _seed(tmp_project); root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    resp = c.get(f"/api/works/{tmp_project.name}/matrix?volume=1")
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["characters"][0]["name"] == "韩峥"
    assert isinstance(d["chapters"][0]["povs"], list)  # set→list


def test_api_inspirations_consumed_into_parsed(tmp_project):
    from src.bedrock.repositories.outline import consume_inspiration
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    hz = create_character(conn, name="韩", pronoun="他", role="protagonist")
    consume_inspiration(conn, iid, target_type="character", target_id=hz)
    conn.commit(); conn.close()
    root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    resp = c.get(f"/api/works/{tmp_project.name}/inspirations")
    item = resp.get_json()[0]
    assert isinstance(item["consumed_into"], list)  # 解析为 list 非 JSON 字符串


def test_api_chapters(tmp_project):
    _seed(tmp_project); root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    resp = c.get(f"/api/works/{tmp_project.name}/chapters")
    assert resp.get_json()[0]["title"] == "甲"


def test_api_chapter_text(tmp_project):
    _seed(tmp_project); root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    resp = c.get(f"/api/works/{tmp_project.name}/chapters/1/text")
    assert resp.get_json()["paragraphs"][0]["text"] == "正文段落一。"


def test_api_chapter_text_missing(tmp_project):
    _seed(tmp_project); root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    resp = c.get(f"/api/works/{tmp_project.name}/chapters/999/text")
    assert resp.status_code == 404


def test_api_outline(tmp_project):
    _seed(tmp_project); root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    resp = c.get(f"/api/works/{tmp_project.name}/outline")
    d = resp.get_json()
    assert len(d["volumes"]) == 1
    assert d["volumes"][0]["chapters"][0]["beats"][0]["pov_name"] == "韩峥"


def test_api_characters(tmp_project):
    _seed(tmp_project); root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    resp = c.get(f"/api/works/{tmp_project.name}/characters")
    assert resp.get_json()[0]["name"] == "韩峥"


def test_api_worldbook(tmp_project):
    _seed(tmp_project); root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    d = app.test_client().get(f"/api/works/{tmp_project.name}/overview").get_json()
    assert len(d["worldbook"]["locations"]) == 1


def test_api_reports_scan(tmp_project):
    (tmp_project / "review_report_vol1.md").write_text("# x\n- ch1: escalate_human\n", encoding="utf-8")
    _seed(tmp_project); root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    resp = c.get(f"/api/works/{tmp_project.name}/reports")
    assert any(r["volume_id"] == 1 and r["exists"] for r in resp.get_json())


def test_api_report_renders_markdown(tmp_project):
    (tmp_project / "review_report_vol1.md").write_text("# 报告\n## 修正结果\n- ch1: escalate_human\n", encoding="utf-8")
    _seed(tmp_project); root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    resp = c.get(f"/api/works/{tmp_project.name}/report/1")
    d = resp.get_json()
    assert "<h1>" in d["html_body"] and 1 in d["escalate_chs"] and d["has_escalate"]


def test_api_report_v2_tolerant(tmp_project):
    (tmp_project / "review_report_vol1.md").write_text("# 手写报告\n无 SP5 格式。\n", encoding="utf-8")
    _seed(tmp_project); root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    d = c.get(f"/api/works/{tmp_project.name}/report/1").get_json()
    assert d["escalate_chs"] == [] and d["has_escalate"] is False


def test_api_report_missing_404(tmp_project):
    _seed(tmp_project); root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    assert c.get(f"/api/works/{tmp_project.name}/report/99").status_code == 404


def test_api_path_traversal_rejected(tmp_project):
    _seed(tmp_project); root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    for bad in ["..", "a/b", "C:x", "."]:
        assert c.get(f"/api/works/{bad}/overview").status_code == 404, bad


def test_create_app_requires_projects_root(tmp_path):
    with pytest.raises(SystemExit):
        create_app(str(tmp_path / "nope"))  # 不存在的目录
```

> `tmp_project` fixture 须建在某个 root 下（如 `tmp_path/root/<name>`）。**实现第一步核对 `tmp_project` fixture 位置**：若既有 fixture 直接用 tmp_path，调整测试建 root 逻辑（建 `tmp_path/root/`，把项目放 `tmp_path/root/<name>`，`tmp_project = tmp_path/root/<name>`）。见 Task 6 Step 3 注。

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/bedrock/test_api.py -q`
Expected: FAIL（create_app 签名/api 未就绪）。

- [ ] **Step 3: 实现 `src/bedrock/web/api.py`**

```python
# src/bedrock/web/api.py
"""SP6-C SPA 的 /api 蓝图。全部 JSON，按 work_id 作用域。路径穿越校验 + 每请求 conn。"""
import json
import re
from pathlib import Path
from flask import Blueprint, jsonify, request, current_app, abort

from src.bedrock.db.connection import get_connection
from src.bedrock.web.queries import (
    list_works, overview_stats, chapter_text, outline_tree, pov_matrix,
    list_characters, worldbook_overview, list_factions,
)
from src.bedrock.repositories.outline import list_inspirations
from src.bedrock.repositories.worldbook import get_constant

bp = Blueprint("api", __name__, url_prefix="/api")

_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _resolve_work(work_id):
    """work_id → (project_dir Path)。路径穿越/无 db → raise 404。"""
    root = Path(current_app.config["PROJECTS_ROOT"]).resolve()
    if "/" in work_id or "\\" in work_id or work_id in (".", "..") or _DRIVE_RE.match(work_id):
        abort(404)
    target = (root / work_id).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        abort(404)
    if not (target / "bedrock.db").exists():
        abort(404)
    return target


def _conn(work_dir):
    return get_connection(work_dir)


def _parse_consumed_into(item):
    raw = item.get("consumed_into")
    try:
        item["consumed_into"] = json.loads(raw) if raw else []
    except Exception:
        item["consumed_into"] = []
    return item


@bp.get("/works")
def api_works():
    root = Path(current_app.config["PROJECTS_ROOT"]).resolve()
    return jsonify(list_works(root))


@bp.get("/works/<work_id>/overview")
def api_overview(work_id):
    wd = _resolve_work(work_id)
    conn = _conn(wd)
    try:
        return jsonify(overview_stats(conn))
    finally:
        conn.close()


@bp.get("/works/<work_id>/matrix")
def api_matrix(work_id):
    wd = _resolve_work(work_id)
    vid = request.args.get("volume", type=int)
    conn = _conn(wd)
    try:
        data = pov_matrix(conn, vid) if vid else None
        if data:
            for ch in data["chapters"]:
                ch["povs"] = sorted(ch["povs"])  # set → list
        return jsonify(data)
    finally:
        conn.close()


@bp.get("/works/<work_id>/inspirations")
def api_inspirations(work_id):
    wd = _resolve_work(work_id)
    tf = request.args.get("type") or None
    sf = request.args.get("status") or None
    conn = _conn(wd)
    try:
        items = [_parse_consumed_into(dict(i)) for i in list_inspirations(conn, tf, sf)]
        return jsonify(items)
    finally:
        conn.close()


@bp.get("/works/<work_id>/reports")
def api_reports(work_id):
    wd = _resolve_work(work_id)
    out = []
    for p in sorted(wd.glob("review_report_vol*.md")):
        m = re.search(r"vol(\d+)", p.name)
        if m:
            out.append({"volume_id": int(m.group(1)), "exists": True})
    return jsonify(out)


@bp.get("/works/<work_id>/report/<int:vid>")
def api_report(work_id, vid):
    from src.bedrock.cli.reader_commands import parse_review_outcomes
    import markdown
    wd = _resolve_work(work_id)
    rp = wd / f"review_report_vol{vid}.md"
    if not rp.exists():
        abort(404)
    text = rp.read_text(encoding="utf-8")
    html = markdown.markdown(text, extensions=["extra", "sane_lists"])
    outcomes = parse_review_outcomes(text)
    escalate = {ch for ch, st in outcomes.items() if st == "escalate_human"}
    if escalate:
        ch_alt = "|".join(str(c) for c in sorted(escalate))
        html = re.sub(r"(<li>)(ch(?:%s):\s*escalate_human)" % ch_alt,
                      r'<li class="escalate-highlight">\2', html)
    return jsonify({"html_body": html, "escalate_chs": sorted(escalate), "has_escalate": bool(escalate)})


@bp.get("/works/<work_id>/chapters")
def api_chapters(work_id):
    wd = _resolve_work(work_id)
    conn = _conn(wd)
    try:
        rows = conn.execute(
            "SELECT c.global_number, c.title, c.status, v.id vid, v.name vname "
            "FROM chapter c JOIN volume v ON c.volume_id=v.id ORDER BY c.global_number").fetchall()
        return jsonify([{"global_number": r["global_number"], "title": r["title"],
                         "status": r["status"], "volume_id": r["vid"], "volume_name": r["vname"]}
                        for r in rows])
    finally:
        conn.close()


@bp.get("/works/<work_id>/chapters/<int:gnum>/text")
def api_chapter_text(work_id, gnum):
    wd = _resolve_work(work_id)
    conn = _conn(wd)
    try:
        t = chapter_text(conn, gnum)
        if t is None:
            abort(404)
        return jsonify(t)
    finally:
        conn.close()


@bp.get("/works/<work_id>/outline")
def api_outline(work_id):
    wd = _resolve_work(work_id)
    vid = request.args.get("volume", type=int)
    conn = _conn(wd)
    try:
        return jsonify(outline_tree(conn, vid))
    finally:
        conn.close()


@bp.get("/works/<work_id>/characters")
def api_characters(work_id):
    wd = _resolve_work(work_id)
    conn = _conn(wd)
    try:
        return jsonify(list_characters(conn))
    finally:
        conn.close()


@bp.get("/works/<work_id>/factions")
def api_factions(work_id):
    wd = _resolve_work(work_id)
    conn = _conn(wd)
    try:
        return jsonify(list_factions(conn))
    finally:
        conn.close()
```

> **fixture 适配**：`tmp_project` 既有 fixture（test_web_queries.py 用）指向一个项目目录。为支持多作品 root，在 conftest 让 `tmp_project = tmp_path/"root"/"work0"`（root=父目录）。**若既有 fixture 无法改**，则测试里手动 `root = tmp_path; sub = tmp_path/"w"; init_project(sub...)`，create_app(str(root))。以测试能跑通为准——本 Task 各测试已用 `root = tmp_project.parent` 假设 tmp_project 在 root 下。**实现者第一步：读 `tests/bedrock/conftest.py` 确认 tmp_project 路径，必要时把测试统一改为自建 root（不依赖 fixture 形态）。**

- [ ] **Step 4: 运行确认部分通过（read 端点）**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/bedrock/test_api.py -q -k "works or overview or matrix or inspirations_consumed or chapters or chapter_text or outline or characters or worldbook or reports_scan or report or path_traversal or requires_projects"`
Expected: read 端点通过（write 端点测试尚未加，advance/edit 测试会失败——预期）。

> 注：此时 `create_app(projects_root)` 尚未改（仍是旧 project_dir 签名）。Task 7 改 app.py。所以本 Step 可能因 create_app 签名失败——**把 Task 7 的 app.py 改造提到本 Task Step 3.5 先做**（见下）。

- [ ] **Step 3.5: 改造 `src/bedrock/web/app.py`（create_app + 挂 api 蓝图 + SPA 托管）**

```python
# src/bedrock/web/app.py（整文件重写）
"""SP6-C SPA 工作台。create_app(projects_root)：挂 /api 蓝图 + 托管编译后 SPA 静态。
每请求开/关 conn（api 层负责）。"""
from pathlib import Path
from flask import Flask, send_from_directory

from src.bedrock.web.api import bp as api_bp


def create_app(projects_root):
    root = Path(projects_root).resolve()
    if not root.is_dir():
        raise SystemExit(f"projects_root 不是目录: {projects_root}")
    app = Flask(__name__, static_folder=None)
    app.config["PROJECTS_ROOT"] = str(root)
    app.register_blueprint(api_bp)

    static_dir = Path(__file__).parent / "static"

    @app.get("/")
    def index():
        idx = static_dir / "index.html"
        if idx.exists():
            return send_from_directory(static_dir, "index.html")
        return ("SPA 未构建。运行 `cd frontend && npm install && npm run build` 后重试。", 503)

    @app.get("/<path:filepath>")
    def spa_assets(filepath):
        # 静态资源（vite 输出 assets/...）直接伺服；其余回退 index.html（SPA 路由）
        full = static_dir / filepath
        if full.is_file():
            return send_from_directory(static_dir, filepath)
        idx = static_dir / "index.html"
        if idx.exists():
            return send_from_directory(static_dir, "index.html")
        abort_val = 404
        return ("SPA 未构建。", 503)

    return app
```

> 顶部需 `from flask import abort`（spa_assets 回退用，或直接返回 503 如上）。`/<path:filepath>` 会吞所有非 /api GET——但 /api 蓝图优先注册（url_prefix /api），Flask 蓝图路由优先级高于 app 路由？**需验证**：Flask 中蓝图注册的路由与 app 路由冲突时，按注册顺序匹配，蓝图先注册则 /api/* 优先命中。若冲突，把 spa_assets 改为排除 /api：在函数内 `if filepath.startswith("api"): abort(404)`。实现者验证后定。

- [ ] **Step 5: 运行 read 端点测试通过**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/bedrock/test_api.py -q -k "not advance and not edit"`
Expected: 全部 read + path_traversal + requires_projects 通过。

- [ ] **Step 6: 提交**

```bash
git add src/bedrock/web/api.py src/bedrock/web/app.py tests/bedrock/test_api.py
git commit -m "feat(web): /api 蓝图 read 端点 + create_app(projects_root) + SPA 托管"
```

---

## Task 7: api.py write 端点（advance / edit）+ CSRF + 删 test_web.py

**Files:**
- Modify: `src/bedrock/web/api.py`
- Test: `tests/bedrock/test_api.py`（追加）
- Delete: `tests/bedrock/test_web.py`、`src/bedrock/web/templates/`、`src/bedrock/web/static/app.css`

- [ ] **Step 1: 写失败测试（追加到 `tests/bedrock/test_api.py`）**

```python
# 追加
from src.bedrock.repositories.outline import advance_inspiration


def _json_headers():
    return {"Content-Type": "application/json"}


def test_api_advance_ok(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene"); conn.commit(); conn.close()
    root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    resp = c.post(f"/api/works/{tmp_project.name}/inspirations/{iid}/advance",
                  data=json.dumps({"target": "refined"}), headers=_json_headers())
    assert resp.status_code == 200
    d = resp.get_json(); assert d["ok"] and d["item"]["status"] == "refined"


def test_api_advance_illegal(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    advance_inspiration(conn, iid, "discarded"); conn.commit(); conn.close()
    root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    resp = c.post(f"/api/works/{tmp_project.name}/inspirations/{iid}/advance",
                  data=json.dumps({"target": "refined"}), headers=_json_headers())
    d = resp.get_json(); assert d["ok"] is False
    conn = get_connection(tmp_project)
    assert conn.execute("SELECT status FROM inspiration WHERE id=?", (iid,)).fetchone()["status"] == "discarded"
    conn.close()


def test_api_advance_requires_json_content_type(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene"); conn.commit(); conn.close()
    root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    resp = c.post(f"/api/works/{tmp_project.name}/inspirations/{iid}/advance",
                  data="target=refined")  # form, 无 JSON content-type
    assert resp.status_code == 415


def test_api_edit_content_ok(tmp_project):
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene"); conn.commit(); conn.close()
    root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    resp = c.patch(f"/api/works/{tmp_project.name}/inspirations/{iid}",
                   data=json.dumps({"content": "新内容"}), headers=_json_headers())
    d = resp.get_json(); assert d["ok"] and d["item"]["content"] == "新内容"


def test_api_edit_content_frozen(tmp_project):
    from src.bedrock.repositories.outline import consume_inspiration
    conn = get_connection(tmp_project)
    iid = add_inspiration(conn, content="x", type="scene")
    hz = create_character(conn, name="韩", pronoun="他", role="protagonist")
    consume_inspiration(conn, iid, "character", hz); conn.commit(); conn.close()
    root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    resp = c.patch(f"/api/works/{tmp_project.name}/inspirations/{iid}",
                   data=json.dumps({"content": "改"}), headers=_json_headers())
    assert resp.get_json()["ok"] is False


def test_api_edit_character(tmp_project):
    _seed(tmp_project); root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    cid = get_connection(tmp_project).execute("SELECT id FROM character WHERE name='韩峥'").fetchone()["id"]
    resp = c.patch(f"/api/works/{tmp_project.name}/characters/{cid}",
                   data=json.dumps({"personality": "新性格"}), headers=_json_headers())
    assert resp.get_json()["ok"]


def test_api_edit_character_name_conflict(tmp_project):
    _seed(tmp_project); root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    conn = get_connection(tmp_project)
    cid = conn.execute("SELECT id FROM character WHERE name='韩峥'").fetchone()["id"]; conn.close()
    resp = c.patch(f"/api/works/{tmp_project.name}/characters/{cid}",
                   data=json.dumps({"name": "韩峥"}), headers=_json_headers())  # 同名自身 OK
    # 改成已存在他人名 → 冲突（需第二个角色）
    conn = get_connection(tmp_project)
    create_character(conn, name="林深", pronoun="她", role="supporting"); conn.commit(); conn.close()
    resp = c.patch(f"/api/works/{tmp_project.name}/characters/{cid}",
                   data=json.dumps({"name": "林深"}), headers=_json_headers())
    assert resp.get_json()["ok"] is False


def test_api_edit_chapter_title(tmp_project):
    _seed(tmp_project); root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    cid = get_connection(tmp_project).execute("SELECT id FROM chapter WHERE global_number=1").fetchone()["id"]
    resp = c.patch(f"/api/works/{tmp_project.name}/chapters/{cid}",
                   data=json.dumps({"title": "新甲"}), headers=_json_headers())
    assert resp.get_json()["ok"]


def test_api_edit_beat_contract_locked(tmp_project):
    _seed(tmp_project); root = tmp_project.parent
    conn = get_connection(tmp_project)
    bid = conn.execute("SELECT id FROM beat").fetchone()["id"]
    conn.execute("INSERT OR IGNORE INTO volume_outline(volume_id,status,beat_contracts) VALUES(1,'locked','[]')")
    conn.commit(); conn.close()
    app = create_app(str(root)); c = app.test_client()
    resp = c.patch(f"/api/works/{tmp_project.name}/volumes/1/beats/{bid}/contract",
                   data=json.dumps({"purpose": "新契约"}), headers=_json_headers())
    assert resp.get_json()["ok"] is False  # locked


def test_api_edit_beat_meta_purpose_short(tmp_project):
    _seed(tmp_project); root = tmp_project.parent
    conn = get_connection(tmp_project)
    bid = conn.execute("SELECT id FROM beat").fetchone()["id"]; conn.close()
    app = create_app(str(root)); c = app.test_client()
    resp = c.patch(f"/api/works/{tmp_project.name}/beats/{bid}",
                   data=json.dumps({"purpose": "短"}), headers=_json_headers())
    assert resp.get_json()["ok"] is False


def test_api_edit_master_outline(tmp_project):
    _seed(tmp_project); root = tmp_project.parent
    app = create_app(str(root)); c = app.test_client()
    resp = c.patch(f"/api/works/{tmp_project.name}/master_outline",
                   data=json.dumps({"theme_evolution": "演进"}), headers=_json_headers())
    assert resp.get_json()["ok"]
```

> 顶部需 `import json`（test_api.py 顶部加）。

- [ ] **Step 2: 运行确认失败**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/bedrock/test_api.py -q -k "advance or edit"`
Expected: FAIL（write 端点未实现）。

- [ ] **Step 3: 实现 write 端点（追加到 `src/bedrock/web/api.py`）**

```python
# 追加到 src/bedrock/web/api.py
from src.bedrock.repositories.outline import (
    advance_inspiration, update_inspiration_content, update_master_outline,
)
from src.bedrock.repositories.character import update_character
from src.bedrock.repositories.plot_tree import (
    update_chapter_meta, update_volume_meta, update_beat_meta, update_beat_status,
)
from src.bedrock.repositories.outline import update_beat_contract, OutlineLockedError
from src.bedrock.repositories.worldbook import (
    update_location, update_theme, update_motif,
)


def _require_json():
    if not request.is_json:
        abort(415)


def _ok(item):
    return jsonify({"ok": True, "item": item})


def _err(msg):
    return jsonify({"ok": False, "error": str(msg)})


def _run(mutator):
    """跑一个写函数；ValueError/OutlineLockedError → {ok:false}；成功 → {ok,item}。"""
    try:
        item = mutator()
        return _ok(item)
    except (ValueError, OutlineLockedError) as e:
        return _err(e)


@bp.post("/works/<work_id>/inspirations/<int:iid>/advance")
def api_advance(work_id, iid):
    _require_json()
    wd = _resolve_work(work_id)
    target = (request.get_json(silent=True) or {}).get("target")
    conn = _conn(wd)
    try:
        return _run(lambda: advance_inspiration(conn, iid, target))
    finally:
        conn.close()


@bp.patch("/works/<work_id>/inspirations/<int:iid>")
def api_edit_inspiration(work_id, iid):
    _require_json()
    wd = _resolve_work(work_id)
    body = request.get_json(silent=True) or {}
    conn = _conn(wd)
    try:
        return _run(lambda: update_inspiration_content(
            conn, iid, body.get("content"), source=body.get("source")))
    finally:
        conn.close()


def _patch_entity(work_id, eid, fn, **body):
    _require_json()
    wd = _resolve_work(work_id)
    conn = _conn(wd)
    try:
        return _run(lambda: fn(conn, eid, **body))
    finally:
        conn.close()


@bp.patch("/works/<work_id>/characters/<int:eid>")
def api_edit_character(work_id, eid):
    body = request.get_json(silent=True) or {}
    return _patch_entity(work_id, eid, update_character, **body)


@bp.patch("/works/<work_id>/chapters/<int:eid>")
def api_edit_chapter(work_id, eid):
    body = request.get_json(silent=True) or {}
    return _patch_entity(work_id, eid, update_chapter_meta, **body)


@bp.patch("/works/<work_id>/volumes/<int:eid>")
def api_edit_volume(work_id, eid):
    body = request.get_json(silent=True) or {}
    return _patch_entity(work_id, eid, update_volume_meta, **body)


@bp.patch("/works/<work_id>/locations/<int:eid>")
def api_edit_location(work_id, eid):
    body = request.get_json(silent=True) or {}
    return _patch_entity(work_id, eid, update_location, **body)


@bp.patch("/works/<work_id>/themes/<name>")
def api_edit_theme(work_id, name):
    # theme 表无 id，按 name(PK) 键
    _require_json()
    wd = _resolve_work(work_id)
    body = request.get_json(silent=True) or {}
    conn = _conn(wd)
    try:
        return _run(lambda: update_theme(conn, name, **body))
    finally:
        conn.close()


@bp.patch("/works/<work_id>/motifs/<name>")
def api_edit_motif(work_id, name):
    # motif 表无 id，按 name(PK) 键
    _require_json()
    wd = _resolve_work(work_id)
    body = request.get_json(silent=True) or {}
    conn = _conn(wd)
    try:
        return _run(lambda: update_motif(conn, name, **body))
    finally:
        conn.close()


@bp.patch("/works/<work_id>/beats/<int:eid>")
def api_edit_beat(work_id, eid):
    _require_json()
    wd = _resolve_work(work_id)
    body = request.get_json(silent=True) or {}
    conn = _conn(wd)
    try:
        def go():
            if "status" in body or "deviation_note" in body:
                update_beat_status(conn, eid, body.get("status"),
                                   body.get("deviation_note"))
            meta = {k: body[k] for k in ("purpose", "scene_setting") if k in body}
            if meta:
                update_beat_meta(conn, eid, **meta)
            return dict(conn.execute("SELECT * FROM beat WHERE id=?", (eid,)).fetchone())
        return _run(go)
    finally:
        conn.close()


@bp.patch("/works/<work_id>/volumes/<int:vid>/beats/<int:bid>/contract")
def api_edit_beat_contract(work_id, vid, bid):
    _require_json()
    wd = _resolve_work(work_id)
    body = request.get_json(silent=True) or {}
    conn = _conn(wd)
    try:
        def go():
            update_beat_contract(conn, vid, bid, body)
            return {"volume_id": vid, "beat_id": bid}
        return _run(go)
    finally:
        conn.close()


@bp.patch("/works/<work_id>/master_outline")
def api_edit_master_outline(work_id):
    _require_json()
    wd = _resolve_work(work_id)
    body = request.get_json(silent=True) or {}
    conn = _conn(wd)
    try:
        return _run(lambda: update_master_outline(conn, **body))
    finally:
        conn.close()
```

> `OutlineLockedError` 须从 outline.py 导入——**核对其在 outline.py 的定义名**（spec 见 update_beat_contract 抛 OutlineLockedError）。`update_beat_status`/`update_beat_contract` 已在 outline.py / plot_tree.py。

- [ ] **Step 4: 删除旧视图层**

```bash
git rm -r src/bedrock/web/templates
git rm src/bedrock/web/static/app.css
git rm tests/bedrock/test_web.py
mkdir -p src/bedrock/web/static
echo "# vite build output (gitignored)" > src/bedrock/web/static/.gitkeep
```

> `app.py` 已在 Task 6 Step 3.5 重写（无 Jinja import）。确认 `src/bedrock/web/__init__.py` 无遗留 import 模板。

- [ ] **Step 5: 运行全部 API + 回归**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/bedrock/ -q`
Expected: 全通过（test_queries + test_edit_repos + test_api + test_outline + test_web_queries + 既有 218 中不受影响的；test_web 已删）。

- [ ] **Step 6: 提交**

```bash
git add -A
git commit -m "feat(web): /api write 端点 (advance/edit 全实体) + 删 Jinja/htmx/test_web"
```

---

## Task 8: .gitignore + launch.json + seed 扩展（Phase 1 收尾）

**Files:**
- Modify: `.gitignore`
- Modify: `.claude/launch.json`
- Modify: `scripts/seed_bedrock_demo.py`

- [ ] **Step 1: 扩 `.gitignore`（追加）**

```
# bedrock web SPA build artifacts
frontend/node_modules/
frontend/dist/
src/bedrock/web/static/
!src/bedrock/web/static/.gitkeep
```

- [ ] **Step 2: 改 `.claude/launch.json` bedrock-web 配置**

把既有 bedrock-web 配置的 args 从 `--project projects/bedrock_demo` 改为 `--projects-root projects`：

```json
{
  "name": "bedrock-web",
  "runtimeExecutable": "python",
  "runtimeArgs": ["-m", "src.bedrock.web", "--projects-root", "projects", "--port", "5050"],
  "port": 5050
}
```

> `__main__.py` 的 `--port` 默认改 5050（见 Task 9 Step 4 一并处理）。

- [ ] **Step 3: 改 `src/bedrock/web/__main__.py`**

```python
# src/bedrock/web/__main__.py
"""python -m src.bedrock.web --projects-root <dir> [--port 5050]"""
import argparse
from src.bedrock.web.app import create_app


def main():
    parser = argparse.ArgumentParser(prog="bedrock-web")
    parser.add_argument("--projects-root", required=True, help="作品根目录（子目录各含 bedrock.db）")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    app = create_app(args.projects_root)
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 扩 `scripts/seed_bedrock_demo.py`（补 master_outline/volume_outline/世界观，供冒烟）**

在 `main()` 的灵感池之后、写报告之前，追加：

```python
        # master_outline + volume_outline（大纲模式冒烟）
        conn.execute(
            "INSERT OR REPLACE INTO master_outline(id,theme_evolution,key_arcs,key_milestones,rhythm_curve) "
            "VALUES(1,?,?,?,?)",
            ("韩峥从抗拒到承担系统的代价", json.dumps(["韩峥觉醒线", "林深隐痛线"]),
             json.dumps(["ch1 觉知", "ch3 对峙"]), "缓起-急转"))
        conn.execute(
            "INSERT OR IGNORE INTO volume_outline(volume_id,status,beat_contracts) VALUES(?, 'drafted', ?)",
            (v1, json.dumps([{"beat_id": 1, "purpose": "韩峥触膜觉知"}])))
        # 世界观（总览内联编辑冒烟）
        from src.bedrock.repositories.worldbook import add_location, add_theme, add_motif
        add_location(conn, name="封锁线", loc_type="border", description="城市边缘那层温热的膜")
        add_theme(conn, name="边界", description="人与系统之间的不可见界线", evolution="从物理到存在")
        add_motif(conn, name="电流声", meaning="韩峥与系统共振的感知象征", evolution="渐强")
```

> 顶部 `import json`。`v1` 是卷1 id 变量（seed 脚本里已有）。

- [ ] **Step 5: 重 seed + 启动 smoke（API 层）**

```bash
PYTHONIOENCODING=utf-8 python scripts/seed_bedrock_demo.py
PYTHONIOENCODING=utf-8 python -m src.bedrock.web --projects-root projects --port 5050 &
sleep 2
curl -s http://127.0.0.1:5050/api/works | head -c 300
curl -s "http://127.0.0.1:5050/api/works/bedrock_demo/overview" | head -c 300
```
Expected: works 列出 bedrock_demo；overview 返回 JSON 含 master_outline/worldbook。

- [ ] **Step 6: 提交**

```bash
git add .gitignore .claude/launch.json src/bedrock/web/__main__.py scripts/seed_bedrock_demo.py
git commit -m "chore(web): gitignore SPA 产物 + launch.json --projects-root + seed 扩展(大纲/世界观)"
```

---

# Phase 2：SPA 骨架 + 7 只读视图 + 灵感推进/编辑

> Phase 2 任务以**手动冒烟**为验收（本地工具，无前端自动化测试）。每 Task 末尾 `npm run dev` + 浏览器看一眼。冒烟命令统一：`cd frontend && npm run dev`（vite 5173，proxy /api→5050）+ 另起 `python -m src.bedrock.web --projects-root projects`。

## Task 9: frontend 工程脚手架

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/.gitignore`, `frontend/src/main.ts`, `frontend/src/App.vue`, `frontend/src/router.ts`, `frontend/src/api/client.ts`, `frontend/src/stores/workspace.ts`

- [ ] **Step 1: `frontend/package.json`**

```json
{
  "name": "bedrock-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc --noEmit && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3.4.0",
    "vue-router": "^4.3.0",
    "pinia": "^2.1.0",
    "naive-ui": "^2.38.0",
    "marked": "^12.0.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "typescript": "^5.4.0",
    "vite": "^5.2.0",
    "vue-tsc": "^2.0.0"
  }
}
```

- [ ] **Step 2: `frontend/vite.config.ts`**

```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: { outDir: '../src/bedrock/web/static', emptyOutDir: true },
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:5050' },
  },
})
```

- [ ] **Step 3: `frontend/tsconfig.json` + `frontend/.gitignore` + `frontend/index.html`**

```json
// tsconfig.json
{ "compilerOptions": { "target": "ES2020", "module": "ESNext", "moduleResolution": "bundler",
  "strict": true, "jsx": "preserve", "types": ["vite/client"],
  "lib": ["ES2020", "DOM", "DOM.Iterable"] },
  "include": ["src/**/*.ts", "src/**/*.vue"] }
```
```
# .gitignore
node_modules/
dist/
```
```html
<!-- index.html -->
<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>磐石 Bedrock</title></head>
<body><div id="app"></div>
<script type="module" src="/src/main.ts"></script></body></html>
```

- [ ] **Step 4: `frontend/src/api/client.ts`（fetch 封装）**

```typescript
// src/api/client.ts
const BASE = ''  // 同源（dev 经 vite proxy，prod 同进程）

async function req(method: string, path: string, body?: any) {
  const res = await fetch(BASE + path, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (res.status === 415) throw new Error('请求格式错误（需 JSON）')
  if (res.status === 404) throw new Error('未找到（work_id/资源不存在）')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export const api = {
  works: () => req('GET', '/api/works'),
  overview: (w: string) => req('GET', `/api/works/${w}/overview`),
  matrix: (w: string, v?: number) => req('GET', `/api/works/${w}/matrix${v ? '?volume=' + v : ''}`),
  inspirations: (w: string, type?: string, status?: string) =>
    req('GET', `/api/works/${w}/inspirations${[type, status].filter(Boolean).length ? '?' + [type && 'type=' + type, status && 'status=' + status].filter(Boolean).join('&') : ''}`),
  advance: (w: string, id: number, target: string) =>
    req('POST', `/api/works/${w}/inspirations/${id}/advance`, { target }),
  editInspiration: (w: string, id: number, body: any) =>
    req('PATCH', `/api/works/${w}/inspirations/${id}`, body),
  reports: (w: string) => req('GET', `/api/works/${w}/reports`),
  report: (w: string, vid: number) => req('GET', `/api/works/${w}/report/${vid}`),
  chapters: (w: string) => req('GET', `/api/works/${w}/chapters`),
  chapterText: (w: string, g: number) => req('GET', `/api/works/${w}/chapters/${g}/text`),
  outline: (w: string, v?: number) => req('GET', `/api/works/${w}/outline${v ? '?volume=' + v : ''}`),
  characters: (w: string) => req('GET', `/api/works/${w}/characters`),
  factions: (w: string) => req('GET', `/api/works/${w}/factions`),
  patch: (w: string, entity: string, id: number | string, body: any) =>
    req('PATCH', `/api/works/${w}/${entity}/${id}`, body),
  patchBeatContract: (w: string, vid: number, bid: number, body: any) =>
    req('PATCH', `/api/works/${w}/volumes/${vid}/beats/${bid}/contract`, body),
  patchMaster: (w: string, body: any) => req('PATCH', `/api/works/${w}/master_outline`, body),
}
```

- [ ] **Step 5: `frontend/src/stores/workspace.ts`（pinia）**

```typescript
// src/stores/workspace.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'

export interface Work { id: string; name: string; volumes: number; chapters_completed: number; chapters_writing: number }

export const useWorkspace = defineStore('workspace', () => {
  const works = ref<Work[]>([])
  const activeId = ref<string | null>(null)
  const active = computed(() => works.value.find(w => w.id === activeId.value) || null)

  async function loadWorks() { works.value = await api.works() }
  function setActive(id: string) { activeId.value = id }

  return { works, activeId, active, loadWorks, setActive }
})
```

- [ ] **Step 6: `frontend/src/router.ts` + `frontend/src/main.ts`**

```typescript
// src/router.ts
import { createRouter, createWebHistory } from 'vue-router'
const routes = [
  { path: '/', redirect: () => '/works' },
  { path: '/works', component: () => import('./views/Overview.vue'), props: true },
  { path: '/works/:wid', component: () => import('./views/Overview.vue'), props: true },
  { path: '/works/:wid/characters', component: () => import('./views/Characters.vue'), props: true },
  { path: '/works/:wid/matrix', component: () => import('./views/Matrix.vue'), props: true },
  { path: '/works/:wid/inspirations', component: () => import('./views/Inspirations.vue'), props: true },
  { path: '/works/:wid/report', component: () => import('./views/Report.vue'), props: true },
  { path: '/works/:wid/read', component: () => import('./views/Reader.vue'), props: true },
  { path: '/works/:wid/outline', component: () => import('./views/Outline.vue'), props: true },
]
export const router = createRouter({ history: createWebHistory(), routes })
```
```typescript
// src/main.ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import naive from 'naive-ui'
import App from './App.vue'
import { router } from './router'

createApp(App).use(createPinia()).use(router).use(naive).mount('#app')
```

- [ ] **Step 7: `frontend/src/App.vue`（NLayout 外壳 + WorkSwitcher + SideNav）**

```vue
<!-- src/App.vue -->
<script setup lang="ts">
import { onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NLayout, NLayoutSider, NLayoutHeader, NLayoutContent, NSelect, NMenu, NSpin } from 'naive-ui'
import { useWorkspace } from './stores/workspace'

const ws = useWorkspace()
const route = useRoute()
const router = useRouter()
onMounted(() => ws.loadWorks())

const workOptions = computed(() => ws.works.map(w => ({ label: `${w.name}（${w.volumes}卷）`, value: w.id })))
watch(() => route.params.wid, (wid) => { if (wid) ws.setActive(wid as string) }, { immediate: true })

function onWork(v: string | null) {
  if (v) { ws.setActive(v); router.push(`/works/${v}`) }
}

const menuOptions = computed(() => {
  const w = ws.activeId
  if (!w) return []
  const base = `/works/${w}`
  return [
    { label: '总览', key: 'overview' },
    { label: '角色', key: 'characters' },
    { label: 'POV 矩阵', key: 'matrix' },
    { label: '灵感池', key: 'inspirations' },
    { label: 'Review 报告', key: 'report' },
    { label: '正文·阅读', key: 'read' },
    { label: '正文·大纲', key: 'outline' },
  ].map(m => ({ ...m, props: { onClick: () => router.push(m.key === 'overview' ? base : `${base}/${m.key}`) } }))
})
</script>

<template>
  <NLayout has-sider style="height:100vh">
    <NLayoutSider bordered :width="220" content-style="padding:12px;background:#18181c">
      <div style="margin-bottom:12px">
        <NSelect v-if="workOptions.length" :value="ws.activeId" :options="workOptions" @update:value="onWork" placeholder="选择作品"/>
        <NSpin v-else size="small"/>
      </div>
      <NMenu :options="menuOptions" :disabled="!ws.activeId"/>
      <div style="position:absolute;bottom:8px;font-size:11px;color:#666;padding:0 4px">{{ ws.activeId || '未选作品' }}</div>
    </NLayoutSider>
    <NLayout>
      <NLayoutHeader bordered style="height:48px;padding:0 20px;display:flex;align-items:center;background:#18181c">
        <strong style="color:#4ec9b0">磐石 Bedrock</strong>
        <span style="margin-left:12px;color:#888">{{ ws.active?.name }}</span>
      </NLayoutHeader>
      <NLayoutContent content-style="padding:20px;background:#15171c" style="height:calc(100vh - 48px);overflow:auto">
        <RouterView v-if="ws.activeId" />
        <div v-else style="color:#666;padding:40px">请从左侧选择一个作品。</div>
      </NLayoutContent>
    </NLayout>
  </NLayout>
</template>
```

- [ ] **Step 8: 安装依赖 + 占位视图 + 冒烟骨架**

为 7 视图各建最小占位（`<template><h3>视图名</h3></template>`），先跑通骨架。

```bash
cd frontend && npm install
# 建 7 个占位 views（Overview/Characters/Matrix/Inspirations/Report/Reader/Outline 各一句）
npm run dev
```
浏览器开 http://127.0.0.1:5173 → 应见深色外壳 + 左侧作品下拉（选 bedrock_demo）+ 7 菜单项可切换占位页。
Expected: 外壳渲染、work 切换、菜单导航正常。

- [ ] **Step 9: 提交**

```bash
git add frontend/  # node_modules/dist gitignored
git commit -m "feat(web-frontend): Vue3+Naive UI 工程脚手架 (外壳/路由/store/api client)"
```

---

## Task 10: Overview 视图（统计 + 卷列表 + 角色快照 + 世界观只读）

**Files:**
- Modify: `frontend/src/views/Overview.vue`

**Spec：**
- 顶部：`NStatistic` 网格（卷数/章 completed/章 writing/角色/字数/灵感各状态计数），数据来自 `api.overview(wid)`。
- 卷列表：`NCard`/`NList`，每卷 name+volume_type+章数+status 徽章+escalate 计数（卷名/theme_seeds 的内联编辑留 Task 16，本 Task 只读展示）。
- 角色快照：`NCard` 网格只读（name/role 徽章/state/pronoun/personality_excerpt），点击 → `router.push(\`/works/${wid}/characters\`)`。
- 世界观区：**本 Task 只读展示** location/theme/motif（编辑留 Task 16）。
- Naive 组件：`NStatistic`/`NCard`/`NTag`/`NGrid`/`NSpin`。
- 风格：深色（`background:#1a1d24` 卡片，`color:#e6e9ef` 文字），与 App 外壳一致。

- [ ] **Step 1: 实现 Overview.vue（按 spec 绑定 overview 数据，只读）**
- [ ] **Step 2: 冒烟** — 选 bedrock_demo → 见统计数字、卷列表、角色快照卡（韩峥/林深/沈夜）、世界观三组。
- [ ] **Step 3: 提交** `git commit -m "feat(web): Overview 视图 (统计/卷列表/角色快照/世界观只读)"`

---

## Task 11: Characters 视图（列表只读 + 跳转）

**Files:**
- Modify: `frontend/src/views/Characters.vue`

**Spec：**
- `api.characters(wid)` → `NDataTable`：列 name/role(徽章)/state(徽章)/pronoun/faction_name/personality 摘要/secret_count/knowledge_count。
- 顶部 `NSelect` 筛 role（protagonist/supporting/antagonist/minor）+ state。
- 点行 → 暂只 `console.log`（NDrawer 编辑表单留 Task 17）。本 Task 不编辑。
- secrets/knowledge 只读计数列展示。

- [ ] **Step 1: 实现 Characters.vue（只读列表 + 筛选）**
- [ ] **Step 2: 冒烟** — 见 3 角色行 + 筛选生效。
- [ ] **Step 3: 提交** `git commit -m "feat(web): Characters 视图 (只读列表+筛选)"`

---

## Task 12: Matrix 视图（NDataTable + BeatDrawer）

**Files:**
- Modify: `frontend/src/views/Matrix.vue`
- Create: `frontend/src/components/BeatDrawer.vue`

**Spec：**
- 顶部 `NSelect` 选卷（从 overview.volume_list）。
- `NDataTable`：列 = 该卷 characters（动态列，从 `api.matrix(wid,vid).characters`）+ 末列"合计"；行 = chapters（global_number+title）。单元格有 POV → 青色 ●（`NButton` text 圆点），点击 → `BeatDrawer` 显示该章该角色 beats（sequence+purpose+status）。
- 整卷无 POV → `NEmpty`。● hover 放大。
- BeatDrawer：`NDrawer` + 列出 beats；beat 数据需一个端点——**复用 outline 数据**：`api.outline(wid,vid)` 已含每章 beats+ pov_name，前端在矩阵里点击时从已加载 outline 过滤，或新增轻量 `GET /api/works/<wid>/beats?chapter=&character=`。**选复用 outline**（避免新端点）：Matrix 视图同时拉 outline，点 ● 从 outline.chapters[id].beats 里筛 pov_name==该角色。
- 若 outline 复用太绕，**回退方案**：Task 12 内 api.py 加 `GET /api/works/<wid>/matrix/beats?chapter=<cid>&character=<chid>`（读 beat 表），BeatDrawer 调它。实现者择一，注明。

- [ ] **Step 1: 实现 Matrix.vue + BeatDrawer.vue**
- [ ] **Step 2: 冒烟** — bedrock_demo 卷1 → 见韩峥/林深列、ch1/ch3 韩峥 ●、点 ● 弹 beat drawer。
- [ ] **Step 3: 提交** `git commit -m "feat(web): Matrix 视图 (NDataTable + BeatDrawer)"`

---

## Task 13: Inspirations 视图（筛选 + 卡片 + 推进 + 编辑）★完整写视图

**Files:**
- Modify: `frontend/src/views/Inspirations.vue`

> 这是**唯一给完整代码的视图**，作为其余视图的范式参考。

- [ ] **Step 1: 实现 Inspirations.vue（完整）**

```vue
<!-- src/views/Inspirations.vue -->
<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useMessage, NCard, NTag, NSelect, NButton, NModal, NInput, NSpace, NEmpty, NSpin } from 'naive-ui'
import { api } from '../api/client'

const props = defineProps<{ wid: string }>()
const msg = useMessage()
const items = ref<any[]>([])
const loading = ref(true)
const typeF = ref<string | null>(null)
const statusF = ref<string | null>(null)
const editing = ref<any | null>(null)
const editContent = ref('')
const editSource = ref('')

const typeOpts = ['premise','scene','character','theme','mechanic','setting','twist'].map(t => ({ label: t, value: t }))
const statusOpts = ['raw','refined','consumed','partial','discarded'].map(s => ({ label: s, value: s }))
const statusColor: Record<string,string> = { raw:'default', refined:'info', consumed:'success', partial:'warning', discarded:'error' }

async function load() {
  loading.value = true
  try { items.value = await api.inspirations(props.wid, typeF.value || undefined, statusF.value || undefined) }
  catch (e:any) { msg.error(e.message) }
  finally { loading.value = false }
}
watch(() => props.wid, load, { immediate: true })

const TRANSITIONS: Record<string, string[]> = {
  raw: ['refined','consumed','discarded'],
  refined: ['consumed','partial','discarded'],
  partial: ['consumed','discarded'],
  consumed: ['discarded'],
  discarded: [],
}
const editable = (it: any) => ['raw','refined','partial'].includes(it.status) && (!it.consumed_into || it.consumed_into.length === 0)

async function advance(it: any, target: string) {
  try {
    const r = await api.advance(props.wid, it.id, target)
    if (r.ok) { Object.assign(it, r.item); msg.success(`→ ${target}`) }
    else msg.error(r.error)
  } catch (e:any) { msg.error(e.message) }
}
function openEdit(it: any) { editing.value = it; editContent.value = it.content; editSource.value = it.source || '' }
async function saveEdit() {
  try {
    const r = await api.editInspiration(props.wid, editing.value.id, { content: editContent.value, source: editSource.value })
    if (r.ok) { Object.assign(editing.value, r.item); msg.success('已保存') }
    else msg.error(r.error)
  } catch (e:any) { msg.error(e.message) }
  editing.value = null
}
</script>

<template>
  <h2 style="color:#e6e9ef">灵感池 <small style="color:#666;font-size:13px">{{ items.length }} 条</small></h2>
  <NSpace style="margin-bottom:16px">
    <NSelect v-model:value="typeF" :options="typeOpts" placeholder="类型" clearable style="width:140px" @update:value="load"/>
    <NSelect v-model:value="statusF" :options="statusOpts" placeholder="状态" clearable style="width:140px" @update:value="load"/>
  </NSpace>
  <NSpin v-if="loading"/>
  <NEmpty v-else-if="!items.length" description="无匹配灵感"/>
  <div v-else style="display:flex;flex-direction:column;gap:10px">
    <NCard v-for="it in items" :key="it.id" size="small" :style="{ opacity: it.status==='discarded'?.6:1 }">
      <NSpace align="center" style="margin-bottom:6px">
        <NTag size="small" round type="default">{{ it.type }}</NTag>
        <NTag size="small" round :type="statusColor[it.status]">{{ it.status }}</NTag>
        <NButton v-if="editable(it)" size="tiny" quaternary @click="openEdit(it)">编辑</NButton>
      </NSpace>
      <p style="margin:4px 0;color:#e6e9ef">{{ it.content }}</p>
      <small style="color:#666">{{ it.source }}</small>
      <div v-if="it.consumed_into?.length" style="margin-top:4px">
        <NTag v-for="(c,i) in it.consumed_into" :key="i" size="tiny" type="success">{{ c.target_type }}#{{ c.target_id }}</NTag>
      </div>
      <NSpace style="margin-top:8px">
        <NButton v-for="t in TRANSITIONS[it.status]" :key="t" size="small" :type="t==='discarded'?'error':'default'"
                 @click="advance(it, t)">→ {{ t }}</NButton>
      </NSpace>
    </NCard>
  </div>

  <NModal v-model:show="editing" preset="card" title="编辑灵感" style="max-width:560px">
    <NInput v-model:value="editContent" type="textarea" :rows="5"/>
    <NInput v-model:value="editSource" placeholder="来源" style="margin-top:8px"/>
    <template #footer><NSpace justify="end"><NButton @click="editing=null">取消</NButton><NButton type="primary" @click="saveEdit">保存</NButton></NSpace></template>
  </NModal>
</template>
```

- [ ] **Step 2: 冒烟** — 见 5 条灵感各状态、推进按钮按状态显示、点编辑弹窗改 content 保存、consumed 显示已采用 tag、discarded 无按钮。
- [ ] **Step 3: 提交** `git commit -m "feat(web): Inspirations 视图 (筛选/推进/编辑, 完整范式)"`

---

## Task 14: Report 视图（marked 渲染 + escalate 高亮）

**Files:**
- Modify: `frontend/src/views/Report.vue`

**Spec：**
- 顶部 `NSelect` 选卷（只列 `api.reports(wid)` 有报告的卷）。
- `api.report(wid,vid)` → `{html_body, escalate_chs, has_escalate}`。
- `has_escalate` → 顶部 `NAlert` 提示。
- `v-html="html_body"` 渲染， escalate 项靠服务端注入的 `escalate-highlight` class 高亮（前端只加 CSS：`.escalate-highlight{border-left:3px solid #e06c6c;background:rgba(224,108,108,.1);padding:6px 10px;margin:4px 0;list-style:none;color:#e6e9ef}`，放 Report.vue `<style>` 或全局）。
- 缺报告 → `NResult` 404/空态。

- [ ] **Step 1: 实现 Report.vue（marked 不需要——服务端已渲染 html_body，直接 v-html）**
- [ ] **Step 2: 冒烟** — bedrock_demo 卷1 → 见报告 + ch3 escalate 红框高亮。
- [ ] **Step 3: 提交** `git commit -m "feat(web): Report 视图 (markdown 渲染 + escalate 高亮)"`

> 注：`marked` 依赖保留（未来前端渲染用）；本视图直接用服务端 html_body。

---

## Task 15: Reader 视图（章节目录 + 散文 + 上下章）

**Files:**
- Modify: `frontend/src/views/Reader.vue`

**Spec：**
- 左侧目录：`api.chapters(wid)` 按卷分组（`NCollapse` 或分组列表）。选中 → 右侧渲染。
- 右侧：`api.chapterText(wid,gnum)` → paragraphs 按 seq；散文排版（max-width 720px、line-height 1.9、首行缩进 2em、章标题 `chapter.title` 大字）。
- 底部：上一章/下一章按钮，首章禁用上一章、末章禁用下一章（按 chapters 全局序）。

- [ ] **Step 1: 实现 Reader.vue**
- [ ] **Step 2: 冒烟** — 选 ch1 → 见两段正文、上下章导航。
- [ ] **Step 3: 提交** `git commit -m "feat(web): Reader 视图 (散文阅读 + 上下章)"`

---

## Task 16: Outline 视图（多级分组树）

**Files:**
- Modify: `frontend/src/views/Outline.vue`

**Spec：**
- `NSelect` 选卷（默认全部）。
- `api.outline(wid,vid?)` → `{master_outline, volumes[]}`。
- 顶部：master_outline 卡片（theme_evolution / key_arcs NTag / key_milestones NTag / rhythm_curve），字段空省略。
- `NTree`（`block-line` + `expand-on-click`）：卷节点（name+volume_type+status+volume_outline.status）→ 章节点（global_number+title+status）→ beat 节点（sequence+purpose+`[status]`+pov_name+¶count）；deviated beat 显示 deviation_note 红字。
- 缺字段优雅省略（volume_outline null → 不显示锁定状态；beats 空 → 章节点无子）。
- 编辑留 Task 18（本 Task 只读树）。

- [ ] **Step 1: 实现 Outline.vue（NTree 数据来自 outline，只读）**
- [ ] **Step 2: 冒烟** — 见 master_outline 卡片 + 卷1展开 → ch1 → beat1（韩峥 POV、¶2）。
- [ ] **Step 3: 提交** `git commit -m "feat(web): Outline 视图 (作品/卷/章/beat 多级树, 只读)"`

---

# Phase 3：元数据 + 大纲编辑

## Task 17: 角色编辑表单（NDrawer 全字段）

**Files:**
- Create: `frontend/src/components/edit/CharacterForm.vue`
- Modify: `frontend/src/views/Characters.vue`（接点行 → Drawer）

**Spec：**
- Characters 点行 → 打开 `NDrawer`（宽 600）`CharacterForm`。
- 表单字段：name(NInput)/pronoun(NSelect 他她它祂TA)/gender(NSelect 男女无未知其他,null)/role(NSelect)/state(NSelect active dormant deceased ascended merged)/faction(NSelect from api.factions)/personality(NInput textarea)/goals(textarea)/abilities(NTag 动态输入)/aliases(NTag 动态输入)。
- 仅提交改动字段（diff 初始值）；调 `api.patch(wid,'characters',id, changedFields)`。
- 成功 → `useMessage().success` + 刷新行；`{ok:false}` → error(r.error)；name 冲突/枚举违例走此路径。
- secrets/knowledge 只读折叠区 + "v1 暂不可编辑"提示。

- [ ] **Step 1: 实现 CharacterForm.vue + 接入 Characters.vue**
- [ ] **Step 2: 冒烟** — 改韩峥 personality 保存成功；改 pronoun 为非法值 → NMessage error 且不变；改 name 为林深 → 冲突 error。
- [ ] **Step 3: 提交** `git commit -m "feat(web): 角色编辑表单 (NDrawer 全字段 + amendment)"`

---

## Task 18: 大纲编辑（beat 契约/状态/meta + master_outline）

**Files:**
- Modify: `frontend/src/views/Outline.vue`（beat 节点加编辑入口）
- Create: `frontend/src/components/edit/BeatEdit.vue`
- Create: `frontend/src/components/edit/MasterOutlineEdit.vue`

**Spec：**
- beat 节点右侧「编辑」按钮 → `BeatEdit`（NPopover 或 NModal）：purpose(NInput,≥10)/scene_setting(NInput textarea JSON)/status(NSelect planned/written/verified/deviated/overridden)/deviation_note(NInput)。
  - purpose/scene_setting → `api.patch(wid,'beats',id,{purpose,scene_setting})`。
  - status/deviation_note → `api.patch(wid,'beats',id,{status,deviation_note})`。
  - beat 契约编辑：若 volume_outline.status != locked，提供「编辑契约」→ `api.patchBeatContract(wid,vid,bid,{purpose,scene_setting,pov,...})`；**locked → 按钮禁用 + tooltip「卷已锁定，需 CLI unlock」**，且即便强行请求，后端返回 `{ok:false}`（OutlineLockedError）→ NMessage。
- master_outline 卡片「编辑」→ `MasterOutlineEdit`：theme_evolution(textarea)/key_arcs(NTag list)/key_milestones(NTag list)/rhythm_curve(text) → `api.patchMaster(wid, body)`。
- 卷名/theme_seeds 编辑留 Task 19（本 Task 只 beat + master）。

- [ ] **Step 1: 实现 BeatEdit + MasterOutlineEdit + 接入 Outline.vue**
- [ ] **Step 2: 冒烟** — 改 beat purpose（≥10）成功；改 <10 → error；locked 卷契约 → 按钮 disabled/请求 error；改 master_outline theme_evolution 成功。
- [ ] **Step 3: 提交** `git commit -m "feat(web): 大纲编辑 (beat 契约/状态/meta + master_outline)"`

---

## Task 19: 总览内联编辑（世界观 + 卷名/theme_seeds）+ 章标题

**Files:**
- Create: `frontend/src/components/edit/WorldbookInline.vue`
- Modify: `frontend/src/views/Overview.vue`（卷列表 + 世界观区接编辑）
- Modify: `frontend/src/views/Reader.vue`（章标题旁「编辑」）

**Spec：**
- `WorldbookInline`：location/theme/motif 三组 NCard，description/evolution/meaning/loc_type/state 用内联 `NInput`/双击编辑 → `api.patch(wid,'locations'|'themes'|'motifs',id,body)`。
- Overview 卷列表：卷名内联编辑（NInput）+ theme_seeds（NTag list）→ `api.patch(wid,'volumes',id,{name,theme_seeds})`。
- Reader 章标题旁「编辑」icon → NInput → `api.patch(wid,'chapters',id,{title})`。
- 失败 → NMessage，不变。

- [ ] **Step 1: 实现 WorldbookInline + 接入 Overview 卷编辑 + Reader 章标题编辑**
- [ ] **Step 2: 冒烟** — 改地点描述/卷名/theme_seeds/章标题均成功保存；改 theme_seeds 非法（API 层校验列表）→ error。
- [ ] **Step 3: 提交** `git commit -m "feat(web): 总览内联编辑 (世界观/卷名/theme_seeds) + 章标题编辑"`

---

## Task 20: 一键启动 + 构建 + 最终回归

**Files:**
- Create: `scripts/start_webui.bat`
- Modify: `frontend/vite.config.ts`（已配 outDir，确认）

- [ ] **Step 1: `scripts/start_webui.bat`**

```bat
@echo off
cd /d %~dp0\..\
where npm >nul 2>nul || (echo [error] 未找到 npm，请先安装 Node.js & exit /b 1)
if not exist src\bedrock\web\static\index.html (
  echo [build] SPA 未构建，执行 npm install + build...
  pushd frontend
  call npm install && call npm run build || (echo [error] build 失败 & popd & exit /b 1)
  popd
)
python -m src.bedrock.web --projects-root projects
```

- [ ] **Step 2: 生产构建 + 单进程验证**

```bash
cd frontend && npm run build && cd ..
# static/index.html 应已生成到 src/bedrock/web/static/
python -m src.bedrock.web --projects-root projects --port 5050 &
sleep 2
curl -s http://127.0.0.1:5050/ | head -c 100   # 应返回 SPA index.html
curl -s http://127.0.0.1:5050/api/works | head -c 100
```
Expected: `/` 返回 SPA HTML；`/api/works` 返回 JSON。

- [ ] **Step 3: 最终全量回归**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/bedrock/ -q`
Expected: 全通过（test_queries + test_edit_repos + test_api + test_outline + test_web_queries + 既有 repository/cli；test_web 已删）。

- [ ] **Step 4: 浏览器终验（单进程模式）**

开 http://127.0.0.1:5050 → 冒烟全部：作品切换 / 7 视图 / 灵感推进+编辑 / 角色编辑 / 世界观内联编辑 / beat 契约(locked 拒) / master_outline 编辑 / escalate 高亮 / 阅读上下章 / 大纲树。

- [ ] **Step 5: 提交**

```bash
git add scripts/start_webui.bat frontend/vite.config.ts
git commit -m "feat(web): 一键启动脚本 + 生产构建验证 + 最终回归"
```

---

## Self-Review（计划自检）

**1. Spec 覆盖：**
- §1 7 视图 → Task 9-16（Overview/Characters/Matrix/Inspirations/Report/Reader/Outline）✓
- §2 amendment 骨架 → Task 1 `_amendment` + 各 edit repo 调用 ✓
- §5.3 灵感推进/编辑 → Task 2(update_inspiration_content) + Task 7(api) + Task 13(view) ✓
- §5.7 层1 元数据 → Task 3/4/5(repo) + Task 7(api) + Task 17/19(view) ✓
- §5.7 层2 大纲 → Task 4/5(repo) + Task 7(api) + Task 18(view) ✓
- §6 路径穿越/CSRF/失败语义 → Task 6/7(api `_resolve_work`/`_require_json`/`_run`) ✓
- §7 read 查询 → Task 1 ✓
- §8 一键启动 → Task 20 ✓
- §9 测试 → Task 1/2/3/4/5(纯函数) + Task 6/7(api) ✓；test_web 删 → Task 7 ✓
- §10 删 Jinja/htmx/app.css → Task 7 ✓；launch.json/gitignore → Task 8 ✓
- §11 验收 → Task 20 Step 4 终验 ✓
- §12 正文独立 spec → 本计划不含（正确，正文留后续）✓

**2. Placeholder 扫描：** 前端 Task 10-12/14-16/18-19 用 spec+绑定+验收（按计划顶部「前端约定」声明），非 TBD/TODO；所有后端 Task 有完整代码。Matrix Task 12 的 beat 数据端点给了「复用 outline / 回退加端点」二选一（注明择一，非空缺）。✓

**3. 类型/签名一致性：** `update_inspiration_content(conn,iid,content,source=None)` / `update_character(conn,cid,**fields)` / `update_chapter_meta(conn,ch_id,title)` / `update_volume_meta(conn,vid,name=None,theme_seeds=None)` / `update_beat_meta(conn,beat_id,purpose=None,scene_setting=None)` / `update_location/theme/motif(conn,id,...)` / `update_master_outline(conn,**fields)` —— repo 层、api `_patch_entity` 透传、测试三处一致 ✓。API client `api.patch(wid,entity,id,body)` ↔ 后端 `PATCH /works/<wid>/<entity>/<id>` 一致 ✓。

---

**Plan complete and saved to `docs/superpowers/plans/2026-06-15-bedrock-web-spa.md`.**

**Two execution options:**

**1. Subagent-Driven (推荐)** — 每个 Task 派新子代理实现 + 两阶段审核（spec 合规 → 代码质量），任务间快迭代。后端 Task（1-8）逻辑重，走完整两阶段审核；前端 Task（9-20）偏机械/视觉，单次审核或冒烟即可。

**2. Inline Execution** — 本会话内 executing-plans 批量执行 + checkpoint。

Phase 划分：Phase 1（Task 1-8 后端）可先全做完、全绿、独立冒烟 API，再开 Phase 2 前端。

哪种？
