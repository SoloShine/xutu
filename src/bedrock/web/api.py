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
from src.bedrock.repositories.outline import (
    list_inspirations, advance_inspiration, update_inspiration_content,
    update_master_outline, update_beat_contract, OutlineLockedError,
)
from src.bedrock.repositories.character import update_character
from src.bedrock.repositories.plot_tree import (
    update_chapter_meta, update_volume_meta, update_beat_meta, update_beat_status,
)
from src.bedrock.repositories.worldbook import update_location, update_theme, update_motif
from src.bedrock.style.template_repo import (
    list_fingerprints, set_style_config, dim_definitions, save_fingerprint_from_text,
)
from src.bedrock.checks.style_drift import measure_work_actual

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


@bp.get("/works/<work_id>/matrix/beats")
def api_matrix_beats(work_id):
    wd = _resolve_work(work_id)
    cid = request.args.get("chapter", type=int)
    chid = request.args.get("character", type=int)
    conn = get_connection(wd)
    try:
        rows = conn.execute(
            "SELECT sequence, purpose, status, deviation_note FROM beat "
            "WHERE chapter_id=? AND pov_character_id=? ORDER BY sequence",
            (cid, chid)).fetchall()
        return jsonify([dict(r) for r in rows])
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
            "SELECT c.id, c.global_number, c.title, c.status, v.id vid, v.name vname "
            "FROM chapter c JOIN volume v ON c.volume_id=v.id ORDER BY c.global_number").fetchall()
        return jsonify([{"id": r["id"], "global_number": r["global_number"], "title": r["title"],
                         "status": r["status"], "volume_id": r["vid"], "volume_name": r["vname"]} for r in rows])
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


@bp.get("/works/<work_id>/style")
def api_style(work_id):
    """文风指纹 + 配置(作品级 + 卷级) + 维度定义。Polish 据指纹微调;directive 注入 writer。"""
    wd = _resolve_work(work_id)
    conn = get_connection(wd)
    try:
        return jsonify({
            "configs": list_fingerprints(conn),
            "dim_definitions": dim_definitions(),
        })
    finally:
        conn.close()


@bp.get("/works/<work_id>/style/actual")
def api_style_actual(work_id):
    """当前实测指纹(live extract 已写章节 9维 + 标量)。与目标指纹对照。?volume=N 限单卷。"""
    wd = _resolve_work(work_id)
    vid = request.args.get("volume", type=int)
    conn = get_connection(wd)
    try:
        return jsonify(measure_work_actual(conn, vid))
    finally:
        conn.close()


@bp.post("/works/<work_id>/style/preview-reference")
def api_style_preview_ref(work_id):
    """预览参考作品:切章信息(总章数/是否切片/样章标题/字数),不存。body: {text}。"""
    _require_json()
    body = request.get_json(silent=True) or {}
    text = body.get("text")
    if not text:
        return _err("需 text(参考作品正文)")
    from src.bedrock.style.reference_import import preview_chapters
    return jsonify(preview_chapters(text))


@bp.post("/works/<work_id>/style/import-reference")
def api_style_import(work_id):
    """导入参考作品 → 提取文风指纹+派生指令。body: {path 或 text, scope, volume_id?, sample?, chapter_range?}。
    path=服务端读本地文件(自带编码探测);text=已读好的正文(浏览器 FileReader)。纯程序零LLM。"""
    _require_json()
    wd = _resolve_work(work_id)
    body = request.get_json(silent=True) or {}
    scope = body.get("scope", "work")
    if scope not in ("work", "volume"):
        return _err("scope 必须 work|volume")
    if body.get("text"):
        text = body["text"]
        source_work = body.get("source_work") or "外部参考"
    elif body.get("path"):
        from pathlib import Path
        p = Path(body["path"])
        if not p.is_file():
            return _err(f"文件不存在: {body['path']}")
        from src.bedrock.style.reference_import import decode_bytes
        text = decode_bytes(p.read_bytes())
        source_work = p.stem
    else:
        return _err("需 path 或 text")
    conn = get_connection(wd)
    try:
        cr = body.get("chapter_range")
        rid, meta, seeded = save_fingerprint_from_text(
            conn, scope=scope, text=text,
            volume_id=body.get("volume_id") if scope == "volume" else None,
            source_work=source_work, sample=body.get("sample"),
            chapter_range=cr)
        return _ok({"id": rid, "source_work": source_work, "directive_seeded": seeded, **meta})
    except Exception as e:
        return _err(e)
    finally:
        conn.close()


@bp.post("/works/<work_id>/style")
def api_set_style(work_id):
    """改文风配置(directive/word_count_target/max_edit_rounds/hygiene/enabled_dims)。
    body: {scope:'work'|'volume', volume_id?, directive?, ...}。只更新给出的字段。"""
    _require_json()
    wd = _resolve_work(work_id)
    body = request.get_json(silent=True) or {}
    scope = body.get("scope", "work")
    if scope not in ("work", "volume"):
        return _err("scope 必须 work|volume")
    conn = get_connection(wd)
    try:
        rid = set_style_config(
            conn, scope, volume_id=body.get("volume_id"),
            directive=body.get("directive"),
            word_count_target=body.get("word_count_target"),
            max_edit_rounds=body.get("max_edit_rounds"),
            hygiene=body.get("hygiene"),
            enabled_dims=body.get("enabled_dims"),
            scalar_targets=body.get("scalar_targets"),
        )
        return _ok({"id": rid, "scope": scope})
    except Exception as e:
        return _err(e)
    finally:
        conn.close()


# 引用占位，避免 linter 抱怨未用（worldbook_overview 已被 overview_stats 内嵌使用，
# 此处显式 re-export 供未来 worldbook 独立端点复用）。
__all__ = ["bp", "worldbook_overview"]


# --- P1-T7: write 端点 ---

def _require_json():
    if not request.is_json:
        abort(415)


def _ok(item):
    return jsonify({"ok": True, "item": item})


def _err(msg):
    return jsonify({"ok": False, "error": str(msg)})


def _run(mutator):
    """跑写函数；ValueError/锁异常/其他业务错 → {ok:false}；成功 → {ok,item}。"""
    try:
        return _ok(mutator())
    except Exception as e:  # ValueError / OutlineLockedError / 其他业务错
        return _err(e)


@bp.post("/works/<work_id>/inspirations/<int:iid>/advance")
def api_advance(work_id, iid):
    _require_json()
    wd = _resolve_work(work_id)
    target = (request.get_json(silent=True) or {}).get("target")
    conn = get_connection(wd)
    try:
        return _run(lambda: advance_inspiration(conn, iid, target))
    finally:
        conn.close()


@bp.patch("/works/<work_id>/inspirations/<int:iid>")
def api_edit_inspiration(work_id, iid):
    _require_json()
    wd = _resolve_work(work_id)
    body = request.get_json(silent=True) or {}
    conn = get_connection(wd)
    try:
        return _run(lambda: update_inspiration_content(conn, iid, body.get("content"), source=body.get("source")))
    finally:
        conn.close()


def _patch_entity(work_id, key, fn):
    _require_json()
    wd = _resolve_work(work_id)
    body = request.get_json(silent=True) or {}
    conn = get_connection(wd)
    try:
        return _run(lambda: fn(conn, key, **body))
    finally:
        conn.close()


@bp.patch("/works/<work_id>/characters/<int:eid>")
def api_edit_character(work_id, eid):
    _require_json(); wd = _resolve_work(work_id); body = request.get_json(silent=True) or {}
    conn = get_connection(wd)
    try:
        return _run(lambda: update_character(conn, eid, **body))
    finally:
        conn.close()


@bp.patch("/works/<work_id>/chapters/<int:eid>")
def api_edit_chapter(work_id, eid):
    return _patch_entity(work_id, eid, update_chapter_meta)


@bp.patch("/works/<work_id>/volumes/<int:eid>")
def api_edit_volume(work_id, eid):
    return _patch_entity(work_id, eid, update_volume_meta)


@bp.patch("/works/<work_id>/locations/<int:eid>")
def api_edit_location(work_id, eid):
    return _patch_entity(work_id, eid, update_location)


@bp.patch("/works/<work_id>/themes/<name>")
def api_edit_theme(work_id, name):
    # theme 无 id，按 name(PK) 键
    return _patch_entity(work_id, name, update_theme)


@bp.patch("/works/<work_id>/motifs/<name>")
def api_edit_motif(work_id, name):
    return _patch_entity(work_id, name, update_motif)


@bp.patch("/works/<work_id>/beats/<int:eid>")
def api_edit_beat(work_id, eid):
    _require_json(); wd = _resolve_work(work_id); body = request.get_json(silent=True) or {}
    conn = get_connection(wd)
    try:
        def go():
            if "status" in body or "deviation_note" in body:
                update_beat_status(conn, eid, body.get("status"), body.get("deviation_note"))
            meta = {k: body[k] for k in ("purpose", "scene_setting") if k in body}
            if meta:
                update_beat_meta(conn, eid, **meta)
            return dict(conn.execute("SELECT * FROM beat WHERE id=?", (eid,)).fetchone())
        return _run(go)
    finally:
        conn.close()


@bp.patch("/works/<work_id>/volumes/<int:vid>/beats/<int:bid>/contract")
def api_edit_beat_contract(work_id, vid, bid):
    _require_json(); wd = _resolve_work(work_id); body = request.get_json(silent=True) or {}
    conn = get_connection(wd)
    try:
        return _run(lambda: (update_beat_contract(conn, vid, bid, body), {"volume_id": vid, "beat_id": bid})[1])
    finally:
        conn.close()


@bp.patch("/works/<work_id>/master_outline")
def api_edit_master_outline(work_id):
    _require_json(); wd = _resolve_work(work_id); body = request.get_json(silent=True) or {}
    conn = get_connection(wd)
    try:
        return _run(lambda: update_master_outline(conn, **body))
    finally:
        conn.close()
