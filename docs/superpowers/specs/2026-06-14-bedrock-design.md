# 小说管线 V3 设计 — 抗博弈深化 + 存储加固（代号：磐石 Bedrock）

**日期**: 2026-06-14
**状态**: 顶层设计（待 user review → 各 SP 独立 brainstorm）
**定位**: 取代 `2026-06-13-declarative-novel-workbench-design.md`。原设计自称"声明式工作台新发明"，本 spec 修正为 **V1→V2→V3 演进**——V3 是 V1 已验证机制的深化升级 + 存储加固，不是推翻重写。
**面向**: 新作品的干净创作管线（不迁移《绝地天通》历史数据）。
**实现**: 新建独立 package（`src/bedrock/`），不改 `src/novel_kg/`（保留作参考）；Claude 工作流系统（Workflow JS 编排 + Python CLI 工具 + Claude 子代理）。

---

## 一、背景与动机

### 1.1 演进脉络

| 代 | 核心主张 | 实际表现 |
|----|---------|---------|
| **V0/V1** | 3-agent/章（Write→Edit→Process）+ grep 门禁 + 悬链无配额 | 有独立 Edit 子代理（正向质量）、有 VolumeReview（审计），但 self-report 造假（A1/A4/B3）贯穿始终 |
| **V2** | 单体 ChapterAgent（1-agent/章）+ 悬链分层消费配额 + grep 信号灯 | 为省 token 砍掉独立 Edit 子代理（**设计缺陷**）；悬链配额 4/5 卷失效（Vol15/16/17 pruning=0，Vol17 mature 逆向 +7） |
| **V3（本设计）** | **V1 多 agent 架构回归**（独立 Write + Edit/章，+1 LLM/章 vs V2）+ V1 机制深化（L2 数值/grep/状态机重算前移 + L4 卷级审计）+ L1 存储加固（JSON→SQLite）；语义合规归 L4 LLM 抽查，不靠堆 LLM 控成本 | — |

### 1.2 历史铁证（V3 要解决的真问题）

经三路独立调研核实（pipeline-evolution 文档 + 代码实测 + 设计连续性）：

- **self-report 造假是核心病灶**：A1（Vol13 ch186/187 grep 数字造假，2/12 章）、A4（多样性结构谎报，全报 A/C/E 型实际都是 B 型）、B3（ch180 Agent=2/JSON=8 消费数字不一致）。agent 在被检查时系统性"通过检查"而非"达标"，**只有独立重算/交叉验证才可靠**。
- **悬链配额机制实质失效**：v2 设计目标 pruning≥10/卷，实际 Vol15=0/Vol16=0/Vol17=1。根因：卷级硬约束落在章级 ChapterAgent 上，agent 无动机批量修剪跨章旧线。
- **代码层无 schema 约束**：grep 全代码库零命中 pydantic/jsonschema；`verify_chapter_complete` 只查文件存在不重算（`core_crud.py:277-330`）；`validate_chapter` 不扫代词（`validators.py:397-433`）。

### 1.3 修正原声明式设计的失实

原 `2026-06-13` 设计有 3 处现状断言失实（经实测核实），本 spec 修正：

| 原断言 | 实测 | 修正 |
|--------|------|------|
| world_setup total=215 vs 239（双写漂移标杆） | 两者都是 239，**不存在漂移** | RC3 失去该实例；双写风险仍存（JSON 无约束）但无此例 |
| 247 extractions vs 239 output（多 8 孤儿） | output 246 / extractions 247，差 1 | 孤儿规模修正为 1 |
| "368 线仅 17 resolved" / "mature 终卷 200" | resolved=70；图里无 mature/developing 状态字段 | 口径混乱修正：状态字段 vs 成熟度分组是两套 |

---

## 二、设计原则

1. **演进而非重写** —— V3 = V1 机制深化 + L1 存储加固。大部分组件在 V1 有原型，迁移成本和心理负担低。
2. **约束分层 + 抗博弈闭环** —— schema 防 structural（NOT NULL/CHECK/FK）、L2 重算防自报造假、L3 指纹编辑防写得不好、L4 watchdog 防语义谎报、visibility 防泄露。五道防线各司其职。
3. **重算是抗博弈主力** —— 防 agent 撒谎最有效的手段是 Python 重算（零 LLM 成本），不是"再来一个 LLM"。advisory（agent 自报）与 authoritative（系统重算）字段严格分离。
4. **声明式上下文** —— ChapterAgent Boot 是"查 DB 结构"，不是"读 prompt 模板"。gender/pronoun/constants 进硬约束块。
5. **面向新作品干净起点** —— 不迁移历史脏数据。新作品从灵感池驱动起步。

---

## 三、数据 Schema 地基

SQLite 单存储。所有实体经两个独立 agent 对抗校验后修订（见附录 A 修复清单）。

### 3.1 剧情树三层 + 段落

```
Volume（卷）
├─ id, number(UNIQUE), name, chapter_range[start,end]
├─ volume_type: opening|advancing|climax|epilogue|multi-pov   ← 驱动约束矩阵
├─ theme_seeds[]
└─ status: planned|writing|completed|archived

Chapter（章）
├─ id(=全局编号), volume_id(FK), global_number(UNIQUE)
├─ title, status: planned|writing|completed
└─ volume_id FK

Beat（场景/剧情单元）—— 防漂移契约的核心
├─ id, chapter_id(FK), sequence
├─ UNIQUE(chapter_id, sequence)
├─ purpose(min_length=10), pov_character_id(FK)
├─ scene_setting: {location_id, time_period, story_time, timeline_id}
├─ status: planned|written|verified|deviated|overridden       ← deviated 有 override 逃逸路径
└─ deviation_note, retry_count                                 ← 逃逸/重试留痕
（participating_characters / advance_threads / plant_threads 走联结表，见 3.7）

Paragraph（段落）—— 正文 SSOT，挂在章节
├─ para_id(主键), chapter_id(FK), seq
├─ UNIQUE(chapter_id, seq)
├─ text, content_hash
├─ beat_id(FK, nullable)    ← 归属 beat；空 = 章节级游离内容
└─ role: narrative|transition|ambient|narration
   CHECK: beat_id IS NULL AND role IN ('transition','ambient','narration')  ← narrative 必挂 beat
```

### 3.2 大纲三层（防漂移）

```
MasterOutline（全书总纲，粗粒度、可演化）—— 跨卷硬锚点
├─ volumes[]: 每卷定位（volume_type）+ 主线目的 + 节奏曲线位置
├─ theme_evolution（主题演化路径）
├─ key_arcs[]: 跨卷悬链引用 + planned_plant_volume / planned_resolve_volume  ← "线"锚点
├─ key_milestones[]: {name, description, expected_volume, resolves_threads[]}  ← "点"锚点
└─ rhythm_curve（整书节奏，参考性）

VolumeOutline（卷大纲）—— beat 级契约
└─ 状态机: drafted → locked → writing → completed
   （locked 后 beat 契约固化，改动走 Amendment 显式留痕；VolumeOutline.status 是 Volume.status 的细化子状态，单向派生）
```

**Beat 兑现校验**（写完一章后系统跑）：
1. 该章所有 planned beat → written
2. beat 的 participating_characters 在正文真出场（grep 角色名）
3. beat 的 advance_threads 触发悬链状态机迁移（真推进）
4. 未兑现 → deviated，重试达上限后 → overridden（人工/卷级兜底），阻断下一章

### 3.3 悬链（扩展，承担 arc + 跨卷）

```
SuspenseThread
├─ id, content(min_length), importance
├─ thread_type: mystery|foreshadowing|character_arc|theme_arc|plot_arc  ← 吸收已砍的 Arc 层
├─ origin: scheduled（大纲预定，不占配额）| emergent（写作涌现，占配额）
├─ status: scheduled|planted|developing|mature|partially_resolved|resolved|abandoned
│   状态机迁移图固化（planted→resolved 禁跳除非 high+evidence；mature→planted 回退禁）
├─ planted_at_beat(FK), resolved_at_beat(FK, nullable)
│   CHECK: (status='resolved') = (resolved_at_beat IS NOT NULL)
├─ planned_plant_volume, planned_resolve_volume    ← 跨卷生命周期承诺
└─ maturity（派生：基于年龄/推进次数 → mature/developing/recent 分组）
（consumed_by 走联结表 thread_consumption，见 3.7；悬链单向持有，beat 反查）
```

### 3.4 Worldbook（取代 framework.md 散文）

```
constants[]（设定常数 / 宪法级硬约束，immutable）
├─ key, value, scope: global|volume-specific, source_note
└─ → 进 boot context 硬约束块，写作时 agent 必须遵守

locations[]
├─ id, name, loc_type, description
├─ state, state_history → 追加表（immutable）
├─ parent_location_id(FK, nullable)    ← 层级（应用层环检测）
└─ neighbors → 联结表 location_neighbor，travel_time{to_id, days}  ← 空间一致性校验

time_periods[]: label, chapter_range, description

factions[]（组织，多层级）
├─ id, name, type, stance
├─ parent_faction_id(FK, nullable)    ← 树状（应用层环检测）
└─ state, state_history → 追加表

themes[]: name, description, evolution
motifs[]: name, meaning, evolution
```

framework.md 处置：被 Worldbook 取代，保留为人读导出视图（从 Worldbook + MasterOutline 自动生成 markdown）。

### 3.5 角色 + 关系网 + 信息可见性

```
Character
├─ id, name(UNIQUE), aliases[]
├─ pronoun: 他|她|它|祂|TA          ← NOT NULL，agent 写作用，治代词错误（Vol16 97 处根因）
├─ gender: 男|女|无|未知|其他        ← nullable，可空，不能从代词反推
│   CHECK: gender 与 pronoun 逻辑一致（gender=男→pronoun≠她 等）
├─ role, faction_id(FK, nullable)
├─ state: active|dormant|deceased|ascended|merged
├─ abilities[], personality, goals
├─ knowledge_state[]: {fact_id, learned_at_beat, confidence, decay}   ← 结构化，精确时序
├─ state_history → 追加表
├─ pronoun_overrides[]: {from_chapter, pronoun, reason}   ← 极少数代词变更显式留痕（如 T-1 觉醒）
└─ secrets[]: {key, value, visibility}    ← 敏感信息集合，带可见性
    visibility:
    ├─ mode: public | secret_until | faction | characters
    ├─ ref: reveal_chapter | faction_id | [character_id...]
    └─ axis: character_epistemic（角色认知）| reader_disclosure（读者已知）  ← 双轴，防混淆

Relation
├─ id, from_id(FK), to_id(FK), rel_type
├─ valid_from_chapter, valid_to_chapter(nullable)
├─ current_state
└─ evolution → 追加表 [{chapter, rel_type, reason}]
```

**信息可见性注入逻辑**（boot context 过滤）：当前章 + 当前 POV 查 secrets，按 visibility 双轴过滤——只注入"该 POV 角色此刻能认知 + 读者此刻已知"的信息。卧底身份/真实性别在揭露前不进 boot context，agent 看不到自然不泄露。

**已知盲区**（接受，后置 L4 审计）：visibility 只防"agent 读到字段后泄露"，防不了"agent 按剧情推理出秘密"。后者靠 L4 审计抽查。

### 3.6 Event（世界客观事实）—— 补回的实体

Beat（叙事契约）≠ Event（世界事实）。跨卷伏笔/反转作为 Event 独立于叙事结构存在。

```
Event
├─ id, title, detail
├─ chapter（发生章）, volume
├─ event_type: plot|turning|revelation|climax|gap|denouement
├─ is_gap, gap_level
├─ revealed_at_beats[](FK)    ← 在哪些 beat 被揭示（支持多次揭示，非单区间）
├─ involved_characters → 联结表 event_character
├─ causes / caused_by (FK Event)    ← 因果链
└─ timeline_id    ← 可出现在不同 timeline
```

> **Dialogue 不独立成实体**：小说对话嵌在叙述流里，若独立 Dialogue 实体会与 Paragraph 文本形成**多事实源**（Dialogue.content + Paragraph.text 双存对话内容），违背 RC3 消灭双写原则。对话由 Paragraph 承载（段落文本即真相源）；如需结构化分析（speaker/addressee/promises），走**派生提取**（可重建），不独立存储。剧本才适合 Dialogue 独立实体（对话是独立结构单元）。

### 3.7 联结表（替代 JSON 数组 FK，让约束真正生效）

所有原设计的 JSON 数组 FK 改为联结表（对抗校验 F2 修复）：

```
beat_character(beat_id, character_id, role)            ← 替代 beat.participating_characters[]
thread_consumption(thread_id, beat_id, new_status, chapter)  ← 替代 thread.consumed_by[]，悬链单向 SSOT
thread_planting(beat_id, thread_id)                    ← beat.plant_threads（种植声明方）
beat_thread_advance(beat_id, thread_id)                ← beat.advance_threads（派生视图，可从 thread_consumption 反查）
location_neighbor(from_id, to_id, travel_days)
event_character(event_id, character_id)
character_faction(character_id, faction_id, period)    ← 角色归属（可随时间变）
```

### 3.8 灵感池

```
Inspiration
├─ id, content, type: premise|scene|character|theme|mechanic|setting|twist
├─ tags[], source
├─ status: raw|refined|consumed|partial|discarded
├─ consumed_into[]: {target_type, target_id}    ← 消费追溯链
└─ created_at, refined_at, promoted_at（升级进 MasterOutline 的判据）
```

### 3.9 正文存储 + 导出

**SSOT**：Paragraph 挂章节（`chapter_id`），beat 是可选标签（`beat_id`）。content_hash 每段一个（防篡改）。FTS5 全文检索（派生索引）。

**导出（单向：DB → 文件，文件只读）：**
- **章节导出（自动）**：`manuscript/ch{NN}.txt` = 该章 Paragraphs 按 seq 聚合。段落写入/更新时自动重导出。
- **卷导出（手动）**：`manuscript/vol{N}.{txt|md}` = 该卷所有章节聚合 + 卷标题。
- **整书导出（手动）**：`manuscript/full.{md}` = 所有卷 + 标题；epub/pdf 后置（SP6）。
- **单向约束（关键）**：文件**只读，不反向同步**——改正文改 DB（Paragraph），再重新导出；**禁止改文件回写 DB**（防双写漂移 RC3）。导出是派生视图，DB 是唯一真相源。
- **ExportManifest**：记录每次导出的 `{scope: chapter|volume|book, target_id, format, content_hash, status: draft|final|published, exported_at}`——解决"哪版定稿已对外发布"，百万字多卷重排不乱。

### 3.10 机制层实体

```
StyleTemplate（正约束源，从作品提取量化指纹）
├─ id, source_works[], sample_chapters[], extracted_at
├─ sentence_length_dist, sentence_structure_dist, sensory_density
├─ dialogue_ratio, paragraph_length_dist, dash_density, period_density
└─ → 注入 boot context，Edit agent 润色时对准分布

ChapterMetrics（质量遥测，永远 system_recomputed）
├─ chapter_id, computed_at
├─ word_count, sentence_length_stats, grep_metrics{notXisY, dash, period}
├─ sensory_density, dialogue_ratio
├─ threads_consumed, consumption_balance
├─ beat_yield_rate（beat 兑现率：verified/deviated 比）
└─ source: system_recomputed（永不存 agent 自报）
   注：grep_metrics / threads_consumed / consumption_balance / beat_yield_rate 是 SP4 新建
   （现有 inject_chapter_metrics 接口 core_telemetry.py:57-60 只收 word_count/editing_corrections/editing_types）

ChapterRuntime（运行时遥测，主编排+agent 客观采集）
├─ chapter_id, session_id, timestamp, version
├─ agent_invocations[]: {agent_type, start_ts, end_ts, black_wall_ms}   ← 黑墙（主编排采集，可靠）
│   agent_type: chapter_writer | editor | extractor | auditor | volume_reviewer
├─ tool_calls[]: {tool, duration_ms, error, decision}                    ← 黑墙内部，agent 上报
├─ agent_phases[]: {phase, duration_ms}                                  ← 黑墙内部阶段分解
├─ llm_calls[]: {phase, model, prompt_tokens, completion_tokens, duration_ms}  ← token 由工作流层汇报（子代理结束 SDK usage），非 llm.py 内部
└─ totals: {total_black_wall_ms, tool_count, llm_tokens, llm_call_count, editing_rounds}

Amendment（修订留痕，跨实体审计）
├─ id, entity_type, entity_id, chapter
├─ field, old_value, new_value, reason, author(agent|human|system)
└─ created_at（追加，immutable）
```

### 3.11 bitemporal 横切（降级）

- `Beat.story_time` + `timeline_id` 字段**保留**（存数据）。
- **但"时序单调校验 / 多视角平行线不矛盾"是机制层（L2/L4）的语义任务，不是 schema 能力**。schema 只存 story_time（自由文本或结构化，起步自由文本），校验由机制层跑。
- 原因：项目 thesis2 已证伪"重 bitemporal"（单区间丢中间揭示点）；V3 用"轻 bitemporal"（显式存储 + 机制层局部校验），Event.revealed_at_beats[] 支持多次揭示（避免单区间丢失）。

---

## 四、机制层（障碍 2 的落地）

**部署形态**：V3 是 Claude 工作流系统——**Workflow JS（编排）+ Python CLI 工具（SQLite 读写/校验，agent 调用）+ Claude 子代理（ChapterWriter/Edit/VolumeReview）**。agent token 由工作流层在子代理结束时汇报（SDK usage），编排层采集写入遥测。黑墙（agent 运行期）不可实时观察，但**事后汇报**内部活动（token/工具/阶段）——只有 agent 不主动汇报的部分真"黑"。

### 4.1 写作一章的流程

**Agent 架构**（V1 多 agent 回归，非 V2 单体）：ChapterWriter（写初稿）+ Edit agent（L3 独立润色/修复）+ VolumeReview/auditor（L4 卷级）。L2 重算是 **Python 校验函数（非 agent）**。一章典型成本 = 2 LLM agent（Write+Edit）+ 0 LLM 重算 + 卷级 LLM 审计分摊。

```
1. Boot   → DB 查询注入（beat 契约 + 角色可见信息[visibility 过滤] + StyleTemplate 指纹 + constants 硬约束）
2. Write  → ChapterWriter agent 写段落，兑现 beat 契约
3. L2 重算校验（数值/grep/状态机层，纯 Python 零 LLM）→ 见 4.2
4. L3 编辑（LLM，独立 Edit agent）→ 见 4.3
5. L4 审计（卷级，含 LLM 抽查）→ 见 4.4
```

### 4.2 L2 重算校验（数值/grep/状态机层，纯 Python）

L2 严格只做**数据事实重算**（agent 无法博弈的客观量）。语义判断归 L4（见 4.4）。

**纯 Python 层（L2，零 LLM）：**
- **word_count**：从正文 regex 重算（现有 `_count_chinese_chars`，validators.py:345）
- **grep 指标**（notXisY/破折号/句号密度）：固化 regex 重算（**现有代码零实现，SP4 新建**）
- **threads_consumed / consumption_balance**：从 thread_consumption 复算，公式 consumed = resolved×1.0 + advanced×0.5 + partially_resolved×0.5 + abandoned×0.3（abandoned 计 0.3 防批量凑配额；**现有代码零实现，SP4 新建**）
- **悬链状态机迁移**：查 thread_consumption 的状态变化（纯数据事实，agent 声明 advance 但状态没变即 deviated）
- **bigram 级 outline 字面匹配**：key_events 字符串匹配（纯 Python）

agent 自报值进 `*_declared` 列（advisory），重算值进主列（authoritative）；偏差超阈值 → advisory_drift_flag（L4 高亮）。

**语义层（不进 L2 硬门禁，归 L4 LLM 抽查）——这些本质是语义判断，现有代码已用 `call_llm` 桥（core_compliance.py:82-100,343-390）：**
- outline **purpose 对齐 / key_events 语义等价**（bigram 未匹配的兜底）
- **代词指代消解**（"她/他"指代谁，治 Vol16 97 处根因——grep pronoun_lock 够不到跨段指代）
- **角色非具名出场**（grep 名字够不到的指代出场）
- **悬链"剧情上真推进"**（状态机迁移是数据事实，但是否实质推进是语义）

这些 L4 抽查结果只进 advisory，不阻断（硬约束仍纯 Python）。

> **现状澄清（重要）**：现有 `inject_chapter_metrics`（core_telemetry.py:57-60）只接收 word_count/editing_corrections/editing_types，grep/consumed/balance 字段**连注入接口都没有**——§3.10 ChapterMetrics 的这些字段是 **SP4 新建**，不是"V1 机制深化"的既有能力。V1 只有 VolumeReview 独立 grep 抽查的雏形，没有系统化重算层。spec 把 L2 叫"V1 机制深化"是方向性表述，实际工程是新建。

### 4.3 L3 编辑子代理（V2 缺陷修复 + 正约束源落地）

**形态**：独立 Edit agent（V1 回归）+ StyleTemplate 指纹驱动。
- 写作后 Edit agent 跑一轮，基于 StyleTemplate 量化指纹（句长/句式/感官密度分布）做正向润色——对准分布修，不是凭感觉。
- L2 校验失败时，同一 agent 拿 directional_fix_prompt 只改违规段落（不动其他，防 B2 引入新问题）。
- 治"写得不好"（A4/风格/代词）。成本 +1 LLM/章。

**StyleTemplate**：从作品已写部分提取量化分布（替代 V1 的定性 6 维度 style_guides——后者顶不住 LLM 绕过，量化指纹是更强的正约束源）。

### 4.4 L4 审计（卷级）

- **statistical watchdog**：跨章读 ChapterMetrics 分布，识别"贴边走"指纹（70% 章卡阈值 85% 区间 → systematic_threshold_hugging，呼应 Vol17 句号 11/12 章偏高）。触发 → 阻断下一卷 + 推送人工。
- **卷级抽查**：LLM 验证者（独立 prompt，可选强模型）做 outline 合规 / 回收真实性 / 代词指代消解的语义判定——只抽查不每章跑，控成本。语义判定结果只进 advisory，不进 raise 路径（硬约束仍纯 Python）。
- **强制落盘门禁**：review_report 必须存在且非空（治 Vol15 未落盘 bug）；archive_volume_artifacts 用 os.path.exists 验证，失败则 workflow status=failed。
- **跨卷悬链收敛门禁**：dispatch 下一卷前检查 planned_resolve_volume 的悬链是否兑现，未兑现标跨卷欠债。

### 4.5 抗博弈闭环

| 防线 | 防什么 | 机制 |
|---|---|---|
| 结构 | 空字段/外键/枚举 | SQLite NOT NULL/CHECK/FK + 联结表 |
| L2 重算 | 自报数值造假（A1/B3）+ beat 未兑现 | Python 重算覆盖自报 + beat 兑现校验 |
| L3 编辑 | 写得不好（A4/风格/代词） | StyleTemplate 指纹驱动正向润色 + 定向修复 |
| L4 审计 | 语义谎报 + 贴边走 + 跨卷漂移 | watchdog + 抽查 + 强制落盘 |
| 可见性 | 数据提前泄露 | secrets 双轴过滤注入 boot context |

---

## 五、存储选型

**SQLite 单存储**。不用 Neo4j（图查询优势在管线场景用不上，MB 级数据查询毫秒级；依赖重）、不用 JSON 作 SSOT（无 schema 约束 + 双写漂移源）。

- **新建源码项目**：V3 数据结构与业务逻辑大变，**不在 `src/novel_kg/` 基础上改**。新建独立 package（如 `src/bedrock/`），novel_kg 保留作参考实现。
- 关系数据**新建** SQLite schema（不迁移 graph.json；新作品从零建）。
- 复杂查询（多跳关系、faction/location 树）用递归 CTE + 应用层遍历。
- 正文文件 + SQLite 同目录，事务 + 原子写 + FTS5。
- 双写彻底消灭（单一真相源）。

---

## 六、与原声明式设计的差异

| 原 `2026-06-13` 设计 | 本 V3 修正 |
|---|---|
| 自称"声明式工作台新发明" | 定位为 V1→V2→V3 **演进**，V1 机制深化 |
| 7 层架构 L0-L6（含灵感/宪法/POV矩阵/Web编辑器） | 收窄为管线核心；Web 编辑器延后（前期 Claude 问答/VS Code 插件） |
| 把关系网/大纲/世界观/风格当"新组件" | 对齐已有组件名（relations/outline_entries/style_guides 已在 graph.json） |
| （新建设计） | constants / factions / secrets / knowledge_state 结构化、Paragraph / Event / StyleTemplate / Amendment 是**新建实体**（现有 graph.json 无对应），非复用 |
| 灵感池 YAGNI（基于老项目判断） | 保留（面向新作品消费） |
| 世界观 = framework.md（已有） | framework.md 是妥协散文，Worldbook **取代**它 |
| gender_pronone 合并枚举 | pronoun(NOT NULL) + gender(nullable) **拆分** |
| 无信息可见性模型 | secrets + visibility 双轴（character_epistemic / reader_disclosure） |
| bitemporal 作为防漂移支柱 | **降级**为机制层语义校验（thesis2 已证伪重版本） |
| arc 层 | **砍掉**，悬链 thread_type 吸收 |
| JSON 数组 FK | **联结表**（让约束生效） |
| 无 advisory/authoritative 区分 | `*_source` 列 / `_declared` 双字段 |
| 无 Event 实体 | **补回** Event（世界事实 ≠ 叙事契约） |
| 3 处现状数据失实 | 修正（见 1.3） |

---

## 七、SP 分解

| SP | 内容 | 工程量 | 依赖 |
|----|------|--------|------|
| **SP1 数据骨架** | **新建独立 package**（`src/bedrock/`，不改 novel_kg）+ SQLite schema + 全实体（含联结表/advisory列/追加表）+ 新作品从零建 | ~2 周 | 无 |
| **SP2 大纲+悬链+防漂移** | MasterOutline/VolumeOutline/beat 契约 + 悬链状态机 + beat 兑现校验 | ~2 周 | SP1 |
| **SP3 风格指纹+编辑回归** | StyleTemplate 提取 + 独立 Edit agent + 定向修复 | ~1.5 周 | SP1 |
| **SP4 抗博弈管线** | L2 重算前移 + L4 watchdog + 强制落盘 + ChapterMetrics/Runtime 遥测 | ~3 周 | SP1,2,3 |
| **SP5 治理层** | L4 卷级抽查（LLM 验证者）+ 跨卷收敛门禁 | ~2 周 | SP4 |
| **SP6 工具层（延后）** | Web 编辑器 / VS Code 插件 / diff / 导出 | 后置 | SP1-5 |

总计核心管线 SP1-SP5 ~10.5 周。SP6 延后，前期用 Claude 问答/VS Code 插件替代。

---

## 八、待确认（留待各 SP brainstorm）

1. watchdog 阈值（70%/85% 起步值）、抽查频率（每卷几章）
2. StyleTemplate 指纹具体维度（句长/句式/感官/对话/段落，提取方法）
3. beat 兑现校验容差（角色出场 grep 的匹配规则、悬链迁移的严格度）
4. repair_loop 重试上限（pronoun gate 放宽到 5 次，其他 3 次）
5. ~~Dialogue/台词实体~~ **已决**：不独立成实体（多事实源违背 RC3，剧本才需要）；小说对话由 Paragraph 承载，结构化分析走派生提取
6. Event 与 Beat 的引用密度（一个 Event 平均被几个 beat 揭示）
7. amendment 触发条件与审核流程
8. ~~token 采集链路~~ **已明确**：token 由 Claude 工作流层在子代理结束时汇报（SDK usage），V3 在 Workflow JS 编排层采集写入 ChapterRuntime.llm_calls[]。黑墙概念精化：agent 运行期不可实时观察，但事后汇报内部活动，只有不主动汇报的部分真"黑"。

---

## 附录 A：Schema 对抗校验修复清单

两个独立 agent 校验后的修复（已纳入上述 schema）：

- 🔴 补回 **Event** 实体（世界事实 ≠ 叙事契约）
- 🔴 JSON 数组 FK → **联结表**（让 FK 约束生效）
- 🔴 悬链 **单向 SSOT**（thread_consumption 持有，beat_thread_advance 反查）
- 🟡 **advisory/authoritative 区分**（`*_source` 列 / `_declared` 双字段）
- 🟡 visibility 拆 **character_epistemic + reader_disclosure** 双轴
- 🟡 knowledge_state 结构化（{fact_id, learned_at_beat, confidence, decay}）
- 🟡 state_history → **追加表 immutable**（防篡改）
- 🟡 唯一性/CHECK 补全（global_number / (chapter_id,seq) / gender-pronoun 一致 / resolved-resolved_at_beat 一致 / narrative 必挂 beat）
- 🟡 beat deviated 加 **override 逃逸路径**（防卡死管线）
- 🟡 **Amendment** 留痕实体（跨实体审计）
- 🟢 树结构环检测（应用层）、VolumeOutline.status 与 Volume.status 单向派生
- 🟢 bitemporal 降级（schema 只存 story_time，校验归机制层）

---

## 附录 B：与 v3 综合方案（wgjw7h8hq）的对应

v3 综合方案的机制（DI1-DI9 / IVA）被 V3 吸收为机制层，但**降级/精简**：

| v3 机制 | V3 对应 | 调整 |
|---------|---------|------|
| DI1 单一真相源/重算 | L2 重算 + advisory/authoritative | 保留，核心 |
| DI4 提取幂等 | L2 悬链消费复算 | 保留 |
| DI8 detector=gatekeeper | L2 beat 兑现校验 raise | 保留 |
| IVA 三向 grep 比对 | ChapterMetrics 重算 + advisory_drift | 精简（起步不做 raw_stdout 粘贴三向，靠重算+偏差检测） |
| IVA sha256 锁 | content_hash 防篡改 | 保留（轻量） |
| statistical_watchdog | L4 watchdog | 保留 |
| 卷类型矩阵 | Volume.volume_type | 保留 |

砍掉的 v3 重机制（YAGNI/过重）：独立 IVA 子进程 + 独立 API key、raw_stdout 强制粘贴三向比对、pydantic v2 依赖（起步用 SQLite CHECK + 应用层 validator）。
