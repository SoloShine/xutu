# CLAUDE.md — 小说创作系统

## 渐进式披露

项目特定内容（设定/大纲/当前进度/字数目标）不在本文件中定义，而是放在以下位置，按需读取：

| 内容 | 位置 | 何时读取 |
|------|------|---------|
| 世界观、20卷大纲 | `projects/<项目名>/framework.md` | 写作前 |
| 当前卷管线说明 | `projects/<项目名>/handoff.md` | 每卷开始前 |
| 图谱状态 | CLI命令 `get_graph_stats --project <项目名>` | 每次入图后 |

模板文件（新建项目时从根目录复制）：
- `.template.framework.md` → `projects/<项目名>/framework.md`
- `.template.handoff.md` → `projects/<项目名>/handoff.md`

写作前必须读取 `framework.md` 的前几节（核心设定）和对应卷的大纲部分。

---

## ⚠️ 铁律

### 写作管线（严格串行，每章三步）

```
Step 0: 读取框架 → Step 1: 子代理写初稿 → Step 2: 子代理编辑审查 → Step 3: 子代理提取JSON → Step 4: CLI写入图谱+弧线 → 下一章
```

**Step 0（每卷/新会话必做）：**
- 读 `projects/<项目名>/framework.md` — 核心设定 + 当前卷大纲
- 读 `projects/<项目名>/handoff.md` — 会话交接块（前卷结尾状态 / 活跃悬念线 / 风格参考）
- `get_graph_stats --project <项目名>` — 图谱总览
- `get_all_threads --project <项目名>` — 当前悬念线状态
- **`get_derivation_context --project <项目名> --chapter <N> --lookback 3`** — 获取前三章弧线上下文（推演本章起点和方向）

- **子代理写作：** 严禁在主会话中写正文。必须使用 Agent 工具派生子代理完成。
- **严格串行：** ChN未完成入图之前，不能开始ChN+1。多章批处理时在单一子代理内部也必须严格串行。
- **prompt落盘：** 每次写作/提取完成后，将prompt保存到 `prompts/` 目录。
- **chapter_arc必写：** Step 4 除 `write_extraction` 外必须同时写 `add_chapter_arc`（purpose/scenes/ending/structure_type）。

### 每章检查清单

- [ ] **标题格式：** `**第X卷 第N章 标题**`（加粗，带卷标）
- [ ] **汉字数：** 3000-5000（用 python 验证）
- [ ] **风格：** 网文风格——短段落、感官描写、第三人称有限视角
- [ ] **章末参考来源：** 引用真实出处 + 虚构部分标注"为虚构设定"
- [ ] **编辑审查已完成**（get_editing_prompt 生成审查 prompt，子代理修改终稿）
- [ ] **提取JSON已写入图谱**（用 get_graph_stats 确认）
- [ ] **chapter_arc 已写入**（purpose/scenes/ending/structure_type）
- [ ] **prompt已落盘**

### 文件命名（代码自动推导，无需手动构造）

所有文件使用全局章节编号（两位数字）。CLI 工具的 `--json-file` 和 `--text-file` 参数**省略时自动使用标准路径**。

| 内容 | 标准路径（自动） | CLI示例 |
|------|----------------|---------|
| 正文输出 | `projects/<项目>/output/ch{NN}_generated.txt` | 子代理写入 |
| 提取JSON | `projects/<项目>/extractions/extraction_ch{NN}.json` | 子代理写入，CLI读取 |
| 写作prompt | `projects/<项目>/prompts/writing_ch{NN}.txt` | 手动落盘 |
| 提取prompt | `projects/<项目>/prompts/extraction_ch{NN}.txt` | 手动落盘 |

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
│   └── telemetry/                  # 遥测报告
├── src/novel_kg/                   # 代码
│   ├── server.py / core.py / kg_json.py / mcp_cli.py / telemetry.py
├── .mcp.json                       # MCP Server配置
├── .template.framework.md           # framework.md标准模板
├── .template.handoff.md             # handoff.md标准模板
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
| `get_extraction_prompt` | `--project --chapter N --text-file PATH` | 生成提取prompt |
| `get_writing_prompt` | `--project --chapter N` | 生成写作prompt |
| `get_editing_prompt` | `--project --chapter N [--draft-file PATH]` | 生成编辑审查prompt |
| `get_derivation_prompt` | `--project --chapter N` | 生成推演prompt |

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

**后端：** 默认JSON文件后端（零依赖）。Neo4j可选（`KG_BACKEND=neo4j`）。

---

## graphify

代码库知识图谱，用于代码搜索与架构理解。

- `graphify query "<question>"` — 代码问题查询
- `graphify path "<A>" "<B>"` — 文件关系查询
- `graphify explain "<concept>"` — 概念解释
- `graphify update .` — 代码修改后更新图谱

详见 `graphify-out/GRAPH_REPORT.md` 和 `graphify-out/wiki/index.md`。
