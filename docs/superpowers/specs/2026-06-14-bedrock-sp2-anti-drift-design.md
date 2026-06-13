# 磐石 Bedrock SP2 — 防漂移校验库 设计

**日期**: 2026-06-14
**状态**: SP2 设计（待 user review → writing-plans）
**代号**: 磐石 Bedrock（V3 小说管线）
**范围**: 纯 Python 防漂移校验库 + 配置基础设施。不含 agent 编排、不含 LLM。
**依赖**: SP1 数据骨架（已完成，`src/bedrock/`，38 表，40 测试）
**前置 spec**: `docs/superpowers/specs/2026-06-14-bedrock-design.md`（§3.2 大纲三层、§3.3 悬链、§4.2 L2 重算层、§4.4 L4 审计）

---

## 一、背景

SP1 已落地数据骨架（剧情树/悬链/Worldbook/角色/Event/遥测等 38 表 + repository + 跨字段校验）。SP2 在此之上建**防漂移校验库**——写完一章后检查 beat 契约是否兑现、卷收尾时检查跨卷锚点是否兑现、卷大纲锁定的 amendment 流程。

**形态**：`src/bedrock/checks/` 校验函数库 + `src/bedrock/config/` 配置基础设施。由 SP4 编排（ChapterWriter 写完一章后）调用。SP2 自己不跑 agent、不调 LLM。

**SP2 vs SP4 vs SP5 边界**：
- **SP2**：纯 Python 防漂移校验（章级 beat 兑现 + 卷级跨卷锚点 + 大纲 amendment + override 入口 + 配置基础设施）
- **SP4**：编排（调 SP2 校验 + 重试循环 + watchdog + 强制落盘 + L2 重算）
- **SP5**：LLM 语义抽查（purpose/代词/回收真实性）+ 卷级 mature 收敛门禁 + 章级 emergent 配额 + 系统性端到端测试

---

## 二、设计原则

1. **纯 Python、确定性** —— SP2 校验函数输入 DB 状态，输出确定的 violations，零 LLM、零随机。
2. **校验与编排分离** —— SP2 只提供校验函数 + 状态机入口，不触发 agent 重试（重试由 SP4 编排）。
3. **配置分层** —— 静态常量（代码内 dict，如卷类型矩阵）vs 可变配置（配置文件，项目级覆盖）。
4. **组件级测试** —— SP2 测试是确定性单元测试（校验函数的输入/输出）。系统性端到端测试在 SP5。

---

## 三、组件设计

### ① beat 兑现校验 — `checks/beat_fulfillment.py`

写完一章后，检查该章所有 beat 的契约是否兑现。

**接口**：
```python
def check_beat_fulfillment(conn, chapter_id) -> list[BeatViolation]
```

**校验规则**（L2 纯 Python，确定性）：
0. **planned→written 迁移**：该章每个 beat.status 必须是 written/verified（已写）。planned 状态的 beat → `unwritten_beat` violation（计划了没写）。
1. **角色出场**：每个 beat 的 participating_characters（查 `beat_character`）必须在该 beat 关联的**任一段落**（`Paragraph.beat_id = 该beat`）文本里出现。匹配规则：角色 `name` 或 `aliases[]`（JSON 解析后）任一作为**子串**出现在该 beat 任一段落 text 里即算出场；全部缺失 → `missing_character` violation。
2. **悬链迁移**：每个 beat 的 advance_threads（查 `threads_advanced_at_beat(beat_id)` 反查 `thread_consumption`）必须有消费记录 + 悬链状态机真迁移（`consumed_by_thread` 含该 beat）。声明推进但无消费记录 → `thread_not_advanced` violation。

**输出**：
```python
@dataclass
class BeatViolation:
    beat_id: int
    kind: str          # "unwritten_beat" | "missing_character" | "thread_not_advanced"
    detail: str        # 具体哪个角色/哪条悬链/未写的 beat
    fix_hint: str      # 定向修复提示（喂给 SP4 的修复 prompt）
```

**状态更新归属**：SP2 只输出 violations（纯校验），**不更新 beat 状态**。状态迁移由 SP4 编排负责（直接调 SP1 的 `update_beat_status`）：全部通过 → SP4 把 beat written→verified；有 violation → SP4 把相关 beat written→deviated（deviation_note=violation 摘要）。SP2 不提供状态 helper。

> **标记 SP5**：章级 emergent 配额检查（本章 `origin=emergent` 新悬链数 ≤ 卷类型 `may_plant`）不在 SP2，后置 SP5。

### ② 卷大纲 amendment — 扩展 `repositories/outline.py`

SP1 已有 `lock_volume_outline`。SP2 加 unlock/relock + amendment 强制。

**接口**（SP2 新增）：
```python
def unlock_volume_outline(conn, volume_id, reason, author="human"):
    """locked → drafted。强制记 amendment（who/when/why）。"""
    # 1. 校验当前 status == 'locked'（否则 raise）
    # 2. 写 amendment(entity_type='volume_outline', field='status', old='locked', new='drafted', reason, author)
    # 3. UPDATE volume_outline SET status='drafted', locked_at=NULL

def relock_volume_outline(conn, volume_id):
    """drafted → locked。"""
    # UPDATE volume_outline SET status='locked', locked_at=now

def update_beat_contract(conn, volume_id, beat_id, new_contract):
    """修改 volume_outline.beat_contracts JSON 里 beat_id 对应的契约项。
    内部校验：若 volume_outline.status='locked' → raise OutlineLockedError（必须先 unlock）。"""
```

**beat_contracts JSON 结构**（SP2 定义并固化）：
```json
[{"beat_id": 1, "purpose": "...", "participating_characters": [...], "advance_threads": [...]}, ...]
```
update_beat_contract 按 beat_id 寻址替换对应项；不存在则 append。

**严格规则**：locked 状态下任何 beat 契约修改必须先 unlock（update_beat_contract 内部强制 OutlineLockedError）。

> volume_outline 的 `writing`/`completed` 状态迁移由 SP4 编排负责（开写 locked→writing，卷完成 →completed）。SP2 只管 drafted↔locked（unlock/relock）+ beat 契约修改。

### ③ 跨卷锚点校验 — `checks/cross_volume.py`

卷收尾时（dispatch 下一卷前）检查跨卷锚点是否兑现。

**接口**：
```python
def check_cross_volume_anchors(conn, volume_id) -> CrossVolumeDebtReport
```

**校验规则**（L2 纯 Python）：
1. **悬链 planned_resolve_volume 兑现**：查所有 `planned_resolve_volume IS NOT NULL AND planned_resolve_volume <= volume_id AND status NOT IN ('resolved','abandoned')` 的悬链 = 应回收未回收（thread_overdue）。**planned_resolve_volume IS NULL 的悬链视为无跨卷承诺，不判逾期**（放行）。
2. **里程碑兑现**：master_outline.key_milestones 里 `expected_volume = volume_id` 的里程碑，其 `resolves_threads[]` 必须**全部 status='resolved'**（严格相等，abandoned/partially_resolved 不算兑现）。任一未 resolved → milestone_unmet。里程碑未兑现时，blocking/advisory 分类看其 resolves_threads 里**未兑现悬链**的最高 importance（含 high → blocking，否则 advisory）。

**输出**：
```python
@dataclass
class CrossVolumeDebtReport:
    blocking: list[Anchor]    # importance=high 未兑现 → 硬阻断 dispatch 下一卷
    advisory: list[Anchor]    # importance=medium/low 未兑现 → 记 debt，放行

@dataclass
class Anchor:
    kind: str          # "thread_overdue" | "milestone_unmet"
    ref_id: str        # 悬链 id 或里程碑 name
    importance: str    # high/medium/low
    detail: str
```

**门禁判定**（SP4 编排读这个）：`blocking` 非空 → 硬阻断 dispatch 下一卷；`advisory` 非空 → 记跨卷欠债放行。

### ④ deviated/override 入口 — 扩展 `repositories/plot_tree.py`

beat 校验失败后的逃逸路径（手动 override，跳过校验）。

**接口**：
```python
def mark_override(conn, beat_id, reason, author="human"):
    """beat.status ∈ {deviated, written} → overridden。强制记 amendment（逃逸审计）。"""
    # 1. 校验当前 status IN ('deviated','written')（放宽：允许人工兜底 written 状态）
    # 2. 写 amendment(entity_type='beat', field='status', old=<当前>, new='overridden', reason, author)
    # 3. UPDATE beat SET status='overridden'
```

> 自动重试由 SP4 编排触发（重派 ChapterWriter 改 deviated beat）。SP2 只提供 override 手动入口 + 状态机。

### ⑤ 配置基础设施 — `config/`

**静态常量表** `config/volume_type_matrix.py`（代码内 dict，抄 spec §4.4 卷类型矩阵）：
```python
VOLUME_TYPE_MATRIX = {
    "opening":   {"may_plant_per_chapter": (3,4), "mature_decline_floor": 0,  "pruning_quota": 0,  ...},
    "advancing": {"may_plant_per_chapter": (1,2), "mature_decline_floor": "floor(N/3)", "pruning_quota": 10, ...},
    "climax":    {"may_plant_per_chapter": (0,1), "mature_decline_floor": "floor(N/2)", "pruning_quota": 15, ...},
    "epilogue":  {...},
    "multi-pov": {...},
}
def get_matrix(volume_type) -> dict: ...
```

**配置文件机制** `config/config.py`（可变配置，项目级覆盖）：
```python
def load_config(project_dir) -> Config:
    """读 projects/<P>/bedrock_config.json（若存在）覆盖默认常量。用 json 避免 yaml 依赖。"""
def init_default_config(project_dir):
    """创建默认 bedrock_config.json（首次初始化）。用 json 避免 yaml 依赖。"""
```

> **标记 SP5**：卷类型矩阵的配额查询（may_plant/mature_decline/pruning 检查）不在 SP2。SP2 只建矩阵常量 + config 机制（基础设施先行），查询逻辑后置 SP5。

---

## 四、SP5 标记清单（明确后置）

以下在 SP2 **只建基础设施/不做查询**，逻辑后置 SP5：
- 章级 emergent 配额检查（`may_plant_per_chapter`）
- 卷级 mature 收敛门禁（`mature_decline_floor`）
- pruning 配额（`pruning_quota`）
- 系统性端到端测试（真跑一章写作管线的集成测试）

SP2 的卷类型矩阵常量表 + config 机制是基础设施，SP5 查询时调用。

---

## 五、测试策略

**SP2 测试 = 组件级单元测试**（确定性输入/输出）：
- beat 兑现校验：构造一个章节（beat + paragraph + participating_characters + thread_consumption），断言 violations 正确（角色缺失/悬链未推进各一例）
- amendment：lock → unlock（记 amendment）→ 改契约 → relock 全流程；**+ 负例：locked 下直接 update_beat_contract → raise OutlineLockedError**
- 跨卷锚点：构造 planned_resolve_volume 过期悬链（high/medium 各一），断言 blocking/advisory 分类；**+ NULL planned_resolve_volume 悬链不进 blocking/advisory（无承诺放行）**
- override：deviated → overridden + amendment
- 配置：volume_type_matrix 查表 + config 文件 load/override

**系统性端到端测试在 SP5**（真跑 ChapterWriter → 校验 → 修复循环）。

---

## 六、与 SP1 schema 的接口

SP2 校验函数查以下 SP1 表/联结表：
- `beat` / `paragraph`（beat_id 关联）/ `beat_character`（participating_characters）
- `character`（name + aliases 用于 grep）
- `thread_consumption`（悬链迁移记录）/ `suspense_thread`（planned_resolve_volume + importance + status）
- `volume_outline`（lock 状态）/ `master_outline`（key_milestones JSON）
- `amendment`（unlock/override 留痕）

无新表（SP2 全部基于 SP1 schema）。新增：`src/bedrock/checks/` + `src/bedrock/config/` 两个模块。

---

## 七、文件结构

```
src/bedrock/
├── checks/
│   ├── __init__.py
│   ├── beat_fulfillment.py    # ① beat 兑现校验
│   └── cross_volume.py        # ③ 跨卷锚点校验
├── config/
│   ├── __init__.py
│   ├── volume_type_matrix.py  # ⑤ 静态常量表
│   └── config.py              # ⑤ 配置文件机制
├── repositories/
│   ├── outline.py             # ② 扩展 unlock/relock
│   └── plot_tree.py           # ④ 扩展 mark_override
└── ...（SP1 已有）
tests/bedrock/
├── test_beat_fulfillment.py
├── test_cross_volume.py
├── test_amendment.py
├── test_override.py
└── test_config.py
```
