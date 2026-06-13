# thesis 2 最小验证设计 — 证伪实验蓝图

**日期**: 2026-06-13
**任务**: 设计严格证伪实验，判断 thesis 2（bitemporal fabula/sjuzhet）是否必要
**状态**: 蓝图完成，待选执行方式
**前置决策**: 用户选"不确定，验证中看"——同时测单 sjuzhet + 多 sjuzhet，让数据说话

---

## §1. 验证目标

**证伪 thesis 2**——不预设结论。如果 fabula+predicate（baseline）能解决 thesis 2 想解决的问题，thesis 2 是过度设计，应放弃。

**核心精神**：竞品空白 ≠ 值得做。必要性必须用数据证明。

---

## §2. 测试用例：V16（ch216-227）

**为什么选 V16**：
- 已完成小说，fabula 已确定（可提取）
- 8+ POV 多视角（拾/舟/韩峥/陆/灰衣/T-1/古神/建造者）——天然的"多视角"测试场景
- 12 章 ~3.9 万字——规模适中（不会太大，也不会太简单）
- 多 POV 章节是构造"不同 sjuzhet"的天然素材

---

## §3. 实验设计（6 阶段）

### 阶段 1：提取 V16 fabula
- 读取 V16 12 章正文（`projects/juedi_tiantong_v1/output/ch216-227_generated.txt`）
- 提取核心事件集（目标 ~20-30 个事件）
- 每个事件标注：
  - `event_id`
  - `valid_time`（故事内时间）
  - `involved_agents`（哪些 agent 参与）
  - `event_type`（action / reveal / decision / ...）
  - `description`（一句话描述）

### 阶段 2：构造 2 个 sjuzhet
- **sjuzhet A（原序）**：V16 原小说的叙事序（ch216→ch227）
- **sjuzhet B（POV 重组）**：按 POV 分组重排（如所有韩峥视角事件集中在前，所有陆视角事件集中在后）
- 每个 sjuzhet 标注每个事件的揭示位置

### 阶段 3：实现两种方案

**方案 1（baseline：fabula + predicate）**：
```python
@dataclass
class Event:
    event_id: str
    valid_time: TimeInterval
    involved_agents: list[str]
    # sjuzhet-specific（每个 sjuzhet 一组 predicate）
    revealed_at: dict[str, float]      # {"sjuzhet_A": 0.45, "sjuzhet_B": 0.12}
    visible_to: list[str]              # 哪些 agent 知道此事件
```

**方案 2（thesis 2：bitemporal trace）**：
```python
@dataclass
class Trace:
    event_id: str
    valid_time: TimeInterval
    # bitemporal：每个 sjuzhet 一个 transaction_time
    transaction_time: dict[str, TimeInterval]  # {"sjuzhet_A": (0.40, 0.50), "sjuzhet_B": (0.10, 0.15)}
    revealed_to: dict[str, list[str]]          # 每个 sjuzhet 中哪些 agent 已知
```

### 阶段 4：跑 Killer Query

**单 sjuzhet 查询**：
- Q1: 在 sjuzhet A 的叙事点 K（如 ch220 对应位置 0.4），韩峥知道什么？
- Q2: 在 sjuzhet B 的叙事点 K'（如 0.3），韩峥知道什么？

**多 sjuzhet 查询**：
- Q3: sjuzhet A 和 sjuzhet B 在某叙事点对韩峥的 belief 差异是什么？
- Q4: 加 sjuzhet C（如倒叙版）后，重跑 Q1-Q3。

### 阶段 5：评估指标

| 指标 | baseline（predicate） | thesis 2（bitemporal） |
|------|----------------------|----------------------|
| **表达力** | 能表达 Q1-Q4 吗？ | 能表达 Q1-Q4 吗？ |
| **实现复杂度** | LOC / schema 字段数 | LOC / schema 字段数 |
| **查询自然度** | as-of 查询直观吗？ | as-of 查询直观吗？ |
| **扩展性**（加 sjuzhet C） | 加一列 revealed_at_C | 加一列 transaction_time_C |
| **一致性维护** | 修改 fabula 时 sjuzhet 稳吗？ | 修改 fabula 时 sjuzhet 稳吗？ |

### 阶段 6：证伪判定

- **baseline 在所有指标 ≤ thesis 2** → **thesis 2 过度设计，放弃**
- **thesis 2 在多 sjuzhet 扩展性明显优** → thesis 2 有价值，但仅限多 sjuzhet 场景
- **两者基本等价** → predicate 是更简单选择，thesis 2 不必要

---

## §4. 预期结果（诚实）

**单 sjuzhet**：两者表达力等价，baseline（predicate）更简单（少一层 dict）。**thesis 2 在单 sjuzhet 无优势**。

**多 sjuzhet（N=2）**：可能等价——baseline 加列 revealed_at_B vs thesis 2 加列 transaction_time_B。**结构上同构**。

**核心赌注：扩展性（N=3, 4, ...）**
- baseline：每个新 sjuzhet 加一列 revealed_at_X
- thesis 2：每个新 sjuzhet 加一列 transaction_time_X
- **如果两者扩展方式同构，thesis 2 真的不必要**

**潜在的真实差异（如果有的话）**：
- thesis 2 的 transaction_time 是**区间**（TimeInterval），baseline 的 revealed_at 可能是**点**——区间能表达"事件在多章中逐步揭示"，点不能
- 这是 Chatman 的 "repeating frequency" 场景——同一 fabula 事件在多章反复暗示

**所以验证的关键测试**：**repeating frequency 场景**——同一事件在 sjuzhet 中多区间揭示。如果 baseline 的 revealed_at（点）无法优雅表达，thesis 2 的 transaction_time（区间）有真实优势。

---

## §5. 验证后的分支决策

### 如果 thesis 2 被证伪（baseline ≤ thesis 2）
- **放弃 thesis 2**——省下大量工程时间
- 转向 thesis 1（异质 agent 架构）—— 这是更确定的工程创新
- bitemporal 降级为"渲染端实现细节"，不作为研究 thesis

### 如果 thesis 2 部分证实（仅在 repeating frequency 场景优）
- **降级 thesis 2**——从"核心理论贡献"降为"特定场景的工程优化"
- 核心研究焦点转向 thesis 1
- bitemporal 作为 trace schema 的可选字段（repeating frequency 时用区间）

### 如果 thesis 2 全面证实（多 sjuzhet 扩展性明显优）
- **推进 thesis 2**——有实证支持
- 设计 trace 完整 schema（D）
- 实现多渲染端原型

---

## §6. 执行方式选项

### 方式 A：手动执行（最可控但慢）
- 我读 V16 12 章
- 手动提取 20-30 事件
- 手动建两种 schema
- 手动跑 query 对比
- **优点**：完全可控，理解深
- **缺点**：12 章 ~3.9 万字，手动提取耗时

### 方式 B：派 agent 执行（快但可能粗糙）
- 派 agent 读 V16 + 提取事件 + 实现两种 schema + 跑 query
- **优点**：快
- **缺点**：agent 可能对 schema 细节理解不够，需要多轮修正

### 方式 C：半自动（推荐）
- 我设计两种 schema 的精确数据结构 + 测试 query
- 派 agent 读 V16 + 提取事件 + 填入两种 schema
- 我（或派 agent）跑 query 对比 + 出验证报告
- **优点**：平衡可控性和效率
- **缺点**：需要两步

---

## §7. 关键设计决定（执行前确认）

1. **事件数量**：目标 20-30 个核心事件（覆盖 V16 主要情节，不过度细化）
2. **sjuzhet B 的构造**：按 POV 重组（所有韩峥视角事件在前，所有陆视角在后...）——还是用其他重组方式（如倒叙）？
3. **repeating frequency 测试**：是否构造一个"同一事件多区间揭示"的场景？（这是 thesis 2 唯一可能的真实优势点）
4. **评估的主观性**：查询自然度 / 一致性维护是主观指标，怎么客观化？（建议：用代码 LOC + schema 字段数做代理）

---

## §8. 决策记录

- **2026-06-13**: 验证蓝图设计完成。核心精神是证伪——不预设 thesis 2 有价值。
- **2026-06-13**: 用户选"验证中看"——同时测单 sjuzhet + 多 sjuzhet，让数据说话。
- **2026-06-13**: 关键测试点确认——repeating frequency 场景（同一事件多区间揭示）是 thesis 2 唯一可能的真实优势点。其他场景 baseline 可能等价。
