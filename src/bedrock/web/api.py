# src/bedrock/web/api.py
"""SPA 工作台 /api 蓝图。全部 JSON，按 work_id 作用域。路径穿越校验 + 每请求 conn。

SP6-C htmx 时代的 /report Markdown 渲染 + escalate 高亮逻辑保留到 api_report（共用 reader_commands.parse_review_outcomes）。
本模块只读：list_works / overview_stats / chapter_text / outline_tree / pov_matrix / list_characters /
worldbook_overview / list_factions / list_inspirations。写端点见 P1-T7。
"""
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

bp = Blueprint("api", __name__, url_prefix="/api")

_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _resolve_work(work_id):
    """work_id → project_dir Path。路径穿越/无 db → abort 404。

    work_id 必须是纯目录名（无分隔符、非 . / ..、非 Windows 盘符），且 resolve 后仍在 projects_root 内，
    且对应目录存在 bedrock.db（= 合法 bedrock work）。
    """
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


def _parse_consumed_into(item):
    """consumed_into 是 JSON 字符串（list of {target_type, target_id}），API 层解析为 list 给前端。"""
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
    conn = get_connection(wd)
    try:
        return jsonify(overview_stats(conn))
    finally:
        conn.close()


@bp.get("/works/<work_id>/matrix")
def api_matrix(work_id):
    wd = _resolve_work(work_id)
    vid = request.args.get("volume", type=int)
    conn = get_connection(wd)
    try:
        data = pov_matrix(conn, vid) if vid else None
        if data:
            for ch in data["chapters"]:
                ch["povs"] = sorted(list(ch["povs"]))  # set → list（JSON 不可序列化 set）
        return jsonify(data)
    finally:
        conn.close()


@bp.get("/works/<work_id>/inspirations")
def api_inspirations(work_id):
    wd = _resolve_work(work_id)
    tf = request.args.get("type") or None
    sf = request.args.get("status") or None
    conn = get_connection(wd)
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
    conn = get_connection(wd)
    try:
        rows = conn.execute(
            "SELECT c.global_number, c.title, c.status, v.id vid, v.name vname "
            "FROM chapter c JOIN volume v ON c.volume_id=v.id ORDER BY c.global_number").fetchall()
        return jsonify([{"global_number": r["global_number"], "title": r["title"], "status": r["status"],
                         "volume_id": r["vid"], "volume_name": r["vname"]} for r in rows])
    finally:
        conn.close()


@bp.get("/works/<work_id>/chapters/<int:gnum>/text")
def api_chapter_text(work_id, gnum):
    wd = _resolve_work(work_id)
    conn = get_connection(wd)
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
    conn = get_connection(wd)
    try:
        return jsonify(outline_tree(conn, vid))
    finally:
        conn.close()


@bp.get("/works/<work_id>/characters")
def api_characters(work_id):
    wd = _resolve_work(work_id)
    conn = get_connection(wd)
    try:
        return jsonify(list_characters(conn))
    finally:
        conn.close()


@bp.get("/works/<work_id>/factions")
def api_factions(work_id):
    wd = _resolve_work(work_id)
    conn = get_connection(wd)
    try:
        return jsonify(list_factions(conn))
    finally:
        conn.close()


# 引用占位，避免 linter 抱怨未用（worldbook_overview 已被 overview_stats 内嵌使用，
# 此处显式 re-export 供未来 worldbook 独立端点复用）。
__all__ = ["bp", "worldbook_overview"]
