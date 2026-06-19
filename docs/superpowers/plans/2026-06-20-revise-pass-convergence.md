# Revise Pass 收束(3→1)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `bedrock-chapter.js` 的三个全正文复写阶段(L2+Repair / Polish / Style)合并为一个 `Revise` 阶段(defect manifest 驱动,复测重喂 ≤2 轮),删三套 prompt 与三套 revert,局部缺陷保持 ops,Python 零改。

**Architecture:** Write 后装配一份 defect manifest(L2 违规 ∪ 字数扩写 ∪ 实测文风漂移 ∪ 目标分布,纯 JS 零 LLM),喂给单个 `revisePrompt`;每轮 commit+L2+styleCheck 复测、重算 manifest 只喂剩余缺陷;破 L2 回退 `preRevise`(Write 后已过 L2 版,agent-free)。consistency / 专名 ops 阶段不动。paragraph 存储、L2、persist_gate、CLI 全不动。

**Tech Stack:** Node 沙箱工作流(`.claude/workflows/bedrock-chapter.js`,无 Node API,CLI 经 Bash-runner relay);Python 3 + pytest 回归(`tests/bedrock/`)。

**Spec:** `docs/superpowers/specs/2026-06-20-revise-pass-convergence-design.md`

**实施:** 分支 `bedrock-revise-converge`,从 master 切。所有命令 cwd = `D:/novel_test`。

**关于 TDD 的诚实说明:** 本改动全在 JS 沙箱工作流内,**无 Python 单测可写**(沙箱 JS 不被 Python 测试导入;既有沙箱工作流一律靠 grep 静态检 + 端到端验证,见既有 commit 惯例)。故"测试"步骤为:静态 grep 断言 + `pytest tests/bedrock/` 回归(应全绿,因 Python 零改)+ 端到端 vigilia 章节回归。这是本仓库的既定惯例,非偷懒。

**关键事实(已核实,基于本会话读取的 `bedrock-chapter.js` 当前内容):**
- `meta.phases` 当前 7 项:`Boot / Write / L2+Repair / Polish / Consistency / Style / Persist+Telemetry`。
- 主流程顺序:Boot(43-45)→ Write(47-52)→ **L2+Repair(54-73)** → **Polish(75-94)** → Consistency(96-120)→ 专名(122-134,在 Consistency phase 下)→ **Style(136-172)** → Finalize(174-182)。
- 三旧 prompt:`editRepairPrompt`(374-389)、`editPolishPrompt`(390-401)、`stylePolishPrompt`(216-230)。
- 复用函数:`commitAndL2(project, chapter, prose, label)`(200-204)、`styleCheck(project, chapter, volume)`(207-211,返 `{drifted, target_source, ...}`)、`pct(x)`(213)、`extractProse(s)`(404-409)、`_trackDrift(drift)`(413-417)、`pythonCli(cmdStr, opts)`(312-327)、`HYGIENE_RULES`(28-34)、`finalize(project, chapter, exportPath, round, drift)`(279-286,第 4 参 `round` 用于遥测 `--editing-rounds`)。
- Finalize 调用(176):`finalize(project, chapter, exportPath, round, worstDrift)` —— Revise 段必须定义 `round`(revise 迭代数),保持 finalize 签名不变。

---

## File Structure

**修改(唯一文件):**
- `.claude/workflows/bedrock-chapter.js`
  - `meta.phases`:7→5(删 `L2+Repair`/`Polish`/`Style`,加 `Revise`)。
  - 顶部加 `REVISE_MAX_ROUNDS = 2` 常量。
  - 加 `buildManifest(report, drift, ctx)` + `revisePrompt(ctx, manifest, prevProse)` 两个函数。
  - 主流程:删 `L2+Repair`+`Polish`+`Style` 三段,替换为单一 `Revise` 段。
  - 删 `editRepairPrompt` / `editPolishPrompt` / `stylePolishPrompt` 三函数。

**新建/测试:** 无 Python 新文件。

**Python:** 零改动。

---

## Task 1: 建分支 + 更新 `meta.phases` + 加 `REVISE_MAX_ROUNDS` 常量

**Files:**
- Modify: `.claude/workflows/bedrock-chapter.js`(`meta.phases` line 4-12;`worstDrift` 声明 line 36-37)

- [ ] **Step 1: 建分支**

Run:
```bash
cd D:/novel_test && git checkout -b bedrock-revise-converge master
```
Expected: `Switched to a new branch 'bedrock-revise-converge'`

- [ ] **Step 2: 更新 `meta.phases`**

Edit `.claude/workflows/bedrock-chapter.js`,把:
```js
  phases: [
    { title: 'Boot' },
    { title: 'Write' },
    { title: 'L2+Repair' },
    { title: 'Polish' },
    { title: 'Consistency' },
    { title: 'Style' },
    { title: 'Persist+Telemetry' },
  ],
```
替换为:
```js
  phases: [
    { title: 'Boot' },
    { title: 'Write' },
    { title: 'Revise' },
    { title: 'Consistency' },
    { title: 'Persist+Telemetry' },
  ],
```
同步更新 `meta.description`(line 3),把:
```
  description: '磐石 V3 单章管线：Boot→Write→commit+L2→Repair(≤3轮)→Polish(指纹门控)→Consistency(角色正典)→Style(漂移测量+收敛)→Finalize',
```
替换为:
```
  description: '磐石 V3 单章管线：Boot→Write→commit+L2→Revise(manifest 驱动定向修订,复测重喂≤2)→Consistency(角色正典 ops)→专名(ops)→Finalize',
```

- [ ] **Step 3: 加 `REVISE_MAX_ROUNDS` 常量**

定位(line 36-37):
```js
// drift 最差轮累积器（须在主流程调用前初始化，避 TDZ）
let worstDrift = {}
```
在其**后面**插入:
```js

// Revise 复测重喂上限(收束原 repair≤3 + style≤2,合并取严的 2)。
const REVISE_MAX_ROUNDS = 2
```

- [ ] **Step 4: 静态确认**

Run:
```bash
cd D:/novel_test && grep -n "title: 'Revise'\|REVISE_MAX_ROUNDS" .claude/workflows/bedrock-chapter.js
```
Expected: 见 `{ title: 'Revise' }` 与 `const REVISE_MAX_ROUNDS = 2` 两行;**不再**见 `title: 'L2+Repair'` / `'Polish'` / `'Style'`。

- [ ] **Step 5: Commit**

```bash
cd D:/novel_test && git add .claude/workflows/bedrock-chapter.js && git commit -m "$(cat <<'EOF'
refactor(bedrock-chapter): meta.phases 7→5 + REVISE_MAX_ROUNDS 常量(Revise 收束准备)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 加 `buildManifest` + `revisePrompt`(不删旧 prompt)

**Files:**
- Modify: `.claude/workflows/bedrock-chapter.js`(在 `chapterWriterPrompt` 函数之后、`editRepairPrompt` 之前插入两新函数)

> 设计原则:本任务只**新增**,不动旧 prompt 与主流程。这样每个 commit 后文件仍自洽(旧 prompt 暂时冗余但被引用,Task 4 再删)。

- [ ] **Step 1: 插入 `buildManifest` 与 `revisePrompt`**

定位 `chapterWriterPrompt` 函数结束处(其最后一行 `}` 之后、`function editRepairPrompt` 之前)。把:
```js
function editRepairPrompt(report, prevProse) {
```
替换为(在新函数之前插入):
```js
// defect manifest 装配(纯 JS,零 LLM):合并 L2 违规 + 字数扩写 + 实测文风漂移 + 目标分布。
// 优先级:must_fix(beat 结构/pov)非空或需 expand → correctness 主;否则 style 主。empty=true → Revise 跳过。
function buildManifest(report, drift, ctx) {
  const violations = (report && report.beat_violations) || []
  const mustFix = violations.filter(v => v.kind !== 'word_count_below_floor')
  const expand = violations.some(v => v.kind === 'word_count_below_floor')
  const align = (drift && Array.isArray(drift.drifted)) ? drift.drifted : []
  return {
    empty: mustFix.length === 0 && !expand && align.length === 0,
    must_fix: mustFix,
    expand,
    align,
    targets: (ctx && ctx.fingerprint) || null,
    target_source: (drift && drift.target_source) || null,
    priority: (mustFix.length || expand) ? 'correctness' : 'style',
  }
}

// 定向修订 prompt(合并原 editRepair/editPolish/stylePolish)。manifest 驱动,正确性硬压文风。
// correctness 优先级:先列 L2 硬违规(必改)+ 字数扩写指令,文风降为"不冲突时顺手"。
// style 优先级:只对准实测漂移。manifest.empty 时不调用(由调用方判)。
function revisePrompt(ctx, manifest, prevProse) {
  const lines = [
    '# Edit 子代理 — 定向修订(beat/字数/文风统一收敛)',
    HYGIENE_RULES,
  ]
  if (ctx.style_directive) lines.push('', `【文风指令·定性】${ctx.style_directive}`)
  const ex = ctx.style_examples || {}
  if ((ex.good && ex.good.length) || (ex.bad && ex.bad.length)) {
    lines.push('', '【风格示范】(对照节奏/密度/句式,严禁复述范例原文)')
    ;(ex.good || []).forEach(s => lines.push(`  ✓ ${s}`))
    ;(ex.bad || []).forEach(s => lines.push(`  ✗ ${s}(避免)`))
  }
  if (manifest.priority === 'correctness') {
    lines.push('', '【必须先修·不得破坏结构】下面是 L2 硬违规(beat_id / kind / detail / fix_hint):')
    manifest.must_fix.forEach(v => lines.push(`  - beat${v.beat_id} [${v.kind}]: ${v.detail} → ${v.fix_hint}`))
    if (manifest.expand) {
      lines.push('', '【字数不足·须扩写至下限以上】在现有剧情骨架上增场景细节/感官/心理/对白展开,丰富而非重复。不引入新违规,不压缩剧情。')
      lines.push('【禁灌水】不得无信息扩写、不得重复同一意思、不得堆砌形容词、不得注水对话。扩写须服务于人物/氛围/情节推进;扩写后仍须过文风门禁(修辞密度/对白比/破折号)。')
    }
    if (manifest.align.length) {
      lines.push('', '【次要·文风对准】结构修复后,在不冲突前提下顺手对准(不为此冒险):')
      manifest.align.forEach(d => lines.push(`  - ${d.hint}(实测${pct(d.actual)}/目标${pct(d.target)})`))
    }
  } else {
    lines.push('', `【对准目标分布·文风定向收敛】实测漂移(目标分布: ${JSON.stringify(manifest.targets || {})})`)
    manifest.align.forEach(d => lines.push(`  - ${d.hint}(实测${pct(d.actual)}/目标${pct(d.target)})`))
    lines.push('做最小改动收敛(如删非必要破折号→换句号断句、改"不是A是B"句式、减过密比喻)。')
  }
  lines.push('', '保持剧情/字数下限/beat 结构/pov 不变,不引入新问题。返回修订后的【整章正文】纯文本(段间空行),不裹围栏,不写标题行。')
  lines.push('', '---上一版---', prevProse)
  return lines.join('\n')
}

function editRepairPrompt(report, prevProse) {
```

- [ ] **Step 2: 静态确认**

Run:
```bash
cd D:/novel_test && grep -n "function buildManifest\|function revisePrompt" .claude/workflows/bedrock-chapter.js
```
Expected: 两行均出现,且 `buildManifest` 在 `revisePrompt` 之前。

Run(大括号/模板字面量平衡 sanity):
```bash
cd D:/novel_test && grep -c "pct(" .claude/workflows/bedrock-chapter.js
```
Expected: 计数 ≥3(`pct` 函数定义 + revisePrompt 内引用)。

- [ ] **Step 3: Commit**

```bash
cd D:/novel_test && git add .claude/workflows/bedrock-chapter.js && git commit -m "$(cat <<'EOF'
feat(bedrock-chapter): 加 buildManifest + revisePrompt(Revise 收束,暂保留旧 prompt)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 主流程——删 L2+Repair + Polish + Style 三段,替换单一 Revise 段

**Files:**
- Modify: `.claude/workflows/bedrock-chapter.js`(主流程 line 54-73、75-94、136-172)

> 本任务改主流程。完成后主流程不再调用三旧 prompt(但它们仍存在,Task 4 删)。`round` 变量由 Revise 段定义,供 finalize 复用。

- [ ] **Step 1: 删 L2+Repair 段 + Polish 段,替换为 Revise 段**

定位(line 54-94,从 `// 3. L2 + Repair 循环` 注释到 Polish 段结束的 `}`)。把整段:
```js
// 3. L2 + Repair 循环（≤3 轮；签名比对、likely_rule_or_model 仍在 JS）
phase('L2+Repair')
let round = 0
const sigsByRound = []
while (!report.passed_hard_gate && round < 3) {
  sigsByRound.push((report.beat_violations || []).map(v => `${v.beat_id}:${v.kind}`).sort().join(','))
  prose = extractProse(await agent(editRepairPrompt(report, prose), { label: `Edit-repair-r${round + 1}`, phase: 'L2+Repair' }))
  report = await commitAndL2(project, chapter, prose, `repair-r${round + 1}`)
  _trackDrift(report)
  round++
  log(`L2 r${round} passed=${report.passed_hard_gate} violations=${(report.beat_violations || []).length}`)
}
const likelyRuleOrModel = round === 3
    && new Set(sigsByRound.slice(-2)).size === 1 && !report.passed_hard_gate
if (!report.passed_hard_gate) {
  await pythonCli(
    `mark-unresolved --project ${project} --chapter ${chapter} --rule-or-model ${likelyRuleOrModel ? 1 : 0}`,
    { phase: 'L2+Repair', stdin: JSON.stringify(report.beat_violations || []) })
  log(`l2 unresolved after 3 rounds, likely_rule_or_model=${likelyRuleOrModel}`)
}

// 4. Polish：仅当有 style fingerprint 才跑（无指纹时是空过，省 2 agent）
phase('Polish')
if (report.passed_hard_gate && ctx.fingerprint) {
  const preProse = prose, preReport = report   // 阶段前 L2-pass 快照(含 Repair 扩写的 ≥3000 字)
  const polished = extractProse(await agent(editPolishPrompt(ctx, preProse), { label: 'Edit-polish', phase: 'Polish' }))
  const after = await commitAndL2(project, chapter, polished, 'polish')
  _trackDrift(after)
  if (after.passed_hard_gate) {
    prose = polished; report = after
    log('polish ok')
  } else {
    // Polish 破坏 L2(beat/word_count)→ 回退 pre-Polish(已过 L2)。+1 relay 重 commit;0 新 agent。
    await commitAndL2(project, chapter, preProse, 'polish-revert')
    prose = preProse; report = preReport
    await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`, { phase: 'Polish' })
    log('polish 破坏 L2 → 回退 pre-Polish 版(风格该轮未应用,正确性优先)')
  }
} else {
  log('polish skipped (no fingerprint or L2 not passed)')
}
```
替换为:
```js
// 3. Revise：defect manifest 驱动的定向修订(beat/字数/文风统一收敛),复测重喂≤REVISE_MAX_ROUNDS 轮。
// 收束原 L2+Repair/Polish/Style 三段为一个变异阶段:每轮 commit+L2+styleCheck 复测、重算 manifest 只喂剩余缺陷。
// 破 L2 回退 preRevise(Write 后已过 L2 版,agent-free);commit 被拒 break 保 preRevise。正确性硬压文风。
phase('Revise')
let drift = (report.passed_hard_gate && ctx.fingerprint)
  ? await styleCheck(project, chapter, volume) : null
_trackDrift(drift)
let manifest = buildManifest(report, drift, ctx)
const preReviseProse = prose, preReviseReport = report   // Write 后 L2-pass 快照(回退锚)
let round = 0
while (!manifest.empty && round < REVISE_MAX_ROUNDS) {
  const revised = extractProse(await agent(revisePrompt(ctx, manifest, prose),
    { label: `Edit-revise-r${round + 1}`, phase: 'Revise' }))
  let after
  try {
    after = await commitAndL2(project, chapter, revised, `revise-r${round + 1}`)
  } catch (e) {
    log(`revise r${round + 1} 提交被拒(返回非正文?),保 preRevise: ${String(e.message || e).slice(0, 80)}`)
    break
  }
  if (!after.passed_hard_gate) {
    // revise 破 L2(beat/word_count)→ 回退 preRevise(已过 L2)。+1 relay;0 新 agent。
    await commitAndL2(project, chapter, preReviseProse, 'revise-revert')
    prose = preReviseProse; report = preReviseReport
    await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`, { phase: 'Revise' })
    log('revise 破坏 L2 → 回退 preRevise 版(正确性优先,该轮未应用)')
    break
  }
  prose = revised; report = after
  round++
  drift = await styleCheck(project, chapter, volume); _trackDrift(drift)
  manifest = buildManifest(report, drift, ctx)
  log(`revise r${round} 复测: must_fix=${manifest.must_fix.length} expand=${manifest.expand ? 1 : 0} align=${manifest.align.length}`)
}
if (!report.passed_hard_gate) {
  await pythonCli(
    `mark-unresolved --project ${project} --chapter ${chapter} --rule-or-model 0`,
    { phase: 'Revise', stdin: JSON.stringify(report.beat_violations || []) })
  log(`revise 未过 L2(${round} 轮耗尽)→ mark-unresolved`)
} else if (manifest.align && manifest.align.length) {
  log(`revise 收敛: L2-clean, 文风仍 ${manifest.align.length} 项漂移(advisory,经 worstDrift 记录)`)
} else {
  log(`revise 收敛完成 [${manifest.target_source || '无目标'}]`)
}
```

- [ ] **Step 2: 删 Style 段**

定位(line 136-172,从 `// 4c. Style` 注释到其结束 `}`)。把整段:
```js
// 4c. Style：章级文风漂移测量 + 定向收敛闭环(循环≤2 轮,回喂剩余 hint)。
// 写后测标量 vs 目标(卷级→作品级→自洽),飘→style-polish→重 L2→复测;仍有飘则再喂剩余项,
// 直到不飘或达上限。破 beat 立即停+flag。单章噪声大,只对明显偏离(dash/notXisY/修辞/对白比)动手。
const STYLE_MAX_ROUNDS = 2
phase('Style')
if (report.passed_hard_gate) {
  let drift = await styleCheck(project, chapter, volume)
  _trackDrift(drift)
  let sr = 0
  while (drift && drift.drifted && drift.drifted.length && sr < STYLE_MAX_ROUNDS) {
    const hints = drift.drifted.map(d => `${d.hint}(实测${pct(d.actual)}/目标${pct(d.target)})`).join('；')
    log(`style drift r${sr + 1}: ${drift.drifted.length}项 [${drift.target_source}] → ${hints}`)
    const prose = extractProse(await agent(stylePolishPrompt(ctx, hints, project, chapter),
      { label: `Edit-style-r${sr + 1}`, phase: 'Style' }))
    let after
    try {
      after = await commitAndL2(project, chapter, prose, `style-r${sr + 1}`)
    } catch (e) {
      // commit-paragraphs 拒绝(style-polish 返回工作日志/非正文)→ 不崩,跳过本轮,保留已过 L2 的版本
      log(`style-polish r${sr + 1} 提交被拒(返回非正文?),跳过: ${String(e.message || e).slice(0, 80)}`)
      break
    }
    if (!after.passed_hard_gate) {
      await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`, { phase: 'Style' })
      log('style-polish broke beat → flagged,停收敛')
      break
    }
    report = after
    drift = await styleCheck(project, chapter, volume)   // 复测,下轮只喂仍飘的项
    _trackDrift(drift)
    sr++
    log(`style r${sr} 收敛后复测: ${drift.drifted ? drift.drifted.length : 0}项仍飘`)
  }
  const left = drift && drift.drifted ? drift.drifted.length : 0
  if (left === 0) log(`style: 收敛完成(0 项飘) [${(drift && drift.target_source) || '无目标'}]`)
  else if (sr >= STYLE_MAX_ROUNDS) log(`style: 仍 ${left} 项飘(${(drift.drifted || []).map(d => d.metric).join('/')}),达 ${STYLE_MAX_ROUNDS} 轮上限`)
}
```
整段删除(替换为空)。删后,专名段(其上方)直接接 Finalize 段。

- [ ] **Step 3: 静态确认主流程已切换**

Run:
```bash
cd D:/novel_test && grep -n "phase('Revise')\|phase('L2+Repair')\|phase('Polish')\|phase('Style')\|revise-revert" .claude/workflows/bedrock-chapter.js
```
Expected: **只见** `phase('Revise')` 与 `revise-revert`;**不再见** `phase('L2+Repair')` / `phase('Polish')` / `phase('Style')`。

Run(确认主流程不再调用旧 repair/polish/style prompt;consistency 不受影响):
```bash
cd D:/novel_test && grep -n "revisePrompt(\|editRepairPrompt(\|editPolishPrompt(\|stylePolishPrompt(" .claude/workflows/bedrock-chapter.js
```
Expected: `revisePrompt(` 在主流程出现(≥1);`editRepairPrompt(`/`editPolishPrompt(`/`stylePolishPrompt(` **仅在各自函数定义行出现**(不再在主流程被调用)。Task 4 会删掉这些定义。

- [ ] **Step 4: Commit**

```bash
cd D:/novel_test && git add .claude/workflows/bedrock-chapter.js && git commit -m "$(cat <<'EOF'
refactor(bedrock-chapter): 主流程 L2+Repair/Polish/Style 三段→单一 Revise 段(manifest 驱动,复测重喂≤2)

- 删 L2+Repair + Polish + Style 三段,替为 Revise:buildManifest 装配缺陷→revisePrompt→commit+L2+styleCheck 复测→重算 manifest 只喂剩余
- 破 L2 回退 preRevise(agent-free);commit 被拒 break 保 preRevise
- round 由 Revise 定义,finalize 签名不变
- 单章后置复写 agent:repair≤3+polish+style≤2 → revise≤2

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 删除已废弃的三旧 prompt 函数

**Files:**
- Modify: `.claude/workflows/bedrock-chapter.js`(`editRepairPrompt` 374-389、`editPolishPrompt` 390-401、`stylePolishPrompt` 216-230)

- [ ] **Step 1: 删 `editRepairPrompt` + `editPolishPrompt`**

定位(两函数相邻,Task 2 之后 `editRepairPrompt` 前多了新函数,但这两个旧函数体本身未动)。把:
```js
function editRepairPrompt(report, prevProse) {
  const lines = ['# Edit 子代理 — 定向修复', '违规清单（beat_id / kind / detail / fix_hint）：']
  for (const v of (report.beat_violations || [])) {
    lines.push(`  - beat${v.beat_id} [${v.kind}]: ${v.detail} → ${v.fix_hint}`)
  }
  const needExpand = (report.beat_violations || []).some(v => v.kind === 'word_count_below_floor')
  const rule = needExpand
    ? '本章字数不足(见 word_count_below_floor)。须【扩写】至下限以上:在现有剧情骨架上增场景细节/感官/心理/对白展开,丰富而非重复。不引入新违规,不压缩剧情。'
    : '下面是上一版整章正文。只改与违规相关段落,不引入新违规,不压缩剧情,保持其余原文。'
  lines.push('', rule)
  if (needExpand) {
    lines.push('【禁灌水】不得无信息扩写、不得重复同一意思、不得堆砌形容词、不得注水对话。扩写须服务于人物/氛围/情节推进;扩写后仍须过文风门禁(修辞密度/对白比/破折号)。')
  }
  lines.push('返回修订后的【整章正文】纯文本(段间空行),不裹围栏,不写标题行。', '', '---上一版---', prevProse)
  return lines.join('\n')
}
function editPolishPrompt(ctx, prevProse) {
  return [
    '# Edit 子代理 — 正向润色',
    '目标分布:', JSON.stringify(ctx.fingerprint || {}, null, 2),
    '本章 beat 契约:', JSON.stringify(ctx.beat_contracts, null, 2),
    '',
    HYGIENE_RULES,
    '把当前正文往目标分布微调的同时,严格执行上面的文风硬约束(标点全角/清掉"不是A是B"句式/删非必要破折号)。',
    '保持剧情、beat 结构完整、汉字数不低于下限;不删段、不合并/拆分 beat、不降字数。仅做风格微调(句式/对白/破折号/修辞密度对准目标分布)。',
    '返回润色后的【整章正文】纯文本，不裹围栏。', '', '---当前版---', prevProse,
  ].join('\n')
}
```
整段删除(替换为空)。

- [ ] **Step 2: 删 `stylePolishPrompt`**

定位(line 216-230):
```js
// 文风定向收敛 prompt：agent 读当前正文,针对测量出的漂移项做最小改动(删破折号/改句式/减比喻)。
function stylePolishPrompt(ctx, hints, project, chapter) {
  return [
    '# Edit 子代理 — 文风定向收敛（按测量出的漂移修）',
    `先读本章当前正文(只读): cd "${CWD}" && python -m src.bedrock show-paragraphs --project ${project} --chapter ${chapter}`,
    '把返回 JSON 每段 text 按原顺序拼成当前正文。',
    '',
    HYGIENE_RULES,
    ctx.style_directive ? `【文风指令】${ctx.style_directive}` : '',
    '【本章测量出的文风漂移——必须定向修正这些项】',
    hints,
    '',
    '针对上面漂移做最小改动收敛(如删非必要破折号→换句号断句、改"不是A是B"句式、减过密比喻),',
    '保持剧情/字数/beat/pov 不变,不引入新问题。返回修订后的【整章正文】纯文本(段间空行),不裹围栏,不写标题行。',
  ].join('\n')
}
```
整段删除(替换为空)。删时连上方注释行一并删。

- [ ] **Step 3: 静态确认三旧 prompt 已无残留**

Run:
```bash
cd D:/novel_test && grep -n "editRepairPrompt\|editPolishPrompt\|stylePolishPrompt\|STYLE_MAX_ROUNDS" .claude/workflows/bedrock-chapter.js
```
Expected: **零输出**(三函数名与 `STYLE_MAX_ROUNDS` 在文件中彻底消失)。

Run(确认保留函数仍在):
```bash
cd D:/novel_test && grep -n "function revisePrompt\|function buildManifest\|function consistencyPrompt\|function chapterWriterPrompt" .claude/workflows/bedrock-chapter.js
```
Expected: 四行均出现。

- [ ] **Step 4: Commit**

```bash
cd D:/novel_test && git add .claude/workflows/bedrock-chapter.js && git commit -m "$(cat <<'EOF'
refactor(bedrock-chapter): 删废弃的 editRepair/editPolish/stylePolish 三 prompt

已被统一 revisePrompt 取代。STYLE_MAX_ROUNDS 一并删(并入 REVISE_MAX_ROUNDS)。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 静态总检 + Python 回归

**Files:** 无改动;运行验证

- [ ] **Step 1: 整体结构 sanity(大括号/模板字面量平衡)**

Run:
```bash
cd D:/novel_test && grep -c "phase('" .claude/workflows/bedrock-chapter.js
```
Expected: `5`(Boot/Write/Revise/Consistency/Persist+Telemetry)。

Run:
```bash
cd D:/novel_test && grep -n "phase('" .claude/workflows/bedrock-chapter.js
```
Expected: 5 行,顺序为 Boot → Write → Revise → Consistency → Persist+Telemetry。

Run(主流程关键变量都有定义):
```bash
cd D:/novel_test && grep -n "let round\|let manifest\|preReviseProse\|let prose\|let report" .claude/workflows/bedrock-chapter.js
```
Expected: `let prose`、`let report`(Write 段)、`let round = 0`、`let manifest`、`preReviseProse`(Revise 段)均出现。

Run(目检模板字面量无破损——revisePrompt 内 `${...}` 计数):
```bash
cd D:/novel_test && grep -c "manifest\." .claude/workflows/bedrock-chapter.js
```
Expected: 计数 ≥6(buildManifest 返回字段 + revisePrompt 引用)。

- [ ] **Step 2: Python 全套回归(Python 零改,应全绿)**

Run:
```bash
cd D:/novel_test && python -m pytest tests/bedrock/ -q
```
Expected: 全 PASS,无失败(此前 319 tests,本任务不改 Python,计数应稳定)。报告计数与失败数。

- [ ] **Step 3: 若有失败——定位**

若 Step 2 有失败,**几乎必然是误改了 Python 或 grep 误判**,而非本设计所致(本任务 Python 零改)。先 `git diff master -- src/` 确认 src/ 无改动;若有,回退该改动。若 src/ 干净仍失败,记录失败用例,上报(可能是既有 flaky)。

---

## Task 6: 端到端回归——vigilia ch13 自愈 + 干净章 0 迭代

**Files:** 无改动;运行工作流验证

> 这是验收核心:证明单 Revise pass 能让已知 Polish-破坏章(ch13)自愈,且干净章不触发任何 revise agent(0 迭代)。ch13 此前以破损态(`polish_broke_beat=1` + `word_count_below_floor` + 2946 字)却 `completed`;重跑应得 L2-clean + completed,且 agent 数不增。

- [ ] **Step 1: 重跑 vigilia ch13**

调用(经 Workflow 工具,本会话或新派):
```
Workflow({ scriptPath: ".claude/workflows/bedrock-chapter.js",
           args: { project: "projects/vigilia", chapter: 13, volume: 2 } })
```
> 注:`volume` 传卷号;ch13 在第 2 卷。若不确定卷 id,先 `python -m src.bedrock list-chapters` 无此 CLI,改用 MCP `list_chapters` 查 ch13 的 `volume_id`,或 `list_volumes` 查第 2 卷 id。workflow 的 `volume` 参数历史上接受卷号(boot-context 用)。

- [ ] **Step 2: 核对 ch13 终态**

Run:
```bash
cd D:/novel_test && python -m src.bedrock run-l2 --project projects/vigilia --chapter 13
```
Expected: JSON 输出 `passed_hard_gate=true`,**无** `word_count_below_floor` 违规,汉字数 ≥3000。

Run(状态 + flag):
```bash
cd D:/novel_test && python -m src.bedrock get-review-flag --project projects/vigilia --chapter 13
```
Expected: `status=completed`,`has_flag` 视情况(若该轮 revise 破过 L2 则 `polish_broke_beat=1`,但终态仍 L2-clean + completed)。

- [ ] **Step 3: 核对 agent 数未膨胀**

从 Workflow 完成通知的 usage 看 `agent_count`。Expected: 与普通章相当(约 4~6 LLM agent),**不应**回到旧流的 10+。若 revise 破过 L2,失败路径 +1 回退 relay(非新 agent)。

- [ ] **Step 4: 干净章 0 迭代回归(ch1)**

调用:
```
Workflow({ scriptPath: ".claude/workflows/bedrock-chapter.js",
           args: { project: "projects/vigilia", chapter: 1, volume: 1 } })
```
Expected(完成后):日志见 Revise 段 `manifest.empty=true` → while 循环 0 次迭代 → **无 `Edit-revise-*` agent**。终态 L2-clean + completed。证明 Write 一次过、无回归。

- [ ] **Step 5: 若 ch13 未自愈——诊断**

若 ch13 重跑后仍 `word_count_below_floor` 或 L2 不过:
- 看 Workflow 日志:Revise 段是否进了 `manifest.priority==='correctness'` + `expand=true` 分支(revisePrompt 是否含扩写指令)。
- 若 revise 跑了但字数仍不足:可能是 revisePrompt 扩写指令被 LLM 忽略 → 记录,视为 prompt 调参问题(回退兜底保 L2-clean,但字数未达标 → mark-unresolved,章不 completed,这是正确行为)。
- 若 revise 破 L2 → 日志应有 `revise 破坏 L2 → 回退 preRevise 版`,终态应仍 L2-clean(回退的是 Write 后版;若 Write 后版本身字数不足则需 Repair——此时 manifest 会含 word_count_below_floor,Revise 第 1 轮应扩写)。记录实际链路,上报。

---

## Self-Review

**Spec 覆盖:**
- 控制流 7→5 phase、删 L2+Repair/Polish/Style 加 Revise → Task 1(meta)+ Task 3(主流程)✓
- `buildManifest`(纯 JS,优先级 correctness/style,empty 跳过)→ Task 2 ✓
- `revisePrompt`(合并三 prompt,manifest 驱动)→ Task 2 ✓
- 复测重喂 ≤2(`REVISE_MAX_ROUNDS`)→ Task 1(常量)+ Task 3(while 循环)✓
- 破 L2 回退 preRevise(agent-free)→ Task 3 Step 1 ✓
- commit 被拒 break 保 preRevise → Task 3 Step 1 ✓
- 收尾 mark-unresolved / advisory → Task 3 Step 1 ✓
- 删三旧 prompt → Task 4 ✓
- consistency / 专名 ops 不动 → Task 3 未触碰(只删 L2+Repair/Polish/Style)✓
- Python 零改 → Task 5 Step 2 验证 ✓
- 静态检 + pytest + 端到端 → Task 5 + Task 6 ✓

**Placeholder 扫描:** 无 TBD/TODO;每个步骤含完整代码块或确切命令 + 期望输出。✓

**类型/签名一致:**
- `buildManifest(report, drift, ctx)` → 返 `{empty, must_fix, expand, align, targets, target_source, priority}`;Task 2 定义、Task 3 调用,字段名一致(`manifest.empty`/`must_fix`/`expand`/`align`/`target_source`/`priority`)✓
- `revisePrompt(ctx, manifest, prevProse)` → Task 2 定义、Task 3 调用签名一致 ✓
- `styleCheck(project, chapter, volume)` 返 `{drifted:[...], target_source}` → buildManifest 读 `drift.drifted`/`drift.target_source`,与既有 `styleCheck` 返回结构一致(见 spec + 既有 Style 段用法)✓
- `commitAndL2(project, chapter, prose, label)`、`pct(x)`、`extractProse(s)`、`_trackDrift(drift)`、`pythonCli(cmd, opts)`、`HYGIENE_RULES`、`finalize(..., round, ...)` —— 均既有,Task 3 复用签名未改 ✓
- `report.beat_violations[].{beat_id,kind,detail,fix_hint}`、`drift.drifted[].{hint,actual,target,metric}` —— 与既有 editRepair/stylePolish 读取的字段一致 ✓

**需 impl 核实:**
- Task 6 Step 1 的 `volume` 参数:历史工作流调用传卷号;若 boot-context 需卷 id 而非卷号,先用 MCP `list_volumes` 查第 2 卷 `id`,改传 id。这是运行参数,不影响代码。
- Task 3 Step 2 删 Style 段后,专名段(其上方)与 Finalize 段之间不应留空注释块;目检确认。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-20-revise-pass-convergence.md`. **分支 `bedrock-revise-converge`(Task 1 Step 1 创建)。** 两种执行方式:

1. **Subagent-Driven(推荐)** — 每 Task 派新 subagent + 两阶段 review(spec 合规 + 代码质量)。本计划 6 Task,前 4 Task 是同文件 JS 编辑(串行,不并行),Task 5/6 是验证。
2. **Inline Execution** — 本会话批量执行带 checkpoint。

选哪种?
