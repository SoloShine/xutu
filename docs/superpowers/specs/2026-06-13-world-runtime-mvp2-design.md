# 世界渲染 Runtime MVP2 设计 — 稳定性 + 意图/事件分层

**日期**: 2026-06-13
**状态**: 设计已确认（用户定调"减少不确定性，增加约束和分层"），待写实现计划
**关联**: MVP1 spec（`2026-06-13-world-rendering-runtime-design.md`）/ MVP1 报告（`docs/research/world_runtime/MVP1_REPORT.md`）

---

## §0. 目标

减少 extractor 不确定性（治 MVP1 跨运行波动）+ 显式分层意图/事件（为 MVP4 叙事铺路）。

用户定调：**"目的是要减少不确定性，增加约束和分层是合适的"**。

---

## §1. 背景（MVP1 发现的两个问题）

MVP1 验证 reducer 范式成立，但暴露：

1. **extractor 跨运行波动**（48.5%→16.9%）——同一 .output，两次 extract 出不同 effect log。reducer 确定性 fold，但 effect log 本身随机。"世界冻结/确定性 replay"只在 effect 落盘**之后**成立，**生成 effect 的过程不稳定**。这比鸿沟大小更优先（不稳定则连测量都不可信）。

2. **鸿沟揭示意图层/事件层混淆**——16.9%-48.5% 未落地的 action 是"决策陈述/观望/见证"（意图层），本身无状态变化。extractor 试图用一次翻译把意图层和事件层合并，必然有鸿沟（意图和事件不一一对应）。鸿沟不是 bug，是两层没分离的症状。

**技术前提已验证**：`claude --json-schema` 存在且工作（实测返回 `structured_output` 字段，constrained decoding 解码层强制 schema）。这使稳定性方案可行。

---

## §2. 设计决策（3 个）

| # | 决策 | 解决 |
|---|------|------|
| 1 | **--json-schema constrained decoding** | extractor 输出被 schema 强制，消除自由 JSON 波动（治跨运行不稳定）|
| 2 | **grounded 显式分层** | Effect 加 `grounded: bool`，agent 显式标注"是否落地"。意图层（grounded=false）vs 事件层（grounded=true）分离 |
| 3 | **reducer 只 fold grounded=true** | grounded=false 进 event store（**意图层保留，MVP4 叙事当角色内心/集体立场**）但不 fold snapshot |

**为什么不"消除鸿沟"**：消除=重设 agent prompt 让它产"决策+落地事件"，风险是抑制 thesis 1 验证过的层级冲突涌现（agent 忙着落地，不再深层表态/观望/对质）。改为**分离两层**——意图层和事件层都保留，各司其职。

---

## §3. 改动（4 处）

### 3.1 call_llm 加 schema 支持
- 加 `response_schema: dict | None` 参数 → 传 `--json-schema`
- 当 schema 给定时，返回 `structured_output` 字段（schema 合规对象），不解析自由 `result`
- 不给 schema 时保持 MVP1 行为（向后兼容）

### 3.2 Effect schema 加字段（含 MVP1 reviewer I1）
- `grounded: bool`（意图/事件分离载体，默认 True）
- `agent_id: str` / `agent_type: str`（追溯来源——MVP2 per-agent 分析鸿沟需要）

### 3.3 extractor 用 schema
- 定义 effect 的 JSON schema（含 grounded/agent_id/set/unset/intent）
- 用 call_llm 的 response_schema 参数 → constrained decoding
- 消除 markdown 清理/重试逻辑（schema 强制，不再需要）——保留为兜底

### 3.4 reducer 只 fold grounded=true
- `grounded=false`：进 event store（意图层保留），**不 fold** snapshot
- `grounded=true`：fold snapshot（事件层）

---

## §4. Effect schema（修订）

```python
@dataclass(frozen=True)
class Effect:
    agent_id: str = ""
    agent_type: str = "character"
    set: dict[str, Any] = field(default_factory=dict)
    unset: list[str] = field(default_factory=list)
    intent: str = ""
    grounded: bool = True       # True=事件层(fold) / False=意图层(保留不fold)
    priority: int = 1
```

**注意**：agent_id/agent_type 加在前面（有默认值，向后兼容现有 Effect 构造）。

---

## §5. 验证（MVP2 带的问题）

| Q | 方法 | 判定标准 |
|---|------|---------|
| **Q1 稳定性** | --json-schema 后跑 3 次 extract，比对 effect log | 跨运行波动消除（48.5%→16.9% 那种消失，3 次 effect log 一致或高度一致）|
| **Q2 分层** | 看 grounded 分布 + 意图层/事件层是否清晰 | grounded=false 的 intent 是否真是"观望/见证/陈述"类；grounded=true 的 set 是否真有状态变化 |

---

## §6. MVP1 遗留（顺带做）

- **I1**：Effect 加 agent_id/agent_type（§3.2 已含）——reviewer 说 MVP2 per-agent 分析必需
- **S1**：mocked integration test——mock call_llm 返回 canned effect（schema 合规），锁 extract→reduce→snapshot 契约，不依赖真 LLM/临时 .output。reviewer 说最高价值（把脆弱的 run_mvp1 脚本跑变成可重复的契约测试）

---

## §7. 风险与缓解

| 风险 | 缓解 |
|------|------|
| haiku + --json-schema 未实测（MVP1 实测 opus）| MVP2 Task 2 先验证 haiku+schema（像 MVP1 Task 6 验证 claude.cmd）|
| grounded 是 agent 判断可能不准（误标）| 但比 extractor 事后猜好（显式 > 隐式）；Q2 验证分布合理性 |
| reducer 只 fold grounded 改变 MVP1 fold 行为 | 重跑确认 snapshot 合理性（seal/集体决议仍连贯）|
| --json-schema 的 num_turns=2（internal tool turn）可能成本略增 | 实测成本；haiku 仍便宜 |

---

## §8. 下一步

spec 确认 → writing-plans 出 MVP2 实现计划（预计 6 task：Effect schema / call_llm schema / extractor schema / reducer fold grounded / integration test / 稳定性验证+报告）→ subagent 执行。
