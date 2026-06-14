# 磐石 Bedrock SP6-A 实现计划：只读 CLI 工具集（export/diagnose/show-review-report/diff）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 4 个给人用的只读 CLI 命令（export / diagnose / show-review-report / diff），全部纯函数 + 薄 CLI 封装，零新依赖。

**Architecture:** 新增 `src/bedrock/cli/reader_commands.py`（纯函数 + 命名/渲染工具），`__main__.py` 加 4 个子命令薄封装。export 是唯一写 DB 的命令（仅写 export_manifest，短事务）；diagnose/show-review-report/diff 完全不写 DB。

**Tech Stack:** Python stdlib（hashlib/re/sqlite3）+ pytest（既有 tmp_project fixture）。

**Spec:** `docs/superpowers/specs/2026-06-14-bedrock-sp6a-cli-design.md`（已过两路对抗审核，8🔴+9🟡 已吸收）。

**关键不变量（贯穿全程）：**
- `chapter_filename(global_number)` = `f"ch{n:02d}"`，export 写/diff 读共用。
- export 写的 `export_manifest.content_hash` == 导出文件实际 sha256（round-trip）。
- diagnose 绝不写 `volume_review`（不调 `check_cross_volume_debt`，用纯读 SQL）。
- diff manifest 查询严格 `(scope='chapter', target_id=chapter.id, format, status)`。

---

## Task 1: 共享原语（命名 + 单章渲染）

**Files:**
- Create: `src/bedrock/cli/__init__.py`（空）
- Create: `src/bedrock/cli/reader_commands.py`
- Test: `tests/bedrock/test_reader_commands.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_reader_commands.py
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_reader_commands.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.bedrock.cli.reader_commands'`）

- [ ] **Step 3: 写最小实现**

```python
# src/bedrock/cli/__init__.py
# （空文件，标记 cli 为包）
```

```python
# src/bedrock/cli/reader_commands.py
"""SP6-A 只读 CLI 工具集：export / diagnose / show_review_report / diff 的纯函数。
diagnose / show_review_report / diff 完全不写 DB；export 仅写 export_manifest（短事务）。
正文 SSOT = paragraph 表，export 单向导出绝不回填。"""
from src.bedrock.repositories.plot_tree import list_paragraphs_in_chapter


def chapter_filename(global_number):
    """global_number → 'ch{NN}'（≥2 位补零，与既有 output/ 一致）。
    export 写文件、diff 读文件共用，保证命名一致。"""
    return f"ch{global_number:02d}"


def render_chapter_body(conn, chapter_id, fmt):
    """渲染单章正文 + 章标题（不含卷/书标题）。
    md: '### 第N章 标题' + 段落（按 seq，空行分隔）
    txt: '第N章 标题'（正文行）+ 段落
    段落按 seq 排序，只取 text，不读 role。paragraph 主键 para_id（非 id）。"""
    ch = conn.execute(
        "SELECT global_number, title FROM chapter WHERE id=?",
        (chapter_id,)).fetchone()
    if ch is None:
        raise ValueError(f"chapter id={chapter_id} 不存在")
    paragraphs = list_paragraphs_in_chapter(conn, chapter_id)
    body = "\n\n".join(p["text"] for p in paragraphs)
    if fmt == "md":
        return f"### 第{ch['global_number']}章 {ch['title']}\n\n{body}"
    return f"第{ch['global_number']}章 {ch['title']}\n\n{body}"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_reader_commands.py -v`
Expected: PASS（4 测试）

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/cli/__init__.py src/bedrock/cli/reader_commands.py tests/bedrock/test_reader_commands.py
git commit -m "feat(bedrock): SP6-A 共享原语 chapter_filename + render_chapter_body"
```

---

## Task 2: do_export（三级 scope + manifest 留痕）

**Files:**
- Modify: `src/bedrock/cli/reader_commands.py`
- Test: `tests/bedrock/test_reader_commands.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/bedrock/test_reader_commands.py
import hashlib
from pathlib import Path
from src.bedrock.cli.reader_commands import do_export
from src.bedrock.repositories.worldbook import add_constant


def _seed_multi_volume_book(conn):
    """2 卷各 2 章（卷1: ch1,ch2 completed；卷2: ch3 completed, ch4 writing）。"""
    v1 = create_volume(conn, 1, "第一卷", 1, 2, "opening")
    v2 = create_volume(conn, 2, "第二卷", 3, 4, "climax")
    c1 = create_chapter(conn, volume_id=v1, global_number=1, title="甲", status="completed")
    c2 = create_chapter(conn, volume_id=v1, global_number=2, title="乙", status="completed")
    c3 = create_chapter(conn, volume_id=v2, global_number=3, title="丙", status="completed")
    create_chapter(conn, volume_id=v2, global_number=4, title="丁", status="writing")
    for cid in (c1, c2, c3):
        create_paragraph(conn, chapter_id=cid, seq=1, text=f"正文{cid}",
                         content_hash=f"h{cid}", beat_id=None, role="narration")
    add_constant(conn, key="work_name", value="绝地天通")
    return v1, v2, c1, c2, c3


def _file_sha256(path):
    return hashlib.sha256(Path(path).read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def test_export_chapter_writes_manifest_and_file(tmp_project):
    conn = get_connection(tmp_project)
    v1, v2, c1, c2, c3 = _seed_multi_volume_book(conn)
    result = do_export(conn, tmp_project, scope="chapter", target=c1,
                       fmt="md", final=False, out=None)
    # 文件存在 + 文件名补零
    out_path = Path(result.path)
    assert out_path.exists()
    assert out_path.name == "ch01.md"
    # manifest 写入：round-trip 不变量
    row = conn.execute(
        "SELECT scope,target_id,format,content_hash,status FROM export_manifest "
        "ORDER BY id DESC LIMIT 1").fetchone()
    assert row["scope"] == "chapter"
    assert row["target_id"] == c1
    assert row["format"] == "md"
    assert row["status"] == "draft"
    assert row["content_hash"] == _file_sha256(out_path)   # round-trip 根基
    assert row["content_hash"] == result.content_hash
    conn.close()


def test_export_volume_skips_non_completed(tmp_project, capsys):
    conn = get_connection(tmp_project)
    v1, v2, c1, c2, c3 = _seed_multi_volume_book(conn)
    result = do_export(conn, tmp_project, scope="volume", target=v2,
                       fmt="md", final=False, out=None)
    # 卷2 只有 ch3 completed（ch4 writing 跳过）
    content = Path(result.path).read_text(encoding="utf-8")
    assert "第3章 丙" in content
    assert "第4章" not in content        # writing 章被跳过
    captured = capsys.readouterr()
    assert "ch4" in captured.err or "跳过" in captured.err   # stderr 跳过清单
    conn.close()


def test_export_empty_volume_exits(tmp_project):
    import pytest
    conn = get_connection(tmp_project)
    v1 = create_volume(conn, 1, "空卷", 1, 3, "opening")
    create_chapter(conn, volume_id=v1, global_number=1, title="x", status="writing")
    with pytest.raises(SystemExit):
        do_export(conn, tmp_project, scope="volume", target=v1,
                  fmt="md", final=False, out=None)
    conn.close()


def test_export_book_orders_by_global_number_across_volumes(tmp_project):
    conn = get_connection(tmp_project)
    v1, v2, c1, c2, c3 = _seed_multi_volume_book(conn)
    result = do_export(conn, tmp_project, scope="book", target=None,
                       fmt="md", final=False, out=None)
    content = Path(result.path).read_text(encoding="utf-8")
    # 全局升序：第1章 在 第3章 之前
    assert content.index("第1章") < content.index("第3章")
    # 书名顶层
    assert content.startswith("# 绝地天通")
    # 卷标题（卷1 在卷2前）
    assert content.index("第一卷") < content.index("第二卷")
    conn.close()


def test_export_final_writes_snapshot_subdir(tmp_project):
    conn = get_connection(tmp_project)
    v1, v2, c1, c2, c3 = _seed_multi_volume_book(conn)
    result = do_export(conn, tmp_project, scope="chapter", target=c1,
                       fmt="md", final=True, out=None)
    final_path = tmp_project / "exports" / "final" / "ch01.md"
    assert final_path.exists()
    row = conn.execute(
        "SELECT status FROM export_manifest ORDER BY id DESC LIMIT 1").fetchone()
    assert row["status"] == "final"
    conn.close()


def test_export_manifest_short_transaction_failure_warns(tmp_project, capsys):
    """manifest 写失败降级警告，不阻断文件导出。用 monkeypatch 制造写失败。"""
    import pytest
    conn = get_connection(tmp_project)
    v1, v2, c1, c2, c3 = _seed_multi_volume_book(conn)
    # 暂存原 execute，注入 export_manifest 写时抛错
    orig_exec = conn.execute
    def faulty_execute(sql, *a, **kw):
        if "export_manifest" in sql and "INSERT" in sql:
            raise RuntimeError("simulated manifest write failure")
        return orig_exec(sql, *a, **kw)
    conn.execute = faulty_execute
    # 文件仍应导出（manifest 失败降级）
    result = do_export(conn, tmp_project, scope="chapter", target=c1,
                       fmt="md", final=False, out=None)
    assert Path(result.path).exists()
    captured = capsys.readouterr()
    assert "manifest" in captured.err.lower() or "留痕" in captured.err
    conn.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_reader_commands.py -k export -v`
Expected: FAIL（`do_export` 未定义）

- [ ] **Step 3: 实现 do_export**

```python
# 追加到 src/bedrock/cli/reader_commands.py 顶部 import 区
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

from src.bedrock.repositories.worldbook import get_constant


# 追加到 src/bedrock/cli/reader_commands.py（render_chapter_body 之后）

@dataclass
class ExportResult:
    path: str
    content_hash: str
    chapter_count: int


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _volume_row(conn, volume_id):
    return conn.execute(
        "SELECT number, name FROM volume WHERE id=?", (volume_id,)).fetchone()


def _render_document(conn, chapters, scope, fmt, book_name):
    """渲染整篇文档（含卷/书标题）。chapters: list of sqlite row(id, global_number, volume_id)。
    对 chapter scope 不调用本函数（直接 render_chapter_body）。"""
    # 卷信息缓存 + 分组（按 volume.number 排序）
    vol_cache = {}
    def vol_info(vid):
        if vid not in vol_cache:
            vol_cache[vid] = _volume_row(conn, vid)
        return vol_cache[vid]
    for ch in chapters:
        vol_info(ch["volume_id"])
    ordered_vids = sorted(vol_cache, key=lambda vid: vol_cache[vid]["number"])

    parts = []
    if fmt == "md" and book_name:
        parts.append(f"# {book_name}")
    for vid in ordered_vids:
        vi = vol_cache[vid]
        header = (f"## 第{vi['number']}卷 {vi['name']}" if fmt == "md"
                  else f"第{vi['number']}卷 {vi['name']}")
        parts.append(header)
        vol_chs = sorted([c for c in chapters if c["volume_id"] == vid],
                         key=lambda c: c["global_number"])
        for c in vol_chs:
            parts.append(render_chapter_body(conn, c["id"], fmt))
    return "\n\n".join(parts) + "\n"


def do_export(conn, project_path, scope, target, fmt, final, out):
    """导出正文文件 + 写 export_manifest（短事务，失败降级 stderr 警告）。
    scope: 'chapter'|'volume'|'book'
    target: chapter.id | volume.id | None(book)
    返回 ExportResult。"""
    project_path = Path(project_path)
    book_name_row = get_constant(conn, "work_name")
    book_name = book_name_row["value"] if book_name_row else None

    # 收集 completed 章并确定默认文件名
    if scope == "chapter":
        ch_row = conn.execute(
            "SELECT id, global_number, volume_id FROM chapter WHERE id=?",
            (target,)).fetchone()
        if ch_row is None:
            raise SystemExit(f"chapter id={target} 不存在")
        chapters = [ch_row]
        content = render_chapter_body(conn, target, fmt)
        default_name = f"{chapter_filename(ch_row['global_number'])}.{fmt}"
    elif scope == "volume":
        chapters = conn.execute(
            "SELECT id, global_number, volume_id FROM chapter "
            "WHERE volume_id=? AND status='completed' ORDER BY global_number",
            (target,)).fetchall()
        if not chapters:
            raise SystemExit(f"卷(id={target}) 无已完成章节，不产出空文件")
        content = _render_document(conn, chapters, scope, fmt, book_name)
        v = _volume_row(conn, target)
        default_name = f"vol{v['number']}.{fmt}"
    else:  # book
        chapters = conn.execute(
            "SELECT id, global_number, volume_id FROM chapter "
            "WHERE status='completed' ORDER BY global_number").fetchall()
        if not chapters:
            raise SystemExit("全书无已完成章节")
        content = _render_document(conn, chapters, scope, fmt, book_name)
        default_name = f"book.{fmt}"

    # 落盘
    exports_dir = project_path / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    file_path = Path(out) if out else (exports_dir / default_name)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")

    if final:
        final_dir = exports_dir / "final"
        final_dir.mkdir(parents=True, exist_ok=True)
        (final_dir / file_path.name).write_text(content, encoding="utf-8")

    content_hash = _sha256_text(content)

    # manifest 留痕：独立短事务，失败降级警告（不阻断文件导出）
    target_id = target if scope != "book" else None
    global_numbers = [c["global_number"] for c in chapters]
    import json
    source_snapshot = json.dumps(
        {"chapter_count": len(chapters), "global_numbers": global_numbers,
         "paragraph_total": sum(
             len(list_paragraphs_in_chapter(conn, c["id"])) for c in chapters)},
        ensure_ascii=False)
    status = "final" if final else "draft"
    try:
        conn.execute(
            "INSERT INTO export_manifest(scope,target_id,format,content_hash,status,source_snapshot) "
            "VALUES(?,?,?,?,?,?)",
            (scope, target_id, fmt, content_hash, status, source_snapshot))
        conn.commit()
    except Exception as e:
        print(f"⚠️ export_manifest 留痕失败（文件已导出，不阻断）: {e}", file=sys.stderr)

    return ExportResult(path=str(file_path), content_hash=content_hash,
                        chapter_count=len(chapters))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_reader_commands.py -k export -v`
Expected: PASS（6 测试）

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/cli/reader_commands.py tests/bedrock/test_reader_commands.py
git commit -m "feat(bedrock): SP6-A do_export 三级scope+manifest留痕(short-tx降级)"
```

---

## Task 3: export CLI 薄封装

**Files:**
- Modify: `src/bedrock/__main__.py`

- [ ] **Step 1: 在 `main()` 的 subparser 区追加（在 `p_unlock` 之后）**

```python
    # SP6-A 只读工具集
    p_export = sub.add_parser("export", help="导出正文（paragraph→文件，单向）")
    p_export.add_argument("--project", type=Path, required=True)
    scope_x = p_export.add_mutually_exclusive_group(required=True)
    scope_x.add_argument("--chapter", type=int, help="global_number")
    scope_x.add_argument("--volume", type=int, help="volume.id")
    scope_x.add_argument("--book", action="store_true")
    p_export.add_argument("--format", choices=["md", "txt"], default="md")
    p_export.add_argument("--final", action="store_true")
    p_export.add_argument("--out", type=Path, default=None)
```

- [ ] **Step 2: 在 `args = parser.parse_args()` 后的命令分支追加（`elif args.cmd == "unlock-volume":` 块之后、`finally` 之前）**

```python
        elif args.cmd == "export":
            from src.bedrock.cli.reader_commands import do_export
            if args.book:
                scope, target = "book", None
            elif args.chapter is not None:
                cid = _chapter_id(conn, args.chapter)   # global_number → id
                scope, target = "chapter", cid
            else:
                scope, target = "volume", args.volume
            result = do_export(conn, args.project, scope, target,
                               args.format, args.final, args.out)
            print(result.path)
```

注意：`--chapter` 走 `_chapter_id`（global_number→id）与既有命令一致；`--volume` 直接用 volume.id（不经转换，与 run-watchdog 一致）。

- [ ] **Step 3: 冒烟测试 CLI**

Run: `python -m src.novel_kg.mcp_cli 2>/dev/null; cd D:/novel_test && python -m src.bedrock export --help`
（如果 `python -m src.bedrock` 不是入口，用既有方式调用。先确认既有命令怎么跑：）
Run: `cd D:/novel_test && python -c "from src.bedrock.__main__ import main" && echo ok`
Expected: ok（模块可导入）

- [ ] **Step 4: Commit**

```bash
git add src/bedrock/__main__.py
git commit -m "feat(bedrock): SP6-A export CLI 薄封装"
```

---

## Task 4: diagnose 纯函数（flag-only + --with-l2 + --book）

**Files:**
- Modify: `src/bedrock/cli/reader_commands.py`
- Test: `tests/bedrock/test_reader_commands.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/bedrock/test_reader_commands.py
from src.bedrock.cli.reader_commands import diagnose
from src.bedrock.repositories.suspense import plant_thread
from src.bedrock.repositories.plot_tree import create_beat


def _seed_volume_with_flag(conn, vol_number=1, vid=None):
    """建 1 卷 1 completed 章（落盘），返回 vid。"""
    if vid is None:
        vid = create_volume(conn, vol_number, f"卷{vol_number}", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=vol_number,
                         title="x", status="completed")
    create_paragraph(conn, chapter_id=cid, seq=1, text="一段足够长的正文内容用来测试。",
                     content_hash="h", beat_id=None, role="narration")
    return vid, cid


def test_diagnose_requires_scope(tmp_project):
    import pytest
    conn = get_connection(tmp_project)
    with pytest.raises(SystemExit):
        diagnose(conn, tmp_project, scope=None, with_l2=False)
    conn.close()


def test_diagnose_book_with_l2_mutex(tmp_project):
    import pytest
    conn = get_connection(tmp_project)
    with pytest.raises(SystemExit):
        diagnose(conn, tmp_project, scope=("book", None), with_l2=True)
    conn.close()


def test_diagnose_flag_only_has_mode_banner_and_trace(tmp_project):
    conn = get_connection(tmp_project)
    vid, cid = _seed_volume_with_flag(conn, vol_number=1)
    report = diagnose(conn, tmp_project, scope=("volume", vid), with_l2=False)
    assert "体检模式标记" in report
    assert "flag-only" in report
    assert "未对当前正文做 L2 重算" in report          # 可信度声明
    assert "flag（留痕）" in report                    # L2 来源列
    assert "diagnose-trace" in report                  # trace 注释
    conn.close()


def test_diagnose_flag_only_l2_hard_gate_column_na(tmp_project):
    """flag-only 模式 L2 hard_gate 列填 n/a（flag-only），不裸 '-'。"""
    conn = get_connection(tmp_project)
    vid, cid = _seed_volume_with_flag(conn, vol_number=1)
    report = diagnose(conn, tmp_project, scope=("volume", vid), with_l2=False)
    assert "n/a（flag-only）" in report
    conn.close()


def test_diagnose_with_l2_runs_run_l2(tmp_project):
    conn = get_connection(tmp_project)
    vid, cid = _seed_volume_with_flag(conn, vol_number=1)
    report = diagnose(conn, tmp_project, scope=("volume", vid), with_l2=True)
    assert "flag + live-L2" in report
    assert "live（当前正文）" in report               # L2 来源列
    conn.close()


def test_diagnose_does_not_write_volume_review(tmp_project):
    """【审核修订 H1】diagnose 绝不写 volume_review（不调 check_cross_volume_debt）。"""
    conn = get_connection(tmp_project)
    vid, cid = _seed_volume_with_flag(conn, vol_number=1)
    # 故意种一条本卷 high 未兑现悬链（若 diagnose 调 check_cross_volume_debt 会写 blocking=1）
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="场景目的足够长")
    plant_thread(conn, content="未兑现线索", thread_type="mystery", importance="high",
                 planted_at_beat=bid, origin="emergent", planned_resolve_volume=1)
    before = conn.execute(
        "SELECT blocking FROM volume_review WHERE volume_id=?", (vid,)).fetchone()
    report = diagnose(conn, tmp_project, scope=("volume", vid), with_l2=False)
    after = conn.execute(
        "SELECT blocking FROM volume_review WHERE volume_id=?", (vid,)).fetchone()
    # diagnose 前后 volume_review 状态不变（可能都没行，或行不变）
    assert before == after
    # 但报告里仍列出欠债（纯读 SQL 读出来）
    assert "未兑现线索" in report
    conn.close()


def test_diagnose_book_aggregates_debt(tmp_project):
    """【审核修订 H1】--book 逐卷欠债聚合：任一卷 high 未兑现 → 全书标 BLOCKING。"""
    conn = get_connection(tmp_project)
    v1, _ = _seed_volume_with_flag(conn, vol_number=1)
    v2, c2 = _seed_volume_with_flag(conn, vol_number=2)
    bid = create_beat(conn, chapter_id=c2, sequence=1, purpose="场景目的足够长")
    plant_thread(conn, content="卷2欠债", thread_type="mystery", importance="high",
                 planted_at_beat=bid, origin="emergent", planned_resolve_volume=2)
    report = diagnose(conn, tmp_project, scope=("book", None), with_l2=False)
    assert "BLOCKING" in report
    assert "卷2欠债" in report
    conn.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_reader_commands.py -k diagnose -v`
Expected: FAIL（`diagnose` 未定义）

- [ ] **Step 3: 实现 diagnose**

```python
# 追加到 src/bedrock/cli/reader_commands.py
from src.bedrock.orchestration.persist_gate import verify_chapter_persisted
from src.bedrock.orchestration.l2_pipeline import run_l2


def _read_overdue_threads(conn, volume_number):
    """【审核修订 H1】纯读 SQL：查 planned_resolve_volume<=number 且 high 且未兑现的悬链。
    不调 check_cross_volume_debt（它有写副作用）。"""
    return conn.execute(
        "SELECT id, content, importance, status FROM suspense_thread "
        "WHERE planned_resolve_volume IS NOT NULL AND planned_resolve_volume <= ? "
        "AND importance='high' AND status NOT IN ('resolved','abandoned')",
        (volume_number,)).fetchall()


def _chapter_flag_row(conn, chapter_id):
    return conn.execute(
        "SELECT l2_unresolved, polish_broke_beat, forced_persist_failed, advisory_drift "
        "FROM chapter_review_flag WHERE chapter_id=?", (chapter_id,)).fetchone()


def diagnose(conn, project_path, scope, with_l2):
    """体检报告。scope: ('volume', volume_id) | ('book', None)。
    纯读，不写 DB（不调 check_cross_volume_debt）。"""
    if scope is None:
        raise SystemExit("diagnose 必须指定 --volume 或 --book")
    if scope[0] == "book" and with_l2:
        raise SystemExit("--book 与 --with-l2 互斥（全书逐章重算太重）")

    mode = "flag + live-L2" if with_l2 else "flag-only"
    import datetime as _dt  # 仅 ISO 时间戳（不在 workflow 脚本内运行，可用）
    # 注意：本函数在 CLI 进程内运行（非 workflow JS 脚本），datetime 安全。
    now_iso = _dt.datetime.now().isoformat()

    # 确定要体检的卷
    if scope[0] == "volume":
        volumes = [conn.execute(
            "SELECT id, number, name FROM volume WHERE id=?", (scope[1],)).fetchone()]
    else:  # book
        volumes = conn.execute(
            "SELECT id, number, name FROM volume ORDER BY number").fetchall()

    lines = []
    # 顶部元数据块
    scope_desc = (f"volume {volumes[0]['number']}（id={volumes[0]['id']}）"
                  if scope[0] == "volume"
                  else f"book 全书 {len(volumes)} 卷")
    lines.append("> **⚠️ 体检模式标记 — 请先读本块**")
    lines.append(f"> - **模式**：{mode}")
    lines.append(f"> - **范围**：{scope_desc}")
    lines.append(f"> - **生成时间**：{now_iso}")
    if mode == "flag-only":
        lines.append(">")
        lines.append("> **可信度声明**：本报告基于【管线留痕旗 + chapter.status + "
                     "volume_review + 跨卷欠债】，**未对当前正文做 L2 重算**。"
                     "正文在管线跑完后若被手改，本报告**不会**反映。"
                     "如需对当前正文的独立信任检查，请用 `--volume N --with-l2` 重跑。")
    else:
        lines.append(">")
        lines.append("> **可信度声明**：本报告含对当前正文的逐章 run_l2 重算，反映正文最新状态。")
    lines.append("")

    # 卷级门禁 + 跨卷欠债
    lines.append("## 卷级门禁")
    all_debt = []
    for v in volumes:
        vr = conn.execute(
            "SELECT blocking FROM volume_review WHERE volume_id=?", (v["id"],)).fetchone()
        blocking = vr["blocking"] if vr else 0
        debt = _read_overdue_threads(conn, v["number"])
        lines.append(f"- 卷 {v['number']}(id={v['id']}): volume_review.blocking = {blocking}"
                     f"，high 未兑现悬链 {len(debt)} 条")
        all_debt.extend((v["number"], t) for t in debt)
    lines.append("")

    lines.append("## 跨卷悬链欠债")
    if all_debt:
        for vnum, t in all_debt:
            lines.append(f"- [BLOCKING] 悬链 #{t['id']}「{t['content'][:20]}」"
                         f"应于卷{t['planned_resolve_volume'] if 'planned_resolve_volume' in t.keys() else vnum}回收，"
                         f"status={t['status']}")
    else:
        lines.append("- （无 high 未兑现悬链）")
    lines.append("")

    # 章级状态矩阵
    lines.append("## 章级状态矩阵")
    lines.append("| ch | global | status | 落盘 | l2_unresolved | polish_broke_beat | "
                 "forced_persist_failed | advisory_drift | L2 hard_gate | L2 来源 |")
    lines.append("|----|--------|--------|------|---------------|-------------------|"
                 "-----------------------|----------------|--------------|---------|")
    attention = {"未落盘": [], "l2_unresolved": [], "polish_broke_beat": [],
                 "forced_persist_failed": [], "advisory_drift": []}
    for v in volumes:
        chs = conn.execute(
            "SELECT id, global_number, status FROM chapter WHERE volume_id=? "
            "ORDER BY global_number", (v["id"],)).fetchall()
        for ch in chs:
            persisted = verify_chapter_persisted(conn, ch["id"])
            flag = _chapter_flag_row(conn, ch["id"])
            if ch["status"] != "completed":
                row = (f"| {ch['id']} | {ch['global_number']} | {ch['status']} | "
                       f"{'✓' if persisted else '✗'} | - | - | - | - | n/a | n/a |")
            else:
                l2_src = "live（当前正文）" if with_l2 else "flag（留痕）"
                if with_l2:
                    l2_gate = "pass" if run_l2(conn, ch["id"]).passed_hard_gate else "fail"
                else:
                    l2_gate = "n/a（flag-only）"
                if flag is None:
                    flag = {"l2_unresolved": 0, "polish_broke_beat": 0,
                            "forced_persist_failed": 0, "advisory_drift": "{}"}
                row = (f"| {ch['id']} | {ch['global_number']} | {ch['status']} | "
                       f"{'✓' if persisted else '✗'} | {flag['l2_unresolved']} | "
                       f"{flag['polish_broke_beat']} | {flag['forced_persist_failed']} | "
                       f"{flag['advisory_drift']} | {l2_gate} | {l2_src} |")
                if not persisted:
                    attention["未落盘"].append(ch["global_number"])
                if flag["l2_unresolved"]:
                    attention["l2_unresolved"].append(ch["global_number"])
                if flag["polish_broke_beat"]:
                    attention["polish_broke_beat"].append(ch["global_number"])
                if flag["forced_persist_failed"]:
                    attention["forced_persist_failed"].append(ch["global_number"])
                if flag["advisory_drift"] not in (None, "{}"):
                    attention["advisory_drift"].append(ch["global_number"])
            lines.append(row)
    lines.append("")

    lines.append("## 需关注清单")
    for kind, chs in attention.items():
        if chs:
            lines.append(f"- {kind}：ch{chs}")
    if not any(attention.values()):
        lines.append("- （无需关注）")
    lines.append("")

    lines.append(f"<!-- diagnose-trace: mode={mode} scope={scope[0]}:{scope[1]} "
                 f"project={Path(project_path).name} generated_at={now_iso} -->")
    return "\n".join(lines) + "\n"
```

注意 `_read_overdue_threads` 的 detail 行里我引用了 `t['planned_resolve_volume']`——但 SELECT 没取该列。修正：SELECT 加 `planned_resolve_volume`。**实现时务必把该列加进 SELECT**（见下方修正）。

- [ ] **Step 4: 修正 SELECT 列**

在 `_read_overdue_threads` 的 SQL 里把 `"SELECT id, content, importance, status FROM suspense_thread "` 改为 `"SELECT id, content, importance, status, planned_resolve_volume FROM suspense_thread "`，并把 detail 行简化为 `f"应于卷{t['planned_resolve_volume']}回收"`（去掉冗余三元）。

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_reader_commands.py -k diagnose -v`
Expected: PASS（7 测试）

- [ ] **Step 6: Commit**

```bash
git add src/bedrock/cli/reader_commands.py tests/bedrock/test_reader_commands.py
git commit -m "feat(bedrock): SP6-A diagnose 纯读体检(flag-only/with-l2/book) + 自标注"
```

---

## Task 5: diagnose CLI 薄封装

**Files:**
- Modify: `src/bedrock/__main__.py`

- [ ] **Step 1: 追加 subparser（export 之后）**

```python
    p_diag = sub.add_parser("diagnose", help="体检报告（聚合留痕旗/状态/欠债，可选live L2）")
    p_diag.add_argument("--project", type=Path, required=True)
    diag_scope = p_diag.add_mutually_exclusive_group(required=True)
    diag_scope.add_argument("--volume", type=int, help="volume.id")
    diag_scope.add_argument("--book", action="store_true")
    p_diag.add_argument("--with-l2", action="store_true",
                        help="现场跑 run_l2（仅 --volume，禁 --book）")
    p_diag.add_argument("--out", type=Path, default=None)
```

- [ ] **Step 2: 追加命令分支（export 之后）**

```python
        elif args.cmd == "diagnose":
            from src.bedrock.cli.reader_commands import diagnose
            scope = ("book", None) if args.book else ("volume", args.volume)
            report = diagnose(conn, args.project, scope, with_l2=args.with_l2)
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(report, encoding="utf-8")
                print(args.out)
            else:
                print(report)
```

- [ ] **Step 3: Commit**

```bash
git add src/bedrock/__main__.py
git commit -m "feat(bedrock): SP6-A diagnose CLI 薄封装"
```

---

## Task 6: show_review_report（default + plain + escalate-only + V2 容错）

**Files:**
- Modify: `src/bedrock/cli/reader_commands.py`
- Test: `tests/bedrock/test_reader_commands.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/bedrock/test_reader_commands.py
from src.bedrock.cli.reader_commands import show_review_report

SP5_REPORT = """# VolumeReview 报告 — 卷 3

## 旗章发现（actionable）
- ch7 [is_actionable=True]: 主语缺失，代词指向不明
- ch9 [is_actionable=True]: beat 契约目的未兑现

## 修正结果（三状态）
- ch7: edited_unverified
- ch9: escalate_human
- ch12: escalate_human

## Watchdog
（无）

## 跨卷悬链欠债
（无）
"""

V2_REPORT = """# 卷三 复盘
一、总体评价：本卷节奏偏快。
2.1 林深的转变较突兀。
"""


def _write_report(project_path, vol_id, content):
    report_path = project_path / f"review_report_vol{vol_id}.md"
    report_path.write_text(content, encoding="utf-8")
    return report_path


def test_show_report_default_raw(tmp_project):
    _write_report(tmp_project, 3, SP5_REPORT)
    out = show_review_report(tmp_project, volume=3, escalate_only=False, plain=False)
    assert "旗章发现" in out
    assert out.strip() == SP5_REPORT.strip()


def test_show_report_plain_strips_markdown(tmp_project):
    _write_report(tmp_project, 3, SP5_REPORT)
    out = show_review_report(tmp_project, volume=3, escalate_only=False, plain=True)
    assert "###" not in out
    assert "**" not in out


def test_show_report_escalate_only_outcomes_primary(tmp_project):
    """【审核修订】outcomes-escalate 为主表，左连 actionable。
    ch9 有 actionable fix_instruction；ch12 在 outcomes 但 actionable 无 → 注无 fix_instruction。"""
    _write_report(tmp_project, 3, SP5_REPORT)
    out = show_review_report(tmp_project, volume=3, escalate_only=True, plain=False)
    assert "ch9" in out and "ch12" in out               # 两个 escalate 都列
    assert "beat 契约目的未兑现" in out                  # ch9 的 fix_instruction
    assert "ch12" in out                                 # ch12 无 actionable → 仍列
    # ch7 是 edited_unverified，不应出现在 escalate 清单
    # （但 "ch7" 子串可能匹配 "ch7" 在别处——用更精确断言）
    assert "escalate_human" in out


def test_show_report_escalate_only_plain_compose(tmp_project):
    _write_report(tmp_project, 3, SP5_REPORT)
    out = show_review_report(tmp_project, volume=3, escalate_only=True, plain=True)
    assert "###" not in out
    assert "ch9" in out


def test_show_report_missing_file_exits(tmp_project):
    import pytest
    with pytest.raises(SystemExit):
        show_review_report(tmp_project, volume=99, escalate_only=False, plain=False)


def test_show_report_v2_format_tolerant(tmp_project):
    """【审核修订 H5】V2 手写报告 → escalate-only 返回空 + 警告，不崩溃。"""
    _write_report(tmp_project, 3, V2_REPORT)
    out = show_review_report(tmp_project, volume=3, escalate_only=True, plain=False)
    # 不崩溃；空清单或提示
    assert "escalate" in out.lower() or "无" in out or "未检测到" in out
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_reader_commands.py -k show_report -v`
Expected: FAIL（`show_review_report` 未定义）

- [ ] **Step 3: 实现 show_review_report**

```python
# 追加到 src/bedrock/cli/reader_commands.py
import re

_OUTCOME_RE = re.compile(r"^- ch(\d+):\s*(verified_fixed|edited_unverified|escalate_human)\s*$",
                         re.MULTILINE)
_ACTIONABLE_RE = re.compile(
    r"^- ch(\d+)\s*\[is_actionable=[^\]]*\]:\s*(.+)$", re.MULTILINE)
_MD_NOISE = re.compile(r"(^#{1,6}\s+)|(\*\*)|(```)|(^\\\||^\\|)|(\|)")


def show_review_report(project_path, volume, escalate_only, plain):
    """读 review_report_vol{volume}.md（volume=volume.id，与 write-review-report 文件名一致）。
    只解析 SP5 _write_review_report 格式；V2 手写报告 escalate-only 返回空 + 警告。"""
    report_path = Path(project_path) / f"review_report_vol{volume}.md"
    if not report_path.exists():
        raise SystemExit(f"报告不存在：{report_path}（show-review-report 不生成空报告）")
    text = report_path.read_text(encoding="utf-8")

    if not escalate_only:
        return _strip_markdown(text) if plain else text

    # escalate-only：outcomes 为主表，左连 actionable
    outcomes = {int(m.group(1)): m.group(2) for m in _OUTCOME_RE.finditer(text)}
    actionable = {int(m.group(1)): m.group(2).strip() for m in _ACTIONABLE_RE.finditer(text)}
    escalate_chs = [ch for ch, st in outcomes.items() if st == "escalate_human"]

    if not escalate_chs:
        msg = ("（未检测到 SP5 格式 escalate_human 项——"
               "可能是 V2 手写报告、空卷，或确无 escalate）")
        return msg

    lines = [f"## 卷 {volume} — 需人工判决（escalate_human）", ""]
    for ch in sorted(escalate_chs):
        lines.append(f"### ch{ch}")
        fix = actionable.get(ch)
        lines.append(f"- 原发现（actionable fix_instruction）：{fix if fix else '（无 fix_instruction，可能经由 polish_broke_beat/hard_gate 触发）'}")
        lines.append(f"- 修正结果状态：escalate_human")
        lines.append("")
    result = "\n".join(lines)
    return _strip_markdown(result) if plain else result


def _strip_markdown(text):
    """去 md 噪声：行首 #、**、代码围栏、表格管道符。json 块去围栏保留内容。"""
    out = []
    for line in text.splitlines():
        line = _MD_NOISE.sub(lambda m: "" if any(m.groups()) else "", line)
        out.append(line)
    return "\n".join(out)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_reader_commands.py -k show_report -v`
Expected: PASS（6 测试）

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/cli/reader_commands.py tests/bedrock/test_reader_commands.py
git commit -m "feat(bedrock): SP6-A show_review_report (escalate-only outcomes-primary + V2容错)"
```

---

## Task 7: show-review-report CLI 薄封装

**Files:**
- Modify: `src/bedrock/__main__.py`

- [ ] **Step 1: 追加 subparser（diagnose 之后）**

```python
    p_show = sub.add_parser("show-review-report", help="读 review_report_vol{N}.md")
    p_show.add_argument("--project", type=Path, required=True)
    p_show.add_argument("--volume", type=int, required=True, help="volume.id（文件名以此定位）")
    p_show.add_argument("--escalate-only", action="store_true")
    p_show.add_argument("--plain", action="store_true")
    p_show.add_argument("--out", type=Path, default=None)
```

- [ ] **Step 2: 追加命令分支（diagnose 之后）**

注意：show-review-report 不接 conn（纯文件读），但 argparse 分支在 `conn = get_connection(...)` 之后。为避免无谓开库，可在分支内不使用 conn（已开也无害）。但若项目 DB 不存在会先崩在 get_connection——show-review-report 读的是 markdown 文件不该依赖 DB。**修正**：把 show-review-report 分支提到 `conn = get_connection(args.project)` 之前，单独处理。

实际更简：保留在 conn 块内（项目必有 DB，get_connection 不会失败），分支内不碰 conn。若 review_report 文件不在标准位置另说。采用此简化。

```python
        elif args.cmd == "show-review-report":
            from src.bedrock.cli.reader_commands import show_review_report
            out = show_review_report(args.project, args.volume,
                                     args.escalate_only, args.plain)
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(out, encoding="utf-8")
                print(args.out)
            else:
                print(out)
```

- [ ] **Step 3: Commit**

```bash
git add src/bedrock/__main__.py
git commit -m "feat(bedrock): SP6-A show-review-report CLI 薄封装"
```

---

## Task 8: detect_drift（两路 + 三路定位 + manifest key 锁 + --final 分流）

**Files:**
- Modify: `src/bedrock/cli/reader_commands.py`
- Test: `tests/bedrock/test_reader_commands.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/bedrock/test_reader_commands.py
from src.bedrock.cli.reader_commands import detect_drift, DriftReport


def test_diff_ok_after_export(tmp_project):
    conn = get_connection(tmp_project)
    v1, v2, c1, c2, c3 = _seed_multi_volume_book(conn)
    do_export(conn, tmp_project, scope="chapter", target=c1, fmt="md", final=False, out=None)
    report = detect_drift(conn, tmp_project, scope="chapter", target=c1, fmt="md", final=False)
    assert any(r["status"] == "ok" for r in report.rows)
    conn.close()


def test_diff_drifted_db_changed(tmp_project):
    """export 后改 DB 段落 → drifted，三路定位指向 DB 侧被改。"""
    conn = get_connection(tmp_project)
    v1, v2, c1, c2, c3 = _seed_multi_volume_book(conn)
    do_export(conn, tmp_project, scope="chapter", target=c1, fmt="md", final=False, out=None)
    # 改 DB 段落
    conn.execute("UPDATE paragraph SET text='被手改的正文' WHERE chapter_id=?", (c1,))
    conn.commit()
    report = detect_drift(conn, tmp_project, scope="chapter", target=c1, fmt="md", final=False)
    row = report.rows[0]
    assert row["status"] == "drifted"
    assert "DB 侧被改" in row.get("diagnosis", "")
    conn.close()


def test_diff_drifted_file_changed(tmp_project):
    """export 后手改文件 → drifted，三路定位指向文件侧被改。"""
    conn = get_connection(tmp_project)
    v1, v2, c1, c2, c3 = _seed_multi_volume_book(conn)
    result = do_export(conn, tmp_project, scope="chapter", target=c1, fmt="md", final=False, out=None)
    # 手改文件
    Path(result.path).write_text("被人手改的内容", encoding="utf-8")
    report = detect_drift(conn, tmp_project, scope="chapter", target=c1, fmt="md", final=False)
    row = report.rows[0]
    assert row["status"] == "drifted"
    assert "文件侧被手改" in row.get("diagnosis", "")
    conn.close()


def test_diff_missing_db(tmp_project):
    conn = get_connection(tmp_project)
    v1 = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=v1, global_number=1, title="x", status="completed")
    # 无段落（未落盘）
    report = detect_drift(conn, tmp_project, scope="chapter", target=cid, fmt="md", final=False)
    assert report.rows[0]["status"] == "missing_db"
    conn.close()


def test_diff_missing_file(tmp_project):
    conn = get_connection(tmp_project)
    v1, v2, c1, c2, c3 = _seed_multi_volume_book(conn)
    # 不 export，直接 diff
    report = detect_drift(conn, tmp_project, scope="chapter", target=c1, fmt="md", final=False)
    assert report.rows[0]["status"] == "missing_file"
    conn.close()


def test_diff_manifest_key_only_chapter_scope(tmp_project):
    """【审核修订 H4】该章仅 volume scope 导出过 → diff 不拿 volume hash 顶替，降级两路。"""
    conn = get_connection(tmp_project)
    v1, v2, c1, c2, c3 = _seed_multi_volume_book(conn)
    # 仅卷导出（target_id = volume.id，非 chapter.id）
    do_export(conn, tmp_project, scope="volume", target=v1, fmt="md", final=False, out=None)
    report = detect_drift(conn, tmp_project, scope="chapter", target=c1, fmt="md", final=False)
    row = report.rows[0]
    # 单章文件不存在（只导了整卷 vol1.md）→ missing_file（不误用 volume manifest）
    assert row["status"] == "missing_file"
    conn.close()


def test_diff_final_status_split(tmp_project):
    """【审核修订 H3】draft 覆盖 draft 区后，diff --final 仍基于 final manifest。"""
    conn = get_connection(tmp_project)
    v1, v2, c1, c2, c3 = _seed_multi_volume_book(conn)
    # 先 final 导出
    do_export(conn, tmp_project, scope="chapter", target=c1, fmt="md", final=True, out=None)
    # 再 draft 导出（覆盖 exports/ch01.md，不动 final 区）
    do_export(conn, tmp_project, scope="chapter", target=c1, fmt="md", final=False, out=None)
    # 改 DB → draft 区 drifted；final 区文件未变但与 DB 已偏离
    conn.execute("UPDATE paragraph SET text='改了' WHERE chapter_id=?", (c1,))
    conn.commit()
    report_final = detect_drift(conn, tmp_project, scope="chapter", target=c1, fmt="md", final=True)
    assert report_final.rows[0]["status"] == "drifted"   # final 快照与 DB 偏离被发现
    conn.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_reader_commands.py -k diff -v`
Expected: FAIL（`detect_drift`/`DriftReport` 未定义）

- [ ] **Step 3: 实现 detect_drift**

```python
# 追加到 src/bedrock/cli/reader_commands.py
@dataclass
class DriftReport:
    rows: list   # [{ch_id, global_number, db_paras, file, status, diagnosis}]


def detect_drift(conn, project_path, scope, target, fmt, final):
    """DB 段落聚合内容 ↔ 已导出文件 漂移检测。纯读。
    scope: 'chapter'|'volume'|'book'; target: chapter.id|volume.id|None。"""
    project_path = Path(project_path)
    if scope == "chapter":
        ch_ids = [target]
    elif scope == "volume":
        ch_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM chapter WHERE volume_id=? AND status='completed' "
            "ORDER BY global_number", (target,)).fetchall()]
    else:  # book
        ch_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM chapter WHERE status='completed' ORDER BY global_number").fetchall()]

    exports_dir = project_path / ("exports/final" if final else "exports")
    status_filter = "final" if final else "draft"
    rows = []
    for cid in ch_ids:
        ch = conn.execute(
            "SELECT id, global_number FROM chapter WHERE id=?", (cid,)).fetchone()
        paras = list_paragraphs_in_chapter(conn, cid)
        file_name = f"{chapter_filename(ch['global_number'])}.{fmt}"
        file_path = exports_dir / file_name

        if len(paras) == 0:
            rows.append({"ch_id": cid, "global_number": ch["global_number"],
                         "db_paras": 0, "file": str(file_path),
                         "status": "missing_db", "diagnosis": ""})
            continue
        if not file_path.exists():
            rows.append({"ch_id": cid, "global_number": ch["global_number"],
                         "db_paras": len(paras), "file": str(file_path),
                         "status": "missing_file", "diagnosis": ""})
            continue

        db_content = render_chapter_body(conn, cid, fmt)
        db_hash = _sha256_text(db_content)
        file_hash = _sha256_text(file_path.read_text(encoding="utf-8"))

        if db_hash == file_hash:
            rows.append({"ch_id": cid, "global_number": ch["global_number"],
                         "db_paras": len(paras), "file": str(file_path),
                         "status": "ok", "diagnosis": ""})
        else:
            diagnosis = _three_way_diagnose(
                conn, cid, fmt, status_filter, db_hash, file_hash)
            rows.append({"ch_id": cid, "global_number": ch["global_number"],
                         "db_paras": len(paras), "file": str(file_path),
                         "status": "drifted", "diagnosis": diagnosis})
    return DriftReport(rows=rows)


def _three_way_diagnose(conn, chapter_id, fmt, status_filter, db_hash, file_hash):
    """三路定位：db_hash / file_hash / manifest_hash。
    manifest 查询严格 (scope=chapter, target_id=chapter.id, format, status)。"""
    man = conn.execute(
        "SELECT content_hash FROM export_manifest "
        "WHERE scope='chapter' AND target_id=? AND format=? AND status=? "
        "ORDER BY id DESC LIMIT 1",
        (chapter_id, fmt, status_filter)).fetchone()
    if man is None:
        return "drifted（无该章 chapter-scope manifest，降级两路；无法定位是谁改了）"
    man_hash = man["content_hash"]
    db_eq_man = (db_hash == man_hash)
    file_eq_man = (file_hash == man_hash)
    if db_eq_man and not file_eq_man:
        return "drifted（文件侧被手改：DB 与 manifest 一致，文件被人改）"
    if file_eq_man and not db_eq_man:
        return "drifted（DB 侧被改后未重导：文件与 manifest 一致，DB 正文变了）"
    if not db_eq_man and not file_eq_man:
        return "drifted（DB 与文件都被改过）"
    return "drifted（manifest 与当前一致但 db/file 不等——罕见，检查导出原子性）"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_reader_commands.py -k diff -v`
Expected: PASS（7 测试）

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/cli/reader_commands.py tests/bedrock/test_reader_commands.py
git commit -m "feat(bedrock): SP6-A detect_drift 两路+三路定位(manifest key锁+final分流)"
```

---

## Task 9: diff CLI 薄封装 + 输出渲染

**Files:**
- Modify: `src/bedrock/cli/reader_commands.py`（渲染 DriftReport→markdown）
- Modify: `src/bedrock/__main__.py`

- [ ] **Step 1: 追加渲染函数到 reader_commands.py**

```python
# 追加到 src/bedrock/cli/reader_commands.py
def render_drift_report(report, scope_desc, fmt, final):
    lines = [f"# 漂移检测 — {scope_desc}", ""]
    lines.append(f"> 比对：DB paragraph 表（SSOT）↔ exports/{'final/' if final else'}文件")
    lines.append(f"> 格式：{fmt}（文件名据此选择）")
    lines.append(f"> 信任边界：manifest 为留痕非密码学证据，三路定位假设 manifest 未被直接篡改。")
    lines.append("")
    lines.append("| ch | global | DB段落 | 文件 | 状态 |")
    lines.append("|----|--------|--------|------|------|")
    counts = {"ok": 0, "drifted": 0, "missing_file": 0, "missing_db": 0}
    details = []
    for r in report.rows:
        mark = {"ok": "✓ ok", "drifted": "⚠️ drifted",
                "missing_file": "✗ missing_file",
                "missing_db": "✗ missing_db"}[r["status"]]
        lines.append(f"| {r['ch_id']} | {r['global_number']} | {r['db_paras']}段 | "
                     f"{Path(r['file']).name} | {mark} |")
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        if r["status"] == "drifted" and r["diagnosis"]:
            details.append(f"- **ch{r['global_number']}**: {r['diagnosis']}")
    lines.append("")
    if details:
        lines.append("## 漂移详情")
        lines.extend(details)
        lines.append("")
    lines.append("## 汇总")
    lines.append(f"- ok: {counts['ok']} / drifted: {counts['drifted']} / "
                 f"missing_file: {counts['missing_file']} / missing_db: {counts['missing_db']}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 2: 追加 diff subparser 到 __main__.py（show-review-report 之后）**

```python
    p_diff = sub.add_parser("diff", help="DB↔文件漂移检测（RC3 反向校验）")
    p_diff.add_argument("--project", type=Path, required=True)
    diff_scope = p_diff.add_mutually_exclusive_group(required=True)
    diff_scope.add_argument("--chapter", type=int, help="global_number")
    diff_scope.add_argument("--volume", type=int, help="volume.id")
    diff_scope.add_argument("--book", action="store_true")
    p_diff.add_argument("--format", choices=["md", "txt"], default="md")
    p_diff.add_argument("--final", action="store_true", help="比对 exports/final/ 区")
    p_diff.add_argument("--out", type=Path, default=None)
```

- [ ] **Step 3: 追加命令分支**

```python
        elif args.cmd == "diff":
            from src.bedrock.cli.reader_commands import detect_drift, render_drift_report
            if args.book:
                scope, target, desc = "book", None, "全书"
            elif args.chapter is not None:
                cid = _chapter_id(conn, args.chapter)
                scope, target, desc = "chapter", cid, f"ch{args.chapter}"
            else:
                scope, target, desc = "volume", args.volume, f"vol(id={args.volume})"
            report = detect_drift(conn, args.project, scope, target, args.format, args.final)
            rendered = render_drift_report(report, desc, args.format, args.final)
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(rendered, encoding="utf-8")
                print(args.out)
            else:
                print(rendered)
```

- [ ] **Step 4: 冒烟测试 CLI 整链**

Run:
```bash
cd D:/novel_test
python -c "
import sys; sys.argv=['bedrock']
from src.bedrock.__main__ import main
" 2>&1 | head -1 || true
python -m pytest tests/bedrock/test_reader_commands.py -v 2>&1 | tail -5
```
Expected: 所有 SP6-A 测试通过（约 30 个）

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/cli/reader_commands.py src/bedrock/__main__.py
git commit -m "feat(bedrock): SP6-A diff CLI + 漂移报告渲染"
```

---

## Task 10: 全量回归 + 最终复核

**Files:** 无新文件

- [ ] **Step 1: 跑全部 bedrock 测试，确认 SP1-5 无回归**

Run: `cd D:/novel_test && python -m pytest tests/bedrock/ -v 2>&1 | tail -20`
Expected: SP1-5 既有 121 测试全过 + SP6-A 新增 ~30 测试全过，0 失败（e2e 2 个默认 skip）

- [ ] **Step 2: 核对验收标准**

逐条核对 spec §10：
- [ ] 4 命令独立可运行（export/diagnose/show-review-report/diff）
- [ ] diagnose/show-review-report/diff 不写 DB（grep 实现确认无 conn.execute 写语句，仅 export 写 export_manifest）
- [ ] export manifest 短事务 + 失败降级（test_export_manifest_short_transaction_failure_warns 验证）
- [ ] 零新依赖（reader_commands.py import 仅 stdlib + 既有 src.bedrock 模块）
- [ ] diagnose 自标注（文件名/元数据块/L2 来源列/trace 注释）落实
- [ ] diff 三路定位 manifest key 锁 `(scope=chapter, target_id, format, status)`（test_diff_manifest_key_only_chapter_scope 验证）

- [ ] **Step 3: 静态检查——确认 diagnose 纯读**

Run: `cd D:/novel_test && grep -nE "conn\.(execute|commit)" src/bedrock/cli/reader_commands.py | grep -v "SELECT\|export_manifest"`
Expected: 空输出（diagnose/diff 路径无写语句；仅 do_export 写 export_manifest）

- [ ] **Step 4: 派生最终代码审核子代理**

用 superpowers:subagent-driven-development 的最终审核模式，派 general-purpose 子代理审整个 `src/bedrock/cli/reader_commands.py` + `__main__.py` 的新增分支，对照 spec §10 验收标准 + 抗博弈不变量（diagnose 纯读 / manifest key 锁 / final 分流）。子代理报告问题 → 修复 → 复核。

- [ ] **Step 5: 更新项目记忆**

更新 `C:\Users\Administrator\.claude\projects\D--novel-test\memory\bedrock-v3-status.md`：SP6-A ✅ 完成，记录命令清单与关键不变量。

- [ ] **Step 6: 最终 commit**

```bash
git add -A
git commit -m "test(bedrock): SP6-A 全量回归通过 (SP1-5 无回归) + 最终复核"
```

---

## Self-Review（plan 写完后自检）

**1. Spec 覆盖：**
- §4 export → Task 1（原语）+ Task 2（do_export）+ Task 3（CLI）✅
- §5 diagnose → Task 4（函数）+ Task 5（CLI）✅
- §6 show-review-report → Task 6（函数）+ Task 7（CLI）✅
- §7 diff → Task 8（函数）+ Task 9（CLI）✅
- §8 测试 → 每个 Task 内 TDD ✅
- §10 验收 → Task 10 ✅

**2. 抗博弈不变量贯穿：**
- diagnose 不调 check_cross_volume_debt → Task 4 Step 3 用 `_read_overdue_threads` 纯读 SQL + Task 4 test_diagnose_does_not_write_volume_review 断言 ✅
- manifest key 锁 → Task 8 `_three_way_diagnose` WHERE 子句 + test_diff_manifest_key_only_chapter_scope ✅
- final 分流 → Task 8 status_filter + test_diff_final_status_split ✅
- round-trip hash → Task 2 test_export_chapter_writes_manifest_and_file ✅

**3. 类型一致性：** chapter_filename / render_chapter_body / do_export / diagnose / show_review_report / detect_drift / DriftReport / ExportResult / render_drift_report —— 各 Task 间引用名称一致。

**4. 已知风险点（实现时注意）：**
- Task 4 Step 3 的 `_read_overdue_threads` SELECT 必须含 `planned_resolve_volume` 列（Step 4 已修正）。
- Task 4 用 `datetime.now()` 生成时间戳——本函数在 CLI 进程内运行（非 workflow JS 脚本），`datetime` 安全，无 workflow 沙箱限制。
- Task 7 show-review-report 分支在 conn 块内但不碰 conn——若担心 get_connection 对无 DB 项目失败，可后续优化（当前项目必有 DB，不阻塞）。
