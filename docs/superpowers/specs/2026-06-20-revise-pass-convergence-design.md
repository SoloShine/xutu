# 章节工作流 B 类复写器收束(3→1)— 设计文档

- **日期**:2026-06-20
- **背景**:vigilia《长明》压测暴露 9 缺陷,归因后发现"缝补"痛感几乎全部来自 **B 类全正文复写器**(repair/polish/style)。三者结构同构(拿上一版正文 + 一份缺陷清单 → 吐整章正文),却各挂一套 revert/gate、各跑一次 commit+L2、各算一次 drift,且每个都能打碎前一个建立的不变量 → 级联。详见记忆 [[bedrock-workflow-patching-trap]]。
- **根因**:`bedrock-chapter.js` 把"定向修订"这一种动作拆成了 3 个串行全正文复写阶段。每次复写都重跑"LLM 吐整章 prose → 解析成段落 → 重算 beat 归属 → L2 校验"这条漏链,所以补丁永远在加 gate/revert。
- **目标**:把 repair/polish/style 合并为**1 个 Revise 阶段**(defect manifest 驱动,单 pass + 复测重喂 ≤2 轮),局部缺陷(代词/专名)保持 ops。**paragraph 存储不动**(经审计:9 缺陷中 ≈0~1 个由分段存储导致,且 ops 复写器依赖它存在——分段存储是功臣非祸首)。
- **硬约束**:不增加常态 agent 数(目标单章 4~5,现状 10+);信任锚面(Python L2/persist_gate/CLI)零改动。

---

## 决策记录(已与用户确认)

1. **重试模型 = 单 pass + 复测重喂**:revise 跑后 commit+L2+styleCheck 复测;仍不达标只把**剩余缺陷**重喂同 pass,≤2 轮。等价于把原 repair≤3 + style≤2 合并成一个统一"复测-重喂"后端。级联彻底消失(只有一个变异阶段)。
2. **优先级 = 正确性硬压文风**:manifest 中 `must_fix`(L2 违规)非空时,文风对准降为"不冲突时顺手";`must_fix` 空时才以文风为主。
3. **Revise 上限 = 2 轮**(原 repair 3 / style 2,合并取严的 2)。
4. **style 收敛并入 Revise 重试的复测步**(不再单独 phase)。
5. **consistency / 专名保持 ops 不动**。

---

## 设计

### 1. 控制流对比

**现状**(7 phase,3 个全正文复写器串行):
```
Boot → Write → [L2+Repair≤3] → [Polish] → Consistency(ops) → 专名(ops) → [Style≤2] → Finalize
```

**目标**(5 phase,1 个复写器自带复测重喂):
```
Boot → Write → [Revise: manifest 驱动, 复测重喂≤2] → Consistency(ops) → 专名(ops) → Finalize
```

`meta.phases` 更新为:`Boot / Write / Revise / Consistency / Persist+Telemetry`(专名并入 Consistency phase,沿用现状)。

### 2. 核心组件

#### (a) `buildManifest(report, drift, ctx)` — 纯 JS,零 LLM

Write 之后、Revise 之前装配的统一缺陷清单:
```js
function buildManifest(report, drift, ctx) {
  const violations = (report && report.beat_violations) || []
  const mustFix = violations.filter(v => v.kind !== 'word_count_below_floor')
  const expand = violations.some(v => v.kind === 'word_count_below_floor')
  const drifted = (drift && drift.drifted) || []
  return {
    empty: mustFix.length === 0 && !expand && drifted.length === 0,
    must_fix: mustFix,                       // beat 结构/pov 违规(正确性)
    expand,                                  // 字数不足→需整章扩写
    align: drifted,                          // 实测文风漂移(dash/notXisY/修辞/对白比)
    targets: (ctx && ctx.fingerprint) || null,
    target_source: (drift && drift.target_source) || null,
    priority: (mustFix.length || expand) ? 'correctness' : 'style',
  }
}
```
- 数据源:`report` = 最近一次 `run-l2` 输出;`drift` = `style-check` 输出;`ctx.fingerprint` = boot 装配的目标分布。
- `empty=true` → Revise 跳过(0 agent)。

#### (b) `revisePrompt(ctx, manifest, prevProse)` — 合并三 prompt 为一

合并 `editRepairPrompt` / `editPolishPrompt` / `stylePolishPrompt`。结构:
```
# Edit 子代理 — 定向修订(beat/字数/文风统一收敛)
HYGIENE_RULES
[文风指令](若有) + [正反例](若有)
[manifest.priority 判定]
  - correctness: 【必须先修,不得破坏结构】beat 违规清单 + (若 expand)字数扩写指令(含禁灌水约束)
  - style:      【对准目标分布】实测漂移项 + 目标值
[另一类降为次要:不冲突时顺手]
---上一版--- prevProse
返回修订后的【整章正文】纯文本(段间空行),不裹围栏,不写标题行。
```
- `manifest.empty=true` 时不调用。
- 字数扩写复用现有 `editRepairPrompt` 的扩写规则 + 禁灌水约束(逐字搬入)。

#### (c) Revise 控制流(收束核心)

替换原 `L2+Repair` + `Polish` + `Style` 三段。**注:下方为 e2e 验证后定稿的三路分流逻辑**(初版的"破 L2 一律回退 preRevise"被 vigilia ch13/ch1 端到端证伪——见末尾"e2se 演进")。
```js
phase('Revise')
let drift = (report.passed_hard_gate && ctx.fingerprint) ? await styleCheck(project, chapter, volume) : null
_trackDrift(drift)
let manifest = buildManifest(report, drift, ctx)
let round = 0
while (!manifest.empty && round < REVISE_MAX_ROUNDS) {      // REVISE_MAX_ROUNDS = 2
  const wasCorrectness = manifest.priority === 'correctness'
  const anchorProse = prose, anchorReport = report          // 本轮前状态(仅 style 回退用)
  const revised = extractProse(await agent(revisePrompt(ctx, manifest, prose),
    { label: `Edit-revise-r${round + 1}`, phase: 'Revise' }))
  let after
  try { after = await commitAndL2(project, chapter, revised, `revise-r${round + 1}`) }
  catch (e) { log(`revise 提交被拒,保 anchor`); break }
  round++
  if (after.passed_hard_gate) {
    prose = revised; report = after
    drift = await styleCheck(...); _trackDrift(drift); manifest = buildManifest(report, drift, ctx)
  } else if (wasCorrectness) {
    // correctness 修复仍未全过(扩写未达 floor / 仍有 beat):累进接受为新基,下轮继续修剩余(复刻旧 repair 渐进语义)。不回退——回退丢部分进展。
    prose = revised; report = after
    drift = ctx.fingerprint ? await styleCheck(...) : null; _trackDrift(drift); manifest = buildManifest(report, drift, ctx)
  } else {
    // style 对准破坏了已 L2-clean 的章 → 回退 clean anchor,停(不为文风冒正确性风险)
    await commitAndL2(project, chapter, anchorProse, 'revise-revert')
    prose = anchorProse; report = anchorReport
    await pythonCli(`mark-polish-broke-beat ...`, { phase: 'Revise' })
    break
  }
}
// 收尾 flag
if (!report.passed_hard_gate) {
  await pythonCli(`mark-unresolved --rule-or-model 0`, { phase: 'Revise', stdin: JSON.stringify(report.beat_violations || []) })
} else if (manifest.align && manifest.align.length) {
  log(`revise 收敛: L2-clean, 文风仍 ${manifest.align.length} 项漂移(advisory)`)
}
```
- **复测重喂**:每轮 `buildManifest(report, drift, ctx)` 重算,下轮只喂剩余项(用户选定模型)。
- **三路分流(e2e 定稿)**:`passed`→接受续轮;`correctness` 未全过→**累进接受为新基续修**(不回退,保 partial 进展,如 r1 把 2341 扩到仍<3000 不丢、r2 续扩到 ≥3000);`style` 破坏已 clean 章→**回退 clean anchor 停**。correctness 与 style 失败语义不同,旧单次 Polish 无此区分。
- **commit 被拒**(revise 吐非正文)→ `extractProse` + commit sanitize 接住,break 保 anchor。
- 注:`styleCheck` 复测每轮一次,结果统一喂 manifest,无独立 stylePolish agent。

### 3. 删除 / 保留

- **删**:`editRepairPrompt`、`editPolishPrompt`、`stylePolishPrompt` → `revisePrompt`;`L2+Repair`/`Polish`/`Style` 三个 phase → 一个 `Revise` phase;三套 revert → 一套(`revise-revert`)。
- **保留原样**:Consistency(ops)、专名(ops/确定性,并入 Consistency phase)、`commit-paragraphs`/`run-l2`/`style-check`/`persist_gate`/`verify_chapter_persisted`/`worstDrift` 追踪/`finalize` 遥测。
- **Python 零改动**:用到的 CLI 全已存在。

### 4. agent 数对比

| 路径 | 现状 | 目标 |
|---|---|---|
| Write | 1 | 1 |
| 后置复写 | repair≤3 + polish + style≤2 = 2~6 | revise≤2 = 0~2 |
| consistency + 专名 | 1 + relay | 1 + relay(不变) |
| finalize/telemetry relay | 不变 | 不变 |
| **单章 LLM agent 合计** | **≈10+** | **≈4~5** |

最坏路径(revise 破 L2)仅 +1 回退 relay。

---

## 错误处理

- revise `passed`→接受续轮。
- revise **correctness 未全过**(扩写未达 floor / 仍有 beat)→ 累进接受为新基续修,不回退(保 partial 进展)。
- revise **style 破坏已 clean 章**→ 回退 clean anchor,停(正确性 > 风格,章保 L2-clean + advisory 漂移)。
- revise 吐非正文(日志/元文本)→ `extractProse` + commit sanitize 接住,视为失败轮 break,保 anchor。
- commit 被拒 → break 保 anchor。
- 2 轮后 L2 仍不过 → `mark-unresolved --rule-or-model 0`(既有语义;签名比对简化为 0,因合并后单阶段不做跨轮签名比对——保留钩子,后续需要再加)。
- 仅文风残留(无 must_fix)→ 不阻塞,L2-clean 即可 completed,残留记 advisory(`worstDrift`→finalize `mark-advisory-drift`)。

---

## e2e 演进(实施期发现,已并入设计)

vigilia ch13/ch1 端到端验证暴露了初版控制流的两个真实缺陷,均已修(commits `18e5b3e`、`96cbb3f`):

1. **回退锚不随成功轮推进**:初版 `preReviseProse` 在循环前一次性捕获=Write 的 r0。当 r1 扩到 ≥3000 过 L2、r2(仅 style)削回 <3000 破 L2 时,回退到 r0 短版,丢掉 r1 成功扩写。修:锚每轮重取=本轮前状态(revert to last-good,非原点)。
2. **correctness 失败错误回退**:初版"任何 L2 失败→回退+break",对 correctness 修复(扩写未达 floor)是错的——回退丢部分进展(2341→2800 仍未过却回退到 2341),且只试 1 次就放弃,_regression 了旧 repair≤3 的渐进重试。修:三路分流(correctness 失败累进续修,仅 style 破坏才回退停)。

**e2e 旁证(writer 持续欠产,非本任务范围)**:vigilia writer 跨 3 次运行恒产 2200~2600 字(目标 3000~5000),Revise expand 路径每章都在硬撑。这是 writer/字数自检(defect 8 / WC-Task3)未到位,是独立的下一个杠杆,不属本收束任务。

---

## 测试 / 验证策略

本改动在 JS 沙箱工作流,**无 Python 单测可写**(既有沙箱工作流一律靠 grep 静态检 + 端到端,见既有 commit 惯例)。

- **静态检**:`buildManifest`/`revisePrompt` 抽纯函数;grep 确认三旧 prompt 已删、`revise-revert` 回退分支存在、`meta.phases` 更新、大括号/模板字面量平衡。
- **Python 回归**:`python -m pytest tests/bedrock/ -q` 全绿(Python 零改,应稳;报告计数)。
- **端到端回归**:
  - 重跑 vigilia ch13(已知 Polish 破坏 case)→ 期望单 Revise pass、`passed_hard_gate=true`、无 `word_count_below_floor`、汉字 ≥3000、`status=completed`、agent 数下降。
  - 重跑一章干净章(如 ch1)→ 期望 r0 即 L2-pass + manifest 空 → Revise 0 迭代(无回归)。

---

## 影响面与回退

- **改动**:`.claude/workflows/bedrock-chapter.js` 中段(删 3 phase + 3 prompt,加 1 phase + `buildManifest`/`revisePrompt` + Revise 控制流)。`meta.phases` 更新。
- **不动**:Python 全部、paragraph 存储、既有 DB 章、Consistency/专名/finalize。
- **向后兼容**:既有章在 DB 不动;仅未来章走新流。
- **回退**:独立 commit(`bedrock-revise-converge` 分支),可整体 revert。
- **风险**:单 mega-prompt 对 LLM 更难 → 靠 ≤2 重试 + 回退保正确性,style 降 advisory;需 prompt 调参,回退兜底。

---

## 文件结构

**修改:**
- `.claude/workflows/bedrock-chapter.js` — `meta.phases`;删 `L2+Repair`/`Polish`/`Style` 三段 + `editRepairPrompt`/`editPolishPrompt`/`stylePolishPrompt`;加 `Revise` 段 + `buildManifest` + `revisePrompt`;复用 `commitAndL2`/`styleCheck`/`_trackDrift`/`extractProse`/`pythonCli`/`finalize`。

**新建/测试:** 无 Python 新文件;验证靠静态检 + 端到端(见上)。

**Python:** 零改动。
