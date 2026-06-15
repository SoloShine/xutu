# 磐石 Bedrock Web UI 重做：SPA 工作台

> 本文 **取代** `2026-06-15-bedrock-sp6c-web-design.md` 的视图层设计。SP6-C 已完成的**纯函数层**（`outline.list_inspirations` / `advance_inspiration` / `consume_inspiration`、`queries.pov_matrix`、`reader_commands.parse_review_outcomes`）**全部复用，零改动**。本 spec 只重做**视图层 + 接入层**：把 Flask+Jinja+htmx 的服务端渲染，换成 Vue3+Naive UI 的 SPA + Flask JSON API。
>
> **修订记录**：经 brainstorming 四轮问答 + **两路子代理对抗审核（数据源真实性 / 完备性边界）** 定稿。吸收全部 🔴/🟡。关键修订：①大纲模式改用 bedrock **真实存在**的 `master_outline`/`volume_outline`/`beat` 数据（原 spec 误引 novel_kg 的 `chapter_arc`/`outline_entry` 幻影表，已纠正）；②字数计数点名复用 `checks/word_count.compute_word_count`；③路径穿越校验写全（reject `/`/`\`/`..`/盘符 + 双向 resolve）；④advance 失败语义统一（业务失败 200{ok:false} vs 请求不合格 415）；⑤`pov_matrix` 返回 set 需 API 层转 list；⑥`consumed_into` JSON 字符串需解析；⑦`.gitignore` 主动新增三条；⑧launch.json `--project`→`--projects-root` 语义变更；⑨补 5 个边界测试。

## 1. 目标与范围

把当前"裸 HTML 工作台"重做成**专业 SPA 工作台**：左侧栏作品切换 + 导航，主区多视图，现成组件库撑起专业度（解决 POV 矩阵 100px 小表这类手搓丑件）。

**范围 = 1 个 Vue3 SPA + Flask 退成 JSON API + 多个写操作（灵感状态推进 / 灵感内容编辑 / 元数据编辑 / 大纲编辑），全部走 `add_amendment` 审计骨架**：

| 视图 | 模式/说明 | 读/写 |
|------|-----------|-------|
| 总览 | 作品仪表盘（统计 + 卷列表） | 只读 |
| POV 矩阵 | NDataTable，行=章/列=角色，● 展开 beat | 只读 |
| 灵感池 | 卡片/表格 + 状态推进 + 内容编辑 | 读 + 推进 + 编辑（未消费时） |
| Review 报告 | markdown 渲染 + escalate 高亮 | 只读 |
| 正文 · 阅读模式 | 散文式排版（段落按 seq） | 只读 |
| 正文 · 大纲模式 | 作品→卷→章→beat 多级分组树 | 只读 |

**不在范围**：在线编辑**正文段落**（paragraph.text —— SSOT 由管线写，本期不开；见 §12 正文独立 spec）；治理写入 flip（volume_outline lock/unlock、mark-*，留 CLI/MCP —— Web 可触发 lock-guard 错误但不禁/解锁）；多用户/身份/部署（本地 loopback 单用户）；前端单元测试（本地工具，手动冒烟）；**schema 改动**（本 spec 零 schema 迁移，全部基于既有表）。

## 2. 关键设计决策

- **Vue3 SFC + Vite + Naive UI + vue-router + pinia**。Naive 深色优先、自带 Layout(侧边栏)/DataTable/Tabs/Tree/Drawer/Message，开箱即专业。`marked` 渲染 markdown。TS。
- **Flask 退成纯 JSON API**（`/api` 蓝图）。旧 Jinja 模板 / htmx / `app.css` / `templates/` **全部删除**。
- **纯函数层零改动复用**：`repositories/outline.py`、`queries.py`、`reader_commands.parse_review_outcomes`、`checks/word_count.compute_word_count`。新增查询函数（`list_works`/`overview_stats`/`chapter_text`/`outline_tree`）放 `queries.py`，pytest 锁。
- **多作品 = 扫描 projects root**：`list_works(projects_root)` glob 子目录找 `bedrock.db`，每个开 conn 读 `get_constant(conn,"work_name")` + 卷/章计数。侧边栏作品下拉 = 工作区切换。
- **每请求开/关 conn，不缓存**（沿用 SP6-C）。无 context_processor。
- **两个写操作**：
  - **状态推进** `advance_inspiration`（状态机单向，复用 SP6-C）。业务失败（非法转移/未知 iid/缺 target）返回 `200 {ok:false,error}` 且 DB 不变；**请求不合格**（Content-Type 非 application/json）返回 **415**。
  - **内容编辑** `update_inspiration_content`（新增）。**可编辑 ⟺ `status ∈ {raw,refined,partial}` 且 `consumed_into` 为空**；consumed / discarded 一律冻结（已消费进正文 = 历史记录，编辑会与正文使用脱节）。编辑字段 = `content`（必填非空）+ `source`（可选）。业务失败（已冻结/未知 iid/content 空）返回 `200 {ok:false,error}` 且 DB 不变；Content-Type 非 JSON → 415。
- **审计骨架 = `governance.add_amendment`**：所有 Web 手动编辑（灵感内容 + 元数据 + 大纲）在 repo 层写字段后**记一条 amendment**（`entity_type, entity_id, field, old, new`）。这是管线既有的修正记录机制（beat override→amendment 即此），让 Web 编辑可审计、可被 drift 检测识别。amendment 记录失败不阻断主写（best-effort，记日志）。
- **元数据 / 大纲编辑（层1+层2）**：复用既有 `update_beat_contract`（lock-guarded）/ `update_beat_status`；新建 `update_character`/`update_chapter_meta`/`update_volume_meta`/`update_location`/`update_theme`/`update_motif`/`update_beat_meta`/`update_master_outline`。详见 §5.7。所有编辑同样走 amendment + 失败语义（业务 `200{ok:false}` / 请求不合格 `415`）。
- **CSRF = 同源 + `Content-Type: application/json` 校验**（替代 htmx 的 HX-Request；simple form 发不出 JSON content-type）。
- **路径穿越校验（写全）**：路由用 `<wid>`（string converter，不含 `/`）；`wid` 含 `/`、`\`、等于 `..`/`.` 或匹配盘符前缀（`r'^[A-Za-z]:'`）→ 404；再 `(root.resolve() / wid).resolve()` 后 `is_relative_to(root.resolve())` 失败 → 404；最终需含 `bedrock.db`。
- **node 构建物不入 git**：**主动新增** `.gitignore` 三条：`frontend/node_modules/`、`frontend/dist/`、`src/bedrock/web/static/`（保留 `src/bedrock/web/static/.gitkeep`）。
- **单进程 + 一键启动**：日常用编译后产物，Flask 同进程托管 SPA 静态 + `/api`。一键启动脚本（Windows `.bat`，含 `where npm` 前置检查；附 Mac/Linux 手动命令）自动 build + serve。
- **序列化修正（API 层负责）**：`pov_matrix` 返回的 `povs` 是 Python `set` → API 层 `sorted(list(...))` 再 jsonify；`list_inspirations` 返回的 `consumed_into` 是 JSON 字符串 → API 层 `json.loads` 解析为 list（空/异常降级为 `[]`）。
- **字数口径**：`overview_stats` 字数 = `sum(compute_word_count([p.text]) for p in paragraphs)`，复用 `checks/word_count.py`，与 `chapter_metrics` 同源（不引 telemetry，口径一致）。

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
│   └── static/                    ← vite build 输出（gitignored）；.gitkeep 占位
│       └── .gitkeep
└── scripts/
    └── start_webui.bat            ← 新：一键启动（build + serve）
```

- `create_app(projects_root)`：存 `projects_root`（内部 `resolve()` 成绝对路径）到 config；挂载 `/api` 蓝图；注册 SPA 静态路由（`/` + 未匹配路由回退 `index.html`，仅当 `static/index.html` 存在）。
- **`create_app` 签名变更（project_dir→projects_root，语义不同）**：旧校验"`bedrock.db` 不存在就 SystemExit"改为"`projects_root` 不是目录就 SystemExit"（root 是父目录，自身不含 db）。
- 开发期 Flask 不强求 SPA 产物存在（vite 单独 serve 前端）；生产期缺 `static/index.html` → 首页返回提示"请先 `npm run build`"。

## 4. 应用外壳

Naive `NLayout`（`has-sider`）：

- **左侧栏（NLayoutSider）**：
  - 顶部 `WorkSwitcher`：NSelect 列 `/api/works`。选中 → pinia 设 active work + `router.push('/works/:wid/overview')`。
  - 下方 `SideNav`：NMenu，项 = 总览 / POV矩阵 / 灵感池 / Review报告 / 正文·阅读 / 正文·大纲（全部按 active work 作用域；无 active work 时禁用）。
  - 底部：projects_root 路径（小字）。
- **顶栏（NLayoutHeader）**：作品名（NText strong）+ 面包屑（当前视图名）。
- **主区（NLayoutContent）**：`<router-view>`，深色主题。
- 全局 `NMessageProvider` / `NDialogProvider` 包裹。**全局错误约定**：fetch 失败 → `NMessage.error` + 路由回 overview；未知 work_id → `NResult` 404 页；列表/加载态用 NSpin/NEmpty。

## 5. 视图设计

### 5.1 总览 `Overview.vue` · `GET /api/works/<wid>/overview`

- 顶部 NStatistic 网格：卷数 / 章节(completed) / 章节(writing) / 角色数 / 字数总计 / 灵感各状态计数。
- 下方卷列表（NCard / NList）：每卷 = 名称 + volume_type + 章数 + status 徽章 + escalate 计数（有报告时）。

### 5.2 POV 矩阵 `Matrix.vue` · `GET /api/works/<wid>/matrix?volume=<vid>`

- 卷选择（NSelect，默认最小 number）。
- **NDataTable**：列动态生成 = 该卷 `DISTINCT pov_character_id`（NULL 不产列）+ 末尾"合计"列；行 = 章节（global_number + title）。**表格自动撑满宽度**（解决旧 100px 丑表）。
- 单元格 ●（NTag/圆点，青色）→ 点击 `BeatDrawer`（NDrawer）展示该章该角色 beats（sequence + purpose + status）。
- NULL POV 章：行渲染、单元格空。整卷无 POV：NEmpty 提示。

### 5.3 灵感池 `Inspirations.vue` · `GET /api/works/<wid>/inspirations?type=&status=`

- 筛选栏（NSelect type / NSelect status）。
- 列表（NDataTable 或 NCard 网格）：每条 = type(NTag) + status(NTag，语义色：raw 灰/refined 蓝/consumed 绿/partial 黄/discarded 红) + content + source + 推进按钮（按 `_LEGAL_TRANSITIONS` 显示合法目标）。
- **consumed 条**：额外展示「已采用」+ `consumed_into` 解析后的 target 列表（只读）+ 作废按钮。
- **discarded 条**（终态）：**不渲染任何推进按钮**（合法转移为空集），仅置灰删除线。
- **时间戳**：`created_at`/`refined_at`/`promoted_at` 按 sqlite `datetime('now')` 存（UTC），前端**只显示日期**或按本地时区展示，避免 8 小时偏差。
- **内容编辑**：可编辑卡（status ∈ {raw,refined,partial} 且 consumed_into 空）显示「编辑」按钮 → NModal 表单（content textarea + source input）→ `PATCH .../inspirations/<iid>`。成功乐观更新；`{ok:false}` → NMessage。consumed/discarded 卡不显示编辑按钮。
- 推进 → `POST .../advance` `{target}`：成功乐观更新当前条；`{ok:false}` → `NMessage.error(error)`，DB 不变。

### 5.4 Review 报告 `Report.vue` · `GET /api/works/<wid>/report/<vid>`

- 卷选择（NSelect，只列有 `review_report_vol{N}.md` 的卷，`GET /api/works/<wid>/reports`）。
- api 返回 `{html_body, escalate_chs[], has_escalate}`（markdown 服务端渲染 + `parse_review_outcomes` 抽 escalate 集 + 正则注 `escalate-highlight` class，**沿用 SP6-C 既有逻辑**）。
- 前端 `v-html` 渲染 `html_body`，CSS 高亮 escalate 项（红框红底）。
- has_escalate 时顶部 NAlert 提示。
- **V2 容错（继承 SP6-C H4）**：`parse_review_outcomes` 对 V2 手写报告（无 SP5 格式段）返回**空 dict 不抛错** → `escalate_chs=[]`、`has_escalate=false`，前端不显示 NAlert、不报错、全文正常渲染。spec 显式保留此特性。

### 5.5 正文 · 阅读模式 `Reader.vue` · `GET /api/works/<wid>/chapters/<gnum>/text`

- 左侧或顶部章节目录（按卷分组的 NSelect / 目录列表）。选章 → 主区渲染。
- **散文式排版**：段落按 `paragraph.seq` 升序，等宽容器（max-width ~720px）、舒适行距、首行缩进、章节标题大字。只渲染 `text`，不显示 beat/role 元数据（纯净阅读）。标题取 `chapter.title`（不加"第N章"前缀，避免与导出版重复）。
- 上一章/下一章导航：**首章禁用"上一章"、末章禁用"下一章"**（按 `/api/works/<wid>/chapters` 全局序判断）。

### 5.6 正文 · 大纲模式 `Outline.vue` · `GET /api/works/<wid>/outline?volume=<vid>`（**改用 bedrock 真实表**）

- 卷选择（默认全部卷，可单选）。
- **多级分组树**（Naive `NTree`，可展开/折叠）。数据来自 bedrock **真实存在的** `master_outline` / `volume_outline` / `chapter` / `beat` / `paragraph`：

  ```
  🏛 作品大纲（master_outline，顶部卡片，任一字段有值才渲染）
     ├ theme_evolution
     ├ key_arcs[]（JSON 数组）
     ├ key_milestones[]
     └ rhythm_curve
  📁 第1卷 · 边界  [volume_type=opening · status=completed · volume_outline.status=locked]
     ├ theme_seeds[]
     └ 📄 ch01 牤晓  [status=completed]
          ├ beat 1 [written · POV 韩峥]: <purpose>
          │    └ scene_setting + ¶<count>
          ├ beat 2 [deviated · 沈夜]: <purpose>
          │    └ ⚠ deviation_note
          └ ...
  ```

  - **三级**：卷 → 章 → beat。卷级挂 `volume_outline`(status/locked_at/beat_contracts) + `theme_seeds`；beat 级挂 `pov`(JOIN character.name)、`scene_setting`(JSON)、`status`(planned/written/verified/deviated/overridden)、`deviation_note`、paragraph 计数。
  - 顶部可选挂 `master_outline` 卡片（theme_evolution/key_arcs/key_milestones/rhythm_curve，字段空则省略）。
  - 空字段优雅省略（无 volume_outline 行 / 无 beat / master_outline 字段全空 → 不渲染该节点）。
- 数据来自 `outline_tree(conn, volume_id|None)`：基于 `volume` LEFT JOIN `volume_outline`、`chapter`、`beat`（+ `paragraph` 计数 + `character` 取 POV 名），详见 §7。

## 5.7 可编辑实体工作台（层1 元数据 + 层2 大纲）

所有编辑走统一模式：前端表单（NModal/NDrawer）→ `PATCH /api/works/<wid>/<entity>/<id>`（JSON）→ repo 函数（校验 + 写 + 记 amendment）→ 返回更新后对象。失败语义与灵感编辑一致（业务 `200{ok:false}` / 请求不合格 `415`）。

**v1 可编辑清单**（repo 列：✅既有 / 🆕新建）：

| 实体 | 可编辑字段 | repo 函数 | guard / 备注 | 前端落点 |
|------|-----------|----------|--------------|---------|
| 角色 character | name / pronoun / gender / role / personality / goals / abilities / aliases / state | 🆕 `update_character(conn, cid, **fields)` | name UNIQUE 冲突 → `{ok:false}`；state/pronoun/role 须在 schema CHECK 枚举内 | 总览→角色区，或新「角色」标签页 |
| 章节 chapter | title | 🆕 `update_chapter_meta(conn, ch_id, title)` | title 非空 | 阅读模式章标题旁「编辑」 |
| 卷 volume | name / theme_seeds(JSON) | 🆕 `update_volume_meta(conn, vid, name, theme_seeds)` | theme_seeds 须合法 JSON 数组；status/volume_type **不动**（治理） | 总览卷列表 / 大纲卷节点 |
| 地点 location | description / state / loc_type | 🆕 `update_location(...)` | — | （v1 可并入总览，或延后） |
| 主题 theme | description / evolution | 🆕 `update_theme(...)` | — | 同上 |
| 母题 motif | meaning / evolution | 🆕 `update_motif(...)` | — | 同上 |
| beat 契约 | volume_outline.beat_contracts 项 | ✅ `update_beat_contract(conn, vid, beat_id, new_contract)` | **locked → OutlineLockedError → `{ok:false}`**（不禁/解锁，提示用户走 CLI unlock） | 大纲模式 beat 节点 |
| beat 行 | status / deviation_note | ✅ `update_beat_status(conn, beat_id, status, deviation_note)` | status 须在枚举内 | 大纲模式 beat 节点 |
| beat 行 | purpose / scene_setting | 🆕 `update_beat_meta(conn, beat_id, purpose, scene_setting)` | purpose `CHECK(length>=10)` → 违例 `{ok:false}` | 大纲模式 beat 节点 |
| master_outline | theme_evolution / key_arcs / key_milestones / rhythm_curve | 🆕 `update_master_outline(conn, **fields)` | JSON 字段须合法数组/串 | 大纲模式顶部「作品大纲」卡片 |

**架构约束**：
- **不动的字段（治理/SSOT owned）**：volume.status / volume.volume_type（governance）；chapter.status（管线）；paragraph.*（正文，§12 独立 spec）；inspiration.status 由状态机推进（不在此 PATCH）。
- **统一失败语义**：业务失败（枚举违例/UNIQUE 冲突/locked/未知 id/字段非法）→ `200 {ok:false,error}` + DB 不变 + 前端 NMessage；请求不合格（Content-Type 非 JSON）→ 415。
- **amendment 记录**：每个 update repo 在 commit 前读 old、写后调 `add_amendment(entity_type, entity_id, field, old, new)`（多字段改 → 多条 amendment）。amendment 写失败 best-effort（记日志，不阻断）。
- **JSON 字段**：theme_seeds / scene_setting / abilities / aliases / key_arcs / key_milestones 在 repo 入口 `json.loads` 校验合法性，非法 → `{ok:false}`。

**前端**：各视图在其展示的实体上加「编辑」入口（NButton/双击）→ NModal 表单（按字段类型：text/textarea/NSelect 枚举/NTag 输入数组）→ PATCH → 乐观更新或重拉。失败 NMessage。locked beat 契约的编辑按钮禁用并 tooltip 提示「卷已锁定，需 CLI unlock」。

## 6. API 设计（`/api` 蓝图）

全部按 `work_id`（= projects_root 下的子目录名）作用域。**路径解析**（§2 规则）：路由 `<wid>`（string，不含 `/`）；含 `/`/`\`/`..`/`.`/盘符 → 404；`(root.resolve()/wid).resolve()` 不在 `root.resolve()` 内 → 404；无 `bedrock.db` → 404。

```
GET  /api/works
     → [{id, name, volumes, chapters_completed, chapters_writing, has_any_report}]

GET  /api/works/<wid>/overview
     → {name, volumes:n, chapters:{completed,writing,total}, characters:n,
        word_total, inspirations:{raw,refined,consumed,partial,discarded},
        volume_list:[{id,number,name,volume_type,chapter_count,status,escalate_count?}]}

GET  /api/works/<wid>/matrix?volume=<vid>
     → {volume_name, characters:[{id,name}], chapters:[{id,global_number,title,povs:[char_id]}]}
     // povs 经 API 层 set→sorted(list) 转换

GET  /api/works/<wid>/inspirations?type=&status=
     → [{id,type,status,content,source,created_at,refined_at,promoted_at,
         consumed_into:[{target_type,target_id}]}]   // consumed_into 经 json.loads 解析；异常降级 []

POST /api/works/<wid>/inspirations/<iid>/advance   header: Content-Type: application/json
     body: {target}
     → Content-Type != application/json      → 415                      // 请求不合格
     → 业务失败（非法转移 / 未知 iid / 缺 target / target 非法）
                                              → 200 {ok:false, error}    // DB 不变，前端 NMessage.error
     → 成功                                    → 200 {ok:true, item:{...}}  // 写操作 1：状态推进

PATCH /api/works/<wid>/inspirations/<iid>      header: Content-Type: application/json
     body: {content, source?}
     → Content-Type != application/json      → 415
     → 业务失败（已冻结：consumed/discarded 或 consumed_into 非空 / 未知 iid / content 空）
                                              → 200 {ok:false, error}    // DB 不变
     → 成功                                    → 200 {ok:true, item:{...}}  // 写操作 2：内容编辑（仅未消费）

GET  /api/works/<wid>/reports
     → [{volume_id, exists}]   // 扫描 review_report_vol{N}.md

GET  /api/works/<wid>/report/<vid>
     → {html_body, escalate_chs:[int], has_escalate:bool}
     // V2 手写报告 → escalate_chs=[] / has_escalate=false（不抛错）
     // review_report_vol{vid}.md 不存在 → 404

GET  /api/works/<wid>/chapters
     → [{global_number, title, volume_id, volume_name, status}]

GET  /api/works/<wid>/chapters/<gnum>/text
     → {chapter:{global_number,title}, paragraphs:[{seq,text}]}   // seq 升序；无段落 → paragraphs:[]

GET  /api/works/<wid>/outline?volume=<vid>          // volume 省略 = 全部卷
     → {master_outline:{theme_evolution,key_arcs,key_milestones,rhythm_curve}|null,
        volumes:[{id,number,name,volume_type,status,
          volume_outline:{status,locked_at,beat_contracts}|null,
          theme_seeds:[],
          chapters:[{id,global_number,title,status,
            beats:[{id,sequence,purpose,pov_name,scene_setting,status,deviation_note,paragraph_count}]}]}]}
```

**编辑端点（层1+层2，统一 PATCH，Content-Type: application/json，失败语义同灵感编辑）**：
```
PATCH /api/works/<wid>/characters/<id>         body: {任意可编辑 character 字段}   → 200 {ok,item}|{ok:false,error}
PATCH /api/works/<wid>/chapters/<id>           body: {title}
PATCH /api/works/<wid>/volumes/<id>            body: {name, theme_seeds}
PATCH /api/works/<wid>/locations/<id>          body: {description, state, loc_type}
PATCH /api/works/<wid>/themes/<id>             body: {description, evolution}
PATCH /api/works/<wid>/motifs/<id>             body: {meaning, evolution}
PATCH /api/works/<wid>/volumes/<vid>/beats/<bid>/contract   body: {purpose?, scene_setting?, pov?, ...}   // → update_beat_contract；locked → {ok:false}
PATCH /api/works/<wid>/beats/<id>              body: {status?, deviation_note?, purpose?, scene_setting?}  // status/note→update_beat_status；purpose/scene→update_beat_meta
PATCH /api/works/<wid>/master_outline          body: {theme_evolution?, key_arcs?, key_milestones?, rhythm_curve?}
```
所有 PATCH：Content-Type 非 JSON → 415；业务失败（枚举违例/UNIQUE/locked/未知 id/字段非法/JSON 非法）→ `200 {ok:false,error}` + DB 不变 + 记 amendment（仅成功时）。

## 7. queries.py 新增函数（纯函数，pytest 锁）

```python
from src.bedrock.checks.word_count import compute_word_count
from src.bedrock.repositories.worldbook import get_constant

def list_works(projects_root):
    """扫描 projects_root 子目录，找含 bedrock.db 的。每个开 conn：
    name = get_constant(conn,"work_name")["value"]（None → 降级用目录名）；
    计 volumes / chapters_completed / chapters_writing / has_any_report（扫 review_report_vol*.md）。
    返回 [{id(目录名), name, ...}]。"""

def overview_stats(conn):
    """单作品统计：volumes / chapters{completed,writing,total}（GROUP BY status）/
    characters / word_total（sum(compute_word_count([p.text]) for p in all paragraphs)）/
    inspirations 各 status 计数（GROUP BY status）/ volume_list（含 volume_type）。
    compute_word_count 接收 text 列表，需先 SELECT text 出来再喂。"""

def chapter_text(conn, global_number):
    """阅读模式：SELECT seq, text FROM paragraph WHERE chapter_id=(该 gnum) ORDER BY seq。
    返回 {chapter:{global_number,title}, paragraphs:[{seq,text}]}。无段落 → 空 paragraphs。"""

def update_inspiration_content(conn, inspiration_id, content, source=None):
    """编辑灵感内容（仅未消费时）。guard：
    status IN ('raw','refined','partial') 且 json.loads(consumed_into or '[]')==[] —— 否则 raise
    ValueError（已消费/已弃用 = 冻结）。content 去空后非空校验。source 非 None 则一并更新。
    在任何 UPDATE 前 raise（与 advance_inspiration 同模式，保证非法时不落库）。
    返回更新后整行 dict。"""

def outline_tree(conn, volume_id=None):
    """大纲模式（真实表）：volume [LEFT JOIN volume_outline] → chapter → beat
    [+ paragraph 计数 + JOIN character 取 pov 名]。
    另读 master_outline(id=1) 单行。
    所有 LEFT JOIN → 缺行字段 null。JSON 列(theme_seeds/beat_contracts/scene_setting/
    key_arcs/key_milestones)在函数内 json.loads（异常降级 []/''）。
    返回结构见 §6 outline。"""
```

> **schema 已核对**（本次审核已逐表确认）：`volume`(number/name/volume_type/status/theme_seeds)、`volume_outline`(volume_id/status/locked_at/beat_contracts)、`master_outline`(id=1/theme_evolution/key_arcs/key_milestones/rhythm_curve)、`chapter`(volume_id/global_number/title/status)、`beat`(chapter_id/sequence/purpose/pov_character_id/scene_setting/status/deviation_note)、`paragraph`(chapter_id/seq/text/beat_id/role，主键 para_id)、`character`(name)。**无 chapter_arc/outline_entry**（那是 novel_kg）。

### §7.1 编辑 repo 函数（层1+层2，分布在 character.py / plot_tree.py / worldbook.py / outline.py）

统一模式：读 old → 校验（枚举/UNIQUE/非空/JSON 合法）→ 非法在 UPDATE 前 raise ValueError → UPDATE → `add_amendment`（best-effort）→ commit → 返回更新后 dict。

- 🆕 `character.py :: update_character(conn, cid, **fields)` — 白名单字段（name/pronoun/gender/role/personality/goals/abilities/aliases/state）；name 改值先查 UNIQUE 冲突；JSON 列（abilities/aliases）入参可 list 或 str，存 `json.dumps`；枚举字段（pronoun/role/state/gender）校验。
- 🆕 `plot_tree.py :: update_chapter_meta(conn, ch_id, title)` / `update_volume_meta(conn, vid, name=None, theme_seeds=None)` / `update_beat_meta(conn, beat_id, purpose=None, scene_setting=None)` — purpose 校验 `length>=10`。
- 🆕 `worldbook.py :: update_location / update_theme / update_motif(conn, id, **fields)`。
- 🆕 `outline.py :: update_master_outline(conn, **fields)` — JSON 字段（key_arcs/key_milestones）入参 list，存 `json.dumps`；theme_evolution/rhythm_curve 字符串。
- ✅ 既有复用：`update_beat_contract`（lock-guarded，OutlineLockedError 透传）、`update_beat_status`。
- 🆕 各 update 内部统一调 `governance.add_amendment(conn, entity_type, entity_id, field, old, new)`（每改一字段一条）。封装一个私有 `_record amendments` 助手避免重复。

## 8. 开发与启动

### 开发（热更）
- 终端 A：`cd frontend && npm run dev` → vite @5173，`vite.config.ts` 配 proxy `/api` → `http://127.0.0.1:5050`。
- 终端 B：`python -m src.bedrock.web --projects-root projects/` → Flask @5050 只跑 API（SPA 由 vite 提供）。

### 单进程（日常）
- `npm run build` → `frontend/dist`；`vite.config.ts` 的 `build.outDir = "../src/bedrock/web/static"`，`emptyOutDir = true`。
- Flask 托管：`/` 与未匹配路由（非 `/api`、非静态资源）回退 `static/index.html`；静态资源伺服构建产物。

### 一键启动 `scripts/start_webui.bat`
```bat
@echo off
cd /d %~dp0\..\
where npm >nul 2>nul || (echo [error] 未找到 npm，请先安装 Node.js & exit /b 1)
if not exist src\bedrock\web\static\index.html (
  echo [build] SPA 未构建，执行 npm install + build...
  pushd frontend
  call npm install && call npm run build || (echo [error] build 失败 & popd & exit /b 1)
  popd
)
python -m src.bedrock.web --projects-root projects
```
- Mac/Linux 手动：`cd frontend && npm install && npm run build && cd .. && python -m src.bedrock.web --projects-root projects`。
- 也提供 `python -m src.bedrock.web --projects-root projects --rebuild`（可选 flag，shells out npm）。

## 9. 测试策略（CLI 优先）

### 层 1：纯函数（pytest，TDD 主体）`tests/bedrock/test_queries.py`
- `test_list_works_scans_subdirs`（含/不含 bedrock.db 的目录）
- `test_list_works_name_from_constant`（get_constant work_name；None 降级目录名）
- `test_list_works_counts`（卷/章 completed/writing 计数 + has_any_report）
- `test_overview_stats`（各状态计数 + word_total 用 compute_word_count）
- `test_overview_stats_empty_work`（0 卷 0 章 0 灵感）
- `test_chapter_text_orders_by_seq` / `_empty_chapter`
- `test_outline_tree_full`（卷带 volume_outline + 章带 beats）
- `test_outline_tree_missing_fields_null`（无 volume_outline / 无 beat → null/空，不崩）
- `test_outline_tree_master_outline`（master_outline 字段空则省略）
- `test_outline_tree_groups_by_volume`

### 层 1.5：纯函数 `tests/bedrock/test_outline.py`（+内容编辑）
- `test_update_content_raw_ok`（raw + consumed_into 空 → 改 content 成功）
- `test_update_content_refined_partial_ok`（refined/partial 未消费 → 可改）
- `test_update_content_frozen_consumed`（status=consumed 或 consumed_into 非空 → ValueError，DB 不变）
- `test_update_content_frozen_discarded`（discarded → ValueError）
- `test_update_content_unknown_id`（ValueError）
- `test_update_content_empty_rejected`（content 空白 → ValueError）
- `test_update_content_with_source`（source 一并更新）

### 层 1.6：纯函数 `tests/bedrock/test_edit_repos.py`（层1+层2 编辑 repo）
- `test_update_character_fields`（personality/goals 等改成功 + 记 amendment）
- `test_update_character_name_unique_conflict`（重名 → ValueError，DB 不变）
- `test_update_character_enum_invalid`（pronoun 非法枚举 → ValueError）
- `test_update_chapter_meta_title` / `test_update_volume_meta_theme_seeds_json`
- `test_update_beat_meta_purpose_too_short`（<10 → ValueError）
- `test_update_location/theme/motif`
- `test_update_master_outline_json_fields`
- `test_update_beat_contract_locked_rejected`（locked → OutlineLockedError，beat_contracts 不变）
- `test_update_beat_status_records_amendment`
- `test_update_unknown_id`（各实体 → ValueError）
- `test_amendment_recorded_on_every_edit`（每次成功编辑产出对应 amendment 行）

### 层 2：API（Flask test client）`tests/bedrock/test_api.py`（**取代** `test_web.py`）
- `test_api_works_lists`
- `test_api_overview` / `test_api_overview_empty`
- `test_api_matrix` / `test_api_matrix_no_pov_volume`（NEmpty 分支）/ `test_api_matrix_null_pov_row`
- `test_api_inspirations_filter` / `test_api_inspirations_consumed_into_parsed`（返回 list 非 JSON 字符串）
- `test_api_advance_ok` / `_illegal_returns_error_db_unchanged` / `_unknown_iid_returns_error` / `_missing_target` / `_requires_json_content_type`（415）
- `test_api_edit_content_ok`（raw 未消费 → PATCH 改 content 成功）
- `test_api_edit_content_frozen`（consumed/discarded → `{ok:false}` + DB 不变）
- `test_api_edit_content_empty_rejected` / `_requires_json_content_type`（415）
- **层1+层2 编辑 API**：`test_api_edit_character` / `_name_unique_conflict` / `_enum_invalid` / `test_api_edit_chapter_title` / `test_api_edit_volume_meta` / `test_api_edit_beat_contract_locked`（→ {ok:false}）/ `test_api_edit_beat_status` / `test_api_edit_beat_meta_purpose_short` / `test_api_edit_master_outline` / `test_api_edit_unknown_id_404_or_okfalse`
- `test_api_reports_scan`（列出有报告的卷）
- `test_api_report_renders_markdown` / `_escalate_highlight` / `_v2_tolerant_empty_escalate` / `_missing_404`
- `test_api_chapters`
- `test_api_chapter_text` / `test_api_chapter_text_missing_gnum`
- `test_api_outline` / `test_api_outline_empty_volume`
- `test_api_path_traversal_rejected`（`wid=../etc` / `wid=a/b` / `wid=C:x` → 404）
- `test_create_app_requires_projects_root`（**不是目录** → SystemExit；语义改：root 自身不需 bedrock.db）

### 层 3：前端
- 不写自动化（本地工具）。手动冒烟 6 视图 + 推进交互 + 工作区切换。

### 回归
- 既有 218 条 repository/cli 测试**不受影响**。
- **`tests/bedrock/test_web_queries.py` 保留通过**（用 `pov_matrix`/`list_volumes_simple`，这两个函数零改动）。
- `test_web.py`（11 条 Jinja）**删除**，被 `test_api.py` 取代。

## 10. 与既有系统边界

- **复用**：`outline.{list_inspirations,advance_inspiration,consume_inspiration}`、`queries.pov_matrix`（**API 层 set→list 转换**）、`parse_review_outcomes`、`checks/word_count.compute_word_count`、`worldbook.get_constant`、全部 repositories。
- **删除**：`src/bedrock/web/templates/`、`src/bedrock/web/static/app.css`（Naive 接管主题）、`app.py` 的 Jinja 路由 + context_processor、htmx。
- **改**：`app.py`（JSON API + SPA 托管，签名 project_dir→projects_root）、`__main__.py`（`--projects-root`）、`launch.json`（bedrock-web 配置 **`--project projects/bedrock_demo` → `--projects-root projects`**，语义从单项目变扫整个 root）、`pyproject.toml`（无 Python 新依赖，仅记录前端工程存在）。
- **新增 `.gitignore` 三条**：`frontend/node_modules/`、`frontend/dist/`、`src/bedrock/web/static/`（保留 `.gitkeep`）。
- **不动**：SP1-5 核心管线、SP6-A CLI、SP6-B MCP、demo seed 脚本（仍产出 `projects/bedrock_demo`，工作台自动扫到）、schema（零迁移）。

## 11. 验收标准

- 一键启动 `scripts/start_webui.bat` 起整个工作台（首次自动 build，缺 npm 报错退出）。
- 侧边栏列作品（至少 `bedrock_demo`），切换工作区生效。
- 6 视图（总览/矩阵/灵感池/报告/正文阅读/正文大纲）均可访问、数据正确。
- POV 矩阵 NDataTable 撑满宽度、● 点击弹 beat drawer。
- 灵感池推进：合法生效 + 时间戳；非法/未知 iid/缺 target → `{ok:false}` + DB 不变 + NMessage；Content-Type 非 JSON → 415；consumed 显示 consumed_into、discarded 无按钮。
- 灵感池内容编辑：raw/refined/partial 且未消费 → 可编辑 content(+source)；consumed/discarded → 冻结（`{ok:false}` + DB 不变）；编辑按钮仅可编辑卡显示。
- 元数据编辑（层1）：角色档案 / 章标题 / 卷名+theme_seeds / 世界观（location/theme/motif）可 PATCH；name UNIQUE 冲突 / 枚举违例 → `{ok:false}` + DB 不变；每次成功编辑记 amendment。
- 大纲编辑（层2）：beat 契约（locked → `{ok:false}` 提示 unlock）/ beat 状态+偏差 / beat purpose(>=10)+scene_setting / master_outline 字段可 PATCH；purpose 过短 → `{ok:false}`；记 amendment。
- 正文阅读：段落按 seq、散文排版、上下章导航（首末章禁用）。
- 正文大纲：作品→卷→章→beat 多级树、可折叠、master_outline/volume_outline/beat.status/deviation_note 展示、缺字段优雅省略。
- 报告：markdown 渲染 + escalate 逐项高亮；V2 报告不报错。
- node 构建产物（node_modules/dist/static）不入 git（`.gitignore` 生效）。
- 全部测试通过（既有 218 + 新 test_queries + test_api + 保留 test_web_queries；删 test_web）。
- 手动冒烟 6 视图 + 切工作区 + 推进交互正常。

## 12. 风险

- **Node 依赖**：本机 Node v22 + npm/pnpm 已确认；他人复现需 Node。一键脚本含 `where npm` 前置检查 + `npm install`。
- **构建产物体积**：dist 进 gitignore，不入库。
- **大纲模式数据稀疏**：真实项目里 `master_outline`/`volume_outline` 可能未填充（demo 无）→ outline_tree 对缺字段优雅降级（null/省略），不崩。验收以 demo（有 volume/chapter/beat）为准。
- **多作品性能**：`list_works` 每个开 conn 读计数，项目少（个位数）开销可忽略；不缓存（避免脏读）。
- **`create_app` 签名变更**：断 `__main__.py` + `test_web.py`（后者删除，前者随改）；`launch.json` 同步。
- **JSON 列解析**：theme_seeds/beat_contracts/scene_setting/key_arcs/key_milestones/consumed_into 全部在纯函数/API 层 `json.loads`，异常降级，避免前端拿到原始字符串。
- **内容编辑冻结边界**：guard 同时检查 `status`（非 consumed/discarded）**和** `consumed_into`（空），双条件防"consumed 状态但无 into 记录"或"partial 已部分消费"被误编辑。非法时 UPDATE 前 raise，DB 不变。
- **正文编辑（paragraph）= 独立后续 spec，本期不开**。机器已就绪（`update_paragraph(para_id,text,content_hash,beat_id,role)` / `insert_paragraph_at` 存在）。策略已定：**开 + 完整保护**（重算 content_hash + 记 amendment + 导出后编辑标 drift，与 export_manifest 比对）。本 spec 仅在此记录策略，实现留独立 spec，避免本期 scope 失控。
- **amendment best-effort**：amendment 写失败不阻断主字段写入（仅记日志），保证编辑可用性优先于审计完整性；本地单用户场景可接受。
