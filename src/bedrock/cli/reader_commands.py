"""SP6-A 只读 CLI 工具集：export / diagnose / show_review_report / diff 的纯函数。
diagnose / show_review_report / diff 完全不写 DB；export 仅写 export_manifest（短事务）。
正文 SSOT = paragraph 表，export 单向导出绝不回填。"""
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from src.bedrock.repositories.plot_tree import list_paragraphs_in_chapter
from src.bedrock.repositories.worldbook import get_constant


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


def _warn_skipped(conn, scope, target):
    """volume/book scope 查询非 completed 章并打 stderr 跳过清单。
    chapter scope 不调用（单章是否 completed 由调用方决定，不在此处跳过）。"""
    if scope == "volume":
        skipped = conn.execute(
            "SELECT global_number, status FROM chapter "
            "WHERE volume_id=? AND status!='completed' ORDER BY global_number",
            (target,)).fetchall()
    else:  # book
        skipped = conn.execute(
            "SELECT global_number, status FROM chapter "
            "WHERE status!='completed' ORDER BY global_number").fetchall()
    for row in skipped:
        print(f"⚠️ 跳过 ch{row['global_number']:02d}（status={row['status']}）",
              file=sys.stderr)


def _render_document(conn, chapters, fmt, book_name):
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
        _warn_skipped(conn, scope, target)
        chapters = conn.execute(
            "SELECT id, global_number, volume_id FROM chapter "
            "WHERE volume_id=? AND status='completed' ORDER BY global_number",
            (target,)).fetchall()
        if not chapters:
            raise SystemExit(f"卷(id={target}) 无已完成章节，不产出空文件")
        content = _render_document(conn, chapters, fmt, book_name)
        v = _volume_row(conn, target)
        default_name = f"vol{v['number']}.{fmt}"
    else:  # book
        _warn_skipped(conn, scope, target)
        chapters = conn.execute(
            "SELECT id, global_number, volume_id FROM chapter "
            "WHERE status='completed' ORDER BY global_number").fetchall()
        if not chapters:
            raise SystemExit("全书无已完成章节")
        content = _render_document(conn, chapters, fmt, book_name)
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
