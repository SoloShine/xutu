# 世界渲染研究归档（World Rendering Research Archive）

**归档日期**: 2026-06-14
**研究周期**: 2026-06-13 ~ 2026-06-14
**状态**: 暂停归档。后续有精力再专门研究。
**归档原因**: 研究走完一轮（thesis 验证 → 渲染 POC → runtime MVP1/2），部分路线证伪，需退一步重新审视方向。所有资料是重要资产，完整保留并集中归档。

**本文件是归档入口**（`docs/research/world_rendering_archive/INDEX.md`）。后续研究从本文件开始，按 §5 恢复指南进入。所有路径相对本归档根目录。

---

## §0. 一句话总结

探索用多 agent "具现化"一个含时间维度的小说世界，冻结后并行渲染成正文。两个 thesis：①异质多层 agent 架构（验证成立但条件性）②bitemporal fabula/sjuzhet（证伪）。工程上验证了 reducer 范式（确定性 fold 世界状态）和渲染投影（isActive=false），但 extractor 的"决策→状态"翻译层存在根本性语义波动（MVP2 的 schema 路线证伪）。**研究在"如何稳定生成世界状态"处卡住，需重新审视 agent 产出与状态落地之间的关系。**

---

## §1. 研究时间线

| 阶段 | 内容 | 结论 |
|------|------|------|
| 方向 pivot | 从"声明式工作台"工程优化 → 原创"世界渲染"研究 | 业界空白，值得做 |
| 论文精读 | Park/Riedl/Fowler/Wolf/Mateas 5 篇 | 确认空白 + 设计输入 |
| thesis 2 验证 | bitemporal fabula/sjuzhet 桥接 | **证伪**（2h 发现，省数周）|
| thesis 1 架构 | 异质多层 agent（L3 世界意志/L2 集体/L1 角色 + 横切规律执行者）| 用户洞察修正为"多层级规则相互影响" |
| H4 pilot | 小场景 5×4 / 补强 / 中场景 13×10 | thesis 1 条件性成立，规模放大 |
| 渲染 POC | trace → HTML 视觉小说 + Ren'Py | isActive=false 投影成立（零 token）|
| runtime MVP1 | reducer 纯函数 fold event log → snapshot | **范式成立**（reviewer 独立验证确定性）|
| runtime MVP2 | --json-schema 求稳定性 + grounded 分层 | **证伪**（慢 7-10x 且不解决语义波动）|

---

## §2. 关键结论（成立 vs 证伪）

### ✅ 成立的
1. **reducer 范式**：纯函数 fold event log → snapshot，确定性可 replay（治"生成式误差累积"——生成有随机，但 fold 确定，世界冻结后无新误差）
2. **渲染投影**：世界冻结后渲染端 isActive=false，零 LLM 调用（render POC 验证）
3. **异质 agent 层级冲突**（条件性）：thesis 1 pilot 显示异质系统产生同质系统产生不了的层级冲突（但 pilot 有场景设计偏向，见 §4）

### ❌ 证伪的
1. **thesis 2 bitemporal**：baseline 够用，多区间与 baseline 同构（换名非创新）
2. **MVP2 --json-schema 求稳定**：schema 约束格式不约束语义，跨运行 effect 一致性仅 25.6%，且慢 7-10x

### ⚠️ 未决的
- **extractor 语义波动**：NL action → 结构化 effect 的翻译，LLM 每次判断不同（落地率 17%-58% 跨运行波动）。这是当前卡点。

---

## §3. 资产清单（完整，路径相对归档根）

### 01_positioning/ — 锚点 / 定位
| 文件 | 说明 |
|------|------|
| `01_positioning/2026-06-13-world-rendering-research-positioning.md` | 研究方向锚点（§0-§10 + 决策记录）|
| `01_positioning/2026-06-13-session-handoff.md` | 会话交接 / 恢复入口 |
| `01_positioning/2026-06-13-declarative-novel-workbench-design.md` | 前身（声明式工作台，现降级为工程基础）|

### 02_papers/ — 论文精读
| 文件 | 说明 |
|------|------|
| `02_papers/2026-06-13-paper-synthesis.md` | 5 篇精读汇总（Park/Riedl/Fowler/Wolf/Mateas）+ 设计输入对照表 + trace schema 统一草案 |
| `02_papers/raw/` | 论文原文（Riedl JAIR 2010 / Konle plot temporal graphs，精读素材）|

### 03_thesis2/ — bitemporal（已证伪）
| 文件 | 说明 |
|------|------|
| `03_thesis2/2026-06-13-transaction-time-verification.md` | transaction_time 查证 |
| `03_thesis2/2026-06-13-thesis2-minimal-validation.md` | 验证蓝图（证伪设计）|
| `03_thesis2/2026-06-13-thesis2-validation-report.md` | 验证报告（123 测试点，被证伪）|
| `03_thesis2/thesis2_validation.py` | 验证脚本（可重跑）|
| `03_thesis2/v16-validation-data.json` | V16 提取的 26 事件数据 |

### 04_thesis1/ — 异质 agent 架构
| 文件 | 说明 |
|------|------|
| `04_thesis1/2026-06-13-thesis1-architecture.md` | 架构草案（L3/L2/L1 + 横切 + 三种影响机制 + trace schema）|
| `04_thesis1/2026-06-13-collective-agent-verification.md` | 集体 agent 文献查证（结构性空白）|
| `04_thesis1/2026-06-13-h1-collective-agent-validation.md` | H1 验证（⚠️ 已废除，还原论错误）|
| `04_thesis1/2026-06-13-h4-systemic-validation-design.md` | H4 系统性验证设计 |

### 05_h4_pilots/ — pilot 脚本 + 报告 + 原始数据
| 文件 | 说明 |
|------|------|
| `05_h4_pilots/h4_generation_pilot.js` | 小场景 pilot 脚本（5 agent × 4 ticks）|
| `05_h4_pilots/h4_reinforcement_pilot.js` | 补强脚本（prompt 审计 + 反例场景）|
| `05_h4_pilots/h4_medium_scene_pilot.js` | 中场景脚本（13×10，3 层集体嵌套）|
| `05_h4_pilots/2026-06-13-h4-generation-pilot-report.md` | 小场景报告（异质明显优）|
| `05_h4_pilots/2026-06-13-h4-reinforcement-report.md` | 补强报告（prompt 双向偏差，thesis 1 仍站住）|
| `05_h4_pilots/2026-06-13-h4-medium-scene-design.md` | 中场景设计 |
| `05_h4_pilots/2026-06-13-h4-medium-scene-report.md` | 中场景报告（scale_signal=放大 ⭐）|
| `05_h4_pilots/raw_outputs/01_medium_scene_output.json` | **中场景原始 trace（655KB，130×2 effect，最重要数据）**|
| `05_h4_pilots/raw_outputs/02-06_*.output` | 其他 pilot run 原始输出 |

### 06_render_poc/ — 渲染投影（isActive=false）
| 文件 | 说明 |
|------|------|
| `06_render_poc/render_poc/render_poc.py` | 投影器（trace → HTML 视觉小说 + Ren'Py）|
| `06_render_poc/render_poc/seal_crisis_visual_novel.html` | HTML 视觉小说（207KB，零依赖）|
| `06_render_poc/render_poc/seal_crisis_hetero.rpy` / `_homo.rpy` | Ren'Py 脚本 |
| `06_render_poc/render_poc/event_log.json` | 结构化中间产物 |
| `06_render_poc/render_poc/REPORT.md` | 渲染 POC 报告 |

### 07_runtime/ — runtime MVP1（成立）+ MVP2（证伪）
| 文件 | 说明 |
|------|------|
| `07_runtime/specs/2026-06-13-world-rendering-runtime-design.md` | runtime 设计 spec（6 层架构）|
| `07_runtime/specs/2026-06-13-world-runtime-mvp2-design.md` | MVP2 设计（稳定性 + 意图/事件分层）|
| `07_runtime/plans/2026-06-13-world-runtime-mvp1.md` | MVP1 实现计划（9 task TDD）|
| `07_runtime/plans/2026-06-13-world-runtime-mvp2.md` | MVP2 实现计划（6 task）|
| `07_runtime/world_runtime/MVP1_REPORT.md` | MVP1 报告（reducer 范式成立）|
| `07_runtime/world_runtime/schemas.py` | Event/Effect/Snapshot/ConflictResolution |
| `07_runtime/world_runtime/event_store.py` | append-only JSONL |
| `07_runtime/world_runtime/reducer.py` | 纯函数 fold + priority 裁决 |
| `07_runtime/world_runtime/llm.py` | call_llm wrapper（claude.cmd subprocess + telemetry）|
| `07_runtime/world_runtime/extractor.py` | NL action → effect |
| `07_runtime/world_runtime/run_mvp1.py` | 端到端（extract .output → reduce → snapshot）|
| `07_runtime/world_runtime/tests/` | 33 单测 |
| `07_runtime/world_runtime/snapshots/snap_t0..t9.json` | 10 个世界状态 |
| `07_runtime/world_runtime/events.jsonl` / `run1_events.jsonl` / `run1_stdout.txt` / `run2_stdout.txt` | effect log + 稳定性验证 run |

### 外部 memory（不在本 repo）
- `C:\Users\Administrator\.claude\projects\D--novel-test\memory\research-direction-pivot.md` — 研究方向 pivot 记录（含全部阶段更新 + 归档指针）

---

## §4. 走偏点（诚实记录，后续研究必读）

用户原话："其中的很多东西我们可能都走偏了"。以下是诚实复盘，避免后续重蹈：

### 4.1 thesis 2 bitemporal（已证伪，但快速证伪是好的）
把 transaction_time 叙事化（物理时间 → 叙事章号）听起来创新，但 baseline（fabula + dict[sjuzhet, list[float]]）够用。**走偏点**：被"文献空白"吸引，但空白 ≠ 值得做。**好的是 2 小时就证伪，省了数周。** 教训：竞品空白 ≠ 价值。

### 4.2 thesis 1 pilot 场景设计偏向异质
H4 pilot 的场景（封印危机 + 多层集体）天然利于异质系统。**走偏点**：verdict"异质明显优"部分来自场景设计偏向（pilot 报告诚实标注了）。补强试图控制（赋能式同质 prompt + 反例场景），但场景层偏向未完全消除。后续若重做，需场景正交化。

### 4.3 ⭐ extractor NL→effect 翻译层（根本性走偏，当前卡点）
整个 MVP1/2 架构假设"agent 产 NL 决策 → extractor 翻译成结构化 effect → reducer fold"。**走偏点**：这个翻译层有根本性语义波动——
- 同一 action，extractor 这次判"落地"下次判"没落地"（落地率 17%-58% 跨运行波动）
- schema（--json-schema）只约束格式，约束不了语义判断
- 根因：pilot 的 agent 产"决策陈述/立场"（thesis 1 验证用），不是"事件/状态变化"。extractor 试图把意图翻译成事件，意图和事件不一一对应

**这可能是最大的走偏**——把"生成世界状态"拆成"agent 决策 + extractor 翻译"两层，翻译层引入不可控波动。**后续方向**：考虑让 agent 直接产 effect（不经 extractor），或重新设计 agent 产出语义（决策+落地一体）。

### 4.4 MVP2 --json-schema 路线（证伪）
假设 constrained decoding 能消除 extractor 波动。**走偏点**：没区分"格式稳定"和"语义稳定"。schema 解决前者不解决后者，且付 7-10x 性能代价（单次 7.4 分钟）。**两头空**：慢 + 仍波动（25.6% 一致）。教训：动手前想清楚"这个约束约束的是什么层"。

### 4.5 subagent-driven 方法对机械任务过重（方法走偏）
MVP1/2 用 superpowers subagent-driven（每 task implementer + 2 reviewer subagent）。**走偏点**：plan 里代码已完整给定，implementer 基本是"复制+TDD"，这种机械任务套完整 review 流程过重——大量耗在 subagent 协调。对比 Workflow 跑 261 agent 17 分钟。**教训**：机械实现直接做，subagent-driven 只用于需独立判断的复杂 task。

### 4.6 claude.cmd subprocess 性能认知偏差
早期假设 claude.cmd subprocess 单次几秒（MVP1 haiku 验证）。但 sonnet + --json-schema 单次 7.4 分钟。**走偏点**：没尽早做 sonnet+schema 的性能基准测试，等到 MVP2 Task 6 跑很久才发现。教训：涉及 LLM 的方案，先做单次性能基准再 scale。

---

## §5. 恢复指南（后续研究从这开始）

1. **先读本文件 §2-§4**（10 分钟）——了解什么成立、什么证伪、哪里走偏
2. **读 `01_positioning/` 的 positioning doc + handoff**——研究方向全貌 + 最新会话状态
3. **重点读 §4.3**（extractor 翻译层走偏）——这是当前卡点，决定后续方向
4. 若要看 reducer/runtime 实现：`07_runtime/`；要看 pilot 原始数据：`05_h4_pilots/raw_outputs/`

**重新出发的候选方向**（未验证）：
- **A. agent 直接产 effect**：去掉 extractor 翻译层，agent prompt 直接产"决策+结构化状态变化"一体输出。避免翻译层波动。但要重设 agent prompt（回到"落地鸿沟"最初讨论）
- **B. 接受 effect log 概率性**：承认生成阶段语义不稳定，reducer fold 多次取众数/一致部分。世界冻结后仍确定（fold），只是生成是概率采样
- **C. 重新审视 thesis 1**：pilot 的"异质优势"是否经得起场景正交化？或 thesis 1 本身需重新定义
- **D. 退回渲染端**：reducer 范式 + 渲染投影已成立，是否先用"手工 effect log"驱动渲染验证端到端叙事（治"一脸懵"），把生成问题搁置

---

## §6. 未决问题

1. agent 产"决策陈述"还是"决策+落地事件"？哪个能让世界状态稳定生成？
2. extractor 翻译层是否该去掉（agent 直接产 effect）？
3. thesis 1 的"异质优势"在场景正交化后是否仍成立？
4. reducer 范式 + 渲染投影已成立，是否先用手工数据驱动渲染验证叙事，把生成问题搁置？
5. claude.cmd + LLM 的性能瓶颈——runtime 是否该换调用方式（直接 API vs subprocess）？

---

## §7. 归档结构

```
docs/research/world_rendering_archive/
├── INDEX.md                    # 本文件（归档入口）
├── 01_positioning/             # 锚点 / 定位 / handoff
├── 02_papers/                  # 论文精读
├── 03_thesis2/                 # bitemporal（证伪）
├── 04_thesis1/                 # 异质 agent 架构
├── 05_h4_pilots/               # pilot 脚本 + 报告 + raw_outputs/（原始 trace）
├── 06_render_poc/              # 渲染投影 POC
└── 07_runtime/                 # runtime MVP1/MVP2（spec/plan/code/report）
```

所有世界渲染相关文件已集中到此。docs/research/ 下不再散落（仅保留本归档目录）。外部 memory 在 `C:\Users\Administrator\.claude\projects\D--novel-test\memory\`（不在 repo，记录全部阶段更新）。
