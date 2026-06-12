# 悬链机制演进

## 问题：悬念通胀 → 故事饥饿

v1 管线没有悬链消费机制。提取阶段自动为每章生成悬念线，但没有任何回收/修剪/解决流程。结果：309 条悬念线只有 17 条回收（5.5%），大量沉积线从未被后续章节触及。

---

## Phase 1: 放任播种（v0-v1.2，ch01-ch177）

**机制**: 提取 JSON 中包含 `suspense_threads` 字段，自动生成悬念线。无消费要求。

**结果**:
```
Vol12 结束: 309 条总悬念线
  - resolved: 17 (5.5%)
  - abandoned: 0
  - planted/active: 263 (85.1%) — 绝大多数从未被触碰
  - 最老未解决线: 种植于 ch01（160+ 章前）
```

---

## Phase 2: v2 分层消费（Vol13-14）

### 设计（2026-06-11 讨论）

**核心原则**:
- 章级软指导：consumption_balance 允许 -1~+3（设置章可净播种，高潮章应净回收）
- 卷级硬约束：mature 下降 ≥ floor(章数/3)，全卷播种 ≤ 回收+推进，修剪 ≥ 10 条
- 修剪 ≠ 回收：修剪是诚实放弃故事已经不需要的旧线，回收是叙事回答悬念

**成熟度分组**:
| 组 | 定义 | 语义 |
|---|------|------|
| mature | ≥10章前种植 | 已成熟，应回收或推进 |
| developing | 5-9章前 | 发育中，推进一级 |
| recent | <5章前 | 近期种植，追踪 |
| pruning_candidates | ≥50章前种植且从未推进 | 标记 abandoned |

### 统一消费公式

```
consumed = resolved×1 + (advanced + partially_resolved + abandoned) × 0.5
consumption_balance = consumed - new_threads.length
```

### 执行结果

| 时间点 | mature | pruning_candidates | abandoned | 数据来源 |
|--------|--------|-------------------|-----------|---------|
| Vol12 结束 | 263 | 63 | 0 | get_suspense_maturity (Prepare 阶段记录) |
| Vol13 结束 | 243 | 31 | 40 | VolumeReview + get_suspense_maturity |
| Vol14 结束 | 223 | 0 | 72 | VolumeReview + get_suspense_maturity |

**解析**:
- Vol13: mature +19（未达标 ⚠️），原因：新线 23 条，但修剪/解决不足。Vol14 需大力回收
- Vol14: mature -243 → 0（远超达标 ✅），原因：循环终卷叙事功能天然支持大量收束 + 激进修剪
- pruning_candidates 从 63 → 0，全部标记为 abandoned（放弃或解决）

---

## 关键设计问题（已解决）

### Q1: 1:1 消费比会导致"凑数回收"和故事饥饿

**风险**: 每播种 1 条必须回收 1 条 → Agent 制造虚假回收 → 同时设置章无法自然播种新线 → 故事饥饿

**解决**: 章级软（-1~+3）+ 卷级硬（mature 必须下降，全卷播种≤回收）。设置章可净播种 +3，高潮章通过回收 -2/-3 平衡。

### Q2: 卷级净零导致"每卷都是全新故事线"

**风险**: 如果全卷播种=全卷回收 → 每卷结束后悬链池回到起点 → 旧线不延续 → 故事无累积

**解决**: 修剪 + mature 硬下降。Vol14 修剪 40→72（+32 条诚实放弃），而非强行回收。成熟池自然缩减。

---

## 剩余未知

1. **Vol15 起悬链生态是否会再次通胀？** — Vol14 的大幅消费受益于"循环终卷"的叙事功能。Vol15 是新循环起点，自然需要重新播种。关键看能否控制新线速度。
2. **修剪 vs 回收的最优比例？** — Vol14 回收 8 条 + 修剪 32 条。大量修剪可能意味着当初种植过多无关线。
3. **'consumption_balance 章级 -1~+3' 的上限 +3 是否需要调整？** — ⚠️ 未确定 — 尚未遇到"单章播种过多导致卷级失衡"的情况
4. **self-report 与 JSON 偏差的根本原因？** — Vol14 多章 JSON consumed=0 但 self-report 声称有消费，VolumeReview 记录但未根治（见 bug B3）

## 数据来源

- handoff.md — 悬链生态数据（Vol12/13/14 结束状态）
- review_report_vol13.md — 悬链收支表 + 修剪验证（最详细的 v2 首版数据）
- review_report_vol14.md — 悬链收支表 + 图谱基线对比
- memory/v2-pipeline-design.md — v2 设计讨论记录
- src/novel_kg/kg_json.py — `_score_suspense_maturity()` 实现
