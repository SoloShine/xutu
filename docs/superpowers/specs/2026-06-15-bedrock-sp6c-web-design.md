# 磐石 Bedrock SP6-C 设计：本地 Web UI

> SP6 = 工具层（A+B+C 三子项目）。本 spec 仅覆盖 **SP6-C：本地 Web UI**。
> SP6-A（只读 CLI）✅ + SP6-B（MCP Server）✅ 已完成。本 spec 完成 SP6 工具层。
> 前置：SP1-5 核心管线 + SP6-A + SP6-B 全部完成。

## 1. 目标与范围

SP6-A（CLI）和 SP6-B（MCP）是"命令/对话"入口，适合精确查询。SP6-C 补**可视化浏览**层——POV 矩阵、灵感池、review_report 渲染这些"扫视/挑选/看一眼"的场景，文本承载吃力。本地单用户，Flask 服务端渲染，无构建链。

**SP6-C 范围 = 1 个 Flask app + 3 个视图 + 1 个写点（灵感池状态推进）**：

| 视图 | 数据源 | 读/写 |
|------|--------|-------|
| POV 矩阵 | `chapter → beat.pov_character_id → character` JOIN | 只读 |
| 灵感池 | `inspiration` 表（type 7 类 / status 5 态） | 读 + 状态推进（唯一写点） |
| review_report 渲染 | `review_report_vol{N}.md`（SP5 生成） | 只读（markdown 渲染 + escalate 高亮） |

**不在 SP6-C 范围**：在线编辑正文（正文 SSOT 由管线写，Web 不碰 paragraph）；治理写入（mark-*/unlock-volume，留给 CLI/MCP）；多用户/身份/部署（本地 loopback 单用户）；实时协作。

## 2. 关键设计决策

- **Flask + Jinja2 服务端渲染 + htmx**（局部刷新）。依赖只加 `flask` + `markdown`（Python-Markdown）。htmx 是一行 CDN `<script>`，无 npm 构建。
- **唯一写点 = 灵感池状态推进**。POV 矩阵 / review_report 纯只读。范围最小，无身份/CSRF（本地 loopback 单用户）。
- **状态机单向不回退**：consumed/partial 只能 → discarded，不回 raw/refined（防 LLM/手滑倒退）。合法转移表在纯函数层（repository）。
- **复用既有层**：`queries.py` 用既有 repository（plot_tree/suspense/worldbook）+ 新增 `repositories/inspiration.py`（read list + advance）。**不**绕过纯函数层直接拼 SQL。新增 `inspiration` repository 是 SP6-C 唯一新写 DB 的地方。
- **project 启动时指定一次**：`create_app(project_dir)` 工厂注入。单用户本地，一次服务一个 project。启动校验 bedrock.db 存在（与 SP6-B `_project_ok` 一致，不创建空 db）。
- **测试 CLI 优先**：纯函数层（inspiration repo + 合法转移）是测试主体；Web 路由用 Flask test client（不启浏览器）；视觉只手动看一眼。数据正确性复用 SP6-A CLI/既有 repository 测试已覆盖的数据层。
- **markdown 用 `markdown` 包**（非手写极简）——review_report 渲染 + 后续其他地方复用，依赖值得。

## 3. 架构与文件落点

```
src/bedrock/
├── web/
│   ├── __init__.py
│   ├── app.py              # Flask app 工厂 create_app(project_dir) + 路由
│   ├── queries.py          # 纯查询函数（POV 矩阵聚合数据、灵感池列表）
│   ├── __main__.py         # python -m src.bedrock.web --project <dir> [--port 5000]
│   └── templates/
│       ├── base.html       # 布局 + 导航 + htmx CDN script
│       ├── matrix.html     # POV 矩阵
│       ├── _beats.html     # 矩阵单元格 ● 展开的 beat 列表片段（htmx 局部）
│       ├── inspirations.html  # 灵感池卡片列表
│       ├── _inspiration_card.html  # 单卡片（htmx 状态推进后替换）
│       └── report.html     # review_report markdown 渲染
└── repositories/
    └── inspiration.py      # 新增：list_inspirations + advance_inspiration（合法转移校验）
tests/bedrock/
├── test_inspiration.py     # inspiration repository 纯函数测试（TDD 主体）
└── test_web.py             # Flask test client 测路由 + 渲染
```

- `create_app(project_dir)`：校验 `(Path(project_dir)/"bedrock.db").exists()`，否则启动报错。project 存 app.config。每请求开/关 conn（复用 `get_connection`）。
- 入口：`python -m src.bedrock.web --project <dir> [--port 5000]`，本地 `http://localhost:5000`。

## 4. 三视图设计

### 4.1 POV 矩阵 `GET /matrix?volume=<id>`

数据（`queries.py` 的 `pov_matrix(conn, volume_id)`）：
- 矩阵行 = 该卷章节（global_number + title，按 global_number 升序）。
- 矩阵列 = 该卷出现过的所有 POV 角色（`SELECT DISTINCT pov_character_id` JOIN character，按首次出现排序）。
- 单元格 = 该章是否有此角色 POV 的 beat → ● / 空。

渲染：
- 顶部卷选择器（下拉切卷）。
- 单元格 ● 点击 → htmx `GET /matrix/beats?chapter=<id>&character=<id>` 返回该章该角色 POV 的 beat 列表片段（`_beats.html`），局部展开。
- 统计行：每角色总 POV 章数（一眼看 POV 失衡）。

### 4.2 灵感池 `GET /inspirations?type=<>&status=<>`

数据（`list_inspirations(conn, type_filter, status_filter)`）：`inspiration` 表按 created_at 倒序。

渲染：卡片列表，每卡（`_inspiration_card.html`）：
- type + status 徽章（status 着色：raw 灰 / refined 蓝 / consumed 绿 / partial 黄 / discarded 红）。
- content（截断 + 点击展开全文）。
- source 行。
- 状态推进按钮（htmx POST `/inspirations/<id>/advance`，按当前 status 显示合法转移按钮，非法不显示）。
- 顶部筛选器：type（7 类）/ status（5 态）。

### 4.3 review_report 渲染 `GET /report/<volume_id>`

数据：读 `review_report_vol{volume_id}.md`（SP5 `_write_review_report` 生成）。

渲染：
- markdown 正文用 `markdown` 包转 HTML。
- **escalate_human 高亮**：复用 SP6-A `show_review_report` 的 outcomes 解析（正则 `- ch{N}: escalate_human`），对 escalate 章 `### chN` 标题加红色左边框 + 背景黄。
- 顶部切换：全文 / 仅 escalate_human（复用 show_review_report --escalate-only 逻辑）。
- 文件不存在 → 404（不崩）。

## 5. 灵感池状态推进（唯一写点）

### 5.1 合法状态转移（单向）

```
raw ──→ refined ──→ consumed
 │        │   ╲──→ partial
 │        └──────→ discarded
 └──────────────→ discarded
```

每个 status 显示的推进按钮（非法转移不显示）：
- `raw`：`[→ refined]` `[→ discarded]`
- `refined`：`[→ consumed]` `[→ partial]` `[→ discarded]`
- `consumed` / `partial`：`[→ discarded]`（单向，不回退）
- `discarded`：终态，无按钮

### 5.2 时间戳规则

- `raw → refined`：设 `refined_at`
- `refined → consumed` / `refined → partial`：设 `promoted_at`
- `→ discarded`：不设专门时间戳（created_at 已在）

### 5.3 端点与 repository

**端点** `POST /inspirations/<id>/advance`（htmx 请求）：
- 表单字段 `target`（目标 status）。
- 调 `advance_inspiration(conn, id, target)`，返回更新后卡片（`_inspiration_card.html`，htmx 替换）。
- 错误（非法转移 / 未知 id）→ 返回错误提示卡，原 status 不变，不崩。

**`repositories/inspiration.py`**：
```python
_LEGAL_TRANSITIONS = {
    "raw": {"refined", "discarded"},
    "refined": {"consumed", "partial", "discarded"},
    "consumed": {"discarded"},
    "partial": {"discarded"},
    "discarded": set(),
}

def list_inspirations(conn, type_filter=None, status_filter=None):
    """灵感池列表，created_at 倒序。type/status 可选筛选。"""
    ...

def advance_inspiration(conn, inspiration_id, target):
    """推进状态。校验 (current, target) 合法；非法 raise ValueError。设对应时间戳。
    返回更新后 row（dict）。"""
    row = conn.execute("SELECT status FROM inspiration WHERE id=?", (inspiration_id,)).fetchone()
    if row is None:
        raise ValueError(f"inspiration {inspiration_id} 不存在")
    current = row["status"]
    if target not in _LEGAL_TRANSITIONS.get(current, set()):
        raise ValueError(f"非法转移 {current}→{target}")
    # 设时间戳
    ...
    conn.execute("UPDATE inspiration SET status=?, ... WHERE id=?", ...)
    conn.commit()
    return dict(conn.execute("SELECT * FROM inspiration WHERE id=?", (inspiration_id,)).fetchone())
```

合法转移表 + 校验在纯函数层（repository），路由层只 catch ValueError 转错误卡。

## 6. 测试策略（CLI 优先）

**不启浏览器**（Flask test client 测路由/渲染；数据正确性复用既有 SP6-A CLI/既有 repository 测试）。

### 层 1：inspiration repository 纯函数（TDD 主体）— `test_inspiration.py`
- `test_list_inspirations_all`：全量，created_at 倒序
- `test_list_inspirations_filter_type` / `_filter_status`：筛选
- `test_advance_raw_to_refined`：设 refined_at
- `test_advance_refined_to_consumed`：设 promoted_at
- `test_advance_illegal_rejected`：consumed→raw / discarded→refined 等非法 → raise ValueError，DB status 不变
- `test_advance_to_discarded`：各状态→discarded 合法
- `test_advance_unknown_id`：不存在 → ValueError

### 层 2：Web 路由（Flask test client）— `test_web.py`
- `test_matrix_route_renders`：GET /matrix?volume=X → 200，含卷标题 + POV 表头
- `test_matrix_cell_marks_pov`：章有 POV beat → 单元格含 ●
- `test_matrix_beat_expand_endpoint`：GET /matrix/beats?... → beat 列表片段
- `test_inspirations_route_renders`：GET /inspirations → 卡片列表
- `test_inspirations_advance_htmx`：POST advance（htmx 头）→ 200，返回卡片 status 徽章已变
- `test_inspirations_advance_illegal_returns_error_card`：非法转移 → 错误卡，原 status 不变
- `test_report_route_renders_markdown`：GET /report/<vol> → markdown 转 HTML + escalate 高亮
- `test_report_missing_returns_404`：报告不存在 → 404

### 层 3：project 启动约束
- `test_app_factory_requires_bedrock_db`：create_app(project) 目录无 bedrock.db → 启动报错

### CLI 优先落地
- 灵感池/POV 数据正确性 → 既有 repository 测试已覆盖的数据层；Web 测试只验"路由把数据塞进模板"。
- 状态推进写 DB 正确性 → `test_inspiration.py` 纯函数层锁死；Web 路由测试只验"调了纯函数 + 返回卡片"。
- 渲染视觉 → 不自动化；开发时手动起 Flask + 浏览器看一眼（唯一需要浏览器的环节，验证"渲染本身"）。

**手动冒烟**（完成后，不进自动化）：`python -m src.bedrock.web --project <真项目>` 开浏览器看三视图。

## 7. 与既有命令/系统的边界

- SP6-C 复用 SP6-A 纯函数层（`show_review_report` 的 outcomes 解析）+ 既有 repository。新增 `inspiration` repository（唯一新写 DB 点）。
- SP6-C **不替代** SP6-A CLI / SP6-B MCP——三者共用纯函数/repository 层，各是不同入口（终端 / 对话 / 浏览器）。
- SP6-C **不碰** paragraph 表（正文 SSOT 由管线写）；唯一写是 inspiration.status。
- SP6-C 与旧 novel_kg 系统独立（bedrock 是 V3）。

## 8. 验收标准

- 3 视图各自可访问渲染：POV 矩阵 / 灵感池 / review_report。
- 灵感池状态推进：合法转移生效 + 时间戳正确；非法转移拒绝 + DB 不变 + 错误卡；单向不回退。
- POV 矩阵 ● 点击 htmx 展开 beat 列表（局部刷新）。
- review_report markdown 渲染 + escalate_human 高亮。
- project 目录无 bedrock.db → 启动报错（不创建空 db）。
- 零新依赖（除 `flask` + `markdown`；stdlib + src.bedrock）。
- 全部测试通过（SP1-5 + SP6-A + SP6-B 既有 191 不受影响 + SP6-C 新增 ~16 测试）。
- 手动冒烟 `python -m src.bedrock.web --project <真项目>` 三视图正常显示。
