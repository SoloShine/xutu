# thesis 1 架构设计 — 异质 agent（4 类）

**日期**: 2026-06-13
**状态**: 架构草案，含证伪路径设计
**核心**: 4 类 agent（人物 / 世界意志 / 规律执行者 / 集体），重点设计集体 agent（最强原创）
**教训应用**: 带着 thesis 2 教训——设计时保持证伪意识，不预设每类 agent 都必要

---

## §1. 设计原则

1. **每类 agent 有明确独特性**——不能被其他类 + predicate 替代（否则砍掉）
2. **基于现有原型扩展**——不重新发明（Park/Mateas/Holonic/List&Pettit）
3. **集体 agent 重点设计**——最强差异化点，借鉴 Holonic MAS + List & Pettit 三条件
4. **通信走 trace 事件总线**——不直接 RPC（Mateas 的 story memory 弱通信原则）
5. **每类 agent 留不同性质的 trace**——这是"异质"的表层体现
6. ⭐ **异质 = 多层级规则相互影响系统**（用户 2026-06-13 洞察，本架构的灵魂）

   异质的真正核心**不是**"4 个不同类型的 agent"，而是 4 类 agent 占据**不同层级**，通过三种影响方向（上→下约束 / 下→上涌现 / 横切校验）相互作用的系统：
   - L3 世界意志 → 世界规则（命运 / 必然性 / 宇宙规律）
   - L2 集体 → 集体规则（势力 / 组织 / 文明内部规则）
   - L1 角色 → 角色规则（个人性格 / 选择 / 能力 / 知识）
   - 横切 规律执行者 → 执行规则，违规介入

   **异质的真正价值在层级间冲突**（角色 vs 集体 / 集体 vs 世界命运 / 角色 vs 必然）——这是同质 character 系统产生不了的。详见 §2.0 层级总览 + §3.1 三种影响机制。

---

## §2. 4 类 agent 精确定义（多层级架构）

### 2.0 ⭐ 层级架构总览（异质的核心）

异质 agent **不是**"4 个并列类型"，而是**多层级规则的相互影响系统**：

```
Layer 3: 世界意志 agent —— 世界规则（命运 / 必然性 / 宇宙规律）
    ↓ 约束（top_down）
Layer 2: 集体 agent —— 集体规则（势力 / 组织 / 文明内部规则）
    ↓ 影响（top_down）
Layer 1: 角色 agent —— 角色规则（个人性格 / 选择 / 能力 / 知识）

Cross-cutting: 规律执行者 —— 横切所有层，违规介入
```

**三种影响方向**（异质系统的核心动力学，§3.1 详细机制）：

| 方向 | 机制 | 例子 |
|------|------|------|
| 上→下约束（top_down） | 上层规则限制下层行为 | 世界规则"封锁将破" → 约束集体和角色的可能行动；集体规则"教义禁止" → 约束角色的个人选择 |
| 下→上涌现（bottom_up） | 下层行动累积触发上层变化 | 角色英雄效应 → 改变集体决策；角色或集体行动 → 触发世界规则（破封印 / 应预言） |
| 横切校验（cross_cut） | 规律执行者介入 | 任何层违规 → 规律执行者 propose_reaction / escalate_to_will |

**异质 agent 的真正价值 = 层级间冲突情节**（同质 character 系统产生不了的）：

- 角色 vs 集体规则（个人反抗组织："韩峥拒绝执行穿越者网络的指令"）
- 集体 vs 世界规则（势力对抗命运："教会试图阻止预言应验"）
- 角色 vs 世界命运（个人 vs 必然："陆的选择能否违背封锁必然性"）
- 任意层 vs 规律执行者（违抗规则："集体决策违反世界规则，规律执行者介入"）

下面 §2.1-§2.4 逐类给出 schema，每类标注其在层级中的位置。

---

### 2.1 人物 agent（Character）— **L1 基层**

**基础**：Park 2023 memory/reflection/planning + Riedl frame of commitment。

```python
@dataclass
class CharacterAgent:
    agent_id: str
    agent_type: Literal["character"] = "character"

    # 内部状态（Park）
    memory_stream: MemoryStream  # observation/reflection/plan + importance + recency
    planning_engine: PlanningEngine  # day→hour→5-15min 递归

    # 目的（Riedl frame of commitment）
    internal_goal: Proposition  # 角色自己的目的（≠ author goal）
    current_frame: FrameOfCommitment | None  # 当前意图区间

    # 约束
    personality: Personality
    knowledge_boundary: set[Fact]  # agent 知道什么（POV 限制）
```

**独特性**：有 intentionality（Riedl），有 memory/reflection/planning（Park），目的是个人的。
**痕迹**：个人状态变化 / 关系变化 / 对话 / 决策。

### 2.2 世界意志 agent（WorldWill / DramaManager）— **L3 最高层**

**基础**：Mateas drama manager，**升级为"有目的推动者"**（Mateas 是无目的平衡器）。

```python
@dataclass
class WorldWillAgent:
    agent_id: str
    agent_type: Literal["world_will"] = "world_will"

    # 升级点 1：目的 predicates（Mateas 没有）
    purpose_predicates: list[Predicate]  # "韩峥牺牲"等终止条件
    desired_value_arcs: dict[str, PiecewiseLinearArc]  # 多条悬念线 arc

    # Mateas 标准
    beat_pool: list[Beat]  # beat schema 7 字段
    story_memory: WorkingMemory  # trace 存储

    # 升级点 2：目的压力注入 + 世界冻结（Mateas 没有）
    purpose_pressure_threshold: float
```

**独特性**：不追求个人目的，推动叙事走向"目的已实现"的终态。**与 character 的根本差异**：character 是 emergent（自己长出 goal），world_will 是 deliberative（持 author goal）。
**痕迹**：beat 选择 / value arc 调整 / purpose pressure 注入 / freeze_world 事件。

### 2.3 规律执行者 agent（LawEnforcer）— **横切 cross-cutting**

**基础**：Facade 的 reaction context，**升级为独立 agent**（Facade 嵌入 beat 内）。

```python
@dataclass
class LawEnforcerAgent:
    agent_id: str
    agent_type: Literal["law_enforcer"] = "law_enforcer"

    # Facade 标准
    rule_contexts: dict[ContextID, list[Rule]]  # 上下文相关规则（beat 激活）
    active_contexts: set[ContextID]

    # 升级点：跨 beat 长期规则（Facade 没有）
    cross_beat_rules: list[Rule]  # "韩峥不能说自己是穿越者"等长期约束

    # 违规记录
    violation_log: list[Violation]
```

**独特性**：不发起行动，只对事件反应；维护规则；横切所有层（包括 world_will 和 collective）。**与 character 的差异**：没有 intentionality，没有目的，只执行规则。**与 world_will 的差异**：不推动叙事，只维护约束。
**痕迹**：规则触发 / 违规惩罚 / 约束校验结果（ok/violated/layer）。

### 2.4 集体 agent（Collective / Faction）★ 重点 — **L2 中层**

**基础**：Holonic MAS（Gerber 1999 super-holon）+ List & Pettit 三条件 + Searle collective intentionality。

```python
@dataclass
class CollectiveAgent:
    agent_id: str  # 如 "教会"、"罗马帝国"、"穿越者网络"
    agent_type: Literal["collective"] = "collective"

    # === Holonic 结构（Gerber 1999）===
    super_head: AgentRef  # 代表成员（发言人/决策者，可轮换）
    members: list[AgentRef]  # 成员（character 或 sub-collective，递归）

    # === List & Pettit 三条件（group agency 形式定义）===
    representation: CollectiveRepresentation  # 集体如何对外表达（徽记/名号/法统）
    collective_attitude: CollectiveAttitude  # 集体 belief + desire（独立于成员）
    collective_action: CollectiveActionLog  # 集体行动历史

    # === 决策聚合（核心机制）===
    aggregation_function: AggregationFunction
    # 类型：vote（投票）/ weighted（加权）/ consensus（共识）/ threshold（阈值）
    # Searle 1990：集体意图 ≠ 成员意图之和

    # === 集体记忆（原创：独立 belief store）===
    collective_memory: CollectiveBeliefStore
    # 关键：不依赖单个成员。主教死亡，教会的"百年誓言"仍在
    # 区别于 Project Sid：他们的"文明记忆"是 N 个 agent 记忆的统计涌现

    # === 集体目的 ===
    collective_goal: Proposition  # 集体生存/扩张/演化/传教

    # === 成员可替换性 ===
    persistence_policy: PersistencePolicy  # 成员离开/死亡的处理
```

**集体 agent 的独特 trace**（区别于个人行动）：
- `decree`（法令）——集体决策的正式记录
- `tax_record`（税册）——集体资源流动
- `monument`（纪念碑）——集体记忆的物质化
- `diplomatic_note`（外交照会）——集体间交互
- `policy_change`（政策变迁）——集体态度演化
- `membership_change`（成员变动）——加入/退出/驱逐

**独特性**：
1. **不可还原性**（Searle）：集体决策 ≠ 成员决策之和
2. **独立记忆**：collective_memory 不依赖成员
3. **成员可替换性**：集体 persistence 不依赖单成员
4. **内外双视角**（Hindriks status account）：内部成员怎么看 vs 外部 agent 怎么对待

**与 character 的根本差异**：character 是 single entity with personal goal；collective 是 emergent entity with aggregated goal，但有独立记忆和 persistence。

---

## §3. 通信协议（trace 事件总线）

**原则**（Mateas 弱通信）：所有跨 agent 通信通过 trace，不直接 RPC。

```
┌─────────────────────────────────────────────────┐
│  trace 事件总线（世界级共享）                      │
│  所有 agent 读写同一 trace 流                     │
└─────────────────────────────────────────────────┘
       ↑ 写                    ↑ 读              ↑ 横切
       │                       │                 │
┌──────┴──────┐         ┌──────┴──────┐   ┌──────┴──────┐
│ WorldWill   │         │ Character   │   │ LawEnforcer │
│ 发布 beat   │ ←读——   │ 感知 + 行动 │   │ 校验所有    │
│ 意图        │         │ 留个人 trace│   │ trace       │
└─────────────┘         └─────────────┘   └─────────────┘
       ↑ 写                                    ↑ 校验
       │                                       │
┌──────┴──────────────────────────────────────┴──────┐
│  Collective（集体决策 → 写 collective trace）        │
│  super_head 表达 / 成员通过 aggregation 聚合         │
└─────────────────────────────────────────────────────┘
```

**规则**：
1. 上层（world_will）不调用下层（character），只发布意图（写 trace）
2. 下层 sensor 拉取意图，自主决定如何响应
3. law_enforcer 横切所有层（包括 collective 决策也要过规则）
4. collective 通过 super_head 写 collective trace（不是 N 个成员各自写）
5. world_will 发出 freeze_world 事件时，所有 agent 停止 active behavior

---

### 3.1 ⭐ 三种影响机制（异质系统动力学的核心）

§3 的事件总线是**通信载体**。本节定义**通信内容如何产生层级影响**——三种影响机制。

#### 上→下约束（top_down）

上层 agent 把规则写成 trace，下层 agent 在决策前 sensor 读取作为约束。

```python
# L3 世界意志写世界规则 trace
world_will_trace = Trace(
    agent_type="world_will",
    layer="L3",
    influence_direction="top_down",
    state_delta={"rule": "封锁将在血月破", "constraint_on": ["L2:教会", "L1:韩峥"]}
)

# L1 角色决策前 sensor 读取上层约束
constraints = trace_bus.query(
    receiver=self.agent_id,
    layer_in=["L2", "L3"],
    influence_direction="top_down",
    valid_time_lte=self.current_time
)
# 韩峥的 planning_engine 把 constraints 作为硬约束加入决策空间
```

#### 下→上涌现（bottom_up）

下层 agent 的行动累积到阈值，触发上层 agent 的状态变化或决策。

```python
# L1 角色行动 trace 标注可上升的影响
character_trace = Trace(
    agent_type="character",
    layer="L1",
    influence_direction="bottom_up",
    state_delta={"action": "韩峥揭示穿越者身份", "may_escalate_to": ["L2:穿越者网络", "L3:世界规则"]}
)

# L2 集体的 sensor 监测下层累积
collective.sensor.check_escalation(
    layer_below="L1",
    accumulation_predicate="穿越者身份暴露事件 >= 3"
)
# 达阈值 → 触发集体决策（如"穿越者网络召开紧急会议"）
```

#### 横切校验（cross_cut）

任何 agent 写 trace 后，law_enforcer 自动读取并校验，违规则 propose_reaction。

```python
# 事件总线写入 hook：任何 trace 写入后触发
def on_trace_written(trace: Trace):
    violations = law_enforcer.check(trace)
    if violations:
        law_enforcer.propose_reaction(
            violate_trace=trace,
            reaction_type=violations[0].reaction,  # punish / warn / escalate_to_will
            target_layer=trace.layer
        )
        # 规律执行者写自己的 cross_cut trace
        law_enforcer.write_trace(
            layer="cross_cut",
            influence_direction="cross_cut",
            conflict_with=[f"{trace.layer}:{trace.agent_id}"]
        )
```

#### 三种机制的协作（一个完整的影响链例子）

```
场景：韩峥（L1 角色）决定打破封印

1. [L3 top_down] 世界意志早已写 trace："封印将破是必然"（约束已下发）
2. [L2 top_down] 穿越者网络决策："阻止韩峥"（集体指令下发）
3. [L1]      韩峥 planning：个人目标 "保护陆" vs 集体指令 "阻止" → 冲突
4. [L1]      韩峥选择打破封印 → 写 character_trace（influence_direction=bottom_up, may_escalate_to L3）
5. [cross_cut] 规律执行者检测：韩峥行动违反"封印不可主动破"规则 → propose_reaction
6. [L3 bottom_up] 世界意志 sensor：封印破事件触发 → 推进 purpose_predicate "封印已破"
7. [L2 bottom_up] 穿越者网络 sensor：韩峥叛逆累积 → 召开审判
```

**这三种机制是异质系统能产生"层级间冲突"情节的工程基础**——没有它们，4 类 agent 就只是"4 个独立组件"，不是"相互影响的系统"。H4 验证（§6）会专门测试这三种机制能否涌现出层级冲突。

---

## §4. trace schema（每类 agent 不同）

**注意**：不用 bitemporal（thesis 2 已证伪）。valid_time 是故事内时间，sjuzhet 由渲染端处理（`dict[sjuzhet, list[float]]` predicate）。

```python
@dataclass
class Trace:
    trace_id: str
    agent_id: str
    agent_type: Literal["character", "world_will", "law_enforcer", "collective"]

    # ⭐ 层级标注（异质的核心，§2.0 / §3.1）
    layer: Literal["L1", "L2", "L3", "cross_cut"]
    # character=L1（角色规则）/ collective=L2（集体规则）
    # world_will=L3（世界规则）/ law_enforcer=cross_cut（横切）

    influence_direction: Literal["top_down", "bottom_up", "cross_cut", "peer"]
    # 这条 trace 如何影响其他层（§3.1 三种机制）
    # top_down: 上层约束下层 / bottom_up: 下层涌现上升 / cross_cut: 横切校验 / peer: 同层交互

    conflict_with: list[str] | None  # 这条 trace 触发了哪层的矛盾
    # 如 ["L2:教会规则"] / ["L3:封印必然性"] / ["L1:韩峥个人目标"] / None（无冲突）
    # H4 验证的核心指标：conflict_with 非空的 trace 数量

    # 时间（单轴，故事内）
    valid_time: float  # fabula time

    # 状态增量（delta 风格，Fowler 教训）
    action_type: str
    state_delta: StateDelta

    # 约束校验（law_enforcer 写入）
    constraint_check: ConstraintResult  # {ok, violated, layer: L1/L2/L3}

    # 链式完整性（防 Park memory hacking）
    prev_hash: str
    hash: str

    # === 类型特定字段（异质的核心）===
    character_fields: CharacterTraceFields | None
    # {dialogue, decision, location_change, relationship_change}

    world_will_fields: WorldWillTraceFields | None
    # {beat_selected, value_arc_update, purpose_pressure, freeze_event}

    law_enforcer_fields: LawEnforcerTraceFields | None
    # {rule_id, violation_detail, reaction_proposed, escalation}

    collective_fields: CollectiveTraceFields | None
    # {decree, tax_record, monument, diplomatic_note, policy_change,
    #  aggregation_result, super_head_id, member_votes}
```

---

## §5. 与现有工作差异化

| 现有工作 | 它们怎么做 | 我们差异 |
|---------|-----------|---------|
| **Park Smallville** | 25 个同质 character agent | 4 类异质 agent；集体 agent 独立；world_will 有目的 |
| **Mateas Facade** | drama manager + 2 character + player（3 类）；drama manager 无目的 | 4 类；world_will 有 purpose_predicates + freeze_world；law_enforcer 独立 |
| **Project Sid** | 1000 individual agent 涌现 civilization | 集体作为单一 agent（Holonic super-holon） |
| **Holonic MAS** | 制造业/调度场景的 super-holon | 叙事/世界模拟场景的 collective agent |
| **List & Pettit** | 哲学论证（无计算实现） | 计算实现（aggregation_function + collective_memory） |
| **Game AI faction** | state machine，给玩家体验 | agent，有 collective_attitude + 目的，为叙事 |

---

## §6. ⭐ 证伪路径设计（H4 系统性测试）— thesis 1 的核心 claim

**核心问题**：4 类异质 agent 系统 vs 同质 character baseline，能否产生**同质系统产生不了的层级间冲突情节**？

### ⚠️ 为什么废除原 H1（还原论错误）

原 §6 设计的是 H1：把"集体 agent"单独抽出来对比"individual 聚合"。用户 2026-06-13 指出这是**还原论错误**：

> "这种 agent 设计本身是要具备一定关联性和层级的，单个类型的对比没有太大意义"

单独抽出一类 agent 对比，就像**评估心脏不看循环系统**——异质的核心是**多层级相互影响**，必须把整个系统放在一起测试。H1 的手动场景对比（4 维度主观评估）已归档至 `2026-06-13-h1-collective-agent-validation.md`，仅作历史参考。

### H4 测试目标

不是"某一类 agent 是否必要"，而是"**多层级系统能否产生同质系统产生不了的情节**"。

### 数据来源（学 thesis 2，用真实数据，非手动构造）

从绝地天通已写章节（Vol1-12，~80万字）提取 N 个"层级冲突"场景，结构化标注：

- **角色 vs 集体规则**（如"韩峥拒绝执行穿越者网络指令"）
- **集体 vs 世界规则**（如"教会试图阻止预言应验"）
- **角色 vs 世界命运**（如"陆的选择 vs 封锁必然性"）
- **任意层 vs 规律执行者**（如"违规介入"）

每个场景标注：涉及的 layer、冲突在哪两层、影响链路（top_down / bottom_up / cross_cut）、conflict_with 内容。

### 对比方案

| 方案 | 建模方式 |
|------|---------|
| **A（异质系统）** | 4 类 agent（L3/L2/L1 + 横切）+ §3.1 三种影响机制 |
| **B（同质 baseline）** | 全部 character agent + 任意 predicate（最宽松标准，学 thesis 2 给 baseline 满级装备） |

### 客观指标（可量化，学 thesis 2 的 123 测试点模式）

| 指标 | 异质系统预期 | 同质 baseline 预期 | 判定意义 |
|------|------------|------------------|---------|
| **trace layer 分布** | 4 种 layer（L1/L2/L3/cross_cut）都有 | 只有 L1 | baseline 无法表达多层 |
| **conflict_with 非空 trace 数** | 高（层级冲突显式标注） | 0 或需手工标注 | baseline 无此概念 |
| **影响链长度**（L3→L2→L1 跳数） | 多层链路可追溯 | 只有 L1 内部，无跨层 | baseline 无跨层动力学 |
| **场景字段完整度** | 每个冲突场景的 layer/conflict_with/influence_direction 都能填 | layer 字段填不了 | baseline 表达力缺口 |

### 证伪判定（严格，学 thesis 2 的科研诚实）

- 如果同质 baseline 在所有场景的指标等效异质系统 → **thesis 1 过度设计，砍掉**
- 如果异质系统在 ≥30% 场景上明显优（冲突被表达 vs 丢失）→ **thesis 1 站住**
- **不预设异质系统更优**——如果数据说同质够用，果断放弃（学 thesis 2 的 2 小时证伪避免数周浪费）

### 详细设计

完整的数据提取规范、查询接口、测试脚本设计 → `docs/research/2026-06-13-h4-systemic-validation-design.md`

---

## §7. 待验证假设（重排，H4 为核心）

⚠️ 原假设列表把 H4 放最后，但 H4 才是 thesis 1 的核心 claim。重排后 H4 优先，H1 已废除。

| 优先级 | 假设 | 验证方式 | 状态 |
|--------|------|---------|------|
| ⭐⭐⭐ | **H4: 多层级异质系统产生同质 character 系统产生不了的层级冲突情节** | §6 数据驱动测试（绝地天通场景 + 客观指标） | **待验证（最关键）** |
| ⭐⭐ | H2: world_will 的 purpose_predicates 比 drama manager 的 value arc 更有表达力 | 写一章对比 Mateas 风格 vs purpose-driven | 待验证 |
| ⭐ | H3: law_enforcer 独立 agent 比 constraint check 函数更有价值 | 对比：独立 agent 留 trace + 可 escalate vs 函数调用 | 待验证（风险低） |
| ❌ | ~~H1: 集体 agent 决策 ≠ individual 聚合~~ | ~~§6 场景测试~~ | **已废除（还原论错误）** |

**H4 通过 → thesis 1 站住，继续推进 H2/H3**
**H4 失败 → thesis 1 不成立，回到 drawing board（学 thesis 2 的诚实）**

---

## §8. 下一步

1. ⭐ **设计 H4 数据驱动验证**（Task 27）→ `2026-06-13-h4-systemic-validation-design.md`
2. ⭐ **实现 H4 测试脚本**（学 thesis 2 的 thesis2_validation.py 模式）
3. **跑 H4 验证**（绝地天通场景数据 + 客观指标对比）
4. 根据数据决定 thesis 1 命运
5. （H4 通过后）工程基础：声明式工作台 SQLite/FastAPI 作为 agent 运行环境；trace schema 落地

---

## §9. 决策记录

- **2026-06-13**: thesis 1 架构草案完成。4 类 agent + trace 事件总线 + 类型特定 trace 字段
- **2026-06-13**: 集体 agent 借鉴 Holonic MAS + List & Pettit 三条件 + Searle collective intentionality
- **2026-06-13**: 不用 bitemporal（thesis 2 已证伪），sjuzhet 由渲染端 predicate 处理
- **2026-06-13**: 识别 4 个待验证假设（H1-H4）
- **2026-06-13 晚**: ⭐ **架构修正——用户给出多层级洞察**：异质 = 多层级规则相互影响系统（非"4 个并列类型"）。§1 加原则 6、§2 加层级总览 §2.0、§3 加三种影响机制 §3.1、§4 trace schema 加 layer/influence_direction/conflict_with 字段
- **2026-06-13 晚**: ⭐ **H1 废除**（还原论错误），证伪路径改为 H4 系统性测试。原 H1 归档至 `2026-06-13-h1-collective-agent-validation.md`
- **2026-06-13 晚**: 假设重排，H4 提升为 thesis 1 核心 claim。H4 数据驱动验证设计待出（Task 27）
