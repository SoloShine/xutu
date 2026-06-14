# 磐石 Bedrock SP6-C 设计：本地 Web UI

> SP6 = 工具层（A+B+C 三子项目）。本 spec 仅覆盖 **SP6-C：本地 Web UI**。
> SP6-A（只读 CLI）✅ + SP6-B（MCP Server）✅ 已完成。本 spec 完成 SP6 工具层。
> 前置：SP1-5 核心管线 + SP6-A + SP6-B 全部完成。
>
> **修订记录**：经两路子代理对抗审核（数据源真实性 + 完备性/边界），已吸收 6🔴 + ~10🟡。关键修订：inspiration 函数加到既有 outline.py（不新建仓库）+ consume_inspiration 组合 advance（单一状态机入口）；补 partial→consumed 转移；抽 parse_review_outcomes() 供 CLI/Web 共用；V2 报告容错；POV NULL beat 规则；CSRF 信任边界 + HX-Request 校验；每请求 conn 不缓存。

## 1. 目标与范围

SP6-A（CLI）和 SP6-B（MCP）是"命令/对话"入口。SP6-C 补**可视化浏览**层——POV 矩阵、灵感池、review_report 渲染这些"扫视/挑选/看一眼"的场景。本地单用户，Flask 服务端渲染，无构建链。

**SP6-C 范围 = 1 个 Flask app + 3 个视图 + 1 个写点（灵感池状态推进）**：

| 视图 | 数据源 | 读/写 |
|------|--------|-------|
| POV 矩阵 | `chapter → beat.pov_character_id → character` JOIN（新增聚合 SQL） | 只读 |
| 灵感池 | `inspiration` 表（type 7 类 / status 5 态），复用/扩展 `outline.py` 既有函数 | 读 + 状态推进（唯一写点） |
| review_report 渲染 | `review_report_vol{N}.md`（SP5 生成） | 只读（markdown 渲染 + escalate 高亮） |

**不在 SP6-C 范围**：在线编辑正文（正文 SSOT 由管线写，Web 不碰 paragraph）；治理写入（mark-*/unlock-volume，留 CLI/MCP）；多用户/身份/部署（本地 loopback 单用户）。

## 2. 关键设计决策

- **Flask + Jinja2 服务端渲染 + htmx**（局部刷新）。依赖加 `flask` + `markdown`（Python-Markdown）。htmx 走 CDN `<script>`（离线时降级见下）。
- **唯一写点 = 灵感池状态推进**（`advance_inspiration`）。POV 矩阵 / review_report 纯只读。
- **【审核修订】inspiration 函数加到既有 `repositories/outline.py`**，不新建 inspiration.py——inspiration 的 DB 层（`add_inspiration`/`consume_inspiration`）已在那里（schema 注释 "Outline + Inspiration pool"）。新增 `list_inspirations` + `advance_inspiration`。**`consume_inspiration` 重构为组合 `advance_inspiration(conn, id, 'consumed')` 再写 consumed_into**——单一状态机入口，消除双写点 + consumed 语义分裂。
- **状态机单向不回退**，含 partial→consumed（审核修订 H1）。合法转移表在纯函数层。
- **【审核修订】POV 聚合是新写 SQL**（§4.1 `queries.py`），非"复用既有 repository"——既有 plot_tree 无 distinct-pov/章节聚合函数。灵感池列表/推进复用 outline.py。
- **review_report 高亮复用 `parse_review_outcomes()` 纯函数**（从 `reader_commands._OUTCOME_RE` 提为公共函数，CLI/Web 共用）——不是复用返回 str 的 `show_review_report`（审核修订 H3）。
- **【审核修订】CSRF 信任边界声明**（H6）：本地 loopback 单用户，信任边界 = 本机所有进程 + 用户浏览的网页均可推进 inspiration.status。advance 端点校验 `HX-Request: true` 头作为弱 CSRF 阻挡（网页 simple form 发不出自定义头）。不做完整身份/CSRF token。
- **每请求开/关 conn，不缓存 conn 到 app.config**（只缓存 project_dir）。Flask dev server threaded=True，缓存 conn 会触发 sqlite check_same_thread 崩。
- **project 校验**：create_app 校验 `(Path(project)/"bedrock.db").exists()`（不创建空 db）。**比 SP6-B `_project_ok` 宽松**（不做 workspace 越界约束——因为 project 是本地用户启动时显式传，不来自远程对话）。spec 明确这个差异。
- **测试 CLI 优先**：纯函数层（inspiration 状态机 + parse_review_outcomes + POV 聚合）是测试主体；Web 路由用 Flask test client（不启浏览器）。
- **markdown 用 `markdown` 包**，`markdown.markdown(text, extensions=['extra', 'sane_lists'])`。信任 SP5 生成内容（不 sanitize）；若未来接入外部内容需加 bleach。

## 3. 架构与文件落点

```
src/bedrock/
├── web/
│   ├── __init__.py
│   ├── app.py              # Flask app 工厂 create_app(project_dir) + 路由
│   ├── queries.py          # 纯查询（pov_matrix 聚合 SQL、卷列表），新写
│   ├── __main__.py         # python -m src.bedrock.web --project <dir> [--port 5000]
│   ├── templates/
│   │   ├── base.html       # 布局 + 导航 + htmx CDN + 内联 CSS（status 徽章色 + 矩阵滚动）
│   │   ├── matrix.html     # POV 矩阵
│   │   ├── _beats.html     # 单元格 ● 展开的 beat 列表片段（htmx 局部）
│   │   ├── inspirations.html
│   │   ├── _inspiration_card.html  # 单卡片（htmx advance 后原位替换）
│   │   └── report.html     # review_report markdown 渲染
│   └── static/
│       └── app.css         # 状态徽章色 / 矩阵 overflow-x:auto / escalate 高亮
├── repositories/
│   └── outline.py          # 修改：+ list_inspirations + advance_inspiration；consume_inspiration 组合 advance
└── cli/reader_commands.py  # 修改：_OUTCOME_RE 提为公共 parse_review_outcomes()，show_review_report 改用
tests/bedrock/
├── test_outline.py         # +list_inspirations/advance_inspiration/consume 组合测试
├── test_reader_commands.py # +parse_review_outcomes 回归（show_review_report 不变）
└── test_web.py             # Flask test client 测路由 + 渲染
```

- `create_app(project_dir)`：校验 bedrock.db 存在；project_dir 存 app.config（**不存 conn**）。
- **每请求** `conn = get_connection(Path(app.config["PROJECT_DIR"]))` + `try/finally conn.close()`。不缓存。
- 入口：`python -m src.bedrock.web --project <dir> [--port 5000]`。

## 4. 三视图设计

### 4.1 POV 矩阵 `GET /matrix?volume=<id>`

数据（`queries.py` 的 `pov_matrix(conn, volume_id)`，**新写聚合 SQL**）：
- 矩阵行 = 该卷章节（global_number + title，按 global_number 升序）。
- 矩阵列 = 该卷 `SELECT DISTINCT pov_character_id ... WHERE pov_character_id IS NOT NULL` JOIN character（**NULL beat 不产列**，审核修订 H5），按首次出现排序。
- 单元格 ● = 该章该角色至少有一条 `pov_character_id=<char>` 的 beat。

渲染规则（H5）：
- 某章所有 beat 均 NULL POV → 该行单元格全空但**仍渲染行**（章号+标题可见）。
- 整卷无 POV beat（列空）→ 渲染"本卷无 POV beat"提示，不渲染空表。
- 顶部卷选择器，数据源 `SELECT id, number, name FROM volume ORDER BY number`（与 SP6-B list_volumes 同源，复用 queries.py）。默认卷 = 最小 number。
- 矩阵表外层 `overflow-x:auto`（CSS），角色多时横向滚动；角色名截断 + title 全名。
- 单元格 ● 点击 → htmx `GET /matrix/beats?chapter=<id>&character=<id>` 返回 beat 列表片段（`_beats.html`）局部展开。
- 统计行：每角色总 POV 章数。

### 4.2 灵感池 `GET /inspirations?type=<>&status=<>`

数据（`list_inspirations(conn, type_filter, status_filter)`）：`inspiration` 表按 created_at 倒序。

渲染：卡片列表（`_inspiration_card.html`）：
- type + status 徽章（status 着色 CSS：raw 灰 / refined 蓝 / consumed 绿 / partial 黄 / discarded 红）。
- content（截断 + 点击展开全文）。
- source 行。
- 状态推进按钮（htmx POST，按当前 status 显示合法转移按钮，非法不显示）。
- **advance 后卡片原位替换（htmx hx-swap），不因新 status 不匹配当前筛选而移除**（Y3）；用户手动刷新筛选视图重排。
- 顶部筛选器：type（7 类）/ status（5 态）。

### 4.3 review_report 渲染 `GET /report/<volume_id>`

数据：读 `review_report_vol{volume_id}.md`（SP5 `_write_review_report` 生成，volume_id=volume.id）。

渲染：
- markdown 转 HTML：`markdown.markdown(text, extensions=['extra', 'sane_lists'])`。
- **escalate 高亮**：调 `parse_review_outcomes(text)` 拿 `{ch: state}` dict（新抽公共函数，CLI/Web 共用），对 state=escalate_human 的 `### chN` 标题加 CSS class（红色左边框 + 背景黄）。
- 顶部切换：全文 / 仅 escalate_human。仅 escalate 视图用 escalate 章子集渲染。
- **V2/空 escalate 容错**（H4）：`parse_review_outcomes` 对 V2 手写报告（无 SP5 格式段）返回空 dict → 仅 escalate 视图渲染空状态提示"未检测到 SP5 格式 escalate_human 项（可能是 V2 手写报告或确无 escalate）"；全文视图正常渲染不高亮。
- 文件不存在 → 404（不崩）。

## 5. 灵感池状态推进（唯一写点）

### 5.1 合法状态转移（单向，含 partial→consumed）

```
raw ──→ refined ──→ consumed
 │  ╲      │   ╲──→ partial ──→ consumed
 │   ╲     └──────→ discarded
 │    ╲──→ consumed   (raw 想法可直接用，不经 refined)
 └──────────────→ discarded
```

合法转移表（`outline.py` 的 `_LEGAL_TRANSITIONS`）：
- `raw`：`{refined, consumed, discarded}`（含 raw→consumed 直接用，兼容既有 consume_inspiration 语义）
- `refined`：`{consumed, partial, discarded}`
- `partial`：`{consumed, discarded}`（审核修订 H1：补 partial→consumed）
- `consumed`：`{discarded}`（审核修订 Y2：consumed→discarded 仅作"用过但作废"标记，不回滚正文）
- `discarded`：`{}`（终态）

每个 status 显示的按钮（非法不显示）：
- `raw`：`[→ refined]` `[→ consumed]` `[→ discarded]`
- `refined`：`[→ consumed]` `[→ partial]` `[→ discarded]`
- `partial`：`[→ consumed]` `[→ discarded]`
- `consumed`：`[→ discarded]`
- `discarded`：无

### 5.2 时间戳规则（promoted_at = 最近一次晋升）

- `raw → refined`：设 `refined_at`
- `refined → consumed` / `refined → partial` / `partial → consumed`：设 `promoted_at`（**审核修订 H2**：语义为"最近一次进入 consumed/partial"，多次晋升覆盖更新；本地单用户审计粒度够用，不追踪首次）
- `→ discarded`：不设专门时间戳（created_at 已在）

### 5.3 outline.py 函数（含与既有 consume_inspiration 的关系）

**新增 `list_inspirations`**（只读）：
```python
def list_inspirations(conn, type_filter=None, status_filter=None):
    """灵感池列表，created_at 倒序。type/status 可选筛选（参数化，防注入）。"""
    sql = "SELECT * FROM inspiration"
    clauses, params = [], []
    if type_filter:
        clauses.append("type=?"); params.append(type_filter)
    if status_filter:
        clauses.append("status=?"); params.append(status_filter)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]
```

**新增 `advance_inspiration`**（唯一状态机入口，含合法转移校验）：
```python
_LEGAL_TRANSITIONS = {
    "raw": {"refined", "consumed", "discarded"},
    "refined": {"consumed", "partial", "discarded"},
    "partial": {"consumed", "discarded"},
    "consumed": {"discarded"},
    "discarded": set(),
}

def advance_inspiration(conn, inspiration_id, target):
    """推进状态。校验 (current, target) 合法；非法 raise ValueError。设对应时间戳。
    返回更新后 row（dict）。这是状态机唯一入口——consume_inspiration 组合本函数。"""
    row = conn.execute("SELECT status FROM inspiration WHERE id=?", (inspiration_id,)).fetchone()
    if row is None:
        raise ValueError(f"inspiration {inspiration_id} 不存在")
    current = row["status"]
    if target not in _LEGAL_TRANSITIONS.get(current, set()):
        raise ValueError(f"非法转移 {current}→{target}")
    import datetime as _dt
    now = _dt.datetime.now().isoformat()
    sets = {"status": target}
    if current == "raw" and target == "refined":
        sets["refined_at"] = now
    if target in ("consumed", "partial"):
        sets["promoted_at"] = now
    set_clause = ", ".join(f"{k}=?" for k in sets)
    conn.execute(f"UPDATE inspiration SET {set_clause} WHERE id=?",
                 [*sets.values(), inspiration_id])
    conn.commit()
    return dict(conn.execute("SELECT * FROM inspiration WHERE id=?", (inspiration_id,)).fetchone())
```

**重构 `consume_inspiration`**（组合 advance，消除双写点，兼容多 target）：
```python
def consume_inspiration(conn, inspiration_id, target_type, target_id):
    """记录灵感用进某 target（章节/卷）。若 status 非 consumed，先 advance 推到 consumed
    （状态机校验 + 设 promoted_at）；若已 consumed，直接追加 consumed_into（允许多 target）。
    组合 advance 消除双写点——所有 status 转移经状态机，consumed 行一致有 promoted_at。"""
    row = conn.execute("SELECT status FROM inspiration WHERE id=?", (inspiration_id,)).fetchone()
    if row is None:
        raise ValueError(f"inspiration {inspiration_id} 不存在")
    if row["status"] != "consumed":
        advance_inspiration(conn, inspiration_id, "consumed")
    # 追加 consumed_into（多 target 友好）
    row2 = conn.execute("SELECT consumed_into FROM inspiration WHERE id=?", (inspiration_id,)).fetchone()
    into = json.loads(row2["consumed_into"]) if row2 and row2["consumed_into"] else []
    into.append({"target_type": target_type, "target_id": target_id})
    conn.execute("UPDATE inspiration SET consumed_into=? WHERE id=?",
                 (json.dumps(into, ensure_ascii=False), inspiration_id))
    conn.commit()
```
**注意**：consume_inspiration 组合 advance 后，若当前 status 不允许 → consumed（如 discarded），advance 会 raise ValueError——这是有意的（已 discard 的不能用）。既有调用方（test_outline.py / 管线）在 status=raw/refined/partial 时调用，raw→consumed 已加入合法表，**既有测试 test_outline.py 不受影响**。

### 5.4 端点

`POST /inspirations/<id>/advance`（htmx）：
- **校验 `HX-Request: true` 头**（弱 CSRF，H6）；无此头 → 403。
- 表单字段 `target`。调 `advance_inspiration(conn, id, target)`，返回更新后卡片（`_inspiration_card.html`，htmx 原位替换）。
- `ValueError`（非法转移/未知 id）→ 返回错误提示卡，原 status 不变，不崩。

## 6. parse_review_outcomes 重构（CLI/Web 共用）

把 `reader_commands._OUTCOME_RE` + 解析逻辑提为公共纯函数：

```python
# reader_commands.py（或新模块）
_OUTCOME_RE = re.compile(r"^- ch(\d+):\s*(verified_fixed|edited_unverified|escalate_human)\s*$", re.MULTILINE)

def parse_review_outcomes(text):
    """解析 SP5 review_report 的 outcomes 段，返回 {global_number: state} dict。
    V2 手写报告（无 SP5 格式段）→ 空 dict（不抛错）。"""
    return {int(m.group(1)): m.group(2) for m in _OUTCOME_RE.finditer(text)}
```
- `show_review_report` 改用 `parse_review_outcomes`（行为不变，SP6-A 测试回归）。
- Web review_report 渲染用同函数拿 escalate 章集做高亮。

## 7. 测试策略（CLI 优先，不启浏览器）

### 层 1：纯函数（TDD 主体）
`test_outline.py`：
- `test_list_inspirations_all` / `_filter_type` / `_filter_status`
- `test_advance_raw_to_refined`（设 refined_at）
- `test_advance_refined_to_consumed` / `_to_partial`（设 promoted_at）
- `test_advance_partial_to_consumed`（H1：补的转移，设 promoted_at）
- `test_advance_illegal_rejected`（consumed→raw / discarded→refined / discarded→anything → ValueError，DB status 不变）
- `test_advance_to_discarded`（各状态合法）
- `test_advance_unknown_id`（ValueError）
- `test_consume_inspiration_composes_advance`（H1：consume 先调 advance 推 consumed + 设 promoted_at，再写 consumed_into；status 非法时 advance 抛错）

`test_reader_commands.py`（+parse_review_outcomes 回归）：
- `test_parse_review_outcomes_sp5`（SP5 报告 → {ch:state}）
- `test_parse_review_outcomes_v2_empty`（V2 报告 → 空 dict，不抛错）
- `test_show_review_report_unchanged`（SP6-A 既有 6 测试仍过，行为不变）

### 层 2：Web 路由（Flask test client）
`test_web.py`：
- `test_matrix_route_renders`（200 + 卷标题 + POV 表头）
- `test_matrix_cell_marks_pov`（章有 POV beat → ●）
- `test_matrix_null_pov_row_renders`（H5：章全 NULL POV → 行渲染但单元格空）
- `test_matrix_empty_volume_message`（H5：整卷无 POV → 提示）
- `test_matrix_beat_expand_endpoint`（GET /matrix/beats → beat 列表片段）
- `test_inspirations_route_renders`
- `test_inspirations_advance_htmx`（POST + HX-Request 头 → 200，卡片 status 变）
- `test_inspirations_advance_requires_htmx_header`（H6：无 HX-Request → 403）
- `test_inspirations_advance_illegal_returns_error_card`（非法转移 → 错误卡，原 status 不变）
- `test_report_route_renders_markdown`（SP5 报告 → HTML + escalate 高亮）
- `test_report_v2_tolerant`（H4：V2 报告全文渲染，仅 escalate 视图空状态提示）
- `test_report_missing_returns_404`

### 层 3：project 启动
- `test_app_factory_requires_bedrock_db`（无 bedrock.db → 启动报错，不创建空 db）

### CLI 优先落地
- 数据正确性 → 纯函数层测试锁死；Web 路由测试只验"路由调纯函数 + 返回模板"。
- 视觉 → 不自动化；手动起 Flask + 浏览器看一眼（唯一需要浏览器的环节）。

**手动冒烟**（完成后，不进自动化）：`python -m src.bedrock.web --project <真项目>` 三视图。

## 8. 与既有命令/系统的边界

- SP6-C 复用 SP6-A `parse_review_outcomes`（新抽）+ 既有 repository。新增 `list_inspirations`/`advance_inspiration`（outline.py）+ POV 聚合 SQL（queries.py）。
- `consume_inspiration` 重构为组合 advance——既有调用方（管线）行为：status 非法时 raise（之前直接写）。需确认既有 consume_inspiration 调用点（grep）在 status 合法时调用。
- SP6-C 不替代 SP6-A CLI / SP6-B MCP——三者共用纯函数/repository 层。
- SP6-C 不碰 paragraph（正文 SSOT）；唯一写 inspiration.status。

## 9. 验收标准

- 3 视图各自可访问渲染。
- 灵感池状态推进：合法转移生效 + 时间戳正确（含 partial→consumed）；非法转移拒绝 + DB 不变 + 错误卡；单向不回退；advance 端点校验 HX-Request 头。
- consume_inspiration 组合 advance（单一状态机入口，无双写点）。
- POV 矩阵：NULL POV beat 行正常渲染；整卷无 POV → 提示；● 点击 htmx 展开。
- review_report：markdown 渲染 + escalate 高亮；V2 报告容错（空 escalate 视图提示）。
- parse_review_outcomes 抽公共函数后 show_review_report 行为不变（回归）。
- project 无 bedrock.db → 启动报错（不创建空 db）。
- 每请求开/关 conn，不缓存。
- 零新依赖（除 flask + markdown）。
- 全部测试通过（既有 191 不受影响 + SP6-C 新增 ~22 测试）。
- 手动冒烟三视图正常。
