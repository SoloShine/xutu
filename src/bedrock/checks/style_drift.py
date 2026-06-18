# src/bedrock/checks/style_drift.py
"""章级文风漂移测量。

为何不用整分布直方图比对:单章样本小(50-150段),直方图方差极大,逐桶比对会误杀。
改用**标量指标**(从指纹降维出来的单一数值),宽容差,只标明显偏离——
方向性诊断,非精确匹配。

目标回退链(优先级):
  1. 卷级指纹(set_style_config scope=volume)
  2. 作品级指纹(extract 自参考作品)
  3. 自洽:本卷已写章节的滚动均值(无显式目标时,对齐自身已建立的风格)
漂移只对"越低越好"的气味维度(dash/notXisY)与对白/修辞比率做硬判断,
句长/段长分布不做单章硬卡(噪声大、且随场景类型合理变化)。
"""
import json
from src.bedrock.db.chapter_lookup import chapter_id_by_global
from src.bedrock.repositories.plot_tree import list_paragraphs_in_chapter, list_beats_in_chapter
from src.bedrock.style.extractor import extract_fingerprint, _cn_len, _split_sentences
from src.bedrock.style.template_repo import get_style_config


def _chapter_scalar_metrics(paragraphs):
    """段落列表 → 标量文风指标(单章稳健,非整分布)。"""
    if not paragraphs:
        return {}
    fp = extract_fingerprint(paragraphs)  # 复用提取器(含 dash_density/rhetoric value)
    n_paras = len(paragraphs)
    sentences = []
    for p in paragraphs:
        sentences.extend(_split_sentences(p))
    n_sent = len(sentences) or 1
    sent_lens = [_cn_len(s) for s in sentences]
    para_lens = [_cn_len(p) for p in paragraphs]
    return {
        # 越低越好(气味)——用 per-k 归一,非按段(按段会与段落长度耦合)
        "dash_density": fp.get("dash_density", {}).get("value", 0),  # ——/千字
        "notXisY_rate": fp["structure"].get("notXisY", 0),  # notXisY 句占比
        # 比率
        "dialogue_ratio": fp["dialogue_ratio"].get("value", 0),
        "rhetoric_per_k": fp["rhetoric"].get("value", 0),
        # 形态(诊断用,不做硬卡)
        "short_sent_rate": fp["structure"].get("短句", 0),
        "avg_sent_len": round(sum(sent_lens) / n_sent, 1),
        "avg_para_len": round(sum(para_lens) / n_paras, 1),
    }


def _target_scalars(target_fp):
    """从目标指纹(直方图)降维出标量目标。无目标→None。"""
    if not target_fp:
        return None
    out = {}
    out = {}
    if "dash_density" in target_fp and isinstance(target_fp["dash_density"], dict):
        out["dash_density"] = target_fp["dash_density"].get("value", 0)
    elif "dash" in target_fp:
        out["dash_density"] = None  # 旧指纹无 per-k,无法可比(按段会与长度耦合)
    if "structure" in target_fp:
        out["notXisY_rate"] = target_fp["structure"].get("notXisY", 0)
        out["short_sent_rate"] = target_fp["structure"].get("短句", 0)
    if "dialogue_ratio" in target_fp and isinstance(target_fp["dialogue_ratio"], dict):
        out["dialogue_ratio"] = target_fp["dialogue_ratio"].get("value", 0)
    if "rhetoric" in target_fp and isinstance(target_fp["rhetoric"], dict):
        out["rhetoric_per_k"] = target_fp["rhetoric"].get("value", 0)
    return out or None


def _self_consistency_target(conn, volume_id, current_global_number, window=5):
    """本卷已写章节(global_number < 当前)的标量滚动均值,作自洽目标。无→None。"""
    cur = conn.execute("SELECT id FROM volume WHERE id=?", (volume_id,)).fetchone()
    if not cur:
        return None
    rows = conn.execute(
        "SELECT c.global_number, c.id FROM chapter c WHERE c.volume_id=? "
        "AND c.global_number<? AND c.status='writing' ORDER BY c.global_number DESC LIMIT ?",
        (volume_id, current_global_number, window)).fetchall()
    if not rows:
        return None
    acc = {}
    for r in rows:
        paras = [p["text"] for p in list_paragraphs_in_chapter(conn, r["id"])]
        m = _chapter_scalar_metrics(paras)
        for k, v in m.items():
            acc.setdefault(k, []).append(v)
    return {k: round(sum(v) / len(v), 3) for k, v in acc.items()}


# 各标量的漂移判定(宽容差,单章噪声)。返回 (drifted, severity, hint)。
def _judge(metric, actual, target):
    if target is None or actual is None:
        return False, 0, ""
    t = target
    if metric in ("dash_density", "notXisY_rate"):  # 越低越好:超 target*2 且有绝对量才报
        floor = 0.5 if metric == "dash_density" else 0.03   # dash /k 门槛;notXisY 3%
        if metric == "dash_density":
            if actual > max(t * 2, t + 1.5) and actual > floor:
                sev = round(actual / (t + 1e-9), 1)
                return True, sev, f"破折号密度 {actual:.1f}/千字 远高于目标 {t:.1f}(参考≈{t:.1f}),删非必要项"
            return False, 0, ""
        # notXisY_rate
        if actual > max(t * 2, t + 0.03) and actual > floor:
            sev = round(actual / (t + 1e-9), 1)
            return True, sev, f"「不是A是B」句率 {pct(actual)} 高于目标 {pct(t)},改写该句式"
        return False, 0, ""
    if metric == "rhetoric_per_k":
        if actual > max(t * 2.5, t + 3) and actual > 5:
            return True, round(actual / (t + 1e-9), 1), f"修辞密度 {actual:.1f}/千字 高于目标 {t:.1f},比喻过密"
        return False, 0, ""
    if metric == "dialogue_ratio":
        if abs(actual - t) > 0.25:  # 对白比差 25pp 才算飘(场景类型本就变)
            d = "高" if actual > t else "低"
            return True, round(abs(actual - t), 2), f"对白占比 {pct(actual)} 明显{d}于目标 {pct(t)}"
        return False, 0, ""
    return False, 0, ""


def pct(x):
    return f"{round((x or 0) * 100)}%"


def _compute_actual(conn, volume_id=None):
    """全量计算已写章节的指纹+标量(不读缓存)。"""
    if volume_id:
        rows = conn.execute(
            "SELECT id FROM chapter WHERE volume_id=? AND status='writing' ORDER BY global_number",
            (volume_id,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT id FROM chapter WHERE status='writing' ORDER BY global_number").fetchall()
    paras = []
    for r in rows:
        paras.extend(p["text"] for p in list_paragraphs_in_chapter(conn, r["id"]))
    if not paras:
        return None
    return {
        "fingerprint": extract_fingerprint(paras),
        "scalars": _chapter_scalar_metrics(paras),
        "chapter_count": len(rows),
        "paragraph_count": len(paras),
    }


def refresh_actual_cache(conn, volume_id=None):
    """重算实测并写缓存(章写完/手动刷新调)。返回实测 dict。"""
    scope = "volume" if volume_id else "work"
    data = _compute_actual(conn, volume_id)
    if not data:
        if volume_id:
            conn.execute("DELETE FROM style_actual_cache WHERE scope=? AND volume_id=?", (scope, volume_id))
        else:
            conn.execute("DELETE FROM style_actual_cache WHERE scope=? AND volume_id IS NULL", (scope,))
        conn.commit()
        return {"fingerprint": None, "scalars": None, "chapter_count": 0, "paragraph_count": 0, "cached": False}
    conn.execute(
        "INSERT OR REPLACE INTO style_actual_cache(scope,volume_id,fingerprint,scalars,"
        "chapter_count,paragraph_count,computed_at) VALUES(?,?,?,?,?,?,datetime('now'))",
        (scope, volume_id,
         json.dumps(data["fingerprint"], ensure_ascii=False),
         json.dumps(data["scalars"], ensure_ascii=False),
         data["chapter_count"], data["paragraph_count"]))
    conn.commit()
    return {**data, "cached": True}


def measure_work_actual(conn, volume_id=None, refresh=False):
    """实测:cache-first(大作品免每次全量重算);refresh=True 或无缓存→重算并写缓存。
    返回 {fingerprint, scalars, chapter_count, paragraph_count, cached, computed_at}。"""
    if not refresh:
        scope = "volume" if volume_id else "work"
        row = conn.execute(
            ("SELECT * FROM style_actual_cache WHERE scope=? AND volume_id=?"
             if volume_id else "SELECT * FROM style_actual_cache WHERE scope=? AND volume_id IS NULL"),
            (scope, volume_id) if volume_id else (scope,)).fetchone()
        if row and row["chapter_count"]:
            return {
                "fingerprint": json.loads(row["fingerprint"]),
                "scalars": json.loads(row["scalars"]),
                "chapter_count": row["chapter_count"],
                "paragraph_count": row["paragraph_count"],
                "cached": True, "computed_at": row["computed_at"],
            }
    return refresh_actual_cache(conn, volume_id)



def measure_style_drift(conn, chapter_id, volume_id):
    """测本章文风漂移。返回 {target_source, metrics, drifted[], ok}。
    drifted = [{metric, actual, target, severity, hint}] 仅明显偏离项。"""
    cur = conn.execute("SELECT global_number FROM chapter WHERE id=?", (chapter_id,)).fetchone()
    gnum = cur["global_number"] if cur else None

    paragraphs = [p["text"] for p in list_paragraphs_in_chapter(conn, chapter_id)]
    actual = _chapter_scalar_metrics(paragraphs)

    # 目标回退:卷级字段merge→作品级指纹派生标量,再被用户显式 scalar_targets 覆盖→自洽
    cfg = get_style_config(conn, volume_id)
    target, source = None, None
    if cfg.get("fingerprint"):
        target, source = _target_scalars(cfg["fingerprint"]), f"作品级指纹({cfg.get('source_work', 'work')})"
    # 用户显式标量目标覆盖指纹派生(最高优先)
    st = cfg.get("scalar_targets") or {}
    if st:
        target = dict(target or {})
        target.update({k: v for k, v in st.items() if v is not None})
        source = f"显式标量目标(覆盖{source or '默认'})"
    if not target and gnum:
        sc = _self_consistency_target(conn, volume_id, gnum)
        if sc:
            target, source = sc, "自洽(本卷已写章节均值)"

    if target is None:
        return {"target_source": None, "metrics": actual, "drifted": [], "ok": True,
                "note": "无目标指纹且无已写章节可比,跳过"}

    drifted = []
    for metric in ("dash_density", "notXisY_rate", "rhetoric_per_k", "dialogue_ratio"):
        d, sev, hint = _judge(metric, actual.get(metric), target.get(metric))
        if d:
            drifted.append({"metric": metric, "actual": actual.get(metric),
                            "target": target.get(metric), "severity": sev, "hint": hint})

    return {
        "target_source": source,
        "metrics": actual,
        "target": target,
        "drifted": drifted,
        "ok": len(drifted) == 0,
    }
