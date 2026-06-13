# H4 数据驱动验证设计 — 异质多层级系统 vs 同质 character baseline

**日期**: 2026-06-13
**假设 H4**: 多层级异质系统（L3 世界意志 / L2 集体 / L1 角色 + 横切规律执行者）能产生同质 character 系统产生不了的**层级间冲突情节**
**方法**: 学 thesis 2 的客观查询对比模式——真实数据（绝地天通章节）+ 可量化指标 + 严格证伪
**状态**: 设计完成，待实现脚本 + 跑数据

---

## §0. 为什么这个测试必须数据驱动

### thesis 2 的成功经验

thesis 2 用 123 个客观测试点证伪 bitemporal——每个 query 返回值是否相同是布尔判定，零主观性。2 小时得出结论，避免数周浪费。

### H1 的失败教训

H1（集体 agent vs individual 聚合）用手动构造场景 + 4 维度主观评估，被用户指出**还原论错误**：单独抽出一类 agent 对比无意义。

### H4 必须避免的两个陷阱

| 陷阱 | H1 怎么掉的 | H4 怎么避免 |
|------|-----------|-----------|
| 还原论 | 单独对比集体 agent | **整个系统对比**：4 类一起跑 vs 同质 baseline |
| 主观评估 | 4 维度人工打分 | **客观指标**：trace 字段统计，零主观判断 |

**核心承诺**：H4 的所有判定都基于可运行代码返回的数字，不依赖"我觉得异质更好"。

---

## §1. 测试目标（精确版）

**H4 原假设（要证伪的）**：
> 异质多层级系统在表达"层级冲突"场景时，与同质 character baseline **无显著差异**。

**证伪 H4（即支持 thesis 1）需要证明**：
> 存在 ≥30% 的真实层级冲突场景，异质系统能完整表达（layer / influence_direction / conflict_with 字段都能填），而同质 baseline 表达不了（字段缺失或强行降级）。

**关键不对称**（学 thesis 2）：
- 给 baseline **最宽松标准**（允许任意 predicate，允许手工标注）——如果宽松标准下 baseline 仍追不上，异质系统才真有价值
- 不预设异质系统更优——如果数据说同质够用，果断放弃

---

## §2. 数据来源（绝地天通已写章节）

### 为什么用真实数据

thesis 2 用 V16（ch216-227）提取的 26 事件——真实数据避免"手动构造场景偏袒某方案"的指控。H4 同理。

### 数据范围

绝地天通 Vol1-12 已写章节（ch01-ch177，~80万字），重点提取以下卷的冲突密集段：

| 卷 | 冲突类型 | 候选场景 |
|----|---------|---------|
| Vol4 较量 | 角色 vs 集体 | 韩峥 vs 穿越者网络指令 |
| Vol5 闭环 | 集体 vs 世界规则 | 安全阀方案 vs 封锁必然性 |
| Vol6 前夜 | 角色 vs 世界命运 | 渊传承身份 vs 三方共识 |
| Vol7 集结 | 集体 vs 集体 | 穿越者阵营 vs 守序者阵营 |
| Vol9 余烬 | 角色 vs 集体 | 林深冬眠决定 vs 城市利益 |
| Vol12 复苏 | 集体 vs 世界规则 | 人族信号 vs 代谢系统真相 |

### 提取目标

- **Phase 1**: 提取 **30 个**层级冲突场景（每卷 5 个），结构化标注
- **Phase 2**: 若 Phase 1 结果模糊，扩展到 **50 个**
- **Phase 3**: 若需要 generation test，再扩展

### 提取方式（避免主观性）

3 个 subagent 独立提取 + 交叉验证：

```
agent_A 提取场景列表 → 标注
agent_B 提取场景列表 → 标注
agent_C 提取场景列表 → 标注
↓
取交集（≥2 个 agent 都识别为冲突的场景才入选）
↓
人工 spot check（用户确认 5-10 个样本）
```

**防御"主观标注"指控**：用多 agent 交叉 + 用户抽样确认。

---

## §3. 场景标注 schema

每个提取出的场景用以下结构化格式存储：

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass(frozen=True)
class InfluenceStep:
    """影响链的一步"""
    layer: Literal["L1", "L2", "L3", "cross_cut"]
    direction: Literal["top_down", "bottom_up", "cross_cut", "peer"]
    agent: str           # 如 "韩峥" / "穿越者网络" / "世界意志"
    agent_type: Literal["character", "collective", "world_will", "law_enforcer"]
    action: str          # 如 "决定打破封印"
    is_conflict_point: bool  # 这一步是否触发冲突

@dataclass(frozen=True)
class LayerConflictScene:
    scene_id: str                    # 如 "vol5_ch74_seal_break"
    chapter: int                     # 全局章号
    volume: int
    description: str                 # 场景简述（1-2 句）
    
    # 涉及的层级（必填）
    layers_involved: tuple[str, ...]  # 如 ("L1", "L2", "L3")
    
    # 冲突类型
    conflict_type: Literal[
        "character_vs_collective",   # 角色 vs 集体规则
        "collective_vs_world",        # 集体 vs 世界规则
        "character_vs_world",         # 角色 vs 世界命运
        "any_vs_law_enforcer"         # 任意层 vs 规律执行者
    ]
    
    # 冲突的两端（标注具体 agent）
    conflict_between: tuple[str, str]  # 如 ("L1:韩峥", "L2:穿越者网络")
    
    # 影响链（时序的 step 列表）
    influence_chain: tuple[InfluenceStep, ...]
    
    # 显式 conflict_with 内容（异质系统的 trace 应能填这个）
    expected_conflict_with: tuple[str, ...]  # 如 ("L2:网络指令", "L3:封锁必然")
    
    # 场景需要的 trace 字段（用于字段完整度指标）
    required_fields: tuple[str, ...] = (
        "layer", "influence_direction", "conflict_with"
    )
```

### 标注示例（虚构，待真实数据替换）

```python
example_scene = LayerConflictScene(
    scene_id="vol5_ch74_seal_break",
    chapter=74,
    volume=5,
    description="韩峥决定牺牲自己打破封锁，违背穿越者网络的保全指令",
    layers_involved=("L1", "L2", "L3"),
    conflict_type="character_vs_collective",
    conflict_between=("L1:韩峥", "L2:穿越者网络"),
    influence_chain=(
        InfluenceStep("L3", "top_down", "世界意志", "world_will", "封锁必然性已定", False),
        InfluenceStep("L2", "top_down", "穿越者网络", "collective", "指令保全韩峥", False),
        InfluenceStep("L1", "peer", "韩峥", "character", "决定牺牲破封", True),
        InfluenceStep("cross_cut", "cross_cut", "规律执行者", "law_enforcer", "校验：牺牲是否合规", True),
        InfluenceStep("L3", "bottom_up", "世界意志", "world_will", "封印因韩峥行动而破", False),
    ),
    expected_conflict_with=("L2:网络保全指令", "L3:封印维持"),
)
```

---

## §4. 两套建模系统（异质 vs 同质）

### 异质系统（thesis 1）

```python
def model_heterogeneous(scene: LayerConflictScene) -> list[Trace]:
    """用 4 类 agent + 三种影响机制建模场景"""
    traces = []
    for i, step in enumerate(scene.influence_chain):
        trace = Trace(
            trace_id=f"{scene.scene_id}_hetero_{i}",
            agent_id=step.agent,
            agent_type=step.agent_type,
            layer=step.layer,                              # ✅ 填真实层级
            influence_direction=step.direction,            # ✅ 填真实方向
            conflict_with=list(scene.expected_conflict_with) if step.is_conflict_point else None,
            valid_time=float(i),                           # 时序
            action_type=step.action,
            state_delta={"action": step.action},
        )
        traces.append(trace)
    return traces
```

### 同质 baseline（最宽松标准）

baseline 的设计原则：**给 baseline 满级装备**，看它 widest possible 表达下能否追上。

```python
def model_homogeneous(scene: LayerConflictScene) -> list[Trace]:
    """全部用 character agent，但允许任意 predicate（学 thesis 2 给 baseline 满级）"""
    traces = []
    for i, step in enumerate(scene.influence_chain):
        # baseline 试图用 character + predicate 表达
        # 关键问题：layer / influence_direction / conflict_with 能否用 predicate 表达？
        
        # baseline 尝试 1: 全部降为 character trace
        trace = Trace(
            trace_id=f"{scene.scene_id}_homo_{i}",
            agent_id=step.agent,
            agent_type="character",                        # ⚠️ 全部 character
            layer="L1",                                    # ⚠️ 只能 L1（baseline 无多层概念）
            influence_direction=None,                      # ❌ baseline 无此字段
            conflict_with=None,                            # ❌ baseline 无此字段
            valid_time=float(i),
            action_type=step.action,
            state_delta={
                "action": step.action,
                # baseline 试图用 predicate 补救
                "predicate_layer": step.layer,             # 塞进 state_delta
                "predicate_direction": step.direction,
                "predicate_conflict": scene.expected_conflict_with if step.is_conflict_point else None,
            },
        )
        traces.append(trace)
    return traces
```

### 关键设计决策：baseline 能用 predicate 补救吗？

**能**（给 baseline 最宽松标准）。predicate 信息塞进 `state_delta`。但即便如此，baseline 仍然在以下指标上受损（这就是测试要揭示的）：

- **layer 字段**：baseline 只能填 "L1"（或塞 predicate），**查询时无法用 layer 过滤**
- **influence_direction**：baseline 塞 predicate，**查询时无法用 direction 过滤**
- **conflict_with**：baseline 塞 predicate，**查询时无法直接定位冲突 trace**

这就是 thesis 1 的核心论点：**字段化（first-class field）vs predicate 化（塞进 state_delta）有本质差异**——前者可查询、可索引、可推理；后者需要全表扫描 + 解析。

---

## §5. 客观指标定义（4 个，全部可量化）

### 指标 1: trace layer 分布

```python
def metric_layer_distribution(traces: list[Trace]) -> dict[str, int]:
    """返回各 layer 的 trace 数量"""
    dist = {"L1": 0, "L2": 0, "L3": 0, "cross_cut": 0}
    for t in traces:
        if t.layer in dist:
            dist[t.layer] += 1
    return dist

def metric_layer_diversity(traces: list[Trace]) -> int:
    """返回非零 layer 的种类数（0-4）"""
    dist = metric_layer_distribution(traces)
    return sum(1 for v in dist.values() if v > 0)
```

**判定**：
- 异质系统：layer_diversity = 涉及的层数（通常 2-4）
- 同质 baseline：layer_diversity = 1（只有 L1）

### 指标 2: conflict_with 非空 trace 数

```python
def metric_conflict_trace_count(traces: list[Trace]) -> int:
    """conflict_with 字段非空的 trace 数（first-class field）"""
    return sum(1 for t in traces if t.conflict_with)

def metric_conflict_in_predicate(traces: list[Trace]) -> int:
    """predicate 里塞了 conflict 信息的 trace 数（baseline 的补救）"""
    return sum(1 for t in traces 
               if t.state_delta.get("predicate_conflict"))
```

**判定**：
- 异质系统：conflict_trace_count > 0（first-class，可查询）
- 同质 baseline：conflict_trace_count = 0，但 conflict_in_predicate > 0（塞 predicate，不可查询）

### 指标 3: 影响链跨层跳数

```python
def metric_cross_layer_hops(traces: list[Trace]) -> int:
    """影响链中 layer 切换的次数（跨层动力学强度）"""
    layers = [t.layer for t in traces if t.layer and t.layer != "cross_cut"]
    if len(layers) < 2:
        return 0
    hops = 0
    for i in range(1, len(layers)):
        if layers[i] != layers[i-1]:
            hops += 1
    return hops
```

**判定**：
- 异质系统：cross_layer_hops ≥ 1（有跨层影响）
- 同质 baseline：cross_layer_hops = 0（全 L1，无跨层）

### 指标 4: 场景字段完整度（first-class vs predicate）

```python
def metric_field_completeness_firstclass(
    scene: LayerConflictScene, traces: list[Trace]
) -> float:
    """first-class 字段填充率（layer/influence_direction/conflict_with）"""
    needed = scene.required_fields
    filled = 0
    total = 0
    for t in traces:
        for f in needed:
            total += 1
            val = getattr(t, f, None)
            if val is not None and val != "L1":  # L1 是 baseline 默认值，不算"真填充"
                filled += 1
    return filled / total if total else 0.0

def metric_field_completeness_predicate(
    scene: LayerConflictScene, traces: list[Trace]
) -> float:
    """predicate 字段填充率（baseline 的补救）"""
    predicate_fields = ["predicate_layer", "predicate_direction", "predicate_conflict"]
    filled = 0
    total = 0
    for t in traces:
        for f in predicate_fields:
            total += 1
            if t.state_delta.get(f) is not None:
                filled += 1
    return filled / total if total else 0.0
```

**判定**：
- 异质系统：firstclass 完整度高，predicate = 0
- 同质 baseline：firstclass = 0（或只有 L1 默认值），predicate 完整度高

---

## §6. 复合评分与证伪判定

### 单场景复合评分

```python
def composite_score(traces: list[Trace], scene: LayerConflictScene) -> float:
    """0-1 分，越高表示表达能力越强"""
    diversity = metric_layer_diversity(traces) / 4.0                  # 0-1
    conflict = min(metric_conflict_trace_count(traces) / 2.0, 1.0)    # 0-1（≥2 个冲突 trace 满分）
    hops = min(metric_cross_layer_hops(traces) / 3.0, 1.0)            # 0-1（≥3 跳满分）
    completeness = metric_field_completeness_firstclass(scene, traces) # 0-1
    return (diversity + conflict + hops + completeness) / 4.0
```

### 全局证伪判定

```python
def falsification_verdict(
    scenes: list[LayerConflictScene],
    hetero_results: list[list[Trace]],
    homo_results: list[list[Trace]],
) -> tuple[str, str]:
    """
    返回 (verdict, reason)
    verdict: THESIS_1_STANDS / THESIS_1_FALSIFIED / INCONCLUSIVE
    """
    hetero_wins = 0
    ties = 0
    homo_wins = 0
    
    per_scene = []
    for scene, h_traces, b_traces in zip(scenes, hetero_results, homo_results):
        h_score = composite_score(h_traces, scene)
        b_score = composite_score(b_traces, scene)
        
        if h_score > b_score + 0.1:       # 异质明显优（>10% 差距）
            hetero_wins += 1
        elif b_score > h_score + 0.1:     # baseline 明显优（几乎不可能，但留口子）
            homo_wins += 1
        else:
            ties += 1
        
        per_scene.append({
            "scene_id": scene.scene_id,
            "hetero_score": round(h_score, 3),
            "baseline_score": round(b_score, 3),
            "delta": round(h_score - b_score, 3),
        })
    
    total = len(scenes)
    hetero_ratio = hetero_wins / total
    
    if hetero_ratio >= 0.3:
        verdict = "THESIS_1_STANDS"
        reason = f"异质系统在 {hetero_wins}/{total} 场景明显优（阈值 30%）"
    elif hetero_ratio < 0.1:
        verdict = "THESIS_1_FALSIFIED"
        reason = f"同质 baseline 够用，异质仅优 {hetero_wins}/{total}（< 10%）"
    else:
        verdict = "INCONCLUSIVE"
        reason = f"结果模糊（异质优 {hetero_wins}/{total}），需扩展场景数"
    
    return verdict, reason
```

---

## §7. 测试流程（端到端）

```
Phase 1: 数据提取（3 agent 交叉）
├─ agent_A 扫描绝地天通 Vol1-12 → 候选场景列表 A
├─ agent_B 扫描绝地天通 Vol1-12 → 候选场景列表 B
├─ agent_C 扫描绝地天通 Vol1-12 → 候选场景列表 C
├─ 取交集（≥2 agent 共识）→ 30 个场景
└─ 用户 spot check 5-10 个样本 → 确认标注质量

Phase 2: 建模 + 指标计算（脚本，零主观）
├─ for scene in scenes:
│   ├─ hetero_traces = model_heterogeneous(scene)
│   ├─ homo_traces = model_homogeneous(scene)
│   ├─ 计算 4 个指标（两套系统各一遍）
│   └─ 计算 composite_score
└─ 汇总 per_scene 结果

Phase 3: 证伪判定（脚本）
├─ falsification_verdict(scenes, hetero_results, homo_results)
└─ 输出 verdict + reason + per_scene 明细

Phase 4: 报告（落盘）
├─ 写 2026-06-13-h4-validation-report.md
├─ 落盘 h4_validation_data.json（30 场景 + 指标）
└─ 更新 positioning doc + handoff + memory
```

---

## §8. 测试脚本结构（学 thesis2_validation.py）

文件：`docs/research/h4_validation.py`

```python
"""
H4 系统性验证脚本
学 thesis2_validation.py 的结构：dataclass + query function + 三相对比
"""
from dataclasses import dataclass, field
from typing import Literal, Optional

# === §3 的 schema ===
@dataclass(frozen=True)
class InfluenceStep: ...
@dataclass(frozen=True)
class LayerConflictScene: ...
@dataclass(frozen=True)
class Trace: ...

# === §4 的两套建模 ===
def model_heterogeneous(scene): ...
def model_homogeneous(scene): ...

# === §5 的 4 个指标 ===
def metric_layer_distribution(traces): ...
def metric_layer_diversity(traces): ...
def metric_conflict_trace_count(traces): ...
def metric_conflict_in_predicate(traces): ...
def metric_cross_layer_hops(traces): ...
def metric_field_completeness_firstclass(scene, traces): ...
def metric_field_completeness_predicate(scene, traces): ...

# === §6 的复合评分 + 证伪判定 ===
def composite_score(traces, scene): ...
def falsification_verdict(scenes, hetero_results, homo_results): ...

# === 主循环 ===
def load_scenes(path: str) -> list[LayerConflictScene]: ...
def run_validation(scenes_path: str, report_path: str): ...

if __name__ == "__main__":
    run_validation(
        scenes_path="docs/research/h4_validation_data.json",
        report_path="docs/research/2026-06-13-h4-validation-report.md",
    )
```

---

## §9. 已知风险与防御

### 风险 1: 场景提取的主观性

**风险**：谁来判断"这个场景是层级冲突"？
**防御**：
- 3 agent 独立提取 + 交叉验证（≥2 共识才入选）
- 明确提取标准（见 §2 的冲突类型分类）
- 用户抽样确认 5-10 个

### 风险 2: baseline 的"不公平降级"

**风险**：把异质 trace 强行转成 character trace，可能人为贬低 baseline。
**防御**：
- 给 baseline 最宽松标准——允许塞任意 predicate（§4 的 `predicate_*` 字段）
- 单独计算 `metric_field_completeness_predicate`，诚实呈现 baseline 的补救能力
- **如果 baseline 靠 predicate 能追上异质，那就承认 thesis 1 过度设计**（学 thesis 2 诚实）

### 风险 3: representation test ≠ generation test

**风险**：本测试只验证"能否表达"，不验证"能否产生"。异质系统可能能表达但产生不了。
**防御**：
- 明确标注 H4 Phase 1-3 是 **representation test**（表达能力证伪）
- **Phase 5（后续）**：generation test——实际跑两个 simulation，看涌现情节差异
- representation test 是**前置证伪**：如果连表达都不行，generation 免谈

### 风险 4: 30 个场景可能不够

**风险**：样本太小，统计不显著。
**防御**：
- Phase 1 先跑 30 个，看趋势
- 如果 INCONCLUSIVE，扩展到 50 个
- 如果边界案例（hetero_ratio 在 0.1-0.3 之间），扩展到 100 个

### 风险 5: 复合评分权重的主观性

**风险**：composite_score 的 4 个指标权重相等（各 25%），可能不合理。
**防御**：
- 先用等权重跑
- 敏感性分析：换 3 种权重方案（偏 diversity / 偏 conflict / 偏 hops），看 verdict 是否稳定
- 如果 3 种权重都得出同一 verdict，结论稳健

---

## §10. 与 thesis 2 验证的对照（方法论一致性）

| 维度 | thesis 2 验证 | H4 验证 |
|------|-------------|---------|
| 数据来源 | V16 章节提取的 26 事件 | 绝地天通 Vol1-12 提取的 30+ 场景 |
| 测试点数 | 123 个 query | 30 场景 × 4 指标 = 120+ 测试点 |
| 对比方案数 | 3 套（baseline / single / multi） | 2 套（异质 / 同质 baseline） |
| 客观性 | 布尔判定（query 返回相同/不同） | 数值判定（指标计算 + 阈值） |
| 证伪标准 | baseline 不劣于 thesis 2 → 证伪 | baseline 追不上异质（< 30%）→ 站住 |
| baseline 装备 | 满级（predicate 够用） | 满级（任意 predicate + state_delta 补救） |
| 主观成分 | 零 | 场景提取有（用 3 agent 交叉 + 用户确认防御） |

**关键差异**：thesis 2 是纯客观（query 对比）；H4 在场景提取阶段有少量主观性，但用多 agent 交叉 + 用户抽样来防御。指标计算阶段零主观。

---

## §11. 决策记录

- **2026-06-13 晚**: H4 设计完成。核心 = 数据驱动 + 客观指标 + 严格证伪（学 thesis 2）
- **2026-06-13 晚**: 数据来源定为绝地天通 Vol1-12（~80万字），目标 30 场景（可扩展到 50-100）
- **2026-06-13 晚**: 4 个客观指标——layer 分布 / conflict_with 数 / 跨层跳数 / 字段完整度
- **2026-06-13 晚**: 证伪阈值——异质在 ≥30% 场景明显优 → 站住；< 10% → 证伪；10-30% → 扩样本
- **2026-06-13 晚**: 5 个已知风险全部有防御（主观性 / 不公平降级 / representation vs generation / 样本量 / 权重）
- **待执行**: 实现 h4_validation.py + 提取 30 场景数据 + 跑验证

---

## §12. 下一步行动清单

1. ⭐ 实现 `h4_validation.py`（schema + 建模 + 指标 + 主循环）—— 半天
2. ⭐ 派 3 个 subagent 提取绝地天通场景（交叉验证）—— 1-2 小时
3. 用户 spot check 5-10 个场景标注 —— 15 分钟
4. 跑 H4 验证脚本 —— 5 分钟
5. 写验证报告 + 更新 positioning doc + handoff + memory —— 30 分钟
6. 根据 verdict 决定 thesis 1 命运

**总预计**: 半天到一天。如果 H4 证伪 thesis 1，这半天省下后续数周的工程实现投入（学 thesis 2 的 2 小时省数周）。
