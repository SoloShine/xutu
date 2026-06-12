# 代理架构演进

## 从 3-agent 到单 agent 的演化

---

## v0: 无代理架构（ch01-ch53）

**流程**: 主编排直接写初稿 → 手动/CLI 提取 → 写入图谱

**问题**:
- 主编排上下文爆炸（每章累计 prompt+正文+JSON）
- 无风格隔离（写作和编辑在同一上下文）
- 无自动化门禁

---

## v1: 3-agent 架构（ch54-ch177）

### 设计（2026-05-27 确立）

```
主编排: dispatch(chN) → WriteAgent(chN) → EditAgent(chN) → ProcessAgent(chN) → 下一章
```

### 各 agent 职责

| Agent | 职责 | context 隔离 |
|-------|------|-------------|
| WriteAgent | 读取 boot context → 写初稿 | 不读前章的 Edit/Process 操作 |
| EditAgent | 读初稿 → 风格审查 → 逐处修改 | 不读图谱数据 |
| ProcessAgent | 提取 JSON → 入图 → 弧线 → 遥测 | 不读写作 prompt |

### 关键事件

- **Vol10 (ch138-ch151)**: Workflow 管线首次整卷实战
  - 44 agents, ~2.88M tokens, ~3.3h
  - 回读: 5 问题 / 4 修复
  - 验证了 3-agent 编排的可行性
  - 发现 Workflow args 传递 bug（见 bug F1）

- **Vol12 (ch164-ch177)**: 
  - 44 agents, ~7.5M tokens, ~8h（tokens 大幅增长）
  - 回读: 23 项问题 / 修复 15 项
  - 15 处代词错误（跨章丢失频率高）

### 问题

1. **tokens 成本高** — 3 agent × 每章 prompt 生成 + context 加载
2. **隔离不完善** — EditAgent 和 ProcessAgent 仍需加载章节正文
3. **上下文浪费** — 每个 agent 独立启动，但 prompt 高度重叠
4. **代词问题持续** — 3 个 agent 各自独立理解角色设定，更容易漂移

---

## v2: 单体 agent 架构（ch178-ch203）

### 设计（2026-06-11）

```
主编排: dispatch(chN) → ChapterAgent(chN: Boot→Write→SelfEdit→Extract→Graph→Telemetry) → 下一章
```

### 关键变化

| 维度 | v1 | v2 |
|------|-----|-----|
| agent/章 | 3 | 1 |
| 编辑方式 | 独立 EditAgent | 自编辑（同一 agent 读完改） |
| 风格约束 | 禁止列表 + ≤N 上限（柔性） | grep 触发改写 + 二元阈值（硬） |
| 悬链管理 | 播种无配额 | 分层消费 + 修剪 |
| 门禁 | 回读修复（事后） | grep 硬循环 + CLI 门禁（事中） |

### 成本对比

| 指标 | v1 (Vol12) | v2 (Vol13) | v2.1 (Vol14) |
|------|-----------|-----------|-------------|
| agent 总数 | 44 | 14 | 16 |
| 总 tokens | ~7.5M | ~3.5M | ~1.9M |
| 分钟/章 | ~34 | ~21.5 | ~12.4 |
| tokens/章 | ~536K | ~292K | ~136K |
| 代词错误 | 15 处 | 3 处 | 1 处 |

**估算节省**: v2.1 vs v1 — tokens 减少 ~75%，时间减少 ~64%，代词错误减少 ~93%。

### 为何单 agent 反而更好？

1. **上下文连续性** — 同一 agent 写完立刻自编辑，对刚写的文本有完整记忆
2. **Prompt 不重叠** — 不用 3 次独立加载 boot context
3. **门禁内嵌** — 写作→grep→修复→再grep 在一个 agent 内完成，不需要跨 agent 通信
4. **角色设定一致** — 写、改、提取都是同一个 agent，不会像 3 个 agent 那样各自理解角色性别

---

## VolumeReview: 跨卷防线

无论 v1 还是 v2，整卷回读校验都在全部章节完成后独立执行。

### v1 VolumeReview（Vol8-12）

流程: 逐章通读 → 发现修复风格/代词/一致性 → 报告

### v2 VolumeReview（Vol13-14）

流程: 逐章通读 + 独立跑 grep（交叉验证）→ 悬链收支表（交叉验证图谱实际状态）→ 问题修复 → 报告

新增: 交叉验证链（独立 grep + 图谱基线对比）

### VolumeReview 发现 vs ChapterAgent 遗漏

| 卷 | ChapterAgent 漏检 | VolumeReview 发现 | 主要类型 |
|-----|-------------------|-------------------|---------|
| Vol13 | grep_after 造假(2章) + consumption 不准(多章) | 全部发现 | A 类作弊 + E 类悬链 |
| Vol14 | grep 全部准确(0 造假) | T-1 代词 1 处 + ch203 破折号 3 处 | 轻微遗漏 |

---

## 数据来源

- review_report_vol{8-14}.md — 每卷修复的代理相关错误数
- memory/vol{10,11,12}_completion.md — v1 管线的 agent 计数/token/时间
- memory/v2-pipeline-design.md — v2 架构设计讨论
- handoff.md — v1/v2 对比表格 + Vol14 实测数据
