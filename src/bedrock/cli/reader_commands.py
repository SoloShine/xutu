"""SP6-A 只读 CLI 工具集：export / diagnose / show_review_report / diff 的纯函数。
diagnose / show_review_report / diff 完全不写 DB；export 仅写 export_manifest（短事务）。
正文 SSOT = paragraph 表，export 单向导出绝不回填。"""
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from src.bedrock.repositories.plot_tree import list_paragraphs_in_chapter
from src.bedrock.repositories.worldbook import get_constant
from src.bedrock.orchestration.persist_gate import verify_chapter_persisted
from src.bedrock.orchestration.l2_pipeline import run_l2


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
    import datetime as _dt   # CLI 进程内，datetime 安全（非 workflow JS 脚本）
    source_snapshot = json.dumps(
        {"chapter_count": len(chapters), "global_numbers": global_numbers,
         "paragraph_total": sum(
             len(list_paragraphs_in_chapter(conn, c["id"])) for c in chapters),
         "rendered_at_iso": _dt.datetime.now().isoformat()},
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


def _read_overdue_threads(conn, volume_number):
    """【只读】查 planned_resolve_volume<=number 且 high 且未兑现的悬链。
    绝不调 check_cross_volume_debt（它有写副作用，会污染 volume_review）。"""
    return conn.execute(
        "SELECT id, content, importance, status, planned_resolve_volume FROM suspense_thread "
        "WHERE planned_resolve_volume IS NOT NULL AND planned_resolve_volume <= ? "
        "AND importance='high' AND status NOT IN ('resolved','abandoned')",
        (volume_number,)).fetchall()


def _chapter_flag_row(conn, chapter_id):
    return conn.execute(
        "SELECT l2_unresolved, polish_broke_beat, forced_persist_failed, advisory_drift "
        "FROM chapter_review_flag WHERE chapter_id=?", (chapter_id,)).fetchone()


def diagnose(conn, project_path, scope, with_l2):
    """体检报告。scope: ('volume', volume_id) | ('book', None) | None。
    纯读，不写 DB。"""
    if scope is None:
        raise SystemExit("diagnose 必须指定 --volume 或 --book")
    if scope[0] == "book" and with_l2:
        raise SystemExit("--book 与 --with-l2 互斥（全书逐章重算太重）")

    mode = "flag + live-L2" if with_l2 else "flag-only"
    import datetime as _dt   # 本函数在 CLI 进程内运行（非 workflow JS 脚本），datetime 安全
    now_iso = _dt.datetime.now().isoformat()

    if scope[0] == "volume":
        volumes = [conn.execute(
            "SELECT id, number, name FROM volume WHERE id=?", (scope[1],)).fetchone()]
    else:  # book
        volumes = conn.execute(
            "SELECT id, number, name FROM volume ORDER BY number").fetchall()

    lines = []
    scope_desc = (f"volume {volumes[0]['number']}（id={volumes[0]['id']}）"
                  if scope[0] == "volume"
                  else f"book 全书 {len(volumes)} 卷")
    lines.append("> **⚠️ 体检模式标记 — 请先读本块**")
    lines.append(f"> - **模式**：{mode}")
    lines.append(f"> - **范围**：{scope_desc}")
    lines.append(f"> - **生成时间**：{now_iso}")
    lines.append(">")
    if mode == "flag-only":
        lines.append("> **可信度声明**：本报告基于【管线留痕旗 + chapter.status + "
                     "volume_review + 跨卷欠债】，**未对当前正文做 L2 重算**。"
                     "正文在管线跑完后若被手改，本报告**不会**反映。"
                     "如需对当前正文的独立信任检查，请用 `--volume N --with-l2` 重跑。")
    else:
        lines.append("> **可信度声明**：本报告含对当前正文的逐章 run_l2 重算，反映正文最新状态。")
    lines.append("")

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
                         f"应于卷{t['planned_resolve_volume']}回收，status={t['status']}")
    else:
        lines.append("- （无 high 未兑现悬链）")
    lines.append("")

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

    scope_trace = scope[0] if scope[0] == "book" else f"{scope[0]}:{scope[1]}"
    lines.append(f"<!-- diagnose-trace: mode={mode} scope={scope_trace} "
                 f"project={Path(project_path).name} generated_at={now_iso} -->")
    return "\n".join(lines) + "\n"


# ---- show_review_report (SP6-A Task 6) ----

_OUTCOME_RE = re.compile(
    r"^- ch(\d+):\s*(verified_fixed|edited_unverified|escalate_human)\s*$",
    re.MULTILINE)
_ACTIONABLE_RE = re.compile(
    r"^- ch(\d+)\s*\[is_actionable=[^\]]*\]:\s*(.+)$", re.MULTILINE)
_MD_NOISE = re.compile(r"(^#{1,6}\s+)|(\*\*)|(```)|(\|)")


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
    actionable = {int(m.group(1)): m.group(2).strip()
                  for m in _ACTIONABLE_RE.finditer(text)}
    escalate_chs = [ch for ch, st in outcomes.items() if st == "escalate_human"]

    if not escalate_chs:
        msg = ("（未检测到 SP5 格式 escalate_human 项——"
               "可能是 V2 手写报告、空卷，或确无 escalate）")
        return msg

    lines = [f"## 卷 {volume} — 需人工判决（escalate_human）", ""]
    for ch in sorted(escalate_chs):
        lines.append(f"### ch{ch}")
        fix = actionable.get(ch)
        lines.append(
            f"- 原发现（actionable fix_instruction）："
            f"{fix if fix else '（无 fix_instruction，可能经由 polish_broke_beat/hard_gate 触发）'}")
        lines.append(f"- 修正结果状态：escalate_human")
        lines.append("")
    result = "\n".join(lines)
    return _strip_markdown(result) if plain else result


def _strip_markdown(text):
    """去 md 噪声：行首 #、**、代码围栏、表格管道符。json 块去围栏保留内容。"""
    out = []
    for line in text.splitlines():
        line = _MD_NOISE.sub("", line)
        out.append(line)
    return "\n".join(out)


# ---- detect_drift (SP6-A Task 8) ----

@dataclass
class DriftReport:
    rows: list   # [{ch_id, global_number, db_paras, file, status, diagnosis}]


def detect_drift(conn, project_path, scope, target, fmt, final):
    """DB 段落聚合内容 ↔ 已导出文件 漂移检测。纯读，不写 DB。
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
    """三路定位：db_hash / file_hash / manifest_hash。纯读，不写 DB。
    manifest 查询严格 (scope='chapter' AND target_id=chapter.id AND format AND status)，
    绝不用 volume/book scope 的 hash 顶替单章（整卷/全书 hash 与单章不可比）。"""
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


def render_drift_report(report, scope_desc, fmt, final):
    """DriftReport → markdown 报告。纯渲染，不读 DB/文件。"""
    lines = [f"# 漂移检测 — {scope_desc}", ""]
    lines.append(f"> 比对：DB paragraph 表（SSOT）↔ exports/{'final/' if final else ''}文件")
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
