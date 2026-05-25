# Graph Report - novel_test  (2026-05-26)

## Corpus Check
- 34 files · ~33,869 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 750 nodes · 1233 edges · 82 communities (29 shown, 53 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 46 edges (avg confidence: 0.84)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ebb4930a`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]

## God Nodes (most connected - your core abstractions)
1. `_kg()` - 87 edges
2. `JsonKG` - 65 edges
3. `NovelKG` - 53 edges
4. `call_llm()` - 20 edges
5. `Knowledge Graph MVP` - 20 edges
6. `main()` - 18 edges
7. `Core Business Logic (core.py)` - 17 edges
8. `_persist()` - 15 edges
9. `UserError` - 15 edges
10. `_check_destructive()` - 14 edges

## Surprising Connections (you probably didn't know these)
- `Novel Creation Wizard (Claude Skill)` --references--> `MCP Server Tool Layer (server.py)`  [EXTRACTED]
  .claude/skills/novel-creation-wizard.md → src/novel_kg/server.py
- `Human-AI Collaboration Implementation Plan` --references--> `check_outline_compliance (bigram + pending_semantic)`  [EXTRACTED]
  docs/superpowers/plans/2026-05-20-human-ai-collaboration.md → src/novel_kg/validators.py
- `Purpose Alignment SHA256 Cache` --semantically_similar_to--> `Three-Step Outline Compliance Pipeline`  [INFERRED] [semantically similar]
  tests/test_e2e.py → src/novel_kg/validators.py
- `config.yaml (Neo4j + LLM config)` --semantically_similar_to--> `Prompt Soft-Decoupling (V12 Constraint Separation)`  [INFERRED] [semantically similar]
  src/novel_kg/config.yaml → src/novel_kg/validators.py
- `Human-AI Collaboration + Outline Compliance Design` --references--> `Edit Version Management (Snapshot/Rollback)`  [INFERRED]
  docs/superpowers/specs/2026-05-20-human-ai-collaboration-design.md → src/novel_kg/server.py

## Hyperedges (group relationships)
- **Closed-Loop Extraction→Write Flow** — mine_extraction_pipeline, core_core_module, prompts_prompt_templates, llm_llm_module, config_loader_config_loader [INFERRED 0.85]
- **Writing Prompt Assembly from Graph Context** — main_build_writing_prompt, graph_novelkg, kg_json_jsonkg, config_loader_config_loader [INFERRED 0.85]
- **Parallel Chapter Generation Orchestration** — core_core_module, parallel_chapter_generation, connection_pool_pattern, kg_json_jsonkg [INFERRED 0.75]
- **Post-Hoc Validation System (V12 Constraint Decoupling)** — concept_prompt_soft_decoupling, validators_validate_chapter, validators_character_names, validators_structure, validators_style, validators_forbidden_patterns, validators_length [INFERRED 0.85]
- **Zero-Intrusion Telemetry Observer Pipeline** — concept_telemetry_pipeline, telemetry_wrap_decorator, telemetry_collector, telemetry_toolcall, telemetry_chapter_session, telemetry_extract_decision, telemetry_bind_args, render_telemetry_dashboard, render_telemetry_load, concept_wall_clock_telemetry [INFERRED 0.85]
- **Human-AI Collaboration System (Outline Compliance + Review + Post-Hoc Edit)** — concept_outline_compliance_three_step, validators_outline_compliance, validators_bigram_overlap, concept_edit_version_management, concept_purpose_cache, doc_collaboration_design, doc_collaboration_plan [INFERRED 0.75]

## Communities (82 total, 53 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.10
Nodes (41): add_chapter_arc(), add_character(), add_event(), add_motif(), add_relation(), add_style_guide(), add_suspense_thread(), add_theme() (+33 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (35): Auto-Registration of Undeclared Locations, Edit Version Management (Snapshot/Rollback), Homogeneity Prevention via ending_type, Forbidden Patterns (Regex-Based Style Enforcement), Three-Step Outline Compliance Pipeline, Parallel Chapter Generation (V23), Prompt Soft-Decoupling (V12 Constraint Separation), Purpose Alignment SHA256 Cache (+27 more)

### Community 2 - "Community 2"
Cohesion: 0.10
Nodes (26): analyze_pacing(), _batch_purpose_check(), _check_ending_repetition(), _check_pacing_curve(), _check_purpose_repetition(), _check_scene_density(), close_all(), _create_backend() (+18 more)

### Community 4 - "Community 4"
Cohesion: 0.09
Nodes (17): _bind_args(), ChapterSession, _infer_chapter(), _infer_project(), init_telemetry(), V25 管线遥测模块 — 纯观察者，零侵入。  用法：设置环境变量 NOVEL_TELEMETRY=1 激活。 core.py 底部通过 globals() 替, 注入子代理端到端墙钟时间（主会话在子代理返回后调用）。, 初始化遥测收集器。通常由 core.py 激活时自动调用。 (+9 more)

### Community 5 - "Community 5"
Cohesion: 0.12
Nodes (28): validate_chapter(), _analyze_scene_compression(), apply_name_fixes(), _bigram_overlap(), _count_chinese_chars(), _count_timeline_switches(), _extract_names_from_dialogue(), _extract_subject_names() (+20 more)

### Community 6 - "Community 6"
Cohesion: 0.12
Nodes (26): Backend Abstraction Pattern, Configuration Layering: DEFAULTS→config.yaml→project.yaml, Two-Layer Config Loader (config_loader.py), Configuration Files (.mcp.json, launch.json, settings.json, config.yaml, project.yaml), Connection Pool with Lazy Init, Core Business Logic (core.py), Destructive Operation Guard (Confirm Sentinel), Extraction-to-Graph Pipeline Flow (+18 more)

### Community 8 - "Community 8"
Cohesion: 0.08
Nodes (40): batch_check_outline_compliance(), purpose_cache_dir(), purpose_cache_hash(), purpose_cache_path(), 核心缓存模块 — 目的检查缓存（SHA256）。  从 core.py 拆分，V27。, 读取缓存的目的检查结果，命中返回 result dict，否则 None。, read_purpose_cache(), write_purpose_cache() (+32 more)

### Community 10 - "Community 10"
Cohesion: 0.21
Nodes (13): Novel KG — 小说知识图谱工具包。  三层图谱架构（结构层/风格层/情节层）+ MCP Server + CLI。 支持章节续写、结构化提取、弧线推演、, build_parser(), cmd_check_consistency(), cmd_detect_conflicts(), cmd_get_all_threads(), cmd_get_chapter_context(), cmd_get_derivation_context(), cmd_get_graph_stats() (+5 more)

### Community 11 - "Community 11"
Cohesion: 0.30
Nodes (10): _compact_threads(), _fmt_duration(), _fmt_tokens(), _json(), V25 遥测可视化 — 从 JSON 生成自包含 HTML 仪表盘。 用法: python render_telemetry.py <project> 输出:, _render_chapter_rows(), render_dashboard(), _render_tool_rows() (+2 more)

### Community 13 - "Community 13"
Cohesion: 0.27
Nodes (6): build_graph(), Novel Knowledge Graph MVP 从小说文本提取结构化信息并写入知识图谱  MVP策略：不搞NLP模型微调，直接用结构化模板手工录入。 原因：, load_config(), Novel Knowledge Graph MVP 知识图谱客户端 - Neo4j连接、Schema初始化、CRUD操作 支持项目级隔离：所有节点带 proje, main(), Novel Knowledge Graph MVP 主流程：构建图谱 → 一致性检查 → 基于图谱的续写演示

### Community 16 - "Community 16"
Cohesion: 0.14
Nodes (21): analyze_pacing(), _check_ending_repetition(), _check_pacing_curve(), _check_purpose_repetition(), _check_scene_density(), 核心分析模块 — 叙事节奏分析、编辑影响分析、大纲修订、后端同步。  从 core.py 拆分，V27。, 检查多个字符串是否共享足够多的关键词（bigram方法）, _shared_keywords() (+13 more)

### Community 17 - "Community 17"
Cohesion: 0.32
Nodes (3): _ConfigLoader, _deep_merge(), 两级配置加载器：全局 config.yaml → 项目 project.yaml → 代码 DEFAULTS。  用法：     from config_loa

### Community 20 - "Community 20"
Cohesion: 0.33
Nodes (5): mcpServers, novel-kg, args, command, cwd

### Community 68 - "Community 68"
Cohesion: 0.06
Nodes (35): code:python (# ========== 大纲合规检查 ==========), code:python (@mcp.tool()), code:python (# ---- 16. revise_outline MCP工具 ----), code:bash (git add novel_mcp_server/core.py novel_mcp_server/server.py ), code:python (def get_edited_chapter_text(self, chapter):), code:python (def analyze_edit_impact(project: str, chapter: int) -> dict:), code:python (def _bigram_overlap_str(s1, s2, min_shared=2):), code:python (def accept_edit(project: str, chapter: int, extracted_json: ) (+27 more)

### Community 69 - "Community 69"
Cohesion: 0.06
Nodes (33): code:text (novel_test/), code:bash (cd novel_kg_mvp), code:bash (cd novel_mcp_server), code:block4 (archive/vN-验证名/), Development Notes, graphify, Knowledge Graph MVP, Project Overview (+25 more)

### Community 70 - "Community 70"
Cohesion: 0.06
Nodes (32): accept_edit(project, chapter, confirm), analyze_edit_impact(project, chapter), check_outline_compliance(project, chapter), code:json ({), code:yaml (writing:), code:block3 (AI写chN → 提取+写入图谱 → 大纲合规检查 → 输出给作者), code:block4 (AI写chN → 提取+写入图谱 → 大纲合规检查 →), code:json ({) (+24 more)

### Community 71 - "Community 71"
Cohesion: 0.16
Nodes (18): accept_edit(), add_outline_entry(), invalidate_purpose_cache(), _check_destructive(), clear_chapter_data(), clear_chapter_data(), init_project(), accept_edit() (+10 more)

### Community 72 - "Community 72"
Cohesion: 0.12
Nodes (16): code:json ({), code:bash (cat > D:/novel_test/novel_kg_mvp/projects/<标识符>/project.yaml), code:block3 (项目 <标题> 创建完成！), code:json ({), code:block5 (大纲已写入（X章）：), Phase 1 — 需求收集, Phase 2 — 生成世界观, Phase 3 — 写入图谱 (+8 more)

### Community 73 - "Community 73"
Cohesion: 0.17
Nodes (15): analyze_edit_impact(), 事后影响分析：对比edited文本的提取结果与图谱中该章数据。, 显式修订大纲条目。只修改传入的字段，并记录修订原因。, revise_outline(), list_edits(), 核心编辑管理模块 — 事后编辑采纳、审核关卡、快照管理、回滚。  从 core.py 拆分，V27。, review_chapter(), rollback_edit() (+7 more)

### Community 74 - "Community 74"
Cohesion: 0.17
Nodes (15): get_extraction_prompt(), get_writing_prompt(), get_derivation_prompt(), get_extraction_prompt(), get_parallel_writing_prompt(), get_writing_prompt(), get_parallel_writing_prompt(), 使用冻结上下文生成写作 prompt（并行模式）。 (+7 more)

### Community 75 - "Community 75"
Cohesion: 0.19
Nodes (10): detect_extraction_conflicts(), detect_extraction_conflicts(), _collect_character_names(), detect_conflicts(), get_chapter_time_period(), normalize_characters(), Novel Knowledge Graph MVP 提取管线：章节文本 → 结构化数据 → 冲突检测 → 写入图谱  用于闭环流程——写完新章节后，提取新增信息, 将提取结果中的人名规范化为图谱中已有的标准名。      策略：繁简转换 + 子串匹配。如果图谱中有"王婆"，提取到"老王婆"，     则将"老王婆"替换为" (+2 more)

### Community 76 - "Community 76"
Cohesion: 0.24
Nodes (9): add_location(), check_consistency(), write_extraction(), analyze_parallel_groups(), merge_parallel_results(), prepare_parallel_batch(), 核心并行生成模块 — 依赖分析、批次准备、并行 prompt、结果合并。  从 core.py 拆分，V27。, 为并行组创建图谱快照并预冻结每章的上下文。 (+1 more)

### Community 77 - "Community 77"
Cohesion: 0.25
Nodes (4): Exception, NovelKGError, 所有 novel_kg 错误的基类。      既是异常（可 raise），也可通过 to_dict() 转为标准化 dict。, 转为标准化错误 dict，可直接作为 MCP 工具返回值。

### Community 78 - "Community 78"
Cohesion: 0.33
Nodes (5): 核心遥测模块 — 遥测数据保存 + 工具函数装饰器注入。  从 core.py 拆分，V27。, 注入子代理端到端墙钟时间（主会话在子代理返回后调用）。, save_telemetry_chapter_report(), save_telemetry_session_summary(), set_telemetry_wall_clock()

### Community 79 - "Community 79"
Cohesion: 0.40
Nodes (5): add_location(), check_consistency(), merge_parallel_results(), 合并并行生成结果到图谱（串行写入，冲突检测）。      results: {chapter: {"text": str, "extraction_json":, write_extraction()

### Community 80 - "Community 80"
Cohesion: 0.40
Nodes (5): analyze_edit_impact(), analyze_parallel_groups(), get_all_threads(), 事后影响分析：对比edited文本的提取结果与图谱中该章数据。, 分析章节依赖关系，返回可并行分组。      依赖规则：     - 相邻章节（Ch N 与 Ch N+1）必须串行     - 共享 parallel_gro

## Knowledge Gaps
- **104 isolated node(s):** `command`, `args`, `cwd`, `version`, `configurations` (+99 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **53 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `JsonKG` connect `Community 7` to `Community 0`, `Community 2`, `Community 9`, `Community 15`, `Community 16`, `Community 19`, `Community 21`, `Community 26`, `Community 27`, `Community 28`, `Community 29`, `Community 30`?**
  _High betweenness centrality (0.116) - this node is a cross-community bridge._
- **Why does `NovelKG` connect `Community 3` to `Community 0`, `Community 2`, `Community 75`, `Community 13`, `Community 16`, `Community 18`, `Community 23`, `Community 24`, `Community 25`?**
  _High betweenness centrality (0.084) - this node is a cross-community bridge._
- **Why does `call_llm()` connect `Community 8` to `Community 0`, `Community 2`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `_kg()` (e.g. with `main()` and `main()`) actually correct?**
  _`_kg()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `command`, `args`, `cwd` to the rest of the system?**
  _251 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.09797979797979799 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.07058823529411765 - nodes in this community are weakly interconnected._