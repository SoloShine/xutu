# Stateful Writer Agent(step ①)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `bedrock-chapter.js` 的 Write 段从"一次性 `chapterWriterPrompt` + JS `commitAndL2`"换成一个 stateful 工具型 writer agent(与 editor 同构),内部循环自纠结构(字数 + L2 beat),源头修结构,editor 收结构-clean 稿主业转 style。

**Architecture:** Write 槽位 = 一次 `agent(writerPrompt, {agentType:'general-purpose'})`,writer 自带 Bash 直调 CLI(show-paragraphs/run-l2/commit-paragraphs),内部 写→commit→run-l2 自检→扩/修→复测→收敛。JS 不信 writer 自报,独立 l2Report 复核(信任锚),editor 之后 + finalize 再独立验。多 gate。editor/Consistency/专名/finalize 全不动。

**Tech Stack:** Node 沙箱工作流(`.claude/workflows/bedrock-chapter.js`,无 Node API,CLI 经 agent relay);Python 3 + pytest 回归(`tests/bedrock/`)。

**Spec:** `docs/superpowers/specs/2026-06-21-stateful-writer-agent-design.md`(已过独立审查)

**实施:** 分支 `bedrock-stateful-writer`,从 master 切。所有命令 cwd = `D:/novel_test`。

**关于 TDD:** 全改动在 JS 沙箱工作流,**无 Python 单测**(既有惯例靠 grep 静态检 + 端到端)。"测试"步 = `node --check` + grep + `pytest tests/bedrock/` 回归(Python 零改应全绿)+ 端到端 vigilia 章节。**无需 spike**——stateful 工具循环模式已由 editor(master `93f3237`)验证。

**关键事实(已核实,基于 master `154ab9f` 的 `bedrock-chapter.js`):**
- Write 段当前(行 45-50):
  ```js
  // 2. Write：ChapterWriter 产正文 → commit+L2 relay（verdict 由 relay 跑，JS 解析）
  phase('Write')
  let prose = extractProse(await agent(chapterWriterPrompt(ctx), { label: 'ChapterWriter', phase: 'Write' }))
  let report = await commitAndL2(project, chapter, prose, 'Write')
  _trackDrift(report)
  log(`L2 r0 passed=${report.passed_hard_gate} violations=${(report.beat_violations || []).length} words=${report.metrics?.word_count}`)
  ```
  **`let prose`/`let report` 在此声明(模块作用域)**,下游 Revise/Consistency 重赋值。
- `chapterWriterPrompt(ctx)` 在行 251-295(Write 是唯一调用方)。
- `round` 在 **Revise 段行 61** 声明(`const round = editor.iterations || 0`),喂 finalize。**Write 段不得再声明 round(避 const 冲突)。**
- 复用函数(均既有):`l2Report(project, chapter, phase)`、`readCurrentProse(project, chapter)`、`extractEditorJson(raw)`、`extractProse(s)`、`pythonCli(cmd, opts)`、`commitAndL2(...)`(Consistency 回退仍用,**保留**)、`HYGIENE_RULES`、`editorPrompt`(`writerPrompt` 镜像它)。
- **计划级修正(spec §4 片段)**:spec 写 `report = await l2Report` / `prose = await readCurrentProse`(重赋值),但 Task 2 **整体替换 Write 段**会删掉原 `let prose`/`let report` 声明 → 新 Write 段必须**重新 `let` 声明**二者(下游 Revise/Consistency 仍重赋值)。本计划 Task 2 已按此(用 `let report`/`let prose`)。

---

## File Structure

**修改(唯一文件):** `.claude/workflows/bedrock-chapter.js`
- 加:`writerPrompt(ctx, project, chapter, volume)`(= chapterWriterPrompt 全部内容 + 工具面/迭代协议/返回契约)。
- 改:Write 段(chapterWriterPrompt + commitAndL2 → 单 `agent(writerPrompt)` + 独立 l2Report + readCurrentProse + mark-unresolved)。
- 删:`chapterWriterPrompt`(Task 2 后无调用方)。
- 保留:`commitAndL2`(Consistency 回退用)及所有其他函数。

**Python:** 零改动。

---

## Task 1: 建分支 + 加 `writerPrompt`(不接线)

**Files:** Modify `.claude/workflows/bedrock-chapter.js`

> 只新增函数,不动 Write 段、不删 chapterWriterPrompt。文件每 commit 后自洽。

- [ ] **Step 1: 建分支**

Run:
```bash
cd D:/novel_test && git checkout -b bedrock-stateful-writer master
```
Expected: `Switched to a new branch 'bedrock-stateful-writer'`

- [ ] **Step 2: 在 `chapterWriterPrompt` 之前插入 `writerPrompt`**

定位 `function chapterWriterPrompt(ctx) {`(行 251)。把该行替换为(新函数 + 原行):

```js
// stateful 工具型 writer agent 的 prompt(= chapterWriterPrompt 全部内容 + 工具面/迭代协议/返回契约)。
// writer 自带 Bash 直调 CLI,内部 写→commit→run-l2 自检→扩/修→复测→收敛(结构:字数+beat)。
// 收敛由 run-l2 客观判,不自判;返回 JSON 供 JS 复核(JS 不信自报,独立 relay 再验 L2)。镜像 editorPrompt。
function writerPrompt(ctx, project, chapter, volume) {
  const prev = ctx.prev_chapter_tail
    ? ['【上一章收尾】（本章开篇须自然承接其画面/语气/悬念，禁止复述原文）：',
       ctx.prev_chapter_tail, '']
    : ['（本章为开篇，无前章。）', '']
  const canon = (ctx.characters && ctx.characters.length)
    ? [`【角色正典·必须严格遵守】代词/性别/称呼/性格按下表，不得擅改（如 ${ctx.characters[0].name}=${ctx.characters[0].pronoun}）：`,
       JSON.stringify(ctx.characters.map(c => ({ name: c.name, pronoun: c.pronoun, gender: c.gender, role: c.role, personality: c.personality })), null, 2), '']
    : []
  const multi = (ctx.beat_contracts && ctx.beat_contracts.length > 1)
    ? [`【多 beat 章，共 ${ctx.beat_contracts.length} 个 beat】每个 beat 的内容块**前面**单独起一行写标记 @@beat:<beat_id>@@（beat_id 见各 beat 契约），按契约顺序。这样系统才能把段落正确归属到对应 beat。标记行单独成段（前后空行），不要混入正文。`,
       'beat 契约(注意每个的 beat_id)：' + JSON.stringify(ctx.beat_contracts, null, 2), '']
    : []
  const secrets = (ctx.reader_disclosed_secrets && ctx.reader_disclosed_secrets.length)
    ? [`【读者此刻(本章时点)已知的信息——只能用这些，不得越界】` + JSON.stringify(ctx.reader_disclosed_secrets, null, 2),
       '上面含到本章才解封的揭示(若有)。揭示章可写明已解封的真相；但**未在列表里的角色隐藏身世/动机/来历——一律不得临场编造**(这是结构性防跨章矛盾的硬约束：种子没编码的揭示，writer 凭空编了必和他章冲突)。', '']
    : []
  const directive = ctx.style_directive
    ? [`【文风指令·定性要求(高于统计指纹,必须贯彻)】`, ctx.style_directive, '']
    : []
  const ex = ctx.style_examples || {}
  const demo = (ex.good && ex.good.length) || (ex.bad && ex.bad.length)
    ? [`【风格示范】(对照以下范例的节奏/密度/句式/语气写作。**严禁复述范例原文**,只学其风格)`,
       ...(ex.good || []).map(s => `  ✓ ${s}`),
       ...(ex.bad || []).map(s => `  ✗ ${s}（避免）`),
       '']
    : []
  return [
    '# 章节写作员(stateful,自带工具循环)',
    `你在项目根 D:/novel_test。本章=${chapter} 卷=${volume} 已在 bedrock.db(${project})。`,
    'boot context:', JSON.stringify(ctx, null, 2),
    '',
    ...prev,
    ...canon,
    ...directive,
    ...demo,
    ...secrets,
    HYGIENE_RULES,
    ...multi,
    '',
    '【工具·只准用这些 bedrock CLI】(在 D:/novel_test,命令前缀 python -m src.bedrock)',
    `- 读现状:show-paragraphs --project ${project} --chapter ${chapter}`,
    `- 结构自检(确定性,判字数+beat):run-l2 --project ${project} --chapter ${chapter}`,
    `- 整章落盘:commit-paragraphs --project ${project} --chapter ${chapter}  (stdin=整章正文,段间空行,不裹围栏)`,
    'commit-paragraphs 的 stdin 用管道传入(先写临时文件再 cat,或 printf 管道)。**不要用 heredoc**(本环境易失败)。',
    '',
    '【迭代协议·必须遵守】',
    '1. 按 beat_contracts 写整章正文首版(视角符合 pov,推进 beat 叙事目的,3000–5000 字;多 beat 章按上面 multi 指令标 @@beat)。第一段必须是小说正文(人物/场景/动作),严禁作者旁白/开场白("我将/我会/下面/本章将撰写/遵循beat契约"等自述语会被系统剥除)。不写标题行,不裹 markdown 围栏。',
    '2. 把整章正文写入临时文件,cat 临时文件 | python -m src.bedrock commit-paragraphs --project ' + project + ' --chapter ' + chapter + ' 落盘。',
    '3. python -m src.bedrock run-l2 --project ' + project + ' --chapter ' + chapter + ' 自检。',
    '4. 若 run-l2.passed_hard_gate=false:',
    '   - word_count_below_floor(字数不足)→ 在剧情骨架上整章扩写(增场景细节/感官/心理/对白;禁灌水、禁重复同一意思、禁堆砌形容词)→ 重新 commit → 重 run-l2 复测。',
    '   - beat 违规 → 修(必要时 show-paragraphs 重读确认 @@beat 归属)→ 重新 commit → 复测。',
    '   累进接受:基于上一轮自己写过的版本继续(stateful 上下文记忆),不回退丢进展。',
    '5. 反复直到 run-l2.passed_hard_gate=true,或达 3 次 commit 上限。',
    '收敛由 run-l2 客观输出判定,不得自判"我觉得够了"。文风(style)不在你职责内——交后续 editor,你只保结构(字数+beat)过。',
    '',
    '【返回】收敛或到限后,最后输出一行 JSON(无围栏、无解释,仅该行):',
    '{"converged":true|false,"iterations":<commit次数>,"final_passed":<run-l2终态>,"word_count":<int>,"final_l2_violations":[..]}',
  ].join('\n')
}

function chapterWriterPrompt(ctx) {
```

- [ ] **Step 3: 静态确认**

Run:
```bash
cd D:/novel_test && node --check .claude/workflows/bedrock-chapter.js && echo SYNTAX_OK
cd D:/novel_test && grep -n "function writerPrompt\|function chapterWriterPrompt\|function editorPrompt" .claude/workflows/bedrock-chapter.js
```
Expected: `SYNTAX_OK`;三函数均在,`writerPrompt` 在 `chapterWriterPrompt` 之前。

- [ ] **Step 4: Commit**

```bash
cd D:/novel_test && git add .claude/workflows/bedrock-chapter.js && git commit -m "$(cat <<'EOF'
feat(bedrock-chapter): 加 writerPrompt(stateful writer,暂不接线)

= chapterWriterPrompt 全部内容 + 工具面(show-paragraphs/run-l2/commit-paragraphs,pipe stdin)
+ 迭代协议(写→commit→run-l2→扩/修→复测,cap 3,收敛由 run-l2 客观判)+ JSON 返回契约。镜像 editorPrompt。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 接线——Write 段改为单 writer agent 调度

**Files:** Modify `.claude/workflows/bedrock-chapter.js`(Write 段,行 45-50)

- [ ] **Step 1: 替换 Write 段**

定位当前 Write 段(行 45-50)。把整段:
```js
// 2. Write：ChapterWriter 产正文 → commit+L2 relay（verdict 由 relay 跑，JS 解析）
phase('Write')
let prose = extractProse(await agent(chapterWriterPrompt(ctx), { label: 'ChapterWriter', phase: 'Write' }))
let report = await commitAndL2(project, chapter, prose, 'Write')
_trackDrift(report)
log(`L2 r0 passed=${report.passed_hard_gate} violations=${(report.beat_violations || []).length} words=${report.metrics?.word_count}`)
```
替换为:
```js
// 2. Write：stateful 工具型 writer agent(内部循环自纠结构:字数+beat,与 editor 同构)。
// writer 自带 Bash 直调 CLI,写→commit→run-l2 自检→扩/修→复测→收敛。结构 clean 后交 editor(做 style)。
// 收敛由 L2 客观判——JS 用独立 l2Report relay 复核(不信 writer 自报),editor+finalize 再独立验。多 gate。
phase('Write')
const writerRaw = extractProse(await agent(writerPrompt(ctx, project, chapter, volume),
  { label: 'Writer', phase: 'Write' }))
// writer 常在 JSON 行前后带叙述,逐行找最后一个可解析 {...}(复用 extractEditorJson);仅遥测,收敛判定走下面独立 l2Report。
let writer = extractEditorJson(writerRaw) || { converged: false, final_passed: false, iterations: 0 }
let report = await l2Report(project, chapter, 'Write')   // 独立 relay 复核 L2(信任锚,不信 writer 自报)
let prose = await readCurrentProse(project, chapter)     // writer 改了 DB,刷新 JS 侧 prose(注:Revise 段会再覆盖,下游用 Revise 后值)
if (!report.passed_hard_gate) {
  // mark-unresolved 仅设 review 旗,不阻流;终审 verify-persisted 独立再跑 L2 兜底,破损章不会 completed。
  await pythonCli(
    `mark-unresolved --project ${project} --chapter ${chapter} --rule-or-model 0`,
    { phase: 'Write', stdin: JSON.stringify(report.beat_violations || []) })
  log(`writer 未收敛(L2 仍不过,${writer.iterations || '?'} 轮)→ mark-unresolved`)
} else {
  log(`writer 收敛: 结构 clean, ${writer.word_count || '?'} 字 → 进 editor`)
}
```

> **关键**:`let report`/`let prose` 在此**重新声明**(原声明随旧 Write 段被替换删除);下游 Revise 段(`report = await l2Report`/`prose = await readCurrentProse`)与 Consistency 仍**重赋值**(无 let)。**Write 段不声明 `round`**(仍在 Revise 段行 61 声明,避 const 冲突)。`_trackDrift(report)` 删除(writer 不做 style/drift,L2 report 无 `.drifted`,原即是 no-op)。

- [ ] **Step 2: 静态确认**

Run:
```bash
cd D:/novel_test && node --check .claude/workflows/bedrock-chapter.js && echo SYNTAX_OK
cd D:/novel_test && grep -n "phase('Write')\|writerPrompt(\|chapterWriterPrompt(\|let report\|let prose\|const round" .claude/workflows/bedrock-chapter.js
```
Expected: `SYNTAX_OK`;Write 段用 `writerPrompt(`;**`chapterWriterPrompt(` 仅剩函数定义行**(主流程不再调用,Task 3 删);`let report`/`let prose` 在 Write 段;`const round` 仍只在 Revise 段(无第二处)。

- [ ] **Step 3: Commit**

```bash
cd D:/novel_test && git add .claude/workflows/bedrock-chapter.js && git commit -m "$(cat <<'EOF'
refactor(bedrock-chapter): Write 段→stateful writer agent(内部循环自纠结构)

- Write 从一次性 chapterWriterPrompt+commitAndL2 改为单 agent(writerPrompt)调度
- writer 自带 Bash 直调 CLI(show-paragraphs/run-l2/commit-paragraphs),内部 写→commit→run-l2→扩/修→收敛
- 红线:JS 独立 l2Report 复核 L2,不信 writer 自报 converged;editor+finalize 再独立验
- let report/let prose 在 Write 段声明(原声明随替换删除);round 不在 Write 声明(避 const 冲突)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 删废弃的 `chapterWriterPrompt`

**Files:** Modify `.claude/workflows/bedrock-chapter.js`(行 ~251 起的 chapterWriterPrompt 函数,行号因 Task 1 插入已后移)

- [ ] **Step 1: 删 `chapterWriterPrompt` 函数**

定位 `function chapterWriterPrompt(ctx) {` 整个函数(到其结束 `}`)。删除整段:
```js
function chapterWriterPrompt(ctx) {
  const prev = ctx.prev_chapter_tail
    ? ['【上一章收尾】（本章开篇须自然承接其画面/语气/悬念，禁止复述原文）：',
       ctx.prev_chapter_tail, '']
    : ['（本章为开篇，无前章。）', '']
  const canon = (ctx.characters && ctx.characters.length)
    ? [`【角色正典·必须严格遵守】代词/性别/称呼/性格按下表，不得擅改（如 ${ctx.characters[0].name}=${ctx.characters[0].pronoun}）：`,
       JSON.stringify(ctx.characters.map(c => ({ name: c.name, pronoun: c.pronoun, gender: c.gender, role: c.role, personality: c.personality })), null, 2), '']
    : []
  const multi = (ctx.beat_contracts && ctx.beat_contracts.length > 1)
    ? [`【多 beat 章，共 ${ctx.beat_contracts.length} 个 beat】每个 beat 的内容块**前面**单独起一行写标记 @@beat:<beat_id>@@（beat_id 见各 beat 契约），按契约顺序。这样系统才能把段落正确归属到对应 beat。标记行单独成段（前后空行），不要混入正文。`,
       'beat 契约(注意每个的 beat_id)：' + JSON.stringify(ctx.beat_contracts, null, 2), '']
    : []
  const secrets = (ctx.reader_disclosed_secrets && ctx.reader_disclosed_secrets.length)
    ? [`【读者此刻(本章时点)已知的信息——只能用这些，不得越界】` + JSON.stringify(ctx.reader_disclosed_secrets, null, 2),
       '上面含到本章才解封的揭示(若有)。揭示章可写明已解封的真相；但**未在列表里的角色隐藏身世/动机/来历——一律不得临场编造**(这是结构性防跨章矛盾的硬约束：种子没编码的揭示，writer 凭空编了必和他章冲突)。', '']
    : []
  const directive = ctx.style_directive
    ? [`【文风指令·定性要求(高于统计指纹,必须贯彻)】`, ctx.style_directive, '']
    : []
  // 风格范例(正反例):具体段落,show don't tell。硬约束"对照节奏/密度/句式,禁止复述范例原文"。
  const ex = ctx.style_examples || {}
  const demo = (ex.good && ex.good.length) || (ex.bad && ex.bad.length)
    ? [`【风格示范】(对照以下范例的节奏/密度/句式/语气写作。**严禁复述范例原文**,只学其风格)`,
       ...(ex.good || []).map(s => `  ✓ ${s}`),
       ...(ex.bad || []).map(s => `  ✗ ${s}（避免）`),
       '']
    : []
  return [
    '# ChapterWriter 子代理（磐石 V3）',
    'boot context:', JSON.stringify(ctx, null, 2),
    '',
    ...prev,
    ...canon,
    ...directive,
    ...demo,
    ...secrets,
    HYGIENE_RULES,
    ...multi,
    '按 beat_contracts 写整章正文：视角符合 pov，推进本章 beat 的叙事目的，3000–5000 字。',
    '不自报字数（系统重查）。不写标题行。不包裹 markdown 围栏。',
    '**第一段就必须是小说正文（人物/场景/动作）。严禁任何作者旁白/开场白**——不得出现"我将/我会/下面/本章将撰写/遵循beat契约/按照要求"等自述语，这类内容会被系统剥除。',
    '把整章正文（纯文本，段间空行分隔）作为最终返回值。',
  ].join('\n')
}
```

> 注:上面是 chapterWriterPrompt 的**原貌**(读文件确认逐字匹配,注意 `ctx.reader_disclosed_secrets` 拼写——以文件实际为准)。若不逐字匹配,STOP 上报。

- [ ] **Step 2: 静态确认**

Run:
```bash
cd D:/novel_test && grep -n "chapterWriterPrompt" .claude/workflows/bedrock-chapter.js
```
Expected: **零输出**(chapterWriterPrompt 在文件彻底消失)。

Run:
```bash
cd D:/novel_test && grep -n "function writerPrompt\|function editorPrompt\|function consistencyPrompt\|function l2Report\|function commitAndL2" .claude/workflows/bedrock-chapter.js
cd D:/novel_test && node --check .claude/workflows/bedrock-chapter.js && echo SYNTAX_OK
```
Expected: 五函数均在;`SYNTAX_OK`。

- [ ] **Step 3: Commit**

```bash
cd D:/novel_test && git add .claude/workflows/bedrock-chapter.js && git commit -m "$(cat <<'EOF'
refactor(bedrock-chapter): 删废弃 chapterWriterPrompt(stateful writer 接管)

writerPrompt 取代后无调用方。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 静态总检 + Python 回归

**Files:** 无改动;验证

- [ ] **Step 1: 结构 sanity**

Run:
```bash
cd D:/novel_test && grep -c "phase('" .claude/workflows/bedrock-chapter.js && grep -n "phase('" .claude/workflows/bedrock-chapter.js
```
Expected: `5`,顺序 Boot/Write/Revise/Consistency/Persist+Telemetry。

Run(变量声明无冲突):
```bash
cd D:/novel_test && grep -n "let prose\|let report\|const round" .claude/workflows/bedrock-chapter.js
```
Expected:`let prose`/`let report` 各**仅一处**(Write 段声明);`const round` 仅一处(Revise 段)。无重复声明。

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
Expected: 全 PASS(此前 319 passed,Python 零改,计数应稳定)。报告计数。若失败几乎必是误改 Python——`git diff master -- src/` 确认。

---

## Task 5: 端到端回归——vigilia ch13 + ch1

**Files:** 无改动;运行工作流验证

> 验收:writer 自纠结构(欠产 draft → ≥floor + L2 clean),editor 之后确认 + 做 style,终态 completed。**writer 不再把欠产甩给 editor。**

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

读 Workflow 日志:期望见 `writer 收敛: 结构 clean, N 字 → 进 editor`(writer 在源头把字数扩到位、L2 过),随后 editor run-l2 确认 + 做 style。**writer 不再产欠产稿甩给 editor 补**(对比 editor-stateful 版 writer 恒产 2200~2800)。

- [ ] **Step 3: 重跑 ch1(干净/开篇章)**

```
Workflow({ scriptPath: "D:/novel_test/.claude/workflows/bedrock-chapter.js",
           args: { project: "projects/vigilia", chapter: 1, volume: 1 } })
```
Expected: `status=ok`,L2-clean + completed。writer 自纠结构(若首版即过则 1 次迭代收敛)。

- [ ] **Step 4: 若 writer 未收敛——诊断**

若 ch13 writer 5 次未过 L2(实际 cap 3,若到 3 仍未过):
- 看日志:writer 是否真自主循环(show-paragraphs→commit→run-l2→扩→复测)?是否卡在 heredoc(stdin 指令没遵守,该用 pipe)?
- 若 writer 不循环 → writerPrompt 迭代协议指令没被遵守 → 调 prompt。
- 若 writer 循环但扩写仍不够 → 禁灌水约束过紧 / writer 扩不动 → 记录,可能需调 cap 或 prompt。
- 即便 writer 未收敛,editor 之后会兜底再验(冗余纠偏);终态若 editor 也修不好 → mark-unresolved(正确升级)。记录实际链路,上报。

---

## Self-Review

**Spec 覆盖:**
- Write 段 → stateful writer agent → Task 2 ✓
- writerPrompt(chapterWriterPrompt 内容 + 工具面/协议/返回契约)→ Task 1 ✓
- 工具面 commit-paragraphs + run-l2 + show-paragraphs(pipe stdin)→ Task 1 ✓(采纳独立审查)
- 两条红线(固定编排;收敛由 L2 客观判,JS 独立 l2Report 不信自报)→ Task 2 ✓
- round 不在 Write 声明(避 const 冲突)→ Task 2 ✓
- let report/let prose 在 Write 段声明(计划级修正 spec §4)→ Task 2 ✓
- 删 chapterWriterPrompt → Task 3 ✓
- commitAndL2 保留(Consistency 用)→ 不动 ✓
- 静态 + pytest + 端到端 → Task 4 + Task 5 ✓

**Placeholder 扫描:** 无 TBD/TODO;每步含完整代码或确切命令 + 期望输出。✓

**类型/签名一致:**
- `writerPrompt(ctx, project, chapter, volume)` → Task 1 定义、Task 2 调用签名一致(与 editorPrompt 同参序)✓
- `extractEditorJson`/`l2Report`/`readCurrentProse`/`extractProse`/`pythonCli`/`HYGIENE_RULES` → 均既有(master 存在),签名一致 ✓
- writer 返回字段 `{converged, iterations, final_passed, word_count, final_l2_violations}` → Task 1 契约、Task 2 仅读 `writer.iterations`/`writer.word_count`(遥测,不读 converged/final_passed 作 gate)✓
- `let report`/`let prose` Write 段声明、Revise/Consistency 重赋值、`const round` 仅 Revise 段 → Task 4 Step1 grep 验证无重复声明 ✓

**需 impl 核实:**
- Task 3 chapterWriterPrompt old_string 须与文件逐字匹配(全角标点/`ctx.reader_disclosed_secrets` 拼写);若不符 STOP 上报。
- Task 5:若 writer 不按迭代协议循环(stdin pipe / 扩写),调 prompt;editor 兜底冗余纠偏。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-21-stateful-writer-agent.md`. **分支 `bedrock-stateful-writer`(Task 1 Step 1 创建)。** 无 spike(模式已由 editor 验证)。两种执行:

1. **Subagent-Driven(推荐)** — 每 Task 派新 subagent + 两阶段 review。
2. **Inline Execution** — 本会话批量执行带 checkpoint。

选哪种?
