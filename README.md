# 叙图 / Xutu

> 故事是数据结构，小说是渲染方式。

**叙图**是一个知识图谱驱动的长篇小说创作引擎。它将小说的结构层（人物/地点/事件）、风格层（风格指南/意象）、情节层（章节弧线）和规划层（悬念线/大纲）建模为知识图谱，通过 43 个 MCP 工具让 AI Agent 零代码操作图谱、生成 prompt、校验输出，完成从设定到成稿的全流程闭环创作。

## 核心理念

传统创作中，作者在脑中维护一个隐式的「故事状态」——谁是谁、发生了什么、悬念是否回收。叙图将这个状态外化为显式的知识图谱，让 AI Agent 像数据库查询一样精确地读写故事上下文，而不是把几十万字的全文塞进 prompt。

```
1882 字图谱上下文 > 93KB 全文（续写质量）  → 信息压缩比 49:1
```

## 架构

```
src/novel_kg/           # 核心引擎
├── core.py             # 门面 + 连接池 + 遥测装饰
├── core_crud.py        # CRUD + 查询 + Prompt 组装
├── core_compliance.py  # 大纲合规检查（bigram + LLM 语义 + purpose）
├── core_analysis.py    # 叙事节奏分析 + 编辑影响 + 大纲修订
├── core_parallel.py    # 并行章节生成（依赖分析/冻结/合并）
├── core_edits.py       # 编辑管理（快照/回滚/审核关卡）
├── core_cache.py       # Purpose 检查缓存（SHA256）
├── core_telemetry.py   # 遥测数据落盘
├── core_errors.py      # 统一错误模型
├── kg_json.py          # JSON 文件后端（零依赖，默认）
├── kg_sync.py          # JSON ↔ Neo4j 双向同步
├── graph.py            # Neo4j 后端
├── mine.py             # 提取管线（章节正文 → 结构化事件）
├── validators.py       # 后置校验（人名/结构/风格/篇幅/禁用句式）
├── telemetry.py        # 遥测观察者（零侵入装饰器）
├── render_telemetry.py # 遥测可视化仪表盘
├── server.py           # FastMCP 入口
├── mcp_cli.py          # CLI 入口
└── prompts.py          # Prompt 模板
.claude/
├── templates/          # 项目模板（framework.md / handoff.md）
└── skills/             # Agent 技能
tests/                  # 283 测试点（E2E + 并行 + 遥测）
archive/                # V1-V26 全部验证轮次归档
```

### 四层图谱

| 层 | 节点类型 | 能力 |
|---|---|---|
| 结构层 | Character, Location, Event, Theme, TimePeriod | 人物/地点/事件一致性 |
| 风格层 | StyleGuide, Motif | 叙事风格规则、禁用句式、意象演变 |
| 情节层 | ChapterArc | 每章 purpose/ending_type/rhythm |
| 规划层 | SuspenseThread, OutlineEntry | 悬念线生命周期、全局大纲约束 |

## 验证历程

26 轮增量验证，从概念到 100 章全自动创作：

| 轮次 | 里程碑 | 关键数据 |
|---|---|---|
| V2 | MVP 验证：图谱上下文 > 全文 | 1882 字 = 93KB |
| V6 | 4 轮闭环零漂移 | LLM 集成 + 项目隔离 |
| V11 | 12 章规模验证 | 100,717 字 / 50 事件 / 23 悬念线 |
| V14 | MCP 闭环：26 工具 | Agent 零外部 API 完成 6 章 |
| V17 | 50 章压力测试 | 511K 字 / 243 事件 / 81 悬念线 |
| V19 | 人机协作闭环 | 大纲合规 + 编辑影响 + 审核关卡 |
| V24 | 100 章自演化 | 零大纲 / 515 事件 / 118 悬念线 / 自然收束 |
| V26 | 同质化防治 | ending_type 零重复 / purpose 零重复 |

## 快速开始

```bash
# 安装依赖
pip install -r novel_kg_mvp/requirements.txt

# 运行测试（无外部依赖，~1 秒）
cd tests
python test_e2e.py --no-llm      # 190 测试点
python test_parallel.py           # 27 测试点
python test_telemetry.py          # 66 测试点

# 启动 MCP Server
cd src/novel_kg
python server.py
```

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `KG_BACKEND` | `json` | 后端选择：`json` 或 `neo4j` |
| `KG_PROJECTS_DIR` | `<repo>/projects` | 项目数据目录 |
| `NOVEL_LLM_ENABLED` | `0` | 开启 LLM 语义合规检查 |
| `NOVEL_TELEMETRY` | `0` | 开启遥测数据采集 |

### MCP 工具一览

43 个工具覆盖完整创作流程：

- **图谱 CRUD**（20）：init_project, add_character/location/event/relation, add_chapter_arc/outline_entry/suspense_thread/style_guide/motif/theme/time_period, update_suspense_thread, write_extraction, clear_chapter_data
- **查询**（6）：get_chapter_context, get_derivation_context, get_graph_stats, get_all_*, check_consistency
- **Prompt 生成**（4）：get_extraction_prompt, get_writing_prompt (`--focused` 可选，过滤休眠悬念线), get_editing_prompt, get_derivation_prompt
- **合规检查**（4）：validate_chapter, check_outline_compliance, batch_check_outline_compliance, detect_extraction_conflicts
- **分析**（4）：analyze_pacing, analyze_edit_impact, revise_outline, sync_backends
- **编辑管理**（4）：accept_edit, review_chapter, list_edits, rollback_edit
- **并行生成**（4）：analyze_parallel_groups, prepare_parallel_batch, get_parallel_writing_prompt, merge_parallel_results
- **遥测**（3）：save_telemetry_chapter_report, save_telemetry_session_summary, set_telemetry_wall_clock

## 破坏性操作保护

`init_project` 和 `clear_chapter_data` 需传入确认令牌：

```python
confirm = "I_UNDERSTAND_THIS_IS_DESTRUCTIVE"
```

## 代表作

| 作品 | 章节 | 字数 | 类型 |
|---|---|---|---|
| 《第六次死亡》 | 6 | 55K | 超现实悬疑 |
| 《缝合》 | 6 | 72K | 小城殡仪馆悬疑 |
| 《550kHz》 | 6 | 51K | 超现实悬疑（人机协作） |
| 《铜锈》 | 6 | 52K | 旧物修复悬疑 |
| 《信号源》 | 6 | 57K | 都市悬疑 |
| 《都市仙尊》 | 100 | 882K | 都市修仙（自演化） |
| 《水蚀》 | 12 | 101K | 双时间线悬疑 |
| 《末班电台》 | 6 | 55K | 深夜电台悬疑 |
| 《绝地天通》 | 92 | 320K+ | 20卷神话科幻（进行中） |

## License

MIT
