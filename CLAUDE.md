# CLAUDE.md — 小说创作系统

## 渐进式披露

项目特定内容（设定/大纲/当前进度/字数目标）不在本文件中定义，而是放在以下位置，按需读取：

| 内容 | 位置 | 何时读取 |
|------|------|---------|
| 世界观、20卷大纲 | `projects/<项目名>/framework.md` | 写作前 |
| 当前卷管线说明 | `projects/<项目名>/handoff.md` | 每卷开始前 |
| 图谱状态 | CLI命令 `get_graph_stats --project <项目名>` | 每次入图后 |

模板文件（新建项目时从根目录复制）：
- `.claude/templates/framework.md` → `projects/<项目名>/framework.md`
- `.claude/templates/handoff.md` → `projects/<项目名>/handoff.md`

写作前必须读取 `framework.md` 的前几节（核心设定）和对应卷的大纲部分。

---

## ⚠️ 铁律

### 写作管线（ChapterAgent 架构）

每章由独立子代理（ChapterAgent）完成全部步骤，主编排只做章节调度。主编排上下文每章仅增加 ~1K chars（状态摘要），不再累积 prompt/正文/JSON。

```
主编排: dispatch(chN) → ChapterAgent(chN) → summary → ... → dispatch(chLast) → VolumeReviewAgent → 更新handoff
```

**ChapterAgent 内部流程（严格串行）：**
```
Boot → Step 1: 写初稿 → Step 2: 编辑审查 → Step 3: 提取JSON → Step 4: 入图+弧线 → Step 5: 遥测 → 返回摘要
```

**VolumeReviewAgent（整卷回读校验，全部 ChapterAgent 完成后由主编排派生）：**
```
Phase 1: 逐章通读 → Phase 2: 输出问题清单 → Phase 3: 逐章修复 → Phase 4: 写入报告
```
- 使用 Agent 工具派生，prompt 来自 `.claude/templates/volume_review.md`
- 报告写入 `projects/<项目名>/review_report_vol{N}.md`
- 主编排收到报告后更新 `handoff.md` 会话交接块

**ChapterAgent 内部流程（严格串行）：**
```
Boot → Step 1: 写初稿 → Step 2: 编辑审查 → Step 3: 提取JSON → Step 4: 入图+弧线 → Step 5: 遥测 → 返回摘要
```

---

## ⚠️ v2 管线（实验性）

**Boot（子代理启动时）：**
- `get_boot_context --project <项目> --chapter N` — 最小启动上下文（大纲 + 前章结尾 + 线索召回索引）
- 检查 recall_index 中与本章相关的休眠线索，按需 `recall_thread --thread-id <ID>`

**主编排 Step 0（每卷/新会话必做，仅主编排执行）：**
- 读 `projects/<项目名>/handoff.md` — 会话交接块
- `get_graph_stats --project <项目名>` — 图谱总览
- **新卷开始前（追加）：**
  - 用 `add_outline_entry` 将该卷全部章节大纲写入图谱（`--project --chapter N --purpose --key-events --structure-hint`）
  - 更新 `projects/<项目名>/world_setup.json`：total_chapters、volumes 数组（含新增卷的状态）、新增角色/地点/时间段
  - 验证：`verify_pipeline_step --project <项目> --chapter <首章> --step write` 返回 `ready: true`

**子代理调度规则：**
- 使用 Agent 工具派生 ChapterAgent，prompt 来自 `.claude/templates/chapter_agent.md`
- **严格串行：** ChN 的 ChapterAgent 返回成功后，才能 dispatch ChN+1
- **章间门禁：** dispatch ChN+1 前，必须运行 `verify_chapter_complete --project <项目> --chapter N`，确认 `complete: true`
- **如果 ChN 返回 partial 或 failed：** 不能继续 ChN+1，必须先修复 ChN（必要时手动清查）
- **子代理内部门禁：** ChapterAgent 每步前运行 `verify_pipeline_step --step <write|edit|extract|graph|telemetry>`，`ready: false` 时停止
- **禁止并行派生：** 严禁同时 dispatch 两个 ChapterAgent
- **子代理独立校验：** ChapterAgent 内部运行 `validate_chapter` + `detect_conflicts`，自修到通过
- **prompt落盘：** 自动（每个 get_*_prompt 命令都会落盘到 `prompts/` 目录）
- **chapter_arc必写：** Step 4 必须写 `add_chapter_arc`
- **遥测注入：** ChapterAgent 内部完成（Step 5）
- **context_digest：** 每章完成后 `generate_context_digest` 保存增量摘要到 `digests/digest_ch{NN}.json`

**本地文件同步**（主编排负责，不能只写图谱）：
  - `projects/<项目>/framework.md` — 追加新卷章纲、人物、地点、体量估算
  - `projects/<项目>/project.yaml` — 更新 chapters 总数、新增 volume 条目及状态
  - `projects/<项目>/world_setup.json` — 更新 total_chapters、volumes 数组、新增角色/地点/时间段
- **每卷结束校验：** 校验实写章数 = 大纲计划章数（如不等，更新framework并记录差异原因）
- **整卷回读校验（Step 6）：** 全部章节的 ChapterAgent 完成且 verify_chapter_complete 通过后，主编排派生 VolumeReviewAgent 执行整卷回读校验。prompt 来自 `.claude/templates/volume_review.md`。VolumeReviewAgent 返回后，主编排读取报告并更新 handoff.md 会话交接块。

---

## v2 管线（悬链驱动，实验性）

**核心改进（vs v1）：**

| 维度 | v1 | v2 |
|------|----|----|
| 代理/章 | 3（Write/Edit/Process） | 1（ChapterAgent v2） |
| 风格约束 | 负约束（禁止句式≤N） | 正约束（≥3种多样性结构） |
| grep 角色 | 门禁（不过不让过） | 信号灯（过是绿灯/黄灯/红灯） |
| 悬链 | 播种无配额 | 每章配额+消费平衡 |
| 回读 | 风格指标为主 | 悬链收支表为主 |

**v2 文件：**
- `.claude/templates/chapter_agent_v2.md` — 单体代理模板（Boot→Write→自编辑→提取→入图）
- `.claude/templates/volume_review_v2.md` — 悬链平衡校验+整卷回读
- `.claude/workflows/volume-pipeline-v2.js` — v2 编排（1 agent/ch + VolumeReview v2）

**v2 启动方式：**
```
Workflow({ scriptPath: ".claude/workflows/volume-pipeline-v2.js",
  args: { project: "juedi_tiantong_v1", volume: 13, startChapter: 178, endChapter: 189, volumeName: "边界" } })
```

**v2 新增 CLI：**
- `get_suspense_maturity --project <项目> --chapter N` — 悬链成熟度分组（mature/developing/recent + 配额）
- boot context 输出中新增 `suspense_maturity` 字段

**悬链配额规则：** 每章可种新线 ≤ `new_thread_quota`，consumption_balance ≥ 0（种1条必须回收或推进≥1条旧线）。卷级看净收支。

**v1 保留：** v1 模板和工作流不受影响，可继续使用。

---

### Prompt 体积控制

| 场景 | 命令 | 体积（ch93实测） |
|------|------|-----------------|
| **写作（推荐）** | `get_writing_prompt --focused` | ~26K chars |
| **写作（全量）** | `get_writing_prompt` | ~36K chars |
| **提取（精简）** | `get_extraction_prompt --compact` | ~15K chars |
| **提取（全量）** | `get_extraction_prompt` | ~41K chars |

**聚焦策略：** focused 模式保留 escalated + partially_resolved(high) + 近15章种植的线。休眠线不加载，通过 recall_index 按需召回。

### 每章检查清单

- [ ] **标题格式：** `**第X卷 第N章 标题**`（加粗，带卷标）
- [ ] **汉字数：** 3000-5000（用 python 验证）
- [ ] **风格：** 网文风格——短段落、感官描写、第三人称有限视角
- [ ] **句式多样性：** 「不是X，是Y」否定转折句式每章不超过5处（用 grep 验证）
- [ ] **破折号克制：** 破折号（——）每千字不超过3处，仅用于正式插入语或话题中断
- [ ] **句号密度：** 每千字15-25个句号，禁止用句号切割本应连贯的句子
- [ ] **章末参考来源：** 引用真实出处 + 虚构部分标注"为虚构设定"
- [ ] **编辑审查已完成**（get_editing_prompt 生成审查 prompt，子代理修改终稿）
- [ ] **提取JSON已写入图谱**（用 get_graph_stats 确认）
- [ ] **chapter_arc 已写入**（purpose/scenes/ending/structure_type）
- [ ] **prompt已落盘**
- [ ] **遥测已注入**（count_chapter_words + inject_chapter_metrics + inject_agent_phase）

### 文件命名（代码自动推导，无需手动构造）

所有文件使用全局章节编号（两位数字）。CLI 工具的 `--json-file` 和 `--text-file` 参数**省略时自动使用标准路径**。

| 内容 | 标准路径（自动） | CLI示例 |
|------|----------------|---------|
| 正文输出 | `projects/<项目>/output/ch{NN}_generated.txt` | 子代理写入 |
| 提取JSON | `projects/<项目>/extractions/extraction_ch{NN}.json` | 子代理写入，CLI读取 |
| 写作prompt | `projects/<项目>/prompts/writing_ch{NN}.txt` | 自动落盘 |
| 提取prompt | `projects/<项目>/prompts/extraction_ch{NN}.txt` | 自动落盘 |
| 章节摘要 | `projects/<项目>/digests/digest_ch{NN}.json` | 自动落盘（generate_context_digest） |

**全局编号映射：** Vol1=ch01-12, Vol2=ch13-32, Vol3=ch33-52。卷名和章节名只在正文标题中体现。

---

## 项目结构

```
novel_test/
├── CLAUDE.md                       # 本文件（通用规则）
├── projects/<项目名>/              # 项目特定内容
│   ├── framework.md                # 设定+大纲
│   ├── handoff.md                  # 当前卷管线说明
│   ├── graph.json                  # 图谱数据
│   ├── output/                     # 章节正文
│   ├── extractions/                # 提取JSON
│   ├── prompts/                    # LLM prompt落盘
│   ├── digests/                    # 章节增量摘要
│   └── telemetry/                  # 遥测报告
├── src/novel_kg/                   # 代码
│   ├── server.py / core.py / kg_json.py / mcp_cli.py / telemetry.py
├── .mcp.json                       # MCP Server配置
├── .claude/
│   ├── templates/                # 项目模板
│   │   ├── framework.md          # framework.md标准模板
│   │   ├── handoff.md            # handoff.md标准模板
│   │   ├── chapter_agent.md      # ChapterAgent调度prompt
│   │   └── volume_review.md      # VolumeReviewAgent整卷回读prompt
│   └── skills/                   # Agent skills
└── archive/                        # 历史验证归档（gitignored）
```

---

## 常用CLI命令

```bash
cd D:/novel_test
python -m src.novel_kg.mcp_cli <command> --project <项目名> [参数]
```

写作管线核心命令：

| 命令 | 简写（省略文件路径） | 完整 |
|------|-------------------|------|
| `get_graph_stats` | `--project <项目>` | — |
| `get_chapter_context` | `--project <项目> --chapter N` | — |
| `write_extraction` | **`--project <项目> --chapter N`** | 自动读 `extractions/extraction_ch{NN}.json` |
| `get_extraction_prompt` | **`--project <项目> --chapter N`** | 自动读 `output/ch{NN}_generated.txt` |
| `validate_chapter` | **`--project <项目> --chapter N`** | 自动读 `output/ch{NN}_generated.txt` |

查询分析命令：

| 命令 | 参数 | 用途 |
|------|------|------|
| `get_all_threads` | `--project` | 全部悬念线列表 |
| `get_unresolved_threads` | `--project --chapter N` | 到某章为止未解决的悬念线 |
| `check_consistency` | `--project` | 一致性检查 |
| `analyze_pacing` | `--project` | 叙事节奏分析 |
| `get_derivation_context` | `--project --chapter N [--lookback N]` | 推演新章所需的上下文 |

Prompt生成（自动落盘到 prompts/ 目录）：

| 命令 | 参数 | 用途 |
|------|------|------|
| `get_extraction_prompt` | `--project --chapter N [--compact]` | 生成提取prompt（compact精简版） |
| `get_writing_prompt` | `--project --chapter N [--focused]` | 生成写作prompt（focused精简版） |
| `get_editing_prompt` | `--project --chapter N [--draft-file PATH]` | 生成编辑审查prompt |
| `get_derivation_prompt` | `--project --chapter N` | 生成推演prompt |

ChapterAgent 支持：

| 命令 | 参数 | 用途 |
|------|------|------|
| `get_boot_context` | `--project --chapter N` | 最小启动上下文（大纲+前章结尾+线索索引） |
| `get_framework` | `--project --chapter N` | 按需切片加载 framework（核心设定+当前卷大纲，省70%） |
| `recall_thread` | `--project --thread-id ID` | 按需拉取休眠线索完整内容 |
| `recall_arc` | `--project --chapter N` | 按需拉取某章弧线+事件+人物 |
| `generate_context_digest` | `--project --chapter N [--word-count N]` | 生成本章增量摘要 |
| `verify_pipeline_step` | `--project --chapter N --step <write\|edit\|extract\|graph\|telemetry>` | 步骤前置检查（硬约束） |
| `verify_chapter_complete` | `--project --chapter N` | 章间门禁（全部完成才能开始下一章） |

数据校验：

| 命令 | 参数 | 用途 |
|------|------|------|
| `validate_chapter` | `--project --chapter N --text-file PATH` | 校验章节正文格式 |
| `detect_conflicts` | `--project --json-file PATH` | 检测提取JSON与图谱的冲突 |

手动添加节点：

| 命令 | 参数 | 用途 |
|------|------|------|
| `add_character` | `--project --name NAME [--role] [--personality]` | 添加人物 |
| `add_location` | `--project --name NAME [--loc-type] [--description]` | 添加地点 |
| `add_event` | `--project --event-id ID [--chapter] [--title] [--detail] [--event-type]` | 添加事件（可标记gap） |
| `add_suspense_thread` | `--project --thread-id ID --content TEXT --planted-chapter N [--importance]` | 添加悬念线 |
| `update_suspense_thread` | `--project --thread-id ID [--status] [--importance]` | 更新悬念线状态 |
| `add_chapter_arc` | `--project --chapter N --purpose TEXT --scenes TEXT --ending TEXT` | 添加章节弧线 |
| `add_outline_entry` | `--project --chapter N --purpose TEXT [--key-events] [--structure-hint]` | 添加大纲条目 |
| `add_motif` | `--project --name NAME [--meaning] [--evolution]` | 添加母题 |
| `add_theme` | `--project --name NAME [--description]` | 添加主题 |
| `add_style_guide` | `--project --guide-id ID --rule TEXT` | 添加风格指南 |
| `add_time_period` | `--project --label LABEL --chapter-start N --chapter-end N` | 添加时间段 |
| `add_relation` | `--project --from-label --from-key --from-val --rel-type --to-label --to-key --to-val` | 添加关系边 |

维护命令：

| 命令 | 参数 | 用途 |
|------|------|------|
| `init_project` | `--project [--confirm I_UNDERSTAND_THIS_IS_DESTRUCTIVE]` | 初始化/清空项目 |
| `clear_chapter_data` | `--project --chapter N [--confirm CONFIRM]` | 清除单章数据 |
| `sync_backends` | `--project [--direction json_to_neo4j\|neo4j_to_json]` | JSON↔Neo4j同步 |

遥测命令：

| 命令 | 参数 | 用途 |
|------|------|------|
| `count_chapter_words` | `--project --chapter N` | 统计章节汉字数并注入遥测 |
| `inject_chapter_metrics` | `--project --chapter N [--word-count N] [--editing-corrections N] [--editing-types STR]` | 注入章节指标 |
| `inject_agent_phase` | `--project --chapter N --phase NAME --duration-ms N [--tool-uses N]` | 注入子代理阶段耗时 |
| `save_telemetry_session_summary` | `--project` | 保存会话遥测摘要 |

角色访谈命令：

| 命令 | 参数 | 用途 |
|------|------|------|
| `interview_character` | `--project --character NAME [--chapter N] [--validate] [--dry-run]` | 角色访谈（交互/验证/干跑） |

**后端：** 默认JSON文件后端（零依赖）。Neo4j可选（`KG_BACKEND=neo4j`）。

---

## graphify

代码库知识图谱，用于代码搜索与架构理解。

- `graphify query "<question>"` — 代码问题查询
- `graphify path "<A>" "<B>"` — 文件关系查询
- `graphify explain "<concept>"` — 概念解释
- `graphify update .` — 代码修改后更新图谱

详见 `graphify-out/GRAPH_REPORT.md` 和 `graphify-out/wiki/index.md`。
