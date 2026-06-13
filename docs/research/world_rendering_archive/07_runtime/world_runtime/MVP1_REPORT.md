# MVP1 报告 — reducer 范式反向验证

**日期**: 2026-06-13
**范围**: 世界渲染 runtime MVP1（schemas + event_store + reducer + extractor + 端到端）
**数据源**: 中场景 .output（130 条 NL action，10 tick）
**verdict**: **reducer 范式成立** ✅ —— 纯函数 fold 确定性产出连贯 snapshot，正确捕获中场景演化。

---

## §0. 一句话结论

reducer 范式在真实数据上成立。`reducer(effects, S_t)` 是纯函数 fold，130 个 effect 重 fold 出完全相同的最终 snapshot（replay 一致性 PASS），正确捕获中场景最强涌现（联盟终局"裁决落地接收相"）。effect schema 表达力足够。extractor 语义鸿沟量化为 **16.9% 未落地**（多数 action 落地为状态变化；剩余为观察/见证类无状态变化）——这是真实信号，决定 MVP2 方向。**本次运行 priority 分布干净分离（world_will×10/law_enforcer×10/collective×30/character×80），未产生同优先级平局，unresolved_conflicts=0**；同优先级燃料机制由单测验证（非 runtime 发现）。

---

## §1. 带的问题 + 回答

### Q1：纯函数 reducer 能否确定性产出 snapshot？（机制）
**✅ PASS**

- 130 个 effect（10 tick × ~13 action）重 fold 出完全相同的最终 snapshot
- replay 一致性 PASS：`reducer(effects_log, S_0)` 多次跑出相同 `S_10`
- reducer 是纯函数 fold（deepcopy 隔离 + 确定性 priority 裁决）
- **治"生成式误差累积"**：生成阶段（extractor）有 LLM 随机性，但 effect log 一旦落盘，fold 是确定的。世界冻结后渲染/重放无新误差。这正是 isActive=false 投影的工程基础。

### Q2：effect schema 能否表达中场景关键状态？（表达力）
**✅ PASS**

10 个 snapshot 落盘，连贯反映演化：

| 字段 | 演化 |
|------|------|
| seal_state | intact → weakening（接近 broken，完整 broken 在模拟范围外）|
| han_zheng_status | 波动 → **decided**（共担路径，真自愿锚定，无牺牲）|
| alliance_resolution | 演化为终局 **"裁决落地接收相"**（命运层裁定双方共担路径，联盟 super_head 卸任提交）|
| lu_status | → **investigating**（自主调查封印机制，拒绝共决权）|
| alien_stance | → 全面退场，零接触存在 |
| unresolved_conflicts | **0 个**（priority 分布干净分离，未触发同优先级平局）|

**最强验证**：reducer 正确捕获了中场景报告（§8.2）的最强涌现——联盟终局卸任姿态（集体 super_head 主动放弃释义权/议程框定/背书路径，请求命运层接管）。这不是 prompt 引导的，是从 130 条 NL action fold 出的。说明 reducer + schema 能承载集体作为实体的演化。

7 个预定义字段 + dynamic 涌现都工作（终态 dynamic 含 89 个涌现 key）。**本次运行未产生同优先级冲突**——priority 分布（world_will/law_enforcer/collective/character = 4/3/2/1）干净分离，唯一出现的 `dynamic` 字段冲突在 tick9 被 priority=4 裁决（已裁决，非未裁决）。同优先级"矛盾即燃料"机制由 reducer 单测验证（wolf thesis），但本次真实数据 priority 互不重叠，未在 runtime 触发未裁决保留。

### Q3：extractor 从决策陈述型 action 提取可靠性？（数据局限）
**16.9% 未落地**（22/130 effect 的 set={}）

这是**纯语义鸿沟**（JSON 解析 bug 已 fix，10 tick 全通，仅 2 tick 触发 1 次重试）：

- 少数 action 是观察/见证/陈述类（"记录节点""见证""观望""校验合规"）——本身无状态变化，extractor 正确路由到 set={} + intent 注明"未落地"
- 多数（83.1%）产生实际状态变化
- **这是真实信号**：观察类 action 本就该无状态变化

> 注：未落地比例随 LLM 单次运行的解析激进程度波动（48.5% → 16.9% 跨两次运行）。这本身印证 §3 局限 1"单次 extract 未控制随机性"。reducer 本身确定性，但 effect log 依赖单次 extractor 运行。

鸿沟来源：pilot 的 agent prompt 引导产"决策陈述"（thesis 1 验证用），而非"决策+落地事件"。这接上用户最初的"一脸懵"根因——agent 全是背景/决策陈述。

---

## §2. 判定

**reducer 范式立住**。3 个问题中 Q1/Q2 明确 PASS，Q3 鸿沟量化（16.9%，跨运行 48.5%→16.9% 波动）且性质明确（语义鸿沟非工程 bug）。

→ **进入 MVP2**：判断未落地比例（16.9%–48.5% 跨运行）是否需要重设 agent prompt（决策陈述 → 决策+落地事件）。

---

## §3. 局限（诚实标注）

1. **单次 extract**：LLM 随机性未控制（只跑 1 次）。reducer 本身确定性，但 effect log 依赖单次 extractor 运行。**跨两次运行未落地比例从 48.5% 波动到 16.9%**——直接量化了这个随机性。
2. **snapshot 无 ground truth**：靠人工核中场景已知结局。seal 只到 weakening 未到 broken（必然性未在 10 tick 内完全兑现——可能是 extractor 未捕获"封印破"的最终 effect，或模拟范围本就如此）。
3. **16.9%–48.5% 未落地是鸿沟信号**：MVP2 判断——是接受（观察类 action 本就无状态变化）还是重设 agent prompt（让 action 更"落地"）。
4. **agent_id 不统一**：pilot trace 的 agent_id 乱码（"world_will"/"L3/world_will"/"rule_enforcer"/中英混），导致部分 priority fallback 到 character=1。world_will/law_enforcer 干净（priority 裁决正确），但 collective vs character 的冲突信号可能被误标。
5. **nested dynamic 已修复**：extractor 现在会 unwrap `{"dynamic": {...}}` → 顶层 set（本次运行 0 处嵌套残留）。此前作为 schema 瑕疵存在，现已消除。

---

## §4. 成本

- **开发**：9 task TDD（schemas/event_store/reducer×3/llm/extractor/run_mvp1/报告），26 单测全过
- **运行（实测，来自 events.jsonl 的 12 个 call event）**：
  - 12 次 haiku extractor 调用（10 tick × 1 次 + 2 tick JSON 解析失败触发 1 次重试）
  - **input_tokens: 74,648**（其中 cache_read 46,653，cache_creation 0）
  - **output_tokens: 42,955**
  - reducer 零 LLM
- **可观测性**：telemetry 已 wired——每次 call_llm 自动记录 call event（in/out/tokens/duration/status）到 event store。本次运行记录 12 个 call event（全部 status=ok），可观测性基础就位，成本可从 committed artifact 核验（不再依赖估算）。

---

## §5. 产物

```
docs/research/world_runtime/
├── schemas.py          # Event/Effect/Snapshot/ConflictResolution + PREDEFINED_FIELDS
├── event_store.py      # append-only JSONL + query
├── reducer.py          # 纯函数 fold + priority 裁决 + 同优先级未裁决（22→26 测试）
├── llm.py              # call_llm wrapper（claude.cmd subprocess + telemetry）
├── extractor.py        # NL action → effect（robust JSON 解析 + 重试）
├── run_mvp1.py         # 端到端：extract .output → reduce → 10 snapshot + replay 验证
├── tests/              # 26 单测全过
├── snapshots/          # snap_t0..t9.json（10 个世界状态）
├── events.jsonl        # 130 effect event log（append-only）
└── MVP1_REPORT.md      # 本报告
```

---

## §6. 关键发现（对接研究）

1. **reducer 是"治误差累积"的工程基础**：生成（extractor）有 LLM 随机性，但 fold 确定。世界冻结后可确定性 replay。这验证了 spec §0.3"reducer 纯函数治生成式误差累积"。

2. **snapshot 捕获了集体涌现**：联盟终局"裁决落地接收相"（super_head 主动放弃释义权/议程框定/背书路径，请求命运层接管）被 fold 出——说明 reducer + schema 能承载 thesis 1 的集体作为实体演化，不只是角色状态。

3. **16.9%–48.5% 未落地量化了"决策骨架"问题**：用户最初的"一脸懵"根因（agent 全是背景/决策陈述）现在有了数字——少数到一半 action 不落地为状态变化（比例随单次 LLM 运行波动）。这是 MVP2/agent prompt 重设的依据。

4. **telemetry 已落地（本次运行记录 12 个 call event）**：call_llm wrapper 自动记录每次调用（in/out/tokens/duration/status）到 event store，可观测性基础就位，成本可从 committed artifact 核验。

---

## §7. 下一步

**MVP1 verdict = reducer 范式成立**。MVP2 候选：

- **MVP2（extractor 鸿沟）**：16.9%–48.5% 未落地 → 是接受还是重设 agent prompt？需判断"观察类 action 无状态变化"是否合理，还是 agent 应被引导产"决策+落地事件"。
- **MVP3（记忆召回 O(1)）**：当前 MVP1 用全量 action 喂 extractor（O(N)）。MVP3 改 agent 召回 snapshot slice + K 条相关 event（O(1)），治 O(N²) 膨胀。
- **MVP4（叙事渲染）**：snapshot + event → 可读叙事（治"一脸懵"）。

推荐先 MVP2（extractor 鸿沟是当前最大不确定性，且决定 agent prompt 设计）。

---

## §8. 决策记录

- 2026-06-13: MVP1 plan 写成（9 task TDD）
- 2026-06-13: Task 1-7 完成（schemas/event_store/reducer/llm/extractor，26 单测）
- 2026-06-13: Task 8 端到端首跑——reducer 范式 PASS，但 3/10 tick extractor JSON 失败
- 2026-06-13: extractor JSON robustness fix（正则提取 + 重试）→ 10 tick 全通
- 2026-06-13: **MVP1 verdict = reducer 范式成立**（Q1/Q2 PASS，Q3 鸿沟 48.5% 量化）
- 2026-06-13: **final review 准确性修正**——(1) telemetry wired：extractor 现在把 event_store 传给 call_llm，本次运行记录 12 个 call event（此前为 0，是死代码）；(2) extractor unwrap nested dynamic（`{"dynamic":{...}}` → 顶层 set），本次运行 0 处嵌套残留；(3) llm.py 删硬编码平台路径，改 `shutil.which` 解析（Windows subprocess 不自动搜 PATHEXT）；(4) 报告全部定量声明对齐本次重跑真实数据：unresolved_conflicts 0（非 2，priority 分布干净分离，同优先级燃料机制由单测验证非 runtime 发现）、Q3 16.9%（非 48.5%，跨运行波动 48.5%→16.9%）、§4 成本改实测 token（input 74,648 含 cache_read 46,653 / output 42,955）、§6.4 telemetry "已落地（12 call event）"。核心结论（reducer 范式成立）不变——reviewer 独立验证为真。
