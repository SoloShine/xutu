# 世界渲染 Runtime 设计（World Rendering Runtime）

**日期**: 2026-06-13
**状态**: 设计已确认，待写实现计划
**作者**: brainstorming 共创（用户 + Claude）
**关联**: `docs/research/2026-06-13-thesis1-architecture.md`（异质 agent 架构）/ `docs/research/render_poc/REPORT.md`（渲染层 POC）/ `docs/research/2026-06-13-paper-synthesis.md`（5 篇论文输入）

---

## §0. 目标与背景

### 0.1 目标

把当前 pilot 的"决策骨架"升级为"可观测世界"。当前 pilot（小/中场景）只产出 agent 的决策陈述（NL action 流），存在 4 个根因性缺陷：

1. **O(N²) token 膨胀**：每个 agent 看全量 trace，prompt 随 tick 线性增长（中场景 16.4M token）
2. **没有世界状态**：只有事件流（"发生什么决策"），没有 snapshot（"世界现在什么状态"）→ 无法 pause/inspect/branch（世界树无基础）
3. **决策骨架无事件**：trace 全是背景/决策陈述，决策不落地为实际状态变化
4. **渲染平铺**：13 条 trace 按序列出，无叙事编织 → 看完"一脸懵"

本 runtime 补齐记忆召回 + 事件落地 + 世界状态 + 叙事编织 + 可观测性 5 个缺失维度。

### 0.2 不做什么（YAGNI）

- **不做 bitemporal / transaction_time 叙事化**（thesis 2 已证伪，降级为渲染端实现细节）
- **不做完整世界树 DAG**（branch/merge/cherry-pick）——只做 snapshot 落盘（pause/inspect 基础），branch 留待后续
- **不做 Neo4j 后端**——event store 用 JSONL 文件（零依赖），与现有 novel_kg JSON 后端一致
- **不接入 Langfuse**（列为可选增强，MVP 用自建 dashboard）

### 0.3 核心原则

- **数据说话 / 带着目的验证**：每个 MVP 带一个能被数据回答的问题，回答不了就标注局限（thesis 2 证伪意识延续）
- **event store 是单一真相源**：telemetry / renderer / dashboard 都是它的只读 projection（Fowler read-model）
- **reducer 纯函数**：确定性，可单测，可确定性 replay（治"生成式误差累积"）

---

## §1. 设计决策（6 个，已确认）

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 设计范围 | 全局蓝图 + MVP 切片 | 全局对齐避免盲人摸象，但按切片实现验证（不一次做完）|
| 2 | 状态真相源 | 独立 reducer/engine | 程序化 fold event log 重建 snapshot；确定性 replay；世界树基础 |
| 3 | effect 生成 | NL action + effect 提取器 | 保留 thesis 1 验证过的 NL 决策表达 + agent 自由度；reducer 纯程序化 fold |
| 4 | 记忆召回 | snapshot + 相关 event | prompt 大小恒定（治 O(N²)）；集体记忆库独立可演化 |
| 5 | 运行宿主 | 纯 Python + claude.cmd subprocess | 单一宿主无协作问题；复用 Claude Code 认证/计费，不配 API；reducer 可单测 |
| 6 | 可观测性 | telemetry 作 event store projection + 自建 HTML dashboard | 不引入第二套数据；领域特有可视化（snapshot 演化）现成工具覆盖不了 |

---

## §2. 架构总览

### 2.1 六层架构

```
┌─────────────────────────────────────────────────────────┐
│  纯 Python runtime（单一宿主）                            │
│                                                          │
│  ┌─ 决策层 ──────────────────────────────────────────┐  │
│  │  Agent × N  →  NL action  （claude.cmd subprocess）│  │
│  └───────────────────────────────────────────────────┘  │
│  ┌─ 提取层 ──────────────────────────────────────────┐  │
│  │  EffectExtractor ×1/tick → effect[] （claude.cmd） │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌─ 状态层 ──────────────────────────────────────────┐  │
│  │  Reducer（纯函数）：fold(effects, S_t) → S_{t+1}   │  │
│  │  EventStore（append-only JSONL）                    │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌─ 记忆层 ──────────────────────────────────────────┐  │
│  │  Recall：snapshot slice + K 条相关 event           │  │
│  │  MemoryStore：agent 记忆库 + 集体记忆库（可演化写回）│  │
│  └───────────────────────────────────────────────────┘  │
│  ┌─ 渲染层（isActive=false projection）──────────────┐  │
│  │  Renderer：snapshot + events + POV → 叙事          │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌─ 可观测性层（projection）─────────────────────────┐  │
│  │  Telemetry：所有调用 in/out/cost/duration → event  │  │
│  │  Dashboard：世界状态演化/调用甘特/冲突裁决（HTML）  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 2.2 每 tick 数据流

```
tick 开始（输入 snapshot S_t）
  │
  ├─ 1. 记忆召回（每个 agent）
  │     snapshot_slice + recalled_events = Recall(agent_id, S_t)
  │     → prompt 大小恒定
  │
  ├─ 2. agent 决策（concurrent subprocess）
  │     NL_action_i = Agent_i(snapshot_slice_i, recalled_events_i)
  │     → 每个 agent 一次 claude.cmd 调用，telemetry 自动记录
  │
  ├─ 3. effect 提取（1 次 LLM/tick）
  │     effects = EffectExtractor(all_actions, S_t, 世界规则)
  │     → NL action → 结构化 effect[]
  │
  ├─ 4. reducer fold（纯函数，零 LLM）
  │     S_{t+1}, conflict_resolutions = Reducer(effects, S_t)
  │     → 按 priority 裁决冲突 effect
  │
  └─ 5. 落盘
        EventStore.append(ActionEvent + EffectEvent + StateDeltaEvent)
        Snapshot S_{t+1} → snapshots/snap_t{t+1}.json
        MemoryStore 写回（重要 event + agent 自述 + 集体涌现规则）
tick 结束
```

### 2.3 world_will / law_enforcer 在 reducer 范式下的定位

它们**仍是 agent**（产 NL action → effect），保持 thesis 1 的异质层级冲突。区别在 reducer fold 时给它们的 effect **更高 priority**（必然性不可违背、违规必须介入）。这样既保留异质层级冲突（thesis 1），又有 reducer 裁决冲突 effect（状态真相源）。

---

## §3. 核心数据结构

### 3.1 Event（event log 单元，append-only）

```python
@dataclass(frozen=True)
class Event:
    event_id: str              # 全局唯一（tick + seq）
    tick: int                  # 世界时钟步
    event_type: Literal[
        "action",              # agent NL 决策
        "effect",              # extractor 提取的结构化增量
        "state_delta",         # reducer 产出的 snapshot diff
        "conflict_resolution", # reducer 裁决记录
        "call",                # LLM 调用 telemetry（in/out/cost/duration）
        "memory_write",        # 记忆库写回
    ]
    agent_id: str | None
    agent_type: Literal["character","collective","world_will","law_enforcer"] | None
    layer: Literal["L1","L2","L3","cross_cut"] | None
    payload: dict              # 类型特定内容（见下）
    timestamp: str             # ISO 时间戳（物理，仅 telemetry 用）
```

各 event_type 的 payload：
- `action`: `{nl_action: str}`
- `effect`: `{effect: Effect}`
- `state_delta`: `{diff: {set: {...}, unset: [...]}, from_snap: str, to_snap: str}`
- `conflict_resolution`: `{conflicting_effects: [...], winner: str, reason: str, unresolved: bool}`
- `call`: `{prompt: str, output: str, duration_ms: int, tokens: {in, out}, cost_estimate: float, model: str, status: str}`
- `memory_write`: `{entry: MemoryEntry, owner: {...}}`

### 3.2 Effect（delta 风格，Fowler 教训）

```python
@dataclass(frozen=True)
class Effect:
    set: dict                  # {seal_state: "broken", 韩峥_status: "alive", 联盟决议: "容器化"}
    unset: list                # ["some_obsolete_key"]
    intent: str                # 意图摘要（给渲染层用，不参与 fold）
    priority: int              # world_will=4 > law_enforcer=3 > collective=2 > character=1
```

**原则**（Fowler）：effect 必须 delta 风格而非 absolute，否则 reversal 退化为完全重建。

### 3.3 Snapshot（WorldState，混合状态空间）

```python
@dataclass
class Snapshot:
    tick: int
    # 预定义关键状态（reducer schema 声明，强类型）
    seal_state: str            # "intact" | "weakening" | "broken"
    韩峥_status: str           # "alive" | "sacrificed" | ...
    陆_status: str
    小队决议: str
    网络决议: str
    联盟决议: str
    异族立场: str
    # 动态涌现（agent set 新 key 自动加入，弱类型）
    dynamic: dict
```

**混合策略**：封印/韩峥生死等关键叙事状态预定义（强类型，reducer schema 校验）；细节状态动态涌现（agent 第一次 set 新 key 加入 dynamic）。预定义状态覆盖中场景报告里的核心演化（命运层裁决相/立约修正案等映射到这些字段）。

### 3.4 MemoryEntry（Park 风格 + 集体独立）

```python
@dataclass
class MemoryEntry:
    entry_id: str
    content: str
    importance: int            # 1-10，LLM 评分
    embedding: list[float]     # 召回用（relevance）
    owner: dict                # {type: "agent"|"collective", id: str}
    created_tick: int
    last_access_tick: int      # recency 计算
    evidence_ptrs: list[str]   # 指向 source event_id（防 memory hacking）
```

**集体记忆独立**：`owner.type == "collective"` 的记忆属于集体实体，不依赖任何成员。涌现的新规则（如"立约修正案""规则自我消解相"）写回集体库，下个 tick 该 collective agent 召回时能看到自身演化——这是同质系统复制不了的（同质没有独立集体实体）。

---

## §4. 组件接口

| 组件 | 职责 | input → output | 宿主 |
|------|------|----------------|------|
| **Agent** | 决策 | `(snapshot_slice, recalled_events) → NL action` | claude.cmd subprocess |
| **EffectExtractor** | NL→结构化 | `(本tick所有action, S_t, 世界规则) → effect[]` | claude.cmd subprocess（1次/tick）|
| **Reducer** | fold 状态 | `(effects, S_t) → (S_{t+1}, conflict_resolutions)` | **Python 纯函数** |
| **EventStore** | 持久化 | `append(event)` / `query(filter, rank, top_k)` / `snapshot_at(tick)` | Python（JSONL）|
| **Recall** | 记忆召回 | `(agent_id, S_t) → (snapshot_slice, K条相关event)` | Python |
| **MemoryStore** | 记忆读写 | `write(entry)` / `recall(owner, query, top_k)` | Python（JSONL + embedding）|
| **Renderer** | 叙事投影 | `(snapshot, events, POV) → 叙事文本/HTML` | Python（isActive=false）|
| **Telemetry** | 调用监控 | 自动记录所有 LLM 调用 → CallEvent | Python（call_llm wrapper）|
| **Dashboard** | 监控可视化 | `(event store) → HTML` | Python projection |

### 4.1 call_llm wrapper（所有 LLM 调用的统一入口）

```python
def call_llm(prompt: str, model: str = "sonnet",
             agent_id: str = None, tick: int = None) -> str:
    """所有 LLM 调用都过这里：subprocess claude.cmd + telemetry 自动记录"""
    t0 = time.time()
    r = subprocess.run(
        ['claude', '-p', '--bare', '--output-format', 'json', '--model', model],
        input=prompt, capture_output=True, text=True, encoding='utf-8')
    duration = (time.time() - t0) * 1000
    parsed = json.loads(r.stdout)
    # telemetry 自动落盘（CallEvent）
    EventStore.append(Event(event_type="call", agent_id=agent_id, tick=tick,
        payload={"prompt": prompt, "output": parsed["result"],
                 "duration_ms": duration, "tokens": parsed.get("usage", {}),
                 "model": model, "status": "ok"}))
    return parsed["result"]
```

**关键约束**：
- `--bare`：跳过项目 CLAUDE.md/hooks，纯 LLM 调用（否则会加载小说系统指令污染 agent）
- `--output-format json`：取结构化 usage（token/cost）和 result
- 所有 agent / extractor 调用必须经此 wrapper（telemetry 无死角）

### 4.2 并发

```python
from concurrent.futures import ThreadPoolExecutor

def run_tick_agents(agents, snapshot_slice_fn, recall_fn, tick):
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(
            lambda a: Agent(a, snapshot_slice_fn(a), recall_fn(a, tick), tick)
        ): a for a in agents}
        return {a: f.result() for a, f in futures.items()}
```

max_workers=8（claude.cmd subprocess 并发上限，避免过载）。

---

## §5. 记忆模块（核心诉求，详设计）

### 5.1 召回（read，治 O(N²)）

```python
def recall(agent_id: str, S_t: Snapshot, top_k: int = 8) -> tuple[dict, list]:
    # 1. snapshot slice：该 agent 该看的视角
    slice_ = project_snapshot(S_t, agent_id)
    # 包含：所属集体决议 + 相关世界状态 + agent 自身状态

    # 2. 相关 event：Park 三权重检索
    relevant = EventStore.query(
        filter={
            "owner_self": agent_id,           # 自己的记忆
            "collective": agent_collective(agent_id),  # 所属集体记忆
            "layer_relevant": relevant_layers(agent_id),
        },
        rank={
            "relevance": embedding_similarity(query, event),  # α
            "recency": 0.995 ** (current_tick - event.tick),  # β
            "importance": event.importance,                   # γ
        },
        top_k=top_k
    )
    return slice_, relevant
    # prompt 大小 = O(slice + top_k)，恒定，不随 tick 增长
```

**对比当前 pilot**：现在每 agent 看**全量 N 条 trace**（O(N)，N 随 tick 涨）；之后看 **1 slice + K=8 条**（O(1)）。中场景预期 token 从 16.4M 降到 ~1/10。

### 5.2 写入（write，集体记忆可演化）

```python
def write_memory_tick(tick, actions, snapshot):
    for agent_id, action in actions.items():
        importance = score_importance(action, snapshot)  # LLM 1-10
        if importance >= THRESHOLD:
            MemoryStore.write(MemoryEntry(
                content=summarize(action),
                importance=importance,
                embedding=embed(action),
                owner={"type": owner_type(agent_id), "id": agent_id},
                evidence_ptrs=[event_id_of(action)],
            ))
    # 集体 agent 的涌现规则写回集体库（owner.type=collective）
    # 下个 tick collective agent recall 时能看到自身演化
```

**集体演化机制**：collective agent 决策时若产生新规则（extractor 识别为 rule-type effect），写回该集体记忆库。这是中场景报告"联盟规则自我消解相"等涌现的持久化基础。

---

## §6. 冲突裁决（reducer 内部）

```python
def reducer(effects: list[Effect], S_t: Snapshot) -> tuple[Snapshot, list]:
    resolutions = []
    # 按 priority 分组，同 key 高 priority 覆盖低 priority
    by_key = group_by_affected_key(effects)
    new_state = deepcopy(S_t)

    for key, candidates in by_key.items():
        if len(candidates) == 1:
            apply(new_state, key, candidates[0])
        else:
            # 冲突：按 priority 排序
            ranked = sorted(candidates, key=lambda e: -e.priority)
            if ranked[0].priority > ranked[1].priority:
                # 优先级不同：高者胜
                apply(new_state, key, ranked[0])
                resolutions.append(ConflictResolution(
                    conflicting=candidates, winner=ranked[0],
                    reason="priority", unresolved=False))
            else:
                # 同优先级冲突：记为未裁决矛盾，保留（Wolf 矛盾即基石）
                resolutions.append(ConflictResolution(
                    conflicting=candidates, winner=None,
                    reason="same_priority_unresolved", unresolved=True))
                # L2/L3 矛盾是燃料，不强制消解；仅 L1 宪法层矛盾报错

    new_state.tick = S_t.tick + 1
    return new_state, resolutions
```

**裁决规则**：
- priority：world_will(4) > law_enforcer(3) > collective(2) > character(1)
- 高优先级覆盖低优先级
- 同优先级冲突 → 未裁决矛盾，保留在 snapshot（Wolf：矛盾即基石，L2/L3 矛盾是燃料）
- L1 宪法层矛盾（如物理逻辑不可能）→ 报错，不保留

---

## §7. 可观测性层

### 7.1 telemetry 作 event store projection

所有 LLM 调用经 call_llm wrapper 自动产 CallEvent 存入 event store。**不引入第二套数据**——telemetry、renderer、dashboard 都从 event store 查询投影（Fowler read-model projection）。

### 7.2 自建 HTML dashboard（复用 render POC 模式）

event store → projection → HTML，与 `render_poc.py` 同模式（已验证可行）：

- **世界状态演化时间线**：每个 tick 的 snapshot（封印/韩峥生死/集体决议）随 tick 变化——领域特有，现成工具没有
- **agent 调用甘特图**：每 tick 各 agent 调用顺序/耗时/状态/成本
- **冲突裁决流**：哪些 effect 冲突、按 priority 怎么裁、哪些未裁决
- **snapshot diff 视图**：每 tick 世界变了什么（state_delta）
- **token/cost 累计曲线**

### 7.3 Langfuse（可选增强，MVP 不做）

如需通用 LLM trace UI（timeline/token 对比），可后续在 call_llm wrapper 加 Langfuse SDK 调用。但领域特有视图仍需自建。

---

## §8. 运行宿主（纯 Python + claude.cmd）

### 8.1 目录结构

```
docs/research/world_runtime/
├── runtime.py              # 主编排（tick 循环）
├── reducer.py              # 纯函数 fold（可单测）
├── event_store.py          # append-only JSONL + query
├── recall.py               # 记忆召回
├── memory_store.py         # agent/集体记忆库
├── llm.py                  # call_llm wrapper（subprocess claude.cmd）
├── extractor.py            # effect 提取
├── schemas.py              # Event/Effect/Snapshot/MemoryEntry dataclass
├── dashboard.py            # event store → HTML projection
├── tests/
│   ├── test_reducer.py     # reducer 纯函数单测（核心）
│   └── test_event_store.py
├── snapshots/              # snap_t{N}.json
├── events.jsonl            # append-only event log
└── memory/                 # agent_*.jsonl / collective_*.jsonl
```

### 8.2 运行

```bash
python runtime.py --scene seal_crisis --ticks 10 --model sonnet
# 或离线验证（不调 LLM，用已有 event log）：
python runtime.py --replay events.jsonl
```

---

## §9. MVP 路线（每个带一个问题 + 数据 + 局限 + 判定）

### MVP1：reducer 机制 + effect schema 表达力

**带的问题**：
- Q1：给定结构化 effect，纯函数 reducer 能否确定性产出合理 snapshot？（机制）
- Q2：effect schema（set/unset/intent/priority）能否表达中场景关键状态变化？（表达力）

**数据**：现有中场景 .output 的 130 条 NL action + 场景规则。

**方法**：
1. EffectExtractor（LLM，离线一次性）把 130 条 action + 场景规则 → effect log
2. Reducer（Python 纯函数，零 LLM）从空 snapshot fold 10 tick → 10 个 snapshot
3. 验证 snapshot 序列合理性

**承认的局限**：pilot 的 NL action 是"决策陈述"非"状态变化"，extractor 提取可靠性受限（Q3）。**这个局限本身是发现**——若提取不出可靠 effect，证明 agent prompt 需从"决策陈述"转向"决策+落地事件"（接上"一脸懵"根因）。

**判定标准**：
- Q1：reducer 能否确定性 fold（多次 replay 同 event log 出相同 snapshot）→ 是/否
- Q2：schema 能否承载封印/韩峥生死/集体决议 → 是/否
- 若 Q1/Q2 成立 → reducer 范式立住，进入 MVP2
- 若 fold 出荒谬状态 → 暴露 effect schema 哪里要改（同样有价值）

**成本**：一次性 extractor LLM（~130 条）+ reducer 零 LLM。

### MVP2：extractor 鸿沟 + agent prompt 重设判断

**带的问题**：pilot action 的 effect 提取可靠性多高？鸿沟多大？是否必须重新设计 agent prompt（决策 → 决策+落地）？

**数据**：MVP1 的 effect log + 人工抽检。

**判定**：若提取可靠性 < 阈值 → 确认需 MVP2b。

### MVP2b：为 fold 设计的新小 simulation

**带的问题**：在"为 fold 设计"的数据上（agent 知道要落地状态），extractor 准不准？

**数据**：新跑一个小场景（5 agent × 4 tick，agent prompt 引导产"决策+预期状态变化"）。

**成本**：小场景可控（~1.5M token，同小场景 pilot 量级）。

### MVP3：记忆召回 O(1) prompt

**带的问题**：召回恒定 prompt 后，token 从 O(N)→O(1) 了吗？agent 决策质量退化没？

**数据**：新小场景对比（全量召回 vs snapshot+K 召回）。

**判定**：token 降一个数量级 + 决策质量不退化（盲评）。

### MVP4：叙事渲染治"一脸懵"

**带的问题**：snapshot + event 能否织成可读叙事？

**数据**：MVP1 的 snapshot 序列。

**方法**：升级 render POC 的 renderer——不是平铺 trace，而是选 POV 把 snapshot diff + event 编织成连贯叙事。

---

## §10. 测试策略

- **Reducer 纯函数单测**（核心收益）：给定 effect 序列，断言 snapshot。确定性，可单测，无需 LLM。
  ```python
  def test_reducer_priority():
      effects = [Effect(set={"seal_state":"broken"}, priority=4),  # world_will
                 Effect(set={"seal_state":"protected"}, priority=1)]  # character
      snap, res = reducer(effects, empty_snapshot())
      assert snap.seal_state == "broken"  # 高 priority 胜
  ```
- **replay 一致性**：同 event log 多次 fold 出相同 snapshot（验证确定性，治"误差累积"）
- **MVP1 反向验证**：用人类已知的中场景结局核对 fold 出的 snapshot
- **call_llm wrapper mock**：单测时 mock subprocess，不真调 LLM

---

## §11. 与 thesis 的关系

- **不影响 thesis 1 判定**（规模放大 + prompt 公平双验证成立）。本 runtime 是工程基础设施。
- **强化研究定位**：世界渲染 = 生成（异质 agent 演化，thesis 1）+ 冻结（event sourcing 落盘，本 runtime 核心）+ 渲染（isActive=false 投影，render POC 已验证）。本 runtime 攻克第二段（冻结）。
- **world_will/law_enforcer 保留为 agent**：thesis 1 的异质层级冲突不丢，reducer 给它们 effect 更高 priority。

---

## §12. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| pilot action 是决策陈述，extractor 提取不可靠 | MVP1 Q3 局限 | **承认并记录鸿沟**（MVP2 专门处理）；这不是失败是发现 |
| claude.cmd subprocess 启动开销（~1-2s/次）| runtime 慢 | `--bare` 跳过加载；concurrent.futures 并发（max_workers=8）|
| 动态涌现状态空间不可预测 | reducer 难处理任意 key | 预定义关键状态强类型 + dynamic dict 容纳涌现 |
| embedding 召回需向量库 | 记忆模块复杂度 | MVP 先用关键词/rule 检索；embedding 留 MVP3 优化 |
| 集体记忆写回"涌现规则"难识别 | 集体演化机制失效 | extractor 增加 rule-type effect 识别；MVP3 验证 |
| reducer 范式可能 fold 出荒谬状态 | 架构不成立 | MVP1 正是验证这点；若发生暴露 schema 缺陷（有价值）|

---

## §13. 下一步

本 spec 确认后，转 writing-plans skill 出 MVP1 的实现计划（reducer + event_store + schemas + effect extractor 离线脚本 + 反向验证）。MVP2-4 待 MVP1 结果决定。
