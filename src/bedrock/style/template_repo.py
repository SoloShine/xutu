# src/bedrock/style/template_repo.py
import json
from src.bedrock.repositories.plot_tree import list_paragraphs_in_chapter
from src.bedrock.repositories.telemetry import save_style_template
from src.bedrock.style.extractor import extract_fingerprint, DIM_DEFINITIONS

# 代码默认(无 DB 行时的 fallback)。这些值历史上硬编码在 boot_context,现上提可配。
_DEFAULT_WORD_COUNT = [3000, 5000]
_DEFAULT_MAX_EDIT_ROUNDS = 3
_DEFAULT_HYGIENE = {"notXisY_max": 0, "dash_max_per_k": 5}  # notXisY 目标 0;破折号每千字上限


def _norm_source(s):
    """归一化参考来源名用于 stale 比对:去首尾空白 + 剥常见后缀(.txt/.json/.md)。
    不同写入路径命名不一致(路径导入用 p.stem 剥 .txt,/analyze-style 可能带 .txt),
    严格相等会误报 stale。比对的是'参考作品换没换',不是文件名字符串漂移。"""
    if not s:
        return s
    s = s.strip()
    low = s.lower()
    for ext in (".txt", ".json", ".md"):
        if low.endswith(ext):
            s = s[:-len(ext)]
            break
    return s



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


def _upsert_base(conn, scope, volume_id, fp, source_work, reference_sample=None,
                 directive_to_set=None):
    """指纹 base 的共享 upsert(参考导入 / 本作已写 复用)。
    UPDATE 仅 fingerprint/source_works/reference_sample(可选 directive),**不动 scalar_targets/旋钮**——
    这正是"base + 覆盖层"分离:re-extract/换 base 只更底,手动标量覆盖(scalar_targets)保留。
    无行→建行。返回 row_id。"""
    fp["_scope"] = scope
    fp["_source_work"] = source_work
    if scope == "volume" and volume_id is not None:
        fp["_volume_id"] = volume_id
    row = _row_by_scope(conn, scope, volume_id)
    fp_json = json.dumps(fp, ensure_ascii=False)
    if row:
        sets = ["fingerprint=?", "source_works=?"]
        vals = [fp_json, json.dumps([source_work], ensure_ascii=False)]
        if reference_sample is not None:
            sets.append("reference_sample=?"); vals.append(reference_sample)
        if directive_to_set:
            sets += ["directive=?", "directive_source=?"]; vals += [directive_to_set, source_work]
        vals.append(row["id"])
        conn.execute(f"UPDATE style_template SET {', '.join(sets)} WHERE id=?", vals)
        conn.commit()
        return row["id"]
    rid = save_style_template(conn, fingerprint=fp, source_works=[source_work],
                              scope=scope, volume_id=volume_id if scope == "volume" else None)
    extra_sets, extra_vals = "", []
    if reference_sample is not None:
        extra_sets += ", reference_sample=?"; extra_vals.append(reference_sample)
    if directive_to_set:
        extra_sets += ", directive=?, directive_source=?"; extra_vals += [directive_to_set, source_work]
    if extra_sets:
        conn.execute(f"UPDATE style_template SET {extra_sets[2:]} WHERE id=?", [*extra_vals, rid])
        conn.commit()
    return rid


def save_fingerprint_from_text(conn, scope, text, volume_id=None, source_work=None,
                               sample=None, chapter_range=None, strategy="spread",
                               derive_directive_flag=True):
    """从外部参考全文提取指纹并 upsert(保留 scalar_targets/旋钮)。纯程序,零 LLM。
    chapter_range=[start,end] 1-based;strategy=spread|consecutive|random|all。
    返回 (row_id, meta, directive_seeded)。"""
    from src.bedrock.style.reference_import import import_and_extract, derive_directive, pick_reference_sample
    fp, meta = import_and_extract(text, sample=sample, chapter_range=chapter_range, strategy=strategy)
    reference_sample, llm_sample_titles = pick_reference_sample(text)
    fp["_base_kind"] = "reference"
    fp["_sample_info"] = {
        "kind": "reference",
        "strategy": strategy,
        "stat_range": meta.get("sample_range"),
        "stat_count": meta.get("sampled_chapters"),
        "stat_titles": meta.get("sampled_titles", [])[:6],
        "total_chapters": meta.get("chapter_count"),
        "llm_sample_titles": llm_sample_titles,
    }
    existing_directive = _existing_directive(conn, scope, volume_id)
    directive_to_set = None
    seeded = False
    if derive_directive_flag and not existing_directive:
        directive_to_set = derive_directive(fp)
        seeded = bool(directive_to_set)
    rid = _upsert_base(conn, scope, volume_id, fp, source_work or "外部参考",
                       reference_sample=reference_sample, directive_to_set=directive_to_set)
    return rid, meta, seeded


def save_fingerprint_from_written(conn, scope, volume_id=None, chapter_range=None,
                                  strategy="spread", sample=None):
    """从本作【已写】章节提取指纹作 base(把自洽从 fallback 提升为显式来源)。
    chapter_range=[global_number_start, global_number_end] 1-based 闭区间(按 global_number 过滤);
    无 range→全部 status='writing'/'completed' 章。strategy 同参考导入。
    upsert 保留 scalar_targets/directive;_base_kind='self' 让工作台区分来源。
    返回 (row_id, meta)。meta 含 sampled 的 global_number 列表 + 章名。"""
    from src.bedrock.style.extractor import extract_fingerprint
    rows = conn.execute(
        "SELECT c.id, c.global_number, c.title FROM chapter c "
        "WHERE c.status IN ('writing','completed') ORDER BY c.global_number").fetchall()
    if chapter_range:
        lo, hi = chapter_range
        rows = [r for r in rows if lo <= r["global_number"] <= hi]
    total = len(rows)
    # 复用抽样策略:在已写章集合上抽样。注意传 chapter_range=[1,total]——本作已写章本就是
    # 有意义集合(无需像参考书那样 edge_skip 首尾),传 None 会触发 edge_skip 把少章集吃光。
    from src.bedrock.style.reference_import import sample_chapter_indices
    idxs = sample_chapter_indices(total, sample, [1, total] if total else None, strategy=strategy) if total else []
    picked = [rows[i] for i in idxs]
    paragraphs = []
    for r in picked:
        paragraphs.extend(p["text"] for p in list_paragraphs_in_chapter(conn, r["id"]))
    fp = extract_fingerprint(paragraphs)
    fp["_base_kind"] = "self"
    fp["_sample_info"] = {
        "kind": "self",
        "strategy": strategy,
        "stat_range": [picked[0]["global_number"], picked[-1]["global_number"]] if picked else None,
        "stat_count": len(picked),
        "stat_titles": [r["title"][:30] for r in picked[:8]],
        "total_written": total,
    }
    rid = _upsert_base(conn, scope, volume_id, fp, f"本作已写({total}章)",
                       reference_sample=None, directive_to_set=None)
    meta = {
        "chapter_count": total,
        "sampled_chapters": len(picked),
        "paragraph_count": len(paragraphs),
        "sample_range": fp["_sample_info"]["stat_range"],
        "sampled_titles": fp["_sample_info"]["stat_titles"],
        "sampled_global_numbers": [r["global_number"] for r in picked],
        "sample_strategy": strategy,
    }
    return rid, meta


def _existing_directive(conn, scope, volume_id):
    row = _row_by_scope(conn, scope, volume_id)
    return row["directive"] if row else ""


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
    """合并后的 style 配置。**字段级 merge**:卷级字段的非空值覆盖作品级,空值回退作品级
    (卷级=diff/patch 语义,不是整行替换)。无任何行→代码默认。
    返回 {scope, source_work, fingerprint, directive, word_count_target,
          max_edit_rounds, hygiene, scalar_targets, enabled_dims, has_row}。"""
    work = _row_by_scope(conn, "work", None)
    vol = _row_by_scope(conn, "volume", volume_id) if volume_id else None
    if not work and not vol:
        return {"has_row": False, "scope": None, "fingerprint": None,
                "directive": "", "word_count_target": _DEFAULT_WORD_COUNT,
                "max_edit_rounds": _DEFAULT_MAX_EDIT_ROUNDS, "hygiene": _DEFAULT_HYGIENE,
                "scalar_targets": {}, "enabled_dims": [], "source_work": None}

    def pick_json(field):
        """vol 非空({}外)→vol, else work。"""
        for r in (vol, work):
            if r and r[field] and r[field] != "{}":
                return json.loads(r[field])
        return {}

    def pick_str(field, empty=""):
        for r in (vol, work):
            if r and r[field] and r[field] != empty:
                return r[field]
        return empty

    directive = pick_str("directive")
    directive_source = pick_str("directive_source")
    # fingerprint: 卷级空→作品级
    fp_str = pick_str("fingerprint", "{}")
    fp = json.loads(fp_str) if fp_str else None
    current_source = fp.get("_source_work") if fp else None
    # 指令过时:有指令且记了来源,但来源 ≠ 当前指纹来源(换参考后未重分析)。
    # 后缀归一比对(.txt 等),免路径导入 stem 与 /analyze-style 带后缀的命名漂移误报。
    directive_stale = (bool(directive) and bool(directive_source) and current_source is not None
                       and _norm_source(directive_source) != _norm_source(current_source))
    src_rows = vol if (vol and vol["source_works"] and vol["source_works"] != "[]") else work
    src = json.loads(src_rows["source_works"]) if src_rows and src_rows["source_works"] else []
    # 旋钮:卷级行存在则用其值,否则作品级;都无→默认
    wc = json.loads(vol["word_count_target"]) if vol and vol["word_count_target"] else \
         (json.loads(work["word_count_target"]) if work and work["word_count_target"] else _DEFAULT_WORD_COUNT)
    mer = vol["max_edit_rounds"] if (vol and vol["max_edit_rounds"]) else \
          (work["max_edit_rounds"] if (work and work["max_edit_rounds"]) else _DEFAULT_MAX_EDIT_ROUNDS)
    scope = "volume" if vol else ("work" if work else None)
    return {
        "has_row": True,
        "scope": scope,
        "volume_id": volume_id if vol else None,
        "source_work": (src[0] if src else (fp.get("_source_work") if fp else None)),
        "fingerprint": fp,
        "directive": directive,
        "directive_source": directive_source,
        "directive_stale": directive_stale,
        "word_count_target": wc,
        "max_edit_rounds": mer,
        "hygiene": pick_json("hygiene") or _DEFAULT_HYGIENE,
        "scalar_targets": pick_json("scalar_targets"),   # 用户显式标量目标,覆盖指纹派生
        "enabled_dims": pick_json("enabled_dims"),
    }


def set_style_config(conn, scope, volume_id=None, *, directive=None, word_count_target=None,
                     max_edit_rounds=None, hygiene=None, enabled_dims=None, scalar_targets=None,
                     directive_source=None):
    """upsert 文风配置(只更新非 None 字段)。行不存在则建(scope/volume_id 匹配)。"""
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
    if scalar_targets is not None:
        fields.append("scalar_targets=?"); vals.append(json.dumps(scalar_targets, ensure_ascii=False))
    if directive_source is not None:
        fields.append("directive_source=?"); vals.append(directive_source)
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
        if r["directive_source"]:
            fp["_directive_source"] = r["directive_source"]
            # stale: 指令来源 ≠ 当前指纹来源(换参考后未重分析);后缀归一比对
            fp["_directive_stale"] = bool(fp.get("_source_work")) and _norm_source(fp["_source_work"]) != _norm_source(r["directive_source"])
        if r["scalar_targets"] and r["scalar_targets"] != "{}":
            fp["_scalar_targets"] = json.loads(r["scalar_targets"])
        if r["volume_id"] is not None:
            fp["_volume_id"] = r["volume_id"]
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
