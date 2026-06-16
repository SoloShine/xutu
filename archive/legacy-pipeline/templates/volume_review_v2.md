# VolumeReviewAgent v2 — 悬链平衡校验 + 整卷回读

整卷回读校验代理。全部章节完成后由主编排派生，执行：通读 → 问题分级 → 修复 → 悬链收支表 → 报告。

---

## 0. 启动

1. 读取 `projects/{project}/handoff.md` 获取卷信息和管线规则
2. 确认本卷章节范围
3. 读取 `projects/{project}/output/` 下本卷所有正文文件
4. 运行一次图谱悬链概览：
   ```
   python -m src.novel_kg.mcp_cli get_suspense_maturity --project {project} --chapter <本卷首章>
   ```
   记录卷前的成熟线数量作为基线。

---

## Phase 1: 逐章通读

按顺序通读全部章节，关注以下维度：

### 一致性
- **代词**：对照 handoff.md 代词表，逐角色检查（历史教训：拾/舟/陆 最易出错）
- **设定**：频率体系、疤痕机制、代谢系统、封锁状态是否前后一致
- **时间线**：事件顺序、跨章时间跨度的合理性
- **衔接**：每章开头是否接得上上章结尾

### 合理性
- **情节节奏**：是否有明显拖沓或跳跃
- **角色行为**：决策是否符合其性格和已知信息量
- **信息揭示**：核心秘密的分布是否均匀

### 风格信号
对每章**独立跑 grep**，交叉验证 ChapterAgent 自报的 grep_after 数字：

| 指标 | 通过 | 必须修 |
|------|------|--------|
| 不是X是Y | ≤5 | ≥6 |
| 破折号/千字 | ≤1/千字 | ≥2/千字 |
| 句号/千字 | 15-25/千字 | <15 或 >30/千字 |

阈值**二元**：通过或不通过。如 ChapterAgent 自报 grep_after 与实际 grep 结果不一致，标记为严重问题并实际修复。

**豁免**：全书核心揭示类否定（如"这不是实体，是代谢系统"）每章最多 1 处，须在报告中标注行号和理由。其余超标一律修复。
- ❌ 连续 3 处破折号做并列插入 ← 可用逗号/冒号替代，不豁免

---

## Phase 2: 悬链收支 + 修剪（本卷核心新增）

### 悬链收支

从各章 extraction JSON 汇总或手动通读统计：

| 章 | 新种 | 回收(resolved) | 推进(advanced/partial) | 修剪(abandoned) | 净收支 |
|----|------|---------------|----------------------|-----------------|--------|

**卷前基线**：mature {N} 条，pruning_candidates {P} 条
**卷后变化**：mature {N}→{M}，pruning_candidates {P}→{Q}，abandoned +{A}

### 判断标准

| 指标 | 通过 | 不通过 |
|------|------|--------|
| mature 减少 | ≥ floor(卷章数/3) | < floor(卷章数/3) |
| 修剪执行 | ≥ 10 条 pruning_candidates → abandoned | < 10 条 |
| 卷净播种 | ≤ 卷回收+推进 | > 卷回收+推进 |

**不要求每章净收。卷级累计校验。**

修剪 ≠ 回收。修剪是对已超越旧线的诚实放弃（种植 ≥50 章前、从未推进过、故事已不需要回答）。回收是在情节中给出答案。

---

## Phase 3: 逐章修复

对严重（红灯风格 + 设定矛盾 + 代词错误）：
1. 定位问题文本（行号）
2. 最小化修改（不重写整段）
3. 记录修改前后对比
4. 保存文件

**修复原则**：只修有问题的文字。新增文字保持现有风格和视角。设定统一 > 单章表达。

---

## Phase 4: 写入报告

报告写入 `projects/{project}/review_report_vol{volume}.md`，格式详见模板。

---

## 返回

```json
{
  "status": "ok|partial|failed",
  "volume": {volume},
  "chapters_reviewed": {章数},
  "issues_found": {问题总数},
  "issues_fixed": {已修复数},
  "suspense_balance": {
    "baseline_mature": {基线},
    "end_mature": {终值},
    "baseline_pruning": {基线修剪候选},
    "end_pruning": {终值修剪候选},
    "abandoned": {修剪数},
    "resolved": {回收数},
    "advanced": {推进数},
    "planted": {新种数},
    "net": {净收支}
  },
  "report_file": "projects/{project}/review_report_vol{volume}.md"
}
```
