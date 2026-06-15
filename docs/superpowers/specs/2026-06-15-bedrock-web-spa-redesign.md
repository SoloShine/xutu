# 磐石 Bedrock Web UI 重做：SPA 工作台

> 本文 **取代** `2026-06-15-bedrock-sp6c-web-design.md` 的视图层设计。SP6-C 已完成的**纯函数层**（`outline.list_inspirations` / `advance_inspiration` / `consume_inspiration`、`queries.pov_matrix`、`reader_commands.parse_review_outcomes`）**全部复用，零改动**。本 spec 只重做**视图层 + 接入层**：把 Flask+Jinja+htmx 的服务端渲染，换成 Vue3+Naive UI 的 SPA + Flask JSON API。
>
> **修订记录**：经 brainstorming 四轮问答定稿。关键决策：①前端栈 = Vue3 + Vite + Naive UI；②多作品 / 工作区切换；③正文视图拆阅读模式 + 大纲模式（多级分组）；④单进程托管 + 一键启动；⑤node 构建物不入 git。

## 1. 目标与范围

把当前"裸 HTML 工作台"重做成**专业 SPA 工作台**：左侧栏作品切换 + 导航，主区多视图，现成组件库撑起专业度（解决 POV 矩阵 100px 小表这类手搓丑件）。

**范围 = 1 个 Vue3 SPA + Flask 退成 JSON API + 1 个写点（灵感池状态推进，复用 `advance_inspiration`）**：

| 视图 | 模式/说明 | 读/写 |
|------|-----------|-------|
| 总览 | 作品仪表盘（统计 + 卷列表） | 只读 |
| POV 矩阵 | NDataTable，行=章/列=角色，● 展开 beat | 只读 |
| 灵感池 | 卡片/表格 + 状态推进 | 读 + 推进（唯一写点） |
| Review 报告 | markdown 渲染 + escalate 高亮 | 只读 |
| 正文 · 阅读模式 | 散文式排版（段落按 seq） | 只读 |
| 正文 · 大纲模式 | 卷/章/beat 多级分组树 | 只读 |

**不在范围**：在线编辑正文（正文 SSOT 由管线写）；治理写入（mark-*/unlock，留 CLI/MCP）；多用户/身份/部署（本地 loopback 单用户）；前端单元测试（本地工具，手动冒烟）。

## 2. 关键设计决策

- **Vue3 SFC + Vite + Naive UI + vue-router + pinia**。Naive 深色优先、自带 Layout(侧边栏)/DataTable/Tabs/Tree/Drawer/Message，开箱即专业。`marked` 渲染 markdown。TS。
- **Flask 退成纯 JSON API**（`/api` 蓝图）。旧 Jinja 模板 / htmx / `app.css` / `templates/` **全部删除**。
- **纯函数层零改动复用**：`repositories/outline.py`、`queries.py`、`reader_commands.parse_review_outcomes`。新增查询函数（`list_works`/`overview_stats`/`chapter_text`/`outline_tree`）放 `queries.py`，pytest 锁。
- **多作品 = 扫描 projects root**：`list_works(projects_root)` glob 子目录找 `bedrock.db`，每个开 conn 读 `work_name` 常量 + 卷/章计数。侧边栏作品下拉 = 工作区切换。
- **每请求开/关 conn，不缓存**（沿用 SP6-C）。无 context_processor。
- **唯一写点不变**：`advance_inspiration`（状态机单向）。API 包一层 JSON，非法转移返回 `{error}` 且 DB 不变。
- **CSRF = 同源 + `Content-Type: application/json` 校验**（替代 htmx 的 HX-Request；simple form 发不出 JSON content-type）。
- **路径穿越校验**：work_id 解析后必须在 projects_root 内 + 含 bedrock.db，否则 404。
- **node 构建物不入 git**：`frontend/node_modules`、`frontend/dist`、`src/bedrock/web/static/`（vite 输出目标）全部 gitignore。
- **单进程 + 一键启动**：日常用编译后产物，Flask 同进程托管 SPA 静态 + `/api`。一键启动脚本自动 build + serve。

## 3. 架构与文件落点

```
novel_test/
├── frontend/                      ← 新：Vue3 + Vite + Naive UI 工程（node 项目）
│   ├── package.json
│   ├── vite.config.ts             ← build.outDir → ../src/bedrock/web/static；dev proxy /api → :5050
│   ├── tsconfig.json
│   ├── index.html
│   ├── .gitignore                 ← node_modules / dist
│   └── src/
│       ├── main.ts                ← createApp + Naive + router + pinia
│       ├── App.vue                ← NLayout 外壳（侧边栏 + 顶栏 + router-view）
│       ├── router.ts              ← /works/:wid/{overview,matrix,inspirations,report,read,outline}
│       ├── api/client.ts          ← fetch 封装（统一 /api 前缀 + JSON + 错误处理）
│       ├── stores/workspace.ts    ← pinia: works 列表 + active work
│       ├── components/
│       │   ├── WorkSwitcher.vue   ← 侧边栏作品下拉
│       │   ├── SideNav.vue        ← 侧边栏导航（按 active work 作用域）
│       │   └── BeatDrawer.vue     ← POV ● 点击展开 beat
│       └── views/
│           ├── Overview.vue
│           ├── Matrix.vue
│           ├── Inspirations.vue
│           ├── Report.vue
│           ├── Reader.vue         ← 阅读模式
│           └── Outline.vue        ← 大纲模式（多级分组树）
├── src/bedrock/web/
│   ├── app.py                     ← 改：create_app(projects_root) + 挂载 api 蓝图 + 托管 SPA 静态
│   ├── api.py                     ← 新：/api 蓝图，全部 JSON，work_id 作用域
│   ├── queries.py                 ← 扩：list_works / overview_stats / chapter_text / outline_tree
│   ├── __main__.py                ← 改：--projects-root；一键启动逻辑（见 §6）
│   └── static/                    ← vite build 输出（gitignored）；index.html + assets/
│       └── .gitkeep
└── scripts/
    └── start_webui.bat            ← 新：一键启动（build + serve）
```

- `create_app(projects_root)`：存 `projects_root` 到 config；挂载 `/api` 蓝图；注册 SPA 静态路由（`/` + 未匹配路由回退 `index.html`，仅当 `static/index.html` 存在）。
- 开发期 Flask 不强求 SPA 产物存在（vite 单独 serve 前端）；生产期缺 `static/index.html` → 首页返回提示"请先 `npm run build`"。

## 4. 应用外壳

Naive `NLayout`（`has-sider`）：

- **左侧栏（NLayoutSider）**：
  - 顶部 `WorkSwitcher`：NSelect 列 `/api/works`。选中 → pinia 设 active work + `router.push('/works/:wid/overview')`。
  - 下方 `SideNav`：NMenu，项 = 总览 / POV矩阵 / 灵感池 / Review报告 / 正文·阅读 / 正文·大纲（全部按 active work 作用域；无 active work 时禁用）。
  - 底部：projects_root 路径（小字）。
- **顶栏（NLayoutHeader）**：作品名（NText strong）+ 面包屑（当前视图名）。
- **主区（NLayoutContent）**：`<router-view>`，深色主题。
- 全局 `NMessageProvider` / `NDialogProvider` 包裹（灵感推进报错用）。

## 5. 视图设计

### 5.1 总览 `Overview.vue` · `GET /api/works/<wid>/overview`

- 顶部 NStatistic 网格：卷数 / 章节(completed) / 章节(writing) / 角色数 / 字数总计 / 灵感各状态计数。
- 下方卷列表（NCard / NList）：每卷 = 名称 + 章数 + 状态徽章 + escalate 计数（有报告时）。

### 5.2 POV 矩阵 `Matrix.vue` · `GET /api/works/<wid>/matrix?volume=<vid>`

- 卷选择（NSelect，默认最小 number）。
- **NDataTable**：列动态生成 = 该卷 `DISTINCT pov_character_id`（NULL 不产列）+ 末尾"合计"列；行 = 章节（global_number + title）。**表格自动撑满宽度**（解决旧 100px 丑表）。
- 单元格 ●（NTag/圆点，青色）→ 点击 `BeatDrawer`（NDrawer）展示该章该角色 beats（sequence + purpose）。
- NULL POV 章：行渲染、单元格空。整卷无 POV：NEmpty 提示。

### 5.3 灵感池 `Inspirations.vue` · `GET /api/works/<wid>/inspirations?type=&status=`

- 筛选栏（NSelect type / NSelect status）。
- 列表（NDataTable 或 NCard 网格）：每条 = type(NTag) + status(NTag，语义色：raw 灰/refined 蓝/consumed 绿/partial 黄/discarded 红) + content + source + 推进按钮（按 `_LEGAL_TRANSITIONS` 显示合法目标）。
- 推进 → `POST .../advance` `{target}`：成功乐观更新当前条；非法 → `NMessage.error`，DB 不变。
- consumed 条显示「已采用」+ 作废按钮；discarded 条置灰删除线。

### 5.4 Review 报告 `Report.vue` · `GET /api/works/<wid>/report/<vid>`

- 卷选择（NSelect，只列有 `review_report_vol{N}.md` 的卷，`GET /api/works/<wid>/reports`）。
- api 返回 `{html_body, escalate_chs[], has_escalate}`（markdown 服务端渲染 + `parse_review_outcomes` 抽 escalate 集 + 正则注 `escalate-highlight` class，**沿用 SP6-C 既有逻辑**）。
- 前端 `v-html` 渲染 `html_body`，CSS 高亮 escalate 项（红框红底）。
- has_escalate 时顶部 NAlert 提示。

### 5.5 正文 · 阅读模式 `Reader.vue` · `GET /api/works/<wid>/chapters/<gnum>/text`

- 左侧或顶部章节目录（按卷分组的 NSelect / NCascader / 目录列表）。选章 → 主区渲染。
- **散文式排版**：段落按 `paragraph.seq` 升序，等宽容器（max-width ~720px）、舒适行距、首行缩进、章节标题大字。只渲染 `text`，不显示 beat/role 元数据（纯净阅读）。
- 上一章/下一章导航。

### 5.6 正文 · 大纲模式 `Outline.vue` · `GET /api/works/<wid>/outline?volume=<vid>`

- 卷选择。
- **多级分组树**（Naive `NTree` 或 NCascade，可展开/折叠）：
  ```
  📁 第1卷 · 边界
    📄 ch01 牤晓  [completed]
       ├ arc: purpose / scenes / ending / structure_type
       ├ outline: purpose / key_events / structure_hint
       └ beat 1: <purpose>
          └ ¶1 (role=narration): <text 截断>
  ```
  - 三级：卷 → 章 →（arc + outline_entry + beats）。beat 下可选挂段落预览（截断）。
  - 空字段（无 arc / 无 outline_entry / 无 beat）优雅省略，不渲染空节点。
- 数据来自 `outline_tree(conn, volume_id)`：join `chapter` + `chapter_arc` + `outline_entry` + `beat`（+ 可选 `paragraph` 计数）。

## 6. API 设计（`/api` 蓝图）

全部按 `work_id`（= projects_root 下的子目录名）作用域。`work_id` 解析：拼 `projects_root / work_id`，校验 `resolve()` 在 root 内 + 含 `bedrock.db`，否则 404。

```
GET  /api/works
     → [{id, name, volumes, chapters_completed, chapters_writing, has_any_report}]

GET  /api/works/<wid>/overview
     → {name, volumes:n, chapters:{completed,writing,total}, characters:n,
        word_total, inspirations:{raw,refined,consumed,partial,discarded},
        volume_list:[{id,number,name,chapter_count,status,escalate_count?}]}

GET  /api/works/<wid>/matrix?volume=<vid>
     → {volume_name, characters:[{id,name}], chapters:[{id,global_number,title,povs:[char_id]}]}

GET  /api/works/<wid>/inspirations?type=&status=
     → [{id,type,status,content,source,created_at,refined_at,promoted_at,consumed_into}]

POST /api/works/<wid>/inspirations/<iid>/advance   body: {target}
     → 200 {ok:true, item:{...}}  |  200 {ok:false, error:"..."}（非法转移/未知 id，DB 不变）
     [唯一写点；校验同源 + Content-Type: application/json]

GET  /api/works/<wid>/reports
     → [{volume_id, exists}]   // 扫描 review_report_vol{N}.md

GET  /api/works/<wid>/report/<vid>
     → {html_body, escalate_chs:[int], has_escalate:bool}
     // review_report_vol{vid}.md 不存在 → 404

GET  /api/works/<wid>/chapters
     → [{global_number, title, volume_id, volume_name, status}]

GET  /api/works/<wid>/chapters/<gnum>/text
     → {chapter:{global_number,title}, paragraphs:[{seq, text}]}   // seq 升序，阅读模式

GET  /api/works/<wid>/outline?volume=<vid>
     → {volume_name, chapters:[{id,global_number,title,status,
          arc:{purpose,scenes,ending,structure_type}|null,
          outline:{purpose,key_events,structure_hint}|null,
          beats:[{sequence,purpose,paragraph_count}]}]}   // 大纲模式
```

- advance 端点：`try: advance_inspiration(...) except ValueError as e: return {ok:false, error:str(e)}`。前端据 `ok` 决定更新/报错。**这保持 SP6-C 的"DB 不变 + 不崩 + 错误反馈"语义**。

## 7. queries.py 新增函数（纯函数，pytest 锁）

```python
def list_works(projects_root):
    """扫描 projects_root 子目录，找含 bedrock.db 的。每个开 conn 读 work_name + 计数。
    返回 [{id(目录名), name, volumes, chapters_completed, chapters_writing, has_any_report}]。"""

def overview_stats(conn):
    """单作品的统计聚合：卷/章(分状态)/角色/字数(paragraph.text 汉字数合计)/灵感各状态计数/卷列表。
    字数：sum over paragraph of len(去掉非汉字) —— 复用既有计数口径（telemetry.count 逻辑参考）。"""

def chapter_text(conn, global_number):
    """阅读模式：SELECT seq, text FROM paragraph WHERE chapter_id=? ORDER BY seq。
    返回 {chapter:{global_number,title}, paragraphs:[{seq,text}]}。无段落 → 空 paragraphs。"""

def outline_tree(conn, volume_id):
    """大纲模式：join chapter(+volume) LEFT JOIN chapter_arc LEFT JOIN outline_entry
    LEFT JOIN beat(聚合 paragraph 计数)。返回多级结构（见 §5.6）。
    字段不存在(表/列缺失)优雅降级 → null。"""
```

> **实现第一步先核 schema**：确认 `chapter_arc` / `outline_entry` 表与列名（repos 已有 `add_chapter_arc`/`add_outline_entry`，表必存在）。`paragraph.text` 汉字计数口径与 `telemetry` 对齐。

## 8. 开发与启动

### 开发（热更）
- 终端 A：`cd frontend && npm run dev` → vite @5173，`vite.config.ts` 配 proxy `/api` → `http://127.0.0.1:5050`。
- 终端 B：`python -m src.bedrock.web --projects-root projects/` → Flask @5050 只跑 API（SPA 由 vite 提供）。

### 单进程（日常）
- `npm run build` → `frontend/dist`；`vite.config.ts` 的 `build.outDir = "../src/bedrock/web/static"`，`emptyOutDir = true`。
- Flask 托管：`/` 与未匹配路由（非 `/api`、非静态资源）回退 `static/index.html`；`/static/...` 或 `/assets/...` 伺服构建产物。

### 一键启动 `scripts/start_webui.bat`
```bat
@echo off
cd /d %~dp0\..\
if not exist src\bedrock\web\static\index.html (
  echo [build] SPA 未构建，执行 npm run build...
  pushd frontend
  call npm install && call npm run build
  popd
)
python -m src.bedrock.web --projects-root projects
```
- 首次/产物缺失自动 `npm install && npm run build`；之后直接起 Flask。
- 也提供 `python -m src.bedrock.web --projects-root projects --rebuild`（可选 flag，shells out npm）。

## 9. 测试策略（CLI 优先）

### 层 1：纯函数（pytest，TDD 主体）`tests/bedrock/test_queries.py`
- `test_list_works_scans_subdirs`（含/不含 bedrock.db 的目录）
- `test_list_works_counts`（卷/章计数正确）
- `test_overview_stats`（各状态计数 + 字数）
- `test_chapter_text_orders_by_seq` / `_empty_chapter`
- `test_outline_tree_full`（章带 arc+outline+beats）
- `test_outline_tree_missing_fields_null`（无 arc/无 outline/无 beat → null/空，不崩）
- `test_outline_tree_groups_by_volume`

### 层 2：API（Flask test client）`tests/bedrock/test_api.py`（**取代** `test_web.py`）
- `test_api_works_lists`
- `test_api_overview`
- `test_api_matrix`
- `test_api_inspirations_filter`
- `test_api_advance_ok` / `_illegal_returns_error_db_unchanged` / `_requires_json_content_type`（CSRF）
- `test_api_report_renders_markdown` / `_escalate_highlight` / `_missing_404`
- `test_api_chapters` / `test_api_chapter_text` / `test_api_outline`
- `test_api_path_traversal_rejected`（`work_id=../etc` → 404）
- `test_create_app_requires_projects_root`（不存在 → SystemExit）

### 层 3：前端
- 不写自动化（本地工具）。手动冒烟 5+2 视图 + 推进交互 + 工作区切换。

### 回归
- 既有 218 条 repository/cli 测试**不受影响**（视图层重做不碰纯函数层）。
- `test_web.py`（11 条 Jinja）**删除**，被 `test_api.py` 取代。

## 10. 与既有系统边界

- **复用**：`outline.{list_inspirations,advance_inspiration,consume_inspiration}`、`queries.pov_matrix`、`parse_review_outcomes`、全部 repositories。
- **删除**：`src/bedrock/web/templates/`、`src/bedrock/web/static/app.css`（Naive 接管主题）、`app.py` 的 Jinja 路由、htmx。
- **改**：`app.py`（JSON API + SPA 托管）、`__main__.py`（`--projects-root`）、`launch.json`（bedrock-web 配置）、`pyproject.toml`（无 Python 新依赖，仅记录前端工程存在）。
- **不动**：SP1-5 核心管线、SP6-A CLI、SP6-B MCP、demo seed 脚本（仍产出 `projects/bedrock_demo`，工作台自动扫到）。

## 11. 验收标准

- 一键启动 `scripts/start_webui.bat` 起整个工作台（首次自动 build）。
- 侧边栏列作品（至少 `bedrock_demo`），切换工作区生效。
- 6 视图（总览/矩阵/灵感池/报告/正文阅读/正文大纲）均可访问、数据正确。
- POV 矩阵 NDataTable 撑满宽度、● 点击弹 beat drawer。
- 灵感池推进：合法生效 + 时间戳；非法报错 + DB 不变；consumed/discarded 显示正确；advance 校验 JSON content-type。
- 正文阅读：段落按 seq、散文排版、上下章导航。
- 正文大纲：卷/章/beat 多级树、可折叠、缺字段优雅省略。
- 报告：markdown 渲染 + escalate 逐项高亮。
- node 构建产物（node_modules/dist/static）不入 git。
- 全部测试通过（既有 218 + 新 test_queries + test_api；删 test_web）。
- 手动冒烟 6 视图 + 切工作区 + 推进交互正常。

## 12. 风险

- **Node 依赖**：本机 Node v22 + npm/pnpm 已确认；他人复现需 Node。一键脚本含 `npm install`。
- **构建产物体积**：dist 进 gitignore，不入库。
- **schema 假设**：`chapter_arc`/`outline_entry` 表列名以实现第一步核对为准；`outline_tree` 对缺字段优雅降级。
- **多作品性能**：`list_works` 每个开 conn 读计数，项目少（个位数）开销可忽略；不缓存（避免脏读）。
