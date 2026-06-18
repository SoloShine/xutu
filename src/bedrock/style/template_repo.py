# src/bedrock/style/template_repo.py
import json
from src.bedrock.repositories.plot_tree import list_paragraphs_in_chapter
from src.bedrock.repositories.telemetry import save_style_template
from src.bedrock.style.extractor import extract_fingerprint, DIM_DEFINITIONS

# 代码默认(无 DB 行时的 fallback)。这些值历史上硬编码在 boot_context,现上提可配。
_DEFAULT_WORD_COUNT = [3000, 5000]
_DEFAULT_MAX_EDIT_ROUNDS = 3
_DEFAULT_HYGIENE = {"notXisY_max": 0, "dash_max_per_k": 5}  # notXisY 目标 0;破折号每千字上限


def _gather_paragraphs(conn, chapter_ids):
    """收集这些章节的所有 paragraph.text。"""
    paragraphs = []
    for cid in chapter_ids:
        for p in list_paragraphs_in_chapter(conn, cid):
            paragraphs.append(p["text"])
    return paragraphs


def save_fingerprint(conn, scope, chapter_ids, volume_id=None):
    """提取并 upsert style_template 的 fingerprint(真列 scope/volume_id)。
    upsert:同 scope(+volume_id)行存在→只更新 fingerprint/sample/source,保留 directive/knobs;
    不存在→新建。避免重复行,且 re-extract 不 wipes 用户编辑的指令/旋钮。"""
    paragraphs = _gather_paragraphs(conn, chapter_ids)
    fingerprint = extract_fingerprint(paragraphs)
    fingerprint["_scope"] = scope
    if scope == "volume" and volume_id is not None:
        fingerprint["_volume_id"] = volume_id
    if scope == "volume" and volume_id is not None:
        row = conn.execute(
            "SELECT id FROM style_template WHERE scope='volume' AND volume_id=? ORDER BY id DESC LIMIT 1",
            (volume_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM style_template WHERE scope='work' ORDER BY id DESC LIMIT 1").fetchone()
    fp_json = json.dumps(fingerprint, ensure_ascii=False)
    if row:
        conn.execute(
            "UPDATE style_template SET fingerprint=?, source_works=?, sample_chapters=? WHERE id=?",
            (fp_json, json.dumps([scope], ensure_ascii=False),
             json.dumps(list(chapter_ids), ensure_ascii=False), row["id"]))
        conn.commit()
        return row["id"]
    return save_style_template(
        conn, fingerprint=fingerprint, source_works=[scope], sample_chapters=chapter_ids,
        scope=scope, volume_id=volume_id if scope == "volume" else None)


def _row_by_scope(conn, scope, volume_id):
    """按真列 scope/volume_id 取行(卷级优先)。"""
    if scope == "volume" and volume_id is not None:
        r = conn.execute(
            "SELECT * FROM style_template WHERE scope='volume' AND volume_id=? "
            "ORDER BY id DESC LIMIT 1", (volume_id,)).fetchone()
        if r:
            return r
    return conn.execute(
        "SELECT * FROM style_template WHERE scope='work' ORDER BY id DESC LIMIT 1").fetchone()


def get_effective_fingerprint(conn, volume_id):
    """两级 fallback：卷级 → 作品级 → None。"""
    for scope in ("volume", "work"):
        r = _row_by_scope(conn, scope, volume_id) if scope == "volume" else _row_by_scope(conn, "work", None)
        if r and r["fingerprint"] and r["fingerprint"] != "{}":
            return json.loads(r["fingerprint"])
    return None


def get_style_config(conn, volume_id):
    """合并后的 style 配置(卷级覆盖 → 作品级 → 代码默认)。
    返回 {scope, source_work, fingerprint, directive, word_count_target,
          max_edit_rounds, hygiene, enabled_dims, has_row}。"""
    r = _row_by_scope(conn, "volume", volume_id) or _row_by_scope(conn, "work", None)
    if not r:
        return {"has_row": False, "scope": None, "fingerprint": None,
                "directive": "", "word_count_target": _DEFAULT_WORD_COUNT,
                "max_edit_rounds": _DEFAULT_MAX_EDIT_ROUNDS, "hygiene": _DEFAULT_HYGIENE,
                "enabled_dims": [], "source_work": None}
    fp = json.loads(r["fingerprint"]) if r["fingerprint"] and r["fingerprint"] != "{}" else None
    src = json.loads(r["source_works"]) if r["source_works"] else []
    return {
        "has_row": True,
        "scope": r["scope"],
        "volume_id": r["volume_id"],
        "source_work": src[0] if src else (fp.get("_source_work") if fp else None),
        "fingerprint": fp,
        "directive": r["directive"] or "",
        "word_count_target": json.loads(r["word_count_target"]) if r["word_count_target"] else _DEFAULT_WORD_COUNT,
        "max_edit_rounds": r["max_edit_rounds"] if r["max_edit_rounds"] else _DEFAULT_MAX_EDIT_ROUNDS,
        "hygiene": json.loads(r["hygiene"]) if r["hygiene"] else _DEFAULT_HYGIENE,
        "enabled_dims": json.loads(r["enabled_dims"]) if r["enabled_dims"] else [],
    }


def set_style_config(conn, scope, volume_id=None, *, directive=None, word_count_target=None,
                     max_edit_rounds=None, hygiene=None, enabled_dims=None):
    """upsert 文风配置(只更新非 None 字段)。行不存在则建(scope/volume_id 匹配)。"""
    # 找既有行
    if scope == "volume":
        row = conn.execute(
            "SELECT id FROM style_template WHERE scope='volume' AND volume_id=? "
            "ORDER BY id DESC LIMIT 1", (volume_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM style_template WHERE scope='work' ORDER BY id DESC LIMIT 1").fetchone()
    fields, vals = [], []
    if directive is not None:
        fields.append("directive=?"); vals.append(directive)
    if word_count_target is not None:
        fields.append("word_count_target=?"); vals.append(json.dumps(word_count_target))
    if max_edit_rounds is not None:
        fields.append("max_edit_rounds=?"); vals.append(int(max_edit_rounds))
    if hygiene is not None:
        fields.append("hygiene=?"); vals.append(json.dumps(hygiene, ensure_ascii=False))
    if enabled_dims is not None:
        fields.append("enabled_dims=?"); vals.append(json.dumps(enabled_dims, ensure_ascii=False))
    if row:
        if fields:
            vals.append(row["id"])
            conn.execute(f"UPDATE style_template SET {', '.join(fields)} WHERE id=?", vals)
            conn.commit()
        return row["id"]
    # 无行:新建一行(指纹空,只存旋钮;指纹可后 extract 灌)
    cols = ["scope", "volume_id", "fingerprint"] + [f.split("=?")[0] for f in fields]
    placeholders = ",".join("?" * len(cols))
    params = [scope, volume_id if scope == "volume" else None, "{}"] + vals
    cur = conn.execute(
        f"INSERT INTO style_template({','.join(cols)}) VALUES ({placeholders})", params)
    conn.commit()
    return cur.lastrowid


def list_fingerprints(conn, scope=None):
    """列指纹+配置（可选按 scope 过滤）。"""
    rows = conn.execute("SELECT * FROM style_template ORDER BY id").fetchall()
    out = []
    for r in rows:
        fp = json.loads(r["fingerprint"])
        if r["scope"]:
            fp["_scope"] = r["scope"]
        if r["scope"] == "volume" and r["volume_id"] is not None:
            fp["_volume_id"] = r["volume_id"]
        if r["directive"]:
            fp["_directive"] = r["directive"]
        if scope is None or fp.get("_scope") == scope:
            out.append(fp)
    return out


def delete_volume_fingerprint(conn, volume_id):
    """I1 upsert 助手：删除某 volume 的卷级指纹行（调用方在 save_fingerprint 前调）。
    作品级指纹不动。"""
    rows = conn.execute("SELECT id, fingerprint FROM style_template").fetchall()
    to_delete = []
    for r in rows:
        fp = json.loads(r["fingerprint"])
        if fp.get("_scope") == "volume" and fp.get("_volume_id") == volume_id:
            to_delete.append(r["id"])
    if to_delete:
        placeholders = ",".join("?" * len(to_delete))
        conn.execute(f"DELETE FROM style_template WHERE id IN ({placeholders})", to_delete)
        conn.commit()


def dim_definitions():
    """维度定义(公式/含义),供 API/前端可解释化。"""
    return DIM_DEFINITIONS
