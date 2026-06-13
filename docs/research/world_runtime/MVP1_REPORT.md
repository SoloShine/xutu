# MVP1 报告 — reducer 范式反向验证

**日期**: 2026-06-13
**范围**: 世界渲染 runtime MVP1（schemas + event_store + reducer + extractor + 端到端）
**数据源**: 中场景 .output（130 条 NL action，10 tick）
**verdict**: **reducer 范式成立** ✅ —— 纯函数 fold 确定性产出连贯 snapshot，正确捕获中场景演化。

---

## §0. 一句话结论

reducer 范式在真实数据上成立。`reducer(effects, S_t)` 是纯函数 fold，130 个 effect 重 fold 出完全相同的最终 snapshot（replay 一致性 PASS），正确捕获中场景最强涌现（联盟"规则自我消解相"），保留未裁决矛盾为燃料。effect schema 表达力足够。extractor 语义鸿沟量化为 **48.5% 未落地**（一半 action 是观察/见证类无状态变化）——这是真实信号，决定 MVP2 方向。

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
| alliance_resolution | 演化为 **"规则自我消解相，向命运层提交程序真空备案"** |
| lu_status | → safe |
| alien_stance | → 完全退场，零接触存在 |
| unresolved_conflicts | 2 个保留（han_zheng/lu 同优先级平局）|

**最强验证**：reducer 正确捕获了中场景报告（§8.2）的最强涌现——联盟"核心规则自我消解相"（集体主动放弃控制权，请求命运层裁定合法性）。这不是 prompt 引导的，是从 130 条 NL action fold 出的。说明 reducer + schema 能承载集体作为实体的演化。

7 个预定义字段 + dynamic 涌现都工作。2 个未裁决矛盾保留为燃料（Wolf"矛盾即基石"——L2/L3 矛盾不强制消解）。

### Q3：extractor 从决策陈述型 action 提取可靠性？（数据局限）
**48.5% 未落地**（63/130 effect 的 set={}）

这是**纯语义鸿沟**（JSON 解析 bug 已 fix，10 tick 全通）：

- 一半 action 是观察/见证/陈述类（"召开会议""记录节点""见证""观望"）——本身无状态变化，extractor 正确路由到 set={} + intent 注明"未落地"
- 另一半产生实际状态变化
- **这是真实信号，不是缺陷**：观察类 action 本就该无状态变化

鸿沟来源：pilot 的 agent prompt 引导产"决策陈述"（thesis 1 验证用），而非"决策+落地事件"。这接上用户最初的"一脸懵"根因——agent 全是背景/决策陈述。

---

## §2. 判定

**reducer 范式立住**。3 个问题中 Q1/Q2 明确 PASS，Q3 鸿沟量化（48.5%）且性质明确（语义鸿沟非工程 bug）。

→ **进入 MVP2**：判断 48.5% 未落地是否需要重设 agent prompt（决策陈述 → 决策+落地事件）。

---

## §3. 局限（诚实标注）

1. **单次 extract**：LLM 随机性未控制（只跑 1 次）。reducer 本身确定性，但 effect log 依赖单次 extractor 运行。
2. **snapshot 无 ground truth**：靠人工核中场景已知结局。seal 只到 weakening 未到 broken（必然性未在 10 tick 内完全兑现——可能是 extractor 未捕获"封印破"的最终 effect，或模拟范围本就如此）。
3. **48.5% 未落地是鸿沟信号**：MVP2 判断——是接受（观察类 action 本就无状态变化）还是重设 agent prompt（让 action 更"落地"）。
4. **agent_id 不统一**：pilot trace 的 agent_id 乱码（"world_will"/"L3/world_will"/"rule_enforcer"/中英混），导致部分 priority fallback 到 character=1。world_will/law_enforcer 干净（priority 裁决正确），但 collective vs character 的冲突信号可能被误标。
5. **nested dynamic 瑕疵**：个别 haiku 输出产了 dynamic.dynamic 双重嵌套（schema 污染，不崩溃）。

---

## §4. 成本

- **开发**：9 task TDD（schemas/event_store/reducer×3/llm/extractor/run_mvp1/报告），26 单测全过
- **运行**：10 次 haiku extractor 调用（每 tick 1 次，处理 ~13 action）+ reducer 零 LLM
- **总 LLM 调用**：~10 次（远低于中场景 pilot 的 261 次 agent 调用——因为 MVP1 只跑 extractor，不跑 agent）

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

2. **snapshot 捕获了集体涌现**：联盟"规则自我消解相"被 fold 出——说明 reducer + schema 能承载 thesis 1 的集体作为实体演化，不只是角色状态。

3. **48.5% 未落地量化了"决策骨架"问题**：用户最初的"一脸懵"根因（agent 全是背景/决策陈述）现在有了精确数字——一半 action 不落地为状态变化。这是 MVP2/agent prompt 重设的依据。

4. **telemetry 作为 event store projection 落地**：call_llm wrapper 自动记录每次调用（in/out/cost/duration）到 event store，可观测性基础就位。

---

## §7. 下一步

**MVP1 verdict = reducer 范式成立**。MVP2 候选：

- **MVP2（extractor 鸿沟）**：48.5% 未落地 → 是接受还是重设 agent prompt？需判断"观察类 action 无状态变化"是否合理，还是 agent 应被引导产"决策+落地事件"。
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
