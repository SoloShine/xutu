# 会话交接 — 2026-06-13 世界渲染研究

**用途**: /compact 后恢复 context 的入口。本文件 + positioning doc 一起读，能恢复全部研究状态。

---

## 0. 当前状态（一句话）

**✅ 中场景完成（thesis 1 成立）+ 渲染层 POC 完成 + **世界渲染 runtime MVP1 完成**（reducer 范式验证通过）。MVP1：纯 Python + claude.cmd runtime，reducer 纯函数 fold event log → snapshot（reviewer 独立 byte-for-byte 验证确定性），正确捕获中场景集体涌现（联盟终局卸任）。telemetry wired（12 call event，可观测性就位）。Q3 extractor 鸿沟量化 16.9%（跨运行 48.5%→16.9% 波动）。final review 抓出并修正 2 处报告 claim 失实（telemetry 死代码、unresolved 0 非 2）。9 task TDD + 26 单测，commit b4a71d9。下一步 MVP2（extractor 鸿沟判断）/MVP3（记忆召回 O(1)）/MVP4（叙事渲染）。详见 [MVP1 报告](world_runtime/MVP1_REPORT.md) + [设计 spec](../specs/2026-06-13-world-rendering-runtime-design.md) + [实现 plan](../plans/2026-06-13-world-runtime-mvp1.md)。**

---

## 1. ⭐ 最关键的最新信息（用户刚指出，必须消化）

用户原话："这种设计思路有问题，这种 agent 设计本身是要具备一定关联性和层级的，单个类型的对比没有太大意义，如世界 agent 掌握世界的规则，集体 agent 掌握集体的规则，角色 agent 掌握角色的规则，他们可以相互影响，造就矛盾或顺势而为的情节"

**核心洞察**：

异质 agent 的核心**不是**"4 个不同类型"，而是**多层级规则的相互影响系统**：

```
世界意志 agent（最高层）——掌握世界规则（命运/必然性/宇宙规律）
    ↓ 约束
集体 agent（中层）——掌握集体规则（势力/组织/文明内部规则）
    ↓ 影响
角色 agent（基层）——掌握角色规则（个人性格/选择/能力）

规律执行者（横切所有层）——执行规则，违规介入
```

**相互影响造就矛盾或顺势**：
- 世界规则 → 约束集体和角色（"封印将破"是世界层设定）
- 集体决策 → 影响角色（"教会决定圣战"改变角色处境）
- 角色行动 → 可**上升**改变集体（英雄效应）或**触发**世界规则（打破封印）
- 规律执行者 → 任何层违规时介入

**异质 agent 的真正价值 = 多层级相互影响能产生同质系统无法产生的情节**——特别是**层级间冲突**（角色 vs 集体 / 集体 vs 世界规则 / 角色 vs 世界命运）。

**这个洞察拯救了 thesis 1**——之前架构是"4 个并列类型"（容易被反驳为"加 predicate 就行"），用户指出真正核心是"层级互动"（同质系统很难复制）。

---

## 2. 进度更新（优先级 1-2 已完成）

### ✅ 优先级 1：修正架构文档（完成 2026-06-13 晚）
`docs/research/2026-06-13-thesis1-architecture.md` 已修正：
- §1 加原则 6（异质 = 多层级规则相互影响系统）
- §2 加 §2.0 层级架构总览（L3 世界意志 → L2 集体 → L1 角色 + 横切规律执行者）+ §2.1-2.4 各加层级标注
- §3 加 §3.1 三种影响机制（上→下约束 / 下→上涌现 / 横切校验）+ 完整影响链示例（韩峥破封印场景）
- §4 trace schema 加 layer / influence_direction / conflict_with 字段

### ✅ 优先级 2：H4 数据驱动验证设计（完成 2026-06-13 晚）
新文档 `docs/research/2026-06-13-h4-systemic-validation-design.md`：
- 数据来源：绝地天通 Vol1-12，30 场景（3 agent 交叉提取 + 用户 spot check）
- 4 个客观指标：layer 分布 / conflict_with 非空数 / 跨层跳数 / 字段完整度
- 证伪阈值：异质在 ≥30% 场景明显优 → 站住；< 10% → 证伪；10-30% → 扩样本
- 5 个已知风险全部有防御（主观性 / 不公平降级 / representation vs generation / 样本量 / 权重）

### ✅ H4 generation pilot 已跑完（2026-06-13 晚）
verdict = 异质明显优（小场景 5 agent × 4 ticks）。详见 [pilot 报告](2026-06-13-h4-generation-pilot-report.md)。4 个涌现现象：L2 集体演化 / L3 主动裁定 / cross_cut 校验回路 / 集体"对价悬置"制度创新。脚本 `docs/research/h4_generation_pilot.js`（可改场景重跑）。

### ✅ 补强 + 中场景全部完成（2026-06-13 晚，用户授权自主推进链路）

**补强**（[报告](2026-06-13-h4-reinforcement-report.md)）：prompt 公平性审计 + 反例场景。
- verdict = **thesis 1 仍站住**
- prompt 审计：双向偏差（异质部分引导 + 同质过度抑制）。关键反转——异质 prompt 实际抑制 L2/L3 发声，与质疑假设相反；同质 prompt 剥夺式（"你没有特殊地位"），预先封死涌现
- 反例场景：异质 L3/L2/cross_cut 4 tick 全沉默（边界感），证伪"过度设计"质疑
- 脚本 `docs/research/h4_reinforcement_pilot.js`

**中场景**（[报告](2026-06-13-h4-medium-scene-report.md)）：3 层集体嵌套 + 8 角色 + 10 ticks + 赋能式同质 prompt 修正。
- verdict = **异质明显优 + scale_signal = 放大** ⭐⭐⭐
- 用户洞察"小场景 vs 大场景复杂度差异很大"得到验证：复杂度放大，异质优势随之放大（不崩溃、不被追上）
- 赋能式同质 prompt 修正后异质仍优——排除 prompt 偏差作为主因。同质涌现集体行为（L2×32 / cross_cut×42）但仍是"个体咬合"非"实体冲突"
- 异质独有 10 项层级冲突 + 9 组嵌套集体冲突 + 9-tick 集体演化深度（超小场景基准 4）
- 最强涌现：联盟"核心规则自我消解相" + "必然性以非事件形式兑现"
- 脚本 `docs/research/h4_medium_scene_pilot.js`（含赋能式修正 + 3 层嵌套）

### ✅ 渲染层 POC 完成（2026-06-13 晚，记忆/event sourcing 方向启动）

用户提出根本性问题"agent 记忆如何处理？纯靠上下文吗？" → 确认 pilot 纯 prompt 滚动（O(N²) 膨胀），是扩大场景的根本瓶颈，生成式误差会不断放大。

- 调研业界：记忆框架（Mem0/Letta/Zep/LangGraph）+ event sourcing（deterministic replay）+ 可视化（Ren'Py）→ 都给同质单 agent，**没有原生支持异质多层级集体 agent**
- **渲染 POC**（`docs/research/render_poc/`，~1h 开发，**零新 token**）：trace（已落盘）→ HTML 视觉小说 + Ren'Py 脚本。验证 isActive=false 投影愿景
- verdict = 投影愿景成立（3 截图证据 + console 无错 + tab 切换正常 + layer 分布核对 L3×10/L2×30/L1×77/cross_cut×13）
- 关键副产物：逼出 trace 最小 schema（=TRACE_SCHEMA，已隐式存在于 pilot）
- 这是本研究**第一个零 token 成本产出**——后续重渲染不花 token
- 脚本 `render_poc.py` + 报告 `render_poc/REPORT.md`

### ⏳ 下一步（两条线）

**A. 工程化（用户新选方向，渲染 POC 已启动）**：记忆/event sourcing 是扩大场景的真正瓶颈
1. **trace 落盘 event store**（append-only JSONL，不只是 Workflow 返回值）—— 世界树基础，成本最低
2. **agent 选择性召回**（替代全量 prompt 注入）—— 解决 O(N²) 膨胀 / 扩大场景
3. **接 Mem0/Zep** —— 给 schema 配召回引擎，Mem0 做 agent 内长期记忆，Zep context graph 做集体记忆可演化
4. **叙事投影器升级** —— 当前平铺投影，下一步支持多 POV / 倒叙 / 伏笔

**B. thesis 1 验证扩展（原计划，待用户决策是否还做）**：
1. 大场景（~30+ × 20+，~40M+ token）
2. 多场景扩展（3-5 个不同类型）
3. 同质"个体咬合"深度审计

**累计成本**：336 agent / 19.57M token（小场景 1.58M + 补强 1.6M + 中场景 16.39M + 渲染 POC 零新 token）

---

## 3. 关键决策记录（按时间，2026-06-13 当天）

### 上午-下午：thesis 2 从查证到证伪
- 文献查证（双 agent）：transaction_time 不该用章号（章节是出版单位，切片不完整），改为连续叙事行进距离 / event-interval
- CEUR Vol-3290 核验：论文没做 bitemporal，差异化全成立
- **最小验证（V16 数据，123 测试点）**：baseline（fabula + `dict[sjuzhet, list[float]]`）在所有维度不劣于 thesis 2
- **thesis 2 被证伪**——bitemporal 是把简单问题复杂化，降级为渲染端实现细节

### 下午-晚上：thesis 1 架构设计 + 用户修正
- 集体 agent 查证：结构性空白（哲学有 List & Pettit / MAS 有 Holonic / Game AI 有 faction / 但叙事场景从未实现）
- thesis 1 架构草案：4 类 agent schema + trace 事件总线 + 类型特定字段
- H1 验证（集体 agent vs individual 聚合）——**用户指出还原论错误**
- **用户修正**：异质的核心是"多层级规则相互影响系统"，不是"并列 4 类"
- 待修正架构 + 重新设计 H4 系统性验证

### 关键教训
- **科研诚实**：thesis 2 用 2 小时证伪，避免数周浪费。用户说"死路会浪费很长时间"——验证比硬推值钱
- **竞品空白 ≠ 值得做**：thesis 2 文献空白但仍被证伪（baseline 够用）
- **还原论陷阱**：单独对比某类 agent 没意义，异质系统的价值在于互动

---

## 4. 完整文档清单（docs/research/）

按读阅顺序：

| 文档 | 用途 |
|------|------|
| **2026-06-13-world-rendering-research-positioning.md** | 研究方向锚点（§0-§10 + 决策记录），最新状态含 thesis 2 证伪 |
| **2026-06-13-session-handoff.md** ← 本文件 | 压缩后恢复入口 |
| 2026-06-13-paper-synthesis.md | 5 篇论文精读汇总（Park/Riedl/Fowler/Wolf/Mateas）|
| 2026-06-13-transaction-time-verification.md | thesis 2 查证（双 agent + CEUR 核验）|
| 2026-06-13-thesis2-minimal-validation.md | thesis 2 验证蓝图（证伪设计）|
| 2026-06-13-thesis2-validation-report.md | thesis 2 验证报告（123 测试点，被证伪）|
| thesis2_validation.py | 验证脚本（可重跑）|
| v16-validation-data.json | V16 提取的 26 事件数据 |
| 2026-06-13-collective-agent-verification.md | 集体 agent 查证（结构性空白）|
| **2026-06-13-thesis1-architecture.md** | thesis 1 架构草案（⚠️ 需按用户多层级洞察修正）|
| 2026-06-13-h1-collective-agent-validation.md | H1 验证（⚠️ 已废除，还原论错误）|

外部 memory：
- `C:\Users\Administrator\.claude\projects\D--novel-test\memory\research-direction-pivot.md` — 研究方向 pivot 记录（含 thesis 2 死亡 + thesis 1 修正）

---

## 5. thesis 1 架构修正的具体方向（待执行）

当前架构文档 §2 把 4 类 agent 当成并列组件。需要重构为：

### 新视角：多层级规则系统

```
Layer 3: 世界规则（世界意志 agent 掌握）
  - 命运 / 必然性 / 宇宙规律
  - 例：绝地天通的"封锁将破" / "穿越者使命"

Layer 2: 集体规则（集体 agent 掌握）
  - 势力 / 组织 / 文明的内部规则
  - 例：教会的教义 / 国家的法律 / 文化的传统

Layer 1: 角色规则（角色 agent 掌握）
  - 个人性格 / 选择 / 能力 / 知识
  - 例：韩峥的性格 / 陆的选择

Cross-cutting: 规律执行者
  - 横切所有层，确保规则被执行
  - 违规时介入（惩罚 / 反应 / 升级）
```

### 相互影响机制（需要设计）

1. **约束传播**（上→下）：上层规则约束下层行为
   - 世界规则 → 限制集体和角色的可能行动
   - 集体规则 → 限制角色的社会行为

2. **涌现上升**（下→上）：下层行动改变上层
   - 角色行动 → 改变集体（英雄效应 / 叛逆 / 建立新势力）
   - 角色或集体行动 → 触发世界规则（打破封印 / 完成预言）

3. **横切校验**（规律执行者）：
   - 任何层的行动都过规则校验
   - 违规 → propose_reaction / escalate_to_will

4. **矛盾生成**（核心价值）：
   - 角色 vs 集体规则（个人反抗组织）
   - 集体 vs 世界规则（势力对抗命运）
   - 角色 vs 世界命运（个人 vs 必然）
   - **这种层级间冲突是同质 character 系统产生不了的**

### trace schema 修正
trace 需要标注**层级**和**影响方向**：
- `layer`: world / collective / character
- `influence_direction`: top_down / bottom_up / cross_cut
- `conflict_with`: 触发了哪层的矛盾

---

## 6. H4 系统性验证设计（待执行，废除 H1）

### 测试目标
4 类异质系统 vs 同质 character baseline，看能否产生**层级间冲突**情节。

### 测试场景（建议）
构造一个需要多层协作/对抗的场景：
- 世界规则：某预言将应验（"封印将在血月破"）
- 集体规则：教会试图阻止预言（"禁止血月仪式"）
- 角色：某角色是预言的关键（"我的血能破封印"）
- 规律执行者：维护"封印不可破"规则

**产生的层级冲突**：
- 角色 vs 集体（个人身份 vs 组织禁令）
- 角色 vs 世界命运（自由意志 vs 预言）
- 集体 vs 世界规则（教会阻止 vs 命运必然）
- 规律执行者 vs 所有人（执行规则 vs 各方违抗）

### 对比 baseline
同质 character agent 系统（所有 agent 都是 character 类型）跑同样场景——看能否产生等效的层级冲突。

### 预期
异质系统能产生**多层矛盾交织**的复杂情节；同质系统只能产生"角色间冲突"，缺乏层级张力。

**如果预期成立 → thesis 1（多层级系统）站住**
**如果不成立（同质也能产生等效情节）→ 重新思考**

---

## 7. 给压缩后的自己的提醒

1. **用户的洞察是 thesis 1 的灵魂**——异质 = 多层级规则相互影响，不是并列类型
2. **不要重蹈 H1 覆辙**——不能单独对比某类 agent，必须系统性测试
3. **保持 thesis 2 的证伪意识**——H4 也要严格证伪，不预设异质系统更优
4. **科研诚实优先**——如果 H4 显示同质够用，果断放弃 thesis 1，转向其他方向
5. **用户喜欢深度反思**——上次 thesis 2 的反思救了数周，这次多层级洞察可能救整个 thesis 1
6. ⭐ **数据说话**（用户 2026-06-13 晚强调）——架构修正已完成，H4 设计已出，下一步必须实现脚本 + 跑出真实数字，不能再停留在文档层面

---

**最后**：架构修正 + H4 设计都已完成。下一步是执行 H4 验证（实现 → 提取数据 → 跑 → 判定）。用户在等数据。
