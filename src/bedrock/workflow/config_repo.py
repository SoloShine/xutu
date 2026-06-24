# src/bedrock/workflow/config_repo.py
"""编排旋钮配置 repo。镜像 style/template_repo.py 范式：
- 多 JSON 列（caps/models/phases/prompts）+ scope=work|volume 两级；
- get = 深度逐键 merge（代码默认 ← work ← volume，None/缺失键不覆盖）；
- set = upsert 只更新非 None 类别（行不存在则建，同 scope+volume_id 一行）。

冻结自当前 .js 硬编码快照（phase 1）：消费方为 LangGraph runner（经 CLI get-workflow-config）；
当前 .js 不读此表，保持现状行为。文风项（word_count/hygiene）已在 style_template，此处不重复（RC3）。
"""
import json


# ===== 代码默认（冻结自 .claude/workflows/*.js 现状硬编码）=====
# caps：各 agent 的迭代上限。源：chapter.js / chapter-edit.js / volume-review.js。
_DEFAULT_CAPS = {
    "writer": 3,    # chapter.js WRITER_ITERATIONS_CAP
    "editor": 5,    # chapter.js EDITOR_ITERATIONS_CAP
    "repair": 3,    # chapter-edit.js REPAIR_ITERATIONS_CAP
    "style": 2,     # chapter-edit.js STYLE_MAX_ROUNDS
    "vr_fix": 1,    # volume-review.js VR_FIX_ROUNDS
}

# models:每个流程绑定的 LLM = {endpoint(全局端点名),model}。None=未配置(runner 明确报错)。
# 两层架构:endpoint 名指向全局目录(~/.bedrock/global.db llm_endpoint),作品级只选"哪个端点+哪个模型"。
# 流程清单:chapter(writer/editor/consistency)+ chapter-edit(rewrite/polish/surgical/repair/style)+ volume-review。
_PROCESS_KEYS = ("writer", "editor", "consistency", "rewrite", "polish", "surgical",
                 "repair", "style", "volume_review", "volume_fix", "volume_recheck", "author")
_UNBOUND = {"endpoint": None, "model": None}
_DEFAULT_MODELS = {k: dict(_UNBOUND) for k in _PROCESS_KEYS}

# phases：阶段开关。polish 用 auto（fingerprint 门控）/on/off；布尔项默认 true（.js 现状均启用）。
_DEFAULT_PHASES = {
    "polish": "auto",                       # chapter.js POLISH_FINGERPRINT_GATE
    "consistency": True,                    # chapter.js Consistency 阶段
    "consistency_requires_characters": True,
    "proper_nouns": True,                   # chapter.js 专名硬校验
    "edit_style_convergence": True,         # chapter-edit.js（仅 rewrite/polish）
}

# prompts：.md 模板路径（仅这 3 个是文件；其余 prompt 是 .js 内联函数，LangGraph 迁移时再外化）。
_DEFAULT_PROMPTS = {
    "writer": ".claude/templates/bedrock/chapter_writer.md",
    "editor": ".claude/templates/bedrock/edit_agent.md",
    "volume_review": ".claude/templates/bedrock/volume_review.md",
}

_DEFAULTS = {
    "caps": dict(_DEFAULT_CAPS),
    "models": dict(_DEFAULT_MODELS),
    "phases": dict(_DEFAULT_PHASES),
    "prompts": dict(_DEFAULT_PROMPTS),
}

_CATEGORY_KEYS = ("caps", "models", "phases", "prompts")


def _row_by_scope(conn, scope, volume_id):
    """按真列 scope/volume_id 取行（卷级优先，同 scope+volume_id 取最新一行）。"""
    if scope == "volume" and volume_id is not None:
        r = conn.execute(
            "SELECT * FROM workflow_config WHERE scope='volume' AND volume_id=? "
            "ORDER BY id DESC LIMIT 1", (volume_id,)).fetchone()
        if r:
            return r
    return conn.execute(
        "SELECT * FROM workflow_config WHERE scope='work' ORDER BY id DESC LIMIT 1").fetchone()


def _row_strict(conn, scope, volume_id):
    """严格匹配 scope（无 work 回退）。供 set 用：避免 volume set 误更新 work 行。"""
    if scope == "volume":
        return conn.execute(
            "SELECT id FROM workflow_config WHERE scope='volume' AND volume_id=? "
            "ORDER BY id DESC LIMIT 1", (volume_id,)).fetchone()
    return conn.execute(
        "SELECT id FROM workflow_config WHERE scope='work' ORDER BY id DESC LIMIT 1").fetchone()


def _merge_category(default, work_row, vol_row, field):
    """深度逐键 merge：default ← work（非空键）← volume（非空键）。
    None/缺失键不覆盖（让上层值生效）。work/volume 列存 '{}' 表示该层未设。"""
    out = dict(default)
    for r in (work_row, vol_row):
        if not r:
            continue
        raw = r[field]
        if not raw or raw == "{}":
            continue
        loaded = json.loads(raw)
        for k, v in loaded.items():
            if v is None:
                continue  # None = 不覆盖
            out[k] = v
    return out


def get_workflow_config(conn, volume_id=None):
    """合并后的编排配置。深度逐键 merge：代码默认 ← work 行 ← volume 行。
    无任何行 → 纯代码默认（冻结快照）。返回 {scope, volume_id, caps, models, phases, prompts, has_row}。"""
    work = _row_by_scope(conn, "work", None)
    vol = _row_by_scope(conn, "volume", volume_id) if volume_id else None
    has_row = bool(work or vol)
    return {
        "has_row": has_row,
        "scope": "volume" if vol else ("work" if work else None),
        "volume_id": volume_id if vol else None,
        "caps": _merge_category(_DEFAULT_CAPS, work, vol, "caps"),
        "models": _merge_category(_DEFAULT_MODELS, work, vol, "models"),
        "phases": _merge_category(_DEFAULT_PHASES, work, vol, "phases"),
        "prompts": _merge_category(_DEFAULT_PROMPTS, work, vol, "prompts"),
    }


def set_workflow_config(conn, scope, volume_id=None, *, caps=None, models=None,
                        phases=None, prompts=None):
    """upsert 编排配置（只更新非 None 类别）。行不存在则建（scope/volume_id 匹配）。
    返回 row_id。"""
    if scope not in ("work", "volume"):
        raise ValueError("scope 必须 work|volume")
    if scope == "volume" and volume_id is None:
        raise ValueError("scope=volume 需提供 volume_id")

    row = _row_strict(conn, scope, volume_id)  # 严格匹配 scope（不回退 work；set 不该误改兄弟 scope 行）
    payload = {"caps": caps, "models": models, "phases": phases, "prompts": prompts}
    fields, vals = [], []
    for cat, v in payload.items():
        if v is None:
            continue
        fields.append(f"{cat}=?")
        vals.append(json.dumps(v, ensure_ascii=False))

    if row:
        if fields:
            fields.append("updated_at=?")
            vals.append(_now(conn))
            vals.append(row["id"])
            conn.execute(f"UPDATE workflow_config SET {', '.join(fields)} WHERE id=?", vals)
            conn.commit()
        return row["id"]

    # 无行：新建（未给的类别走 DB 列默认 '{}'）
    cols = ["scope", "volume_id", "caps", "models", "phases", "prompts", "updated_at"]
    placeholders = ",".join("?" * len(cols))
    params = [
        scope,
        volume_id if scope == "volume" else None,
        json.dumps(caps, ensure_ascii=False) if caps is not None else "{}",
        json.dumps(models, ensure_ascii=False) if models is not None else "{}",
        json.dumps(phases, ensure_ascii=False) if phases is not None else "{}",
        json.dumps(prompts, ensure_ascii=False) if prompts is not None else "{}",
        _now(conn),
    ]
    cur = conn.execute(
        f"INSERT INTO workflow_config({','.join(cols)}) VALUES ({placeholders})", params)
    conn.commit()
    return cur.lastrowid


def list_workflow_configs(conn):
    """列全部配置行（供 Web 展示 work + 各 volume 覆盖）。返回 [{id, scope, volume_id, caps, models, phases, prompts, updated_at}]。"""
    rows = conn.execute(
        "SELECT id, scope, volume_id, caps, models, phases, prompts, updated_at "
        "FROM workflow_config ORDER BY scope, volume_id NULLS FIRST, id").fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "scope": r["scope"],
            "volume_id": r["volume_id"],
            "caps": json.loads(r["caps"]) if r["caps"] and r["caps"] != "{}" else {},
            "models": json.loads(r["models"]) if r["models"] and r["models"] != "{}" else {},
            "phases": json.loads(r["phases"]) if r["phases"] and r["phases"] != "{}" else {},
            "prompts": json.loads(r["prompts"]) if r["prompts"] and r["prompts"] != "{}" else {},
            "updated_at": r["updated_at"],
        })
    return out


def get_defaults():
    """代码默认（冻结快照），供 API/前端展示基线。返回深拷贝。"""
    return {k: dict(v) for k, v in _DEFAULTS.items()}


def _now(conn):
    """DB 服务器当前时间（与列默认 datetime('now') 一致）。"""
    r = conn.execute("SELECT datetime('now')").fetchone()
    return r[0]
