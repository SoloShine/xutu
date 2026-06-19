# Stateful Editor Agent(模式 2)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `bedrock-chapter.js` 的 Revise 槽位从"JS 驱动 N 个失忆 agent 轮"换成一个 stateful 工具型 editor agent(自带 Bash 直调 bedrock CLI,内部循环自纠错),消灭轮间失忆(反复修根因)+ 收敛 relay(单章 agent ~17→~7)。

**Architecture:** 工作流确定性骨架不动(Boot→Write→Revise→Consistency→专名→Finalize 序列/交接/最终 verify-persisted 判决全留 JS)。Revise 槽位 = 一次 `agent(editorPrompt, {agentType:'general-purpose'})`,editor 内部 show-paragraphs→run-l2→commit→复测→收敛。两条红线:①固定编排留 JS;②收敛由确定性 L2 客观判——JS 用独立 `l2Report` relay 复核(editor 自报 converged **不算数**),Finalize verify-persisted 终审,双 gate。

**Tech Stack:** Node 沙箱工作流(`.claude/workflows/bedrock-chapter.js`,无 Node API,CLI 经 agent relay);Python 3 + pytest 回归(`tests/bedrock/`)。

**Spec:** `docs/superpowers/specs/2026-06-20-stateful-editor-agent-design.md`

**实施:** 分支 `bedrock-stateful-editor`,从 master 切。所有命令 cwd = `D:/novel_test`。

**关于 TDD 的诚实说明:** 全改动在 JS 沙箱工作流,**无 Python 单测**(沙箱 JS 不被 Python 导入;既有惯例靠 grep 静态检 + 端到端)。故"测试"步 = 静态 grep/`node --check` + `pytest tests/bedrock/` 回归(Python 零改应全绿)+ 端到端 vigilia 章节回归 + 设计期 spike。

**关键事实(已核实,基于本会话读取的合并后 `bedrock-chapter.js`):**
- 当前 Revise 段(行 ~55-108)是"三路分流"版本:`buildManifest` + `while (!manifest.empty && round < REVISE_MAX_ROUNDS)` + `revisePrompt` + anchorProse 三路。
- 复用函数:`l2Report(project, chapter, phase)`(独立 L2 relay,返 `{passed_hard_gate, beat_violations, metrics}`)、`extractProse(s)`、`pythonCli(cmd, opts)`、`_trackDrift(drift)`、`HYGIENE_RULES`、`commitAndL2(...)`(Consistency 回退仍用,**保留**)、`finalize(project, chapter, exportPath, round, worstDrift)`(第 4 参 `round` 用于遥测)。
- `let prose`、`let report` 在 Write 段声明(模块作用域),Revise/Consistency 复用(重赋值,勿重新声明)。
- **集成坑(spec 未显式):editor 改 DB 后,JS 侧 `prose` 变量陈旧;而 Consistency 回退快照 `preConsistencyProse = prose`。故 Revise 段须在 editor 后刷新 `prose`(新增 `readCurrentProse` relay 读 DB),否则 Consistency 回退会丢 editor 成果。**

---

## File Structure

**修改(唯一文件):** `.claude/workflows/bedrock-chapter.js`
- 加:`editorPrompt(ctx, project, chapter, volume)`、`readCurrentProse(project, chapter)`。
- 改:Revise 段(三路分流 while-loop → 单 `agent()` 调度 + 独立 l2Report 复核 + prose 刷新 + mark-unresolved/advisory)。
- 删:`buildManifest`、`revisePrompt`、`REVISE_MAX_ROUNDS`(Task 3 后全部失引用)。

**新建/测试:** 无 Python 新文件;spike + 静态检 + 端到端。

**Python:** 零改动。

---

## Task 1: 建分支 + 加 `editorPrompt` 与 `readCurrentProse`(不接线)

**Files:**
- Modify: `.claude/workflows/bedrock-chapter.js`

> 设计原则:本任务只**新增**两个函数,不动主流程、不删旧代码。文件每 commit 后仍自洽(新函数暂未被调用)。

- [ ] **Step 1: 建分支**

Run:
```bash
cd D:/novel_test && git checkout -b bedrock-stateful-editor master
```
Expected: `Switched to a new branch 'bedrock-stateful-editor'`

- [ ] **Step 2: 插入 `editorPrompt` 函数**

定位 `function revisePrompt(ctx, manifest, prevProse) {`(当前 Revise 三路版用的 prompt)。在它**之前**插入新函数(把 `function revisePrompt(ctx, manifest, prevProse) {` 这一行替换为下面两函数 + 原行):

```js
// stateful 工具型 editor agent 的 prompt(替代失忆 revisePrompt)。editor 自带 Bash 直调 bedrock CLI,
// 内部循环自纠错:相1保 L2 过(修 beat/扩字数,累进接受)、相2减文风漂移(advisory),硬上限 5 次 commit。
// 收敛由 run-l2 客观判,不自判;返回结构化 JSON 供 JS 复核(JS 不信自报,独立 relay 再验 L2)。
function editorPrompt(ctx, project, chapter, volume) {
  const ex = ctx.style_examples || {}
  const demo = (ex.good && ex.good.length) || (ex.bad && ex.bad.length)
    ? ['【风格示范】(对照节奏/密度/句式,严禁复述范例原文)',
       ...(ex.good || []).map(s => `  ✓ ${s}`),
       ...(ex.bad || []).map(s => `  ✗ ${s}(避免)`)].join('\n') : ''
  return [
    '# 章节修订员(stateful,自带工具循环)',
    `你在项目根 D:/novel_test。本章=${chapter} 卷=${volume} 已在 bedrock.db(${project})。`,
    'boot-context(beat 契约/指纹/文风指令/角色正典,必须遵守):',
    JSON.stringify(ctx, null, 2),
    '',
    '【工具·只准用这些 bedrock CLI】(在 D:/novel_test,命令前缀 python -m src.bedrock)',
    `- 读现状:show-paragraphs --project ${project} --chapter ${chapter}`,
    `- 结构自检(确定性,判过没过):run-l2 --project ${project} --chapter ${chapter}`,
    `- 文风自测(确定性,advisory):style-check --project ${project} --chapter ${chapter} --volume ${volume}`,
    `- 整章落盘(扩写/beat 重构用):commit-paragraphs --project ${project} --chapter ${chapter}  (stdin=整章正文,段间空行,不裹围栏)`,
    `- 定点改(局部用,更安全):edit-paragraphs --project ${project} --chapter ${chapter}  (stdin=ops JSON)`,
    'commit-paragraphs/edit-paragraphs 的 stdin 用带引号 heredoc(分隔符 __STDIN__,禁止展开)传入。',
    '',
    HYGIENE_RULES,
    ctx.style_directive ? `【文风指令·定性】${ctx.style_directive}` : '',
    demo,
    '',
    '【迭代协议·必须遵守】',
    '相 1(正确性优先):show-paragraphs 读现状 → run-l2 自检。',
    '  若不过(word_count_below_floor→字数不足;或其他 beat 违规):',
    '    - 字数不足→commit-paragraphs 整章扩写(剧情骨架上增场景细节/感官/心理/对白展开;禁灌水、禁重复、禁堆砌形容词)。',
    '    - beat 违规→edit-paragraphs 定点修 或 commit-paragraphs 整章重写 → 重 run-l2 复测。',
    '  累进接受:每次基于 DB 最新版继续(再 show-paragraphs 读),不回退丢进展。',
    '  反复直到 run-l2.passed_hard_gate=true。',
    '相 2(文风,advisory):L2 过后 style-check 自测 → 有漂移则最小改动收敛',
    '  (删非必要破折号→换句号断句、改"不是A是B"句式、减过密比喻)→ 重 run-l2 确认没破 L2。',
    '  若文风改动破了 L2→commit 回退到上一过 L2 版(再 show-paragraphs 确认),停文风收敛。',
    '收敛:run-l2.passed_hard_gate=true 即 converged(残留言风漂移可接受,advisory)。',
    '硬上限:最多 5 次 commit-paragraphs/edit-paragraphs。到限 L2 仍未过→converged=false 退出。',
    '',
    '【红线】收敛由 run-l2 客观输出判定,不得自判"我觉得行了"。不得绕过 CLI 直改 DB。',
    '      破 L2 的文风改动必须回退。整章正文第一段必须是小说正文,无作者旁白/开场白。',
    '',
    '【返回】收敛或到限后,最后输出一行 JSON(无围栏、无解释,仅该行):',
    '{"converged":true|false,"iterations":<commit次数>,"final_passed":<run-l2终态>,"word_count":<int>,"final_l2_violations":[..],"style_drift_remaining":<int>}',
  ].filter(Boolean).join('\n')
}

// 读 DB 当前段落拼成 prose(editor 改 DB 后刷新 JS 侧 prose,供下游 Consistency 回退快照)。
async function readCurrentProse(project, chapter) {
  const raw = extractProse(await pythonCli(`show-paragraphs --project ${project} --chapter ${chapter}`, { phase: 'Revise' }))
  try {
    const paras = JSON.parse(raw)
    return (Array.isArray(paras) ? paras : []).map(p => p.text).join('\n\n')
  } catch { return '' }
}

function revisePrompt(ctx, manifest, prevProse) {
```

- [ ] **Step 3: 静态确认**

Run:
```bash
cd D:/novel_test && node --check .claude/workflows/bedrock-chapter.js && echo SYNTAX_OK
cd D:/novel_test && grep -n "function editorPrompt\|function readCurrentProse" .claude/workflows/bedrock-chapter.js
```
Expected: `SYNTAX_OK`;两函数均出现,`editorPrompt` 在 `readCurrentProse` 之前,二者在 `revisePrompt` 之前。

- [ ] **Step 4: Commit**

```bash
cd D:/novel_test && git add .claude/workflows/bedrock-chapter.js && git commit -m "$(cat <<'EOF'
feat(bedrock-chapter): 加 editorPrompt + readCurrentProse(stateful editor,暂不接线)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: SPIKE(gate)— 验证 stateful 工具型 agent 在本 harness 可行

**Files:** 无改动;观察验证。**这是 gate:不通过则停,勿进 Task 3。**

> 目的:在全面接线前,证明"一个 general-purpose agent 能在沙箱里自主循环 bedrock CLI(show-paragraphs→run-l2→commit→复测)并按契约返回 JSON"。工具型多步 agent 在本仓已有旁证(telemetryRelay agent 跑多命令),但 editor 的"循环到收敛 + 返回 JSON"未验过。

- [ ] **Step 1: 取 ch13 的 boot-context**

Run:
```bash
cd D:/novel_test && python -m src.bedrock boot-context --project projects/vigilia --chapter 13 --volume 2 > /tmp/ctx13.json 2>/dev/null; echo "exit=$?"; head -c 200 /tmp/ctx13.json
```
Expected: `exit=0`,JSON 开头(含 beat_contracts / fingerprint 等)。

- [ ] **Step 2: 派 spike agent(经 Agent 工具,general-purpose)**

用 Agent 工具(general-purpose)派一个子 agent,prompt = 把 Task 1 的 `editorPrompt` 逻辑应用到 ctx13(读 `/tmp/ctx13.json` 作为 ctx,project=`projects/vigilia`,chapter=13,volume=2)。指示该 agent:在 D:/novel_test 用 Bash 执行 editorPrompt 里列的工具循环,目标让 ch13 的 run-l2 过(它当前应已 L2-clean,故应快速收敛或做一轮文风),最后输出契约 JSON 行。

派发 prompt(交给 spike 子 agent):
```
你在 D:/novel_test。本章=13 卷=2 已在 bedrock.db(projects/vigilia)。
boot-context 见 /tmp/ctx13.json(先 cat 读取)。
工具(只准用这些,命令前缀 python -m src.bedrock):
- show-paragraphs --project projects/vigilia --chapter 13
- run-l2 --project projects/vigilia --chapter 13
- style-check --project projects/vigilia --chapter 13 --volume 2
- commit-paragraphs --project projects/vigilia --chapter 13 (stdin=整章正文 heredoc)
- edit-paragraphs --project projects/vigilia --chapter 13 (stdin=ops JSON)
迭代:show-paragraphs 读现状→run-l2 自检→若不过则 commit 扩写/修→复测,直到 run-l2.passed_hard_gate=true(最多 5 次 commit)。
收敛由 run-l2 客观判,不自判。最后输出一行 JSON:
{"converged":..,"iterations":..,"final_passed":..,"word_count":..,"final_l2_violations":[..],"style_drift_remaining":..}
```

- [ ] **Step 3: 判 spike 结果**

观察 spike agent 的行为与最终输出。**通过判据(全满足才进 Task 3):**
1. agent 自主调用了 ≥2 个 bedrock CLI(至少 show-paragraphs + run-l2)。
2. agent 按循环协议工作(读→检→改→复测),不是一次性返回。
3. 最终输出了一行符合契约的 JSON(含 converged/final_passed/word_count 等字段)。
4. ch13 终态 `run-l2` 客观 `passed_hard_gate=true`(agent 没把章改坏)。

Run(复核):
```bash
cd D:/novel_test && python -m src.bedrock run-l2 --project projects/vigilia --chapter 13 2>&1 | python -c "import sys,json;d=json.load(sys.stdin);print('passed:',d.get('passed_hard_gate'),'words:',d.get('metrics',{}).get('word_count'))"
```
Expected: `passed: True`(ch13 仍 L2-clean)。

- [ ] **Step 4: 判决**

- **通过** → 进 Task 3(不 commit,spike 是观察;ch13 状态保留即可)。
- **不通过**(agent 不会循环 / 不返回 JSON / 把章改坏 / CLI 调不通)→ **STOP**,上报控制器。可能要回退到已合并的 Revise 收束现状(master `50669b7`),stateful 路径在本 harness 不可行。**勿强行进 Task 3。**

---

## Task 3: 接线——Revise 段从失忆 while-loop 改为单 editor agent 调度

**Files:**
- Modify: `.claude/workflows/bedrock-chapter.js`(Revise 段 ~行 55-108)

- [ ] **Step 1: 替换 Revise 段**

定位当前 Revise 段(三路分流 while-loop,从 `// 3. Revise：defect manifest 驱动...` 注释到收尾 `log(\`revise 收敛完成...\`)`)。把整段:
```js
// 3. Revise：defect manifest 驱动的定向修订(beat/字数/文风统一收敛),复测重喂≤REVISE_MAX_ROUNDS 轮。
// 收束原 L2+Repair/Polish/Style 三段为一个变异阶段:每轮 commit+L2+styleCheck 复测、重算 manifest 只喂剩余缺陷。
// 破 L2 回退 preRevise(Write 后已过 L2 版,agent-free);commit 被拒 break 保 preRevise。正确性硬压文风。
phase('Revise')
let drift = (report.passed_hard_gate && ctx.fingerprint)
  ? await styleCheck(project, chapter, volume) : null
_trackDrift(drift)
let manifest = buildManifest(report, drift, ctx)
let round = 0
while (!manifest.empty && round < REVISE_MAX_ROUNDS) {
  const wasCorrectness = manifest.priority === 'correctness'   // 本轮意图:修正确性 还是 对准文风
  const anchorProse = prose, anchorReport = report             // 本轮前状态(仅 style 回退用)
  const revised = extractProse(await agent(revisePrompt(ctx, manifest, prose),
    { label: `Edit-revise-r${round + 1}`, phase: 'Revise' }))
  let after
  try {
    after = await commitAndL2(project, chapter, revised, `revise-r${round + 1}`)
  } catch (e) {
    log(`revise r${round + 1} 提交被拒(返回非正文?),保 anchor: ${String(e.message || e).slice(0, 80)}`)
    break
  }
  round++
  if (after.passed_hard_gate) {
    // 干净:接受,复测下轮剩余文风漂移(无指纹则跳过 styleCheck,与 pre-loop/correctness 分支一致)
    prose = revised; report = after
    drift = (ctx.fingerprint) ? await styleCheck(project, chapter, volume) : null; _trackDrift(drift)
    manifest = buildManifest(report, drift, ctx)
    log(`revise r${round} 复测: must_fix=${manifest.must_fix.length} expand=${manifest.expand ? 1 : 0} align=${manifest.align.length}`)
  } else if (wasCorrectness) {
    // correctness 修复仍未全过(扩写未达 floor / 仍有 beat):累进接受为新基(复刻旧 repair 渐进语义),下轮继续修剩余项。
    // 不回退——回退会丢部分进展(如 r1 把 2341 扩到 2800 仍未过,回退到 2341 等于白扩)。
    prose = revised; report = after
    drift = (ctx.fingerprint) ? await styleCheck(project, chapter, volume) : null; _trackDrift(drift)
    manifest = buildManifest(report, drift, ctx)
    log(`revise r${round} 仍不洁(correctness),累进为下轮基,剩余 must_fix=${manifest.must_fix.length} expand=${manifest.expand ? 1 : 0}`)
  } else {
    // style 对准破坏了已 L2-clean 的章 → 回退 clean anchor,停(不为文风冒正确性风险)。章保 clean+advisory 漂移。
    // anchorReport.passed_hard_gate===true 在此恒成立:进 style 分支要求 manifest.priority==='style',
    // 而 priority==='style' ⟺ must_fix 空 && !expand ⟺ loop 入口 report 已过 L2(无任何硬违规)。
    await commitAndL2(project, chapter, anchorProse, 'revise-revert')
    prose = anchorProse; report = anchorReport
    await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`, { phase: 'Revise' })
    log('revise style 破坏 L2 → 回退 last-good,停(正确性优先)')
    break
  }
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
替换为:
```js
// 3. Revise：stateful 工具型 editor agent(内部循环自纠错,替代失忆轮)。
// editor 自带 Bash 直调 CLI,相1保 L2 过、相2减文风漂移(advisory),硬上限 5 次 commit。
// 收敛由 L2 客观判——JS 用独立 l2Report relay 复核(不信 editor 自报 converged),Finalize verify-persisted 终审。双 gate。
phase('Revise')
const editorRaw = extractProse(await agent(editorPrompt(ctx, project, chapter, volume),
  { label: 'Editor', phase: 'Revise' }))
let editor
try { editor = JSON.parse(editorRaw) } catch { editor = { converged: false, final_passed: false, iterations: 0, style_drift_remaining: 0 } }
const round = editor.iterations || 0   // finalize 遥测 --editing-rounds 用(原 Revise round 的替代)
report = await l2Report(project, chapter, 'Revise')   // 独立 relay 复核 L2(信任锚,不信 editor 自报)
prose = await readCurrentProse(project, chapter)      // editor 改了 DB,刷新 JS 侧 prose(供下游 Consistency 回退快照,防丢 editor 成果)
if (editor.style_drift_remaining > 0)
  _trackDrift({ drifted: new Array(editor.style_drift_remaining), target_source: ctx.fingerprint ? 'editor' : null })
if (!report.passed_hard_gate) {
  await pythonCli(
    `mark-unresolved --project ${project} --chapter ${chapter} --rule-or-model 0`,
    { phase: 'Revise', stdin: JSON.stringify(report.beat_violations || []) })
  log(`editor 未收敛(L2 仍不过,${editor.iterations || '?'} 轮)→ mark-unresolved`)
} else {
  log(`editor 收敛: L2-clean${editor.style_drift_remaining ? `, 文风仍 ${editor.style_drift_remaining} 项漂移(advisory)` : ''}`)
}
```

> 注:`report`/`prose` 是 Write 段的 `let`(模块作用域),这里**重赋值**不重新声明。`round` 新声明为 `const`(finalize 用)。`l2Report`/`readCurrentProse`/`extractProse`/`pythonCli`/`_trackDrift` 均既有或 Task1 新增。

- [ ] **Step 2: 静态确认**

Run:
```bash
cd D:/novel_test && node --check .claude/workflows/bedrock-chapter.js && echo SYNTAX_OK
cd D:/novel_test && grep -n "phase('Revise')\|editorPrompt(\|readCurrentProse(\|buildManifest(\|revisePrompt(" .claude/workflows/bedrock-chapter.js
```
Expected: `SYNTAX_OK`;Revise 段含 `editorPrompt(`/`readCurrentProse(`;主流程**不再**调 `buildManifest(`/`revisePrompt(`(二者仅剩函数定义行,Task 4 删)。

- [ ] **Step 3: Commit**

```bash
cd D:/novel_test && git add .claude/workflows/bedrock-chapter.js && git commit -m "$(cat <<'EOF'
refactor(bedrock-chapter): Revise 段→stateful editor agent(内部循环自纠错,替代失忆轮)

- Revise 从 JS while-loop(buildManifest+revisePrompt+三路分流)改为单 agent(editorPrompt)调度
- editor 自带 Bash 直调 CLI(show-paragraphs/run-l2/style-check/commit/edit-paragraphs),内部循环收敛
- 红线②落代码:JS 用独立 l2Report relay 复核 L2,不信 editor 自报 converged;Finalize verify-persisted 终审
- editor 改 DB 后 readCurrentProse 刷新 prose,防 Consistency 回退丢 editor 成果
- round=editor.iterations 供 finalize 遥测

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 删废弃的 `buildManifest` / `revisePrompt` / `REVISE_MAX_ROUNDS`

**Files:**
- Modify: `.claude/workflows/bedrock-chapter.js`

- [ ] **Step 1: 删 `buildManifest` 函数**

定位 `function buildManifest(report, drift, ctx) {` 整个函数(含其上方两行注释),删除整段:
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
```

- [ ] **Step 2: 删 `revisePrompt` 函数**

定位 `function revisePrompt(ctx, manifest, prevProse) {` 整个函数(含其上方三行注释),删除整段:
```js
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
```

- [ ] **Step 3: 删 `REVISE_MAX_ROUNDS` 常量**

定位:
```js

// Revise 复测重喂上限(收束原 repair≤3 + style≤2,合并取严的 2)。
const REVISE_MAX_ROUNDS = 2
```
删除整段(含注释与前后空行)。

- [ ] **Step 4: 静态确认无残留**

Run:
```bash
cd D:/novel_test && grep -n "buildManifest\|revisePrompt\|REVISE_MAX_ROUNDS" .claude/workflows/bedrock-chapter.js
```
Expected: **零输出**(三者在文件彻底消失)。

Run(确认保留函数仍在,且 pct 仍被引用——editorPrompt 不用 pct,但确认无悬挂):
```bash
cd D:/novel_test && grep -n "function editorPrompt\|function readCurrentProse\|function consistencyPrompt\|function chapterWriterPrompt\|function pct\|function commitAndL2\|function l2Report" .claude/workflows/bedrock-chapter.js
```
Expected: 全部出现。

Run(语法):
```bash
cd D:/novel_test && node --check .claude/workflows/bedrock-chapter.js && echo SYNTAX_OK
```
Expected: `SYNTAX_OK`。

- [ ] **Step 5: Commit**

```bash
cd D:/novel_test && git add .claude/workflows/bedrock-chapter.js && git commit -m "$(cat <<'EOF'
refactor(bedrock-chapter): 删废弃 buildManifest/revisePrompt/REVISE_MAX_ROUNDS

stateful editor 接管 Revise 后三者无引用。buildManifest 的 manifest 装配、revisePrompt 的
失忆轮 prompt、REVISE_MAX_ROUNDS 上限均被 editor 内部循环取代(硬上限 5 在 editorPrompt 内)。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 静态总检 + Python 回归

**Files:** 无改动;验证

- [ ] **Step 1: 结构 sanity**

Run:
```bash
cd D:/novel_test && grep -c "phase('" .claude/workflows/bedrock-chapter.js && grep -n "phase('" .claude/workflows/bedrock-chapter.js
```
Expected: `5`,顺序 Boot/Write/Revise/Consistency/Persist+Telemetry。

Run(主流程变量作用域):
```bash
cd D:/novel_test && grep -n "const round\|let prose\|let report\|report = await l2Report\|prose = await readCurrentProse" .claude/workflows/bedrock-chapter.js
```
Expected: `let prose`/`let report`(Write 段)、`const round`(Revise 段)、`report = await l2Report`/`prose = await readCurrentProse`(Revise 段重赋值)均出现。

Run(Python src 未动):
```bash
cd D:/novel_test && git diff master -- src/ | head -5
```
Expected: 空(src/ 无改动)。

- [ ] **Step 2: Python 全套回归**

Run:
```bash
cd D:/novel_test && python -m pytest tests/bedrock/ -q 2>&1 | tail -5
```
Expected: 全 PASS(此前 319 passed,本任务 Python 零改,计数应稳定)。报告计数。若失败几乎必是误改 Python——`git diff master -- src/` 确认。

---

## Task 6: 端到端回归——vigilia ch13 + ch1

**Files:** 无改动;运行工作流验证

> 验收:stateful editor 让章 L2-clean+completed,且 agent 数显著下降(~17→~7)。ch13(ch14?以 ch13 为准)是已知欠产 stress case;ch1 验干净路径。

- [ ] **Step 1: 重跑 ch13**

```
Workflow({ scriptPath: "D:/novel_test/.claude/workflows/bedrock-chapter.js",
           args: { project: "projects/vigilia", chapter: 13, volume: 2 } })
```

- [ ] **Step 2: 核对 ch13 终态**

Run:
```bash
cd D:/novel_test && python -m src.bedrock run-l2 --project projects/vigilia --chapter 13 2>&1 | python -c "import sys,json;d=json.load(sys.stdin);print('passed:',d.get('passed_hard_gate'),'words:',d.get('metrics',{}).get('word_count'),'violations:',[v.get('kind') for v in d.get('beat_violations',[])])"
```
Expected: `passed: True`,words ≥3000,violations `[]`。

Run(状态):
```bash
cd D:/novel_test && python -c "import sqlite3;c=sqlite3.connect('projects/vigilia/bedrock.db');print('status:',c.execute('SELECT status FROM chapter WHERE global_number=13').fetchone())"
```
Expected: `status: ('completed',)`。

核对 Workflow 完成通知的 `agent_count`:Expected **~6-7**(Boot + Write + Editor + Consistency + 专名 relay + finalize/telemetry relay),**显著低于** 收束版的 ~17。若仍 ~17,说明 editor 没有自带工具循环(退化回 relay 模式)——查 editor 是否真在内部调 CLI。

- [ ] **Step 3: 重跑 ch1(干净路径)**

```
Workflow({ scriptPath: "D:/novel_test/.claude/workflows/bedrock-chapter.js",
           args: { project: "projects/vigilia", chapter: 1, volume: 1 } })
```
Expected: `status=ok`,L2-clean + completed。editor 对干净章应快速收敛(1-2 次内部迭代)。agent 数同样 ~6-7。

- [ ] **Step 4: 若 ch13 未收敛——诊断**

若 ch13 `passed=false`(editor 5 轮未过 L2):
- 看 Workflow 日志:editor 是否真自主循环(show-paragraphs→run-l2→commit→复测)?是否卡在某步?
- 若 editor 不循环(退化成一次性)→ editorPrompt 的迭代协议指令没被遵守 → 调 prompt(强化"必须多次调用工具直到 run-l2 过")。
- 若 editor 循环但扩写仍不够 → writer 欠产问题(见记忆,出 scope);editor 已尽力,mark-unresolved 是正确升级。
- 记录实际链路,上报。

---

## Self-Review

**Spec 覆盖:**
- Revise 槽位 → 单 stateful editor agent → Task 3 ✓
- editorPrompt(工具面/迭代协议/返回契约)→ Task 1 ✓
- 两条红线(固定编排留 JS;收敛由 L2 客观判,JS 独立 relay 复核不信自报)→ Task 3(l2Report 复核 + 不信 editor.converged)✓
- relay 收敛(editor 自带 Bash 直调 CLI)→ Task 3(editor 内部调,JS 不再派 commit/run-l2/styleCheck relay)✓
- 删 buildManifest/revisePrompt/REVISE_MAX_ROUNDS → Task 4 ✓
- advisory 漂移流(style_drift_remaining→_trackDrift→finalize)→ Task 3 ✓
- spike 先行 → Task 2 ✓
- 静态 + pytest + 端到端 → Task 5 + Task 6 ✓
- 集成坑(prose 陈旧致 Consistency 回退丢成果)→ Task 3 readCurrentProse 刷新 ✓

**Placeholder 扫描:** 无 TBD/TODO;每步含完整代码或确切命令 + 期望输出。✓

**类型/签名一致:**
- `editorPrompt(ctx, project, chapter, volume)` → Task 1 定义、Task 3 调用签名一致 ✓
- `readCurrentProse(project, chapter)` → Task 1 定义、Task 3 调用一致 ✓
- `l2Report(project, chapter, phase)` → 既有;Task 3 调用 `l2Report(project, chapter, 'Revise')` 一致 ✓
- editor 返回字段 `{converged, iterations, final_passed, word_count, final_l2_violations, style_drift_remaining}` → Task 1 prompt 契约、Task 3 读取(`editor.iterations`/`editor.style_drift_remaining`)一致 ✓
- `report`/`prose` 为 Write 段 `let`,Task 3 **重赋值**不重声明;`round` 新 `const`(供 finalize 第 4 参)✓
- `finalize(project, chapter, exportPath, round, worstDrift)` 签名不变,`round` 由 Task 3 提供 ✓

**需 impl 核实:**
- Task 2 spike:若 harness 不支持 general-purpose agent 内部工具循环(理论上 telemetryRelay 已旁证),则 stateful 路径不可行 → 回退 master `50669b7`,STOP。
- Task 3:旧 Revise 段 old_string 须与文件逐字匹配(全角标点/注释);若不符 STOP 上报。
- Task 6:`agent_count` 若未显著下降,查 editor 是否真内部调 CLI(而非退化)。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-20-stateful-editor-agent.md`. **分支 `bedrock-stateful-editor`(Task 1 Step 1 创建)。** Task 2 spike 是 gate(不通过则停)。两种执行:

1. **Subagent-Driven(推荐)** — 每 Task 派新 subagent + 两阶段 review。Task 2 spike 由控制器亲自判(派 spike agent + 核对),不外包。
2. **Inline Execution** — 本会话批量执行带 checkpoint。

选哪种?
