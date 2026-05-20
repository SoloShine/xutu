# CLAUDE.md

## Project Overview

小说创作实验项目。当前包含三个阶段的工作：

1. **已完成：《间隙》** — 一部3.5万字的中篇小说，探索自我意识、渺小感与选择的主题。已完成初稿、修订和文学分析，归档于 `archive/v1-间隙-初稿/`。

2. **已完成：知识图谱MVP验证** — 验证「故事是数据结构，小说是渲染方式」的概念。A/B/C/D四组对比验证通过：1882字图谱上下文续写质量超过93KB全文。归档于 `archive/v2-知识图谱MVP-验证/`。

3. **已完成：闭环提取管线验证** — 验证章节文本→结构化数据→回写图谱的闭环可行性。粒度标定5-8事件/章，冲突检测5类，gap误判修复。归档于 `archive/v3-闭环提取管线-验证/`。

4. **已完成：扩展性验证** — 验证从图谱推演新章节ChapterArc的可行性。234字推演arc使结尾从"对但模糊"变为"精确命中"。归档于 `archive/v4-扩展性验证-推演情节层/`。

5. **已完成：泛化验证** — 用萧红《生死场》验证三层架构跨作品有效性。1255字图谱上下文准确预测第13章核心情节，风格层成功约束散文化叙事风格。归档于 `archive/v5-泛化验证-生死场/`。

6. **已完成：项目隔离+LLM集成+多轮稳定性** — Neo4j节点project属性隔离、OpenAI兼容LLM调用（智谱glm-5-turbo）、Click CLI重构。4轮全自动闭环零漂移，归档于 `archive/v6-多轮闭环稳定性验证/`。

7. **已完成：自动提取验证** — LLM从原文自动构建图谱（69事件/30人物 vs 手工25/16），驱动续写质量与手工图谱相当。归档于 `archive/v7-自动提取验证/`。

8. **已完成：冷启动验证** — 沈从文《边城》零配置冷启动：6条风格指南→自动提取75事件/14人物→3214字高质量续写，风格高度还原沈从文。归档于 `archive/v8-冷启动验证-边城/`。

9. **已完成：原创创作验证** — 从零创作6章超现实悬疑短篇《错轨夜车》：200字创作方向→LLM生成世界观→6章自动续写19,671字。7条风格指南全部遵守，6章人物/情节连贯，图谱增长28事件/101关系。归档于 `archive/v9-原创创作验证/`。

10. **已完成：叙事深度验证** — 悬念线追踪+全局大纲+叙事结构+预查询四功能整合验证。海岛疗养院悬疑《潮间带的回声》：10条悬念线完整plant→resolve生命周期，6章大纲零偏移，14悬念线/27事件/118关系。归档于 `archive/v10-叙事深度验证/`。

11. **已完成：12章规模验证** — 修复loop跳章/人名漂移/结构不执行三个Bug，运行12章双时间线悬疑《水蚀》：100,717字、50事件、23悬念线、177关系、3章intercut实际执行。12章闭环零中断，大纲零偏移，人名零漂移。归档于 `archive/v11-12章规模验证/`。

12. **已完成：约束/Prompt解耦重构** — 将50+处"必须/禁止"硬编码从prompt中剥离，改用validators.py后置校验。12处prompt标签软化 + 4个校验器（人名/结构/风格/篇幅）+ 管线集成（自动修复+重试）+ audit-threads命令。端到端验证：软化prompt后LLM产出质量未降级，intercut/风格/人名均正确。归档于 `archive/v12-约束解耦重构/`。

13. **已完成：悬念线隐含解决验证** — 修复audit-threads的json_mode Bug（dict当string处理）。12章管线跑通：提取阶段解决率8.7%→16.7%（提取prompt隐含解决指导生效），audit-threads额外检出3条隐含解决（29.2%综合解决率）。24悬念线/49事件/170关系。归档于 `archive/v13-悬念线隐含解决验证/`。

14. **已完成：MCP闭环验证** — 将图谱操作和prompt模板暴露为26个MCP工具，Agent直接作为LLM完成全流程（零外部API调用）。原创6章工业废墟悬疑《东华澡堂》：36,829字、18事件、6悬念线（5解决+1开放式）、84关系。单章耗时从10-15分钟降至3-5分钟。归档于 `archive/v14-MCP闭环验证/`。

15. **已完成：功能增强验证** — 后端同步+增强一致性+叙事节奏分析三个功能增强。28个MCP工具，58测试点JSON/Neo4j双后端通过。原创6章小城殡仪馆悬疑《缝合》：72,169字、32事件、12悬念线（4解决+8开放）、160关系。一致性检查仅1个设计意图问题，节奏分析检测到2个结尾重复。归档于 `archive/v15-功能增强验证/`。

16. **已完成：串行连贯性验证** — P0修复：前章正文注入（写作prompt含前章结尾3000字）+ 悬念线预算控制（动态max(8,ch*1.5)）。串行6章《缝合》重跑：19,727字、25事件、12悬念线（9解决+3开放=75%解决率）、158关系。感官锚点（甜味/嗡鸣/铜钥匙）形成完整跨章弧线，解决率从33%→75%。归档于 `archive/v16-串行连贯性验证/`。

17. **已完成：50章规模验证** — 50章长篇超现实悬疑《第六次死亡》：510,946字符、243事件、81悬念线、1,237关系、13人物、14地点。50章闭环零中断、零MCP调用失败、人名零漂移。大纲从Ch27起完全偏离但系统通过前章注入+图谱上下文自适应。零号/初雪弧线（五感→名字→说话→"在这"）完全涌现。归档于 `archive/v17-50章规模验证/`。

18. **已完成：风格升级验证（R1）** — prev_text_chars从3000降至500 + 12条升级风格指南（+5条：anti_pattern/rhythm_variation/character_voice/dash_restriction/sensory_diversity）。6章串行《第六次死亡》重跑：20,937字符、28事件、19悬念线（8解决+5部分+6开放）、191关系。破折号从97→2（-98%），6章24个感官锚点零重叠，角色声音区分度明显提升。"不是X是Y"句式仍偏高（13次），需进一步收紧。归档于 `archive/v18-R1-风格升级验证/`。

19. **已完成：节奏标记+禁用句式验证（R2）** — forbidden_patterns配置项（5条正则+validators.py后置校验）+ rhythm字段（tight/ascending/descending/mixed）注入写作prompt。6章串行《第六次死亡》重跑：27,448字符、30事件、12悬念线、186关系。"不是X是Y"句式从13→0（-100%），6章全部通过forbidden_pattern校验。6章rhythm标记全部与实际节奏一致。感官锚点30+个零重叠。归档于 `archive/v18-R2-节奏标记与禁用句式验证/`。

20. **已完成：人机协作+大纲合规验证** — 5个新MCP工具（大纲合规检查/显式修订/事后编辑影响分析/采纳编辑/审核关卡），总计33工具96测试点。原创6章超现实悬疑《550kHz》+ 事后编辑闭环验证：6章大纲零偏移，Ch3事后编辑触发级联影响检测（5事件变更、4下游大纲修订），大纲修订审计轨迹完整。29事件、5悬念线（100%解决率含隐含）、148关系。归档于 `archive/v19-人机协作+大纲合规验证/`。

21. **已完成：语义合规+目的检查验证** — 三步合规管线（bigram→LLM语义→purpose检查）+ V17 50章回溯验证。LLM语义检查解决"深夜来访"="突然出现"等bigram盲区；purpose级别检查精准检测V17的19/50偏离章节（Ch27首次偏离，Ch30-48持续偏离，Ch49-50回归），零误报零漏报。103 E2E测试全部通过。归档于 `archive/v20-语义合规+目的检查验证/`。

22. **已完成：功能增强验证（V21）** — 编辑版本管理+prompt落盘+地点自动注册+批量合规检查。4项增强：①编辑快照自动创建（微秒时间戳防冲突），list_edits/rollback_edit支持回滚；②extraction/writing/derivation prompt自动落盘到projects目录；③write_extraction自动注册未声明地点（type=auto_registered）；④batch_check_outline_compliance多章purpose合并为单次LLM调用。原创6章旧物修复悬疑《铜锈》：51,533字符、39事件、8悬念线（100%解决率）、243关系。6章大纲零偏移，事后编辑闭环验证（Ch3编辑→快照→回滚），批量合规batch_purpose=true。37个MCP工具，140 E2E测试全部通过。归档于 `archive/v21-功能增强验证/`。

## Project Structure

```text
novel_test/
├── CLAUDE.md                    # 本文件
├── archive/
│   ├── v1-间隙-初稿/            # 初稿完整归档（设定/大纲/12章正文/文学分析）
│   ├── v2-知识图谱MVP-验证/     # MVP验证归档（验证报告 + A/B/C/D四组测试输出）
│   └── v3-闭环提取管线-验证/    # 闭环验证归档（验证报告 + V1/V2提取结果）
│   ├── v4-扩展性验证-推演情节层/
│   ├── v5-泛化验证-生死场/
│   └── v6-多轮闭环稳定性验证/  # 4轮闭环+项目隔离+LLM集成
│   └── v9-原创创作验证/        # 6章原创短篇《错轨夜车》
│   └── v10-叙事深度验证/       # 悬念线+大纲+叙事结构+预查询验证
│   └── v11-12章规模验证/       # 12章双时间线悬疑《水蚀》+ Bug修复
│   └── v12-约束解耦重构/       # 后置校验替代prompt威慑 + git初始化
│   └── v14-MCP闭环验证/        # MCP工具闭环验证《东华澡堂》
│   └── v15-功能增强验证/        # 后端同步+增强一致性+节奏分析《缝合》
│   └── v16-串行连贯性验证/      # 前章注入+悬念线预算+串行重跑《缝合》
├── novel_mcp_server/            # MCP Server（28工具，包装novel_kg_mvp）
│   ├── server.py                # FastMCP主文件（薄壳）
│   ├── core.py                  # 业务逻辑+连接池+后端选择+节奏分析
│   ├── kg_json.py               # JSON文件后端（默认，零依赖）
│   ├── kg_sync.py               # JSON↔Neo4j双向同步工具
│   ├── mcp_cli.py               # CLI fallback（薄壳）
│   ├── test_e2e.py              # 双后端E2E测试（140测试点）
│   └── requirements.txt         # mcp[cli]依赖
├── .mcp.json                    # MCP Server配置
├── novel_kg_mvp/                # 知识图谱代码
│   ├── docker-compose.yml       # Neo4j容器
│   ├── config.yaml              # 连接配置 + LLM配置
│   ├── graph.py                 # 图谱客户端（project隔离 + 10种节点类型 + CRUD + 查询）
│   ├── extractor.py             # 手工数据构建（含风格层和情节层）
│   ├── mine.py                  # 提取管线（冲突检测 + 图谱写回）
│   ├── prompts.py               # 提取prompt模板（粒度控制 + 间隙定义 + 隐含解决检测）
│   ├── main.py                  # 主流程（描述性prompt构建 + 场景展开指导）
│   ├── cli.py                   # Click CLI（--project隔离 + --auto + 后置校验 + audit-threads）
│   ├── validators.py            # 后置校验模块（人名/结构/风格/篇幅 + 自动修复）
│   ├── llm.py                   # LLM API调用（OpenAI兼容 + 环境变量Key）
│   ├── projects/                # 项目级文件隔离
│   │   ├── jianxi/              # 《间隙》
│   │   └── sheng_si_chang/      # 《生死场》（含ch1-16完整闭环数据）
│   └── requirements.txt
└── .claude/skills/              # 已归档的网文skill（不再使用）
```

## Knowledge Graph MVP

### 三层图谱架构

| 层 | 节点类型 | 用途 |
|---|---------|------|
| 结构层 | Character, Location, Event, Theme, TimePeriod | 人物/地点/事件/主题一致性 |
| 风格层 | StyleGuide, Motif | 叙事风格规则、禁忌、核心意象演变 |
| 情节层 | ChapterArc | 每章叙事目的、场景序列、结尾锚点 |
| 规划层 | SuspenseThread, OutlineEntry | 悬念线生命周期追踪、全局大纲硬约束 |

### 运行方式
```bash
cd novel_kg_mvp
docker-compose up -d          # 启动Neo4j
pip install -r requirements.txt
python main.py                # 构建图谱并运行验证
```

Neo4j浏览器：http://localhost:7474 （neo4j / novel2024）

### 验证结论
- 1882字图谱上下文（三层） > 93KB全文（续写质量），信息压缩比 49:1
- 风格层修正了LLM最常见的美学偏差（"宣告决定"→"无声选择"）
- 情节层只用254字就修正了叙事方向
- 详见 `archive/v2-知识图谱MVP-验证/验证报告.md`

### 闭环提取管线
- 场景级粒度：5-8事件/章（V1:21事件 → V2:7事件）
- 冲突检测：事件ID重复/地点未注册/人物未注册/事件数量/间隙误判
- Gap精确定义：意识滑出身体+从外部看自己，排除日常觉醒/情感波动
- 详见 `archive/v3-闭环提取管线-验证/验证报告.md`

### 扩展性（推演情节层）
- 从图谱数据推演新章节ChapterArc：近3章arc + 意象演变 + 主题线 + 最后事件
- 234字推演arc使结尾锚点精确命中（vs 无arc时模糊）
- 新增方法：`get_arc_derivation_context()` + `ARC_DERIVATION_PROMPT`
- 详见 `archive/v4-扩展性验证-推演情节层/验证报告.md`

### 已验证（v6-v11）
- [x] 闭环回写：4轮全自动闭环零漂移
- [x] 篇幅改善：场景展开指导使产出1600-4600字
- [x] LLM集成：OpenAI兼容API + 环境变量API Key + Click CLI --auto模式
- [x] 自动提取：LLM从原文自动构建图谱，续写质量与手工图谱相当（v7）
- [x] 冷启动：零手工数据，仅6条风格指南，3214字高质量续写（v8边城）
- [x] 原创创作：200字方向→世界观生成→6章19,671字自动续写，风格/人物/情节连贯（v9）
- [x] 叙事深度：10条悬念线跨章追踪，6章大纲零偏移，14悬念线/118关系（v10）
- [x] 12章规模：12章闭环零中断，3章intercut硬约束执行，100,717字，50事件/177关系（v11）
- [x] Bug修复：loop跳章、人名漂移、叙事结构不执行（v11）
- [x] 约束解耦：50+处"必须/禁止"从prompt中剥离，validators.py后置校验替代威慑指令（v12）
- [x] prompt软化：12处标签改为描述性，LLM产出质量不降级（v12）
- [x] 后置校验：人名/结构/风格/篇幅四校验器，管线集成自动修复+重试（v12）
- [x] 悬念线隐含解决：提取prompt指导使解决率8.7%→16.7%，audit-threads额外+12.5%，综合29.2%（v13）
- [x] MCP闭环：26个MCP工具包装图谱CRUD+prompt模板+校验，Agent零外部API调用完成6章原创（v14）
- [x] MCP配置：`.mcp.json`在项目根目录（非settings.json），server.py用`os.chdir()`解决config.yaml相对路径
- [x] 后端同步：JSON↔Neo4j双向迁移，纯接口设计无后端特定代码，kg_sync.py（v15）
- [x] 增强一致性：人物空间矛盾+事件ID连续+章节编号跳跃+主角缺席检测（v15）
- [x] 叙事节奏：目的重复+结尾重复+场景密度+节奏曲线分析（v15）
- [x] 28工具58测试点：JSON/Neo4j双后端E2E全部通过（v15）
- [x] 串行连贯性：前章正文注入使感官锚点形成完整跨章弧线，甜味/嗡鸣/铜钥匙三锚点六章延续（v16）
- [x] 悬念线预算：动态max(8,ch*1.5)，超限时跳过medium/low线程，解决率33%→75%（v16）
- [x] 串行写作：每章写完立即提取，下一章prompt含前章结尾，字数波动从2.9x降至1.7x（v16）

### 已验证（v17）
- [x] 50章规模：50章闭环零中断、零MCP失败、人名零漂移。大纲偏离后系统自适应（v17）
- [x] 缩放：50章/511K字/243事件/81悬念线/1237关系，图谱查询性能稳定（v17）
- [x] 预算公式：max(8,ch*2.0)在50章规模下运行正常，低优先级悬念线正确跳过（v17）
- [x] 跨session续写：多次context compaction后续写无损失（v17）
- [x] 涌现叙事：零号/初雪弧线完全由Agent基于图谱上下文自发推进，无外部规划（v17）

### 已验证（v18）
- [x] 破折号限制：dash_restriction规则使破折号从97→2（-98%），AI最明显视觉标记消除（v18-R1）
- [x] 感官多样性：sensory_diversity规则使6章24个感官锚点零重叠（v18-R1）
- [x] prev_text自增强切断：从3000→500字符有效切断风格自我复制循环（v18-R1）
- [x] 角色声音区分：character_voice规则使白蕊/老钱/周北说话方式明显不同（v18-R1）
- [x] 禁用句式校验：forbidden_patterns配置+validators.py后置校验使"不是X是Y"从13→0（-100%），prompt威慑无效配置校验有效（v18-R2）
- [x] 节奏标记：rhythm字段（tight/ascending/descending/mixed）注入写作prompt，6章实际节奏均与标记一致（v18-R2）

### 已验证（v19）
- [x] 大纲合规检查：bigram匹配+LLM语义检查，6章零偏移，4字段逐项检查（v19）
- [x] 大纲显式修订：revise_outline保留审计轨迹（reason/revised_chapter/compliance=overridden），级联影响自动追踪（v19）
- [x] 事后编辑影响分析：analyze_edit_impact检测事件/悬念线/人物/下游大纲变更，5事件变更+4大纲级联（v19）
- [x] 审核关卡：review_chapter支持accept/edit/rewrite/revise_outline四种动作（v19）
- [x] 33工具96测试点：JSON后端E2E全部通过（v19）
- [x] 大纲铁律：偏离大纲时显式修订而非静默放弃，完整审计链（v19）

### 已验证（v20）
- [x] LLM语义合规检查：bigram未匹配时追加LLM语义等价判定，"深夜来访"="突然出现"正确匹配（v20）
- [x] 目的级别检查：purpose_alignment独立维度，不受key_events格式影响（v20）
- [x] V17回溯验证：50章全量扫描，19/50偏离章节全部检出（confidence=high），31/50 aligned章节零误报（v20）
- [x] 偏离起点检测：Ch27为V17首次偏离点，与V17原始报告精确吻合（v20）
- [x] 103 E2E测试全部通过（v20）

### 已验证（v21）
- [x] 编辑版本管理：accept_edit自动快照（微秒时间戳），list_edits/rollback_edit回滚，clear_project同步清理快照（v21）
- [x] prompt/extraction落盘：get_extraction_prompt/get_writing_prompt/get_derivation_prompt自动保存到prompts/目录，write_extraction保存到extractions/目录（v21）
- [x] 地点自动注册：write_extraction自动注册未在图谱中的引用地点（type=auto_registered），去重existing+new_locations（v21）
- [x] 批量合规检查：batch_check_outline_compliance多章purpose合并为单次LLM调用，自动检测大纲章节，返回统计摘要（v21）
- [x] 37工具140测试点：JSON后端E2E全部通过（v21）

### 待验证
- 🔲 预查询有效性：长篇（50章+）场景下LLM主动请求上下文的价值
- 🔲 篇幅精确控制：当前波动1.5x（3938-5912字），串行后改善
- 🔲 100章+规模：超50章的一致性保持与图谱查询性能

## Development Notes

- `.claude/skills/` 下的skill是早期网文创作流程的遗留，已不再使用，保留仅供参考
- 项目目前没有package.json或构建脚本
- 优先使用中文沟通
- **生成验证必须使用子代理（Agent工具）**：章节正文生成、提取、校验等闭环操作必须在子代理中完成。主会话只做编排和收集结果。直接在主会话生成正文会浪费上下文且造成污染。

### 测试与开发流程

**代码修改后立即测试（无需重启）：**

```bash
cd novel_mcp_server

# E2E测试：140个测试点覆盖全部37工具，~60秒
python test_e2e.py                    # JSON后端（默认，零依赖）
KG_BACKEND=neo4j python test_e2e.py   # Neo4j后端（需docker-compose up -d）

# 单工具测试
python mcp_cli.py get_graph_stats --project <项目名>
KG_BACKEND=neo4j python mcp_cli.py get_graph_stats --project <项目名>

# 后端同步
python mcp_cli.py sync_backends --project <项目名> --direction json_to_neo4j
python mcp_cli.py analyze_pacing --project <项目名>
KG_BACKEND=neo4j python mcp_cli.py get_graph_stats --project <项目名>
```

**后端选择：** `KG_BACKEND` 环境变量控制，默认 `json`（文件存储于 `novel_kg_mvp/projects/<项目>/graph.json`）。

**代码架构（改哪里）：**

| 改什么 | 改哪里 | 需要重启MCP |
|--------|--------|------------|
| 业务逻辑（37个工具） | `novel_mcp_server/core.py` | 是 |
| JSON后端存储 | `novel_mcp_server/kg_json.py` | 是 |
| Neo4j后端存储 | `novel_kg_mvp/graph.py` | 是 |
| 提取管线 | `novel_kg_mvp/mine.py` | 是 |
| Prompt模板 | `novel_kg_mvp/prompts.py` + `main.py` | 是 |
| MCP工具签名/文档 | `novel_mcp_server/server.py` | 是 |
| CLI参数 | `novel_mcp_server/mcp_cli.py` | 否（每次新进程） |

**开发循环：** 改代码 → `python test_e2e.py` → 通过即可。MCP集成验证仅在需要时重启。

**破坏性操作保护：** `init_project` 和 `clear_chapter_data` 需传 `confirm="I_UNDERSTAND_THIS_IS_DESTRUCTIVE"`。

## 归档规范

每轮验证（V1-V13…）完成后，必须将**全部产出物**归档到 `archive/vN-验证名/` 目录下。归档不完整=验证未完成。

### 目录结构

```
archive/vN-验证名/
├── 验证报告.md              # 必须有。包含：验证目标、架构变更、文件变更、端到端结果、对比数据、待改进
├── world_setup.json         # 项目设定（如有）
├── outline.json             # 全局大纲（如有）
├── project.yaml             # 项目配置（如有）
├── output/                  # 全部章节正文
│   ├── ch1_generated.txt
│   ├── ch2_generated.txt
│   └── ...
├── extractions/             # 提取结果JSON
│   ├── extraction_ch1.json
│   └── ...
└── prompts/                 # 发送给LLM的完整prompt（提取prompt + 续写prompt）
    ├── extraction_ch1.txt
    ├── writing_ch1.txt
    └── ...
```

### 归档检查清单

每轮验证完成时，按此清单逐项确认：

- [ ] **验证报告** — `验证报告.md` 已写入，包含完整数据（图谱统计、解决率、对比表）
- [ ] **章节正文** — `output/ch*_generated.txt` 全部从 `projects/项目名/output/` 复制
- [ ] **提取结果** — `extractions/extraction_ch*.json` 全部复制
- [ ] **LLM prompt** — `prompts/extraction_ch*.txt` + `prompts/writing_ch*.txt` 全部复制
- [ ] **项目设定** — `world_setup.json`、`outline.json`、`project.yaml` 复制（如存在）
- [ ] **CLAUDE.md更新** — Project Overview新增条目，已验证/待验证列表已更新
- [ ] **Git提交** — 代码变更和CLAUDE.md已commit（archive目录本身被gitignore排除）

### 注意事项

- `archive/` 目录在 `.gitignore` 中被排除，不会进入git。归档的目的是**持久化保存产出物**，防止项目目录被清理时丢失
- 如果验证没有独立项目目录（如V12在v11_test上跑单章），则只归档有产出的文件，不强求空目录
- 报告中的数据必须与实际产出文件一致（字数、文件数、统计数字）
