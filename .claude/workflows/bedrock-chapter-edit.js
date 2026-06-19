export const meta = {
  name: 'bedrock-chapter-edit',
  description: '磐石 V3 单章编辑（已落盘章节）：rewrite指令重写 / polish按需润色 / surgical段落外科 / recheck重检修复',
  phases: [
    { title: 'Load' },
    { title: 'Edit' },
    { title: 'Apply+L2' },
    { title: 'Repair' },
    { title: 'Style' },
    { title: 'Finalize' },
  ],
}

// ── 设计 ─────────────────────────────────────────────────
// 对【已落盘】章节做编辑。四模式分派，全部复用精简 relay：
//   - verdict（L2 / verify）一律由独立 relay 跑，编辑 agent 不碰。
//   - 编辑 agent 自带 Bash，自行 `show-paragraphs` 读当前正文/段落（只读，无信任问题）。
//   - 整章类（rewrite/polish）→ commit-paragraphs 覆盖；段落类（surgical）→ edit-paragraphs ops。
// 信任锚：最终 L2 由 relay 对落盘结果重算，与编辑 agent 无关。
// ─────────────────────────────────────────────────────────

const CWD = 'D:/novel_test'
let worstDrift = {}

// 文风硬约束(与 bedrock-chapter.js 同源):标点全角 / 禁"不是A是B" / 慎破折号。
const HYGIENE_RULES = [
  '【文风硬约束·必须遵守】(统计自对标参考作品)',
  '- 标点全角:中文正文一律 。,:;!? 禁半角 , . : ; ! ?',
  '- 禁"不是A是B"句式及一切变体("不是x。是x,"/"并非…而是"等)——一句都不许出现。',
  '- 慎用破折号(——):参考作品 96% 段落不用,非必要不写。',
  '- 段落短促、视角克制、不堆砌感官形容词。',
].join('\n')

// 文风注入块(与 bedrock-chapter.js ChapterWriter 同源):定性指令 + 正反例范例。
// 编辑智能体(rewrite/polish)此前只塞 HYGIENE_RULES,丢了 directive/examples —— 补齐到写作智能体同等。
function pct(n) { return Math.round((n || 0) * 1000) / 10 }
function styleBlock(ctx) {
  const out = []
  if (ctx.style_directive) out.push(`【文风指令·定性要求(高于统计指纹,必须贯彻)】`, ctx.style_directive, '')
  const ex = ctx.style_examples || {}
  if ((ex.good && ex.good.length) || (ex.bad && ex.bad.length)) {
    out.push('【风格示范】(对照以下范例的节奏/密度/句式/语气写作。**严禁复述范例原文**,只学其风格)')
    for (const s of (ex.good || [])) out.push(`  ✓ ${s}`)
    for (const s of (ex.bad || [])) out.push(`  ✗ ${s}（避免）`)
    out.push('')
  }
  return out
}

const _args = typeof args === 'string' ? JSON.parse(args) : (args || {})
const { project, chapter, volume, mode, instruction } = _args
const VALID = new Set(['rewrite', 'polish', 'surgical', 'recheck'])
if (!VALID.has(mode)) throw new Error(`未知 mode=${mode}，需 rewrite|polish|surgical|recheck`)

let ctx = null
if (mode !== 'recheck') {
  phase('Load')
  ctx = await bootContext(project, chapter, volume)
  log(`load: fingerprint=${ctx.fingerprint ? 'yes' : 'no'}, beats=${ctx.beat_contracts?.length || 0}`)
}

let report = null  // 最新 L2 报告（JS 解析，信任锚）

if (mode === 'rewrite') {
  phase('Edit')
  const prose = stripFences(await agent(rewritePrompt(ctx, project, chapter, instruction),
    { label: 'Edit-rewrite', phase: 'Edit' }))
  report = await commitAndL2(project, chapter, prose, 'rewrite')
  log(`rewrite L2 passed=${report.passed_hard_gate} violations=${(report.beat_violations || []).length}`)
}

else if (mode === 'polish') {
  phase('Edit')
  const prose = stripFences(await agent(polishOnDemandPrompt(ctx, project, chapter, instruction),
    { label: 'Edit-polish', phase: 'Edit' }))
  report = await commitAndL2(project, chapter, prose, 'polish')
  log(`polish L2 passed=${report.passed_hard_gate} violations=${(report.beat_violations || []).length}`)
}

else if (mode === 'surgical') {
  phase('Edit')
  const opsRaw = stripFences(await agent(surgicalPrompt(ctx, project, chapter, instruction),
    { label: 'Edit-surgical', phase: 'Edit' }))
  let ops
  try { ops = JSON.parse(opsRaw) } catch { throw new Error(`surgical agent 未返回合法 ops JSON: ${opsRaw.slice(0, 200)}`) }
  report = await applyOpsAndL2(project, chapter, ops, 'surgical')
  log(`surgical applied ${ops.length} ops, L2 passed=${report.passed_hard_gate} violations=${(report.beat_violations || []).length}`)
}

else {  // recheck
  phase('Apply+L2')
  report = await l2Only(project, chapter)
  log(`recheck L2 passed=${report.passed_hard_gate} violations=${(report.beat_violations || []).length}`)
}

// Repair 循环（仅当上面 L2 未过；rewrite/polish/surgical/recheck 共用）
phase('Repair')
let round = 0
const sigsByRound = []
while (!report.passed_hard_gate && round < 3) {
  sigsByRound.push((report.beat_violations || []).map(v => `${v.beat_id}:${v.kind}`).sort().join(','))
  const prose = stripFences(await agent(repairPrompt(report, project, chapter),
    { label: `Edit-repair-r${round + 1}`, phase: 'Repair' }))
  report = await commitAndL2(project, chapter, prose, `repair-r${round + 1}`)
  round++
  log(`repair r${round} passed=${report.passed_hard_gate} violations=${(report.beat_violations || []).length}`)
}
const likelyRuleOrModel = round === 3
    && new Set(sigsByRound.slice(-2)).size === 1 && !report.passed_hard_gate
if (!report.passed_hard_gate) {
  await pythonCli(
    `mark-unresolved --project ${project} --chapter ${chapter} --rule-or-model ${likelyRuleOrModel ? 1 : 0}`,
    { phase: 'Repair', stdin: JSON.stringify(report.beat_violations || []) })
  log(`l2 unresolved after 3 rounds, likely_rule_or_model=${likelyRuleOrModel}`)
}

// Style 阶段:编辑/重写引入的文风漂移测量 + 定向收敛循环(≤2 轮,回喂剩余 hint)。
// rewrite/polish 改了整章 prose 才收敛;surgical/recheck 仅测+记 drift(段落外科/重检不大改文风)。
const STYLE_MAX_ROUNDS = 2
phase('Style')
if (report.passed_hard_gate) {
  let drift = await styleCheck(project, chapter, volume)
  _trackDrift(drift)
  let sr = 0
  const canConverge = (mode === 'rewrite' || mode === 'polish')
  while (drift && drift.drifted && drift.drifted.length && canConverge && sr < STYLE_MAX_ROUNDS) {
    const hints = drift.drifted.map(d => `${d.hint}(实测${pct(d.actual)}/目标${pct(d.target)})`).join('；')
    log(`style drift r${sr + 1} after ${mode}: ${drift.drifted.length}项 [${drift.target_source}] → ${hints}`)
    const prose = stripFences(await agent(stylePolishPrompt(ctx, hints, project, chapter),
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
  else if (canConverge && sr >= STYLE_MAX_ROUNDS) log(`style: 仍 ${left} 项飘,达 ${STYLE_MAX_ROUNDS} 轮上限`)
  else if (!canConverge) log(`style: ${left}项漂移(${mode}模式仅测不收敛) [${(drift && drift.target_source) || '无目标'}]`)
}

phase('Finalize')
const persisted = await finalize(project, chapter, null, round, worstDrift)
if (!persisted) {
  await pythonCli(`mark-forced-persist-failed --project ${project} --chapter ${chapter}`, { phase: 'Finalize' })
  return { status: 'failed', reason: 'forced_persist_failed', mode, rounds: round }
}
return { status: 'ok', mode, chapter, rounds: round, passed: report.passed_hard_gate,
         words: report.metrics?.word_count }

// ── relays ──

async function bootContext(project, chapter, volume) {
  const raw = stripFences(await pythonCli(
    `boot-context --project ${project} --chapter ${chapter} --volume ${volume}`, { phase: 'Load' }))
  try { return JSON.parse(raw) } catch { return { beat_contracts: [], fingerprint: null, _raw: raw } }
}

// commit/edit 各单命令 → run-l2 单命令(l2Only)。verdict 独立跑,不与 commit 混——
// 免 agent 捏坏多命令 stdout 假阴性(曾致 style-polish 误判破 beat + mark 命令调坏)。
async function commitAndL2(project, chapter, prose, label) {
  await pythonCli(`commit-paragraphs --project ${project} --chapter ${chapter}`,
    { phase: 'Apply+L2', stdin: prose })
  return await l2Only(project, chapter)
}

async function applyOpsAndL2(project, chapter, ops, label) {
  await pythonCli(`edit-paragraphs --project ${project} --chapter ${chapter}`,
    { phase: 'Apply+L2', stdin: JSON.stringify(ops) })
  return await l2Only(project, chapter)
}

async function l2Only(project, chapter) {
  const raw = stripFences(await pythonCli(`run-l2 --project ${project} --chapter ${chapter}`, { phase: 'Apply+L2' }))
  try { return JSON.parse(raw) } catch { return { passed_hard_gate: false, beat_violations: [], _raw: raw } }
}

// 文风漂移测量 relay(与 bedrock-chapter.js 同源):style-check 单命令,回 {drifted, target_source, metrics}。
// 编辑工作流此前完全不测文风漂移(_trackDrift 读 run-l2 的 drift 字段,但 L2 不吐 drift→死代码)。
async function styleCheck(project, chapter, volume) {
  const raw = stripFences(await pythonCli(
    `style-check --project ${project} --chapter ${chapter} --volume ${volume}`, { phase: 'Style' }))
  try { return JSON.parse(raw) } catch { return { drifted: [], ok: true } }
}

// 编辑后定向 style-polish:读当前正文 + 漂移 hints + 指令/范例/hygiene,收敛回喂。
function stylePolishPrompt(ctx, hints, project, chapter) {
  return [
    '# Edit 子代理 — 文风漂移定向收敛',
    `先执行只读命令拿当前正文：cd "${CWD}" && python -m src.bedrock show-paragraphs --project ${project} --chapter ${chapter}`,
    '把每段 text 按序拼成当前正文。',
    '',
    ...styleBlock(ctx),
    HYGIENE_RULES,
    `本章文风漂移(需定向收敛,保持剧情/字数/beat 不变):${hints}`,
    '只改与漂移相关的句式/标点/密度,不增删段落,不改剧情。返回收敛后的【整章正文】纯文本,不裹围栏。',
  ].join('\n')
}

async function finalize(project, chapter, exportPath, round, drift) {
  const exportArg = exportPath ? ` --export-path ${exportPath}` : ''
  // verify 判决=独立单命令 relay（信任锚），不与遥测混跑（多命令序列 agent 偶发误判 forced_persist_failed）
  const verifyOut = stripFences(await pythonCli(
    `verify-persisted --project ${project} --chapter ${chapter}${exportArg}`,
    { phase: 'Finalize' }))
  await telemetryRelay(project, chapter, round, drift)
  return verifyOut.trim() === 'True'
}

async function telemetryRelay(project, chapter, round, drift) {
  const runtimeStdin = JSON.stringify({ invocations: [], llm_calls: [] })
  const driftBlock = (drift && Object.keys(drift).length)
    ? `\ncd "${CWD}" && python -m src.bedrock mark-advisory-drift --project ${project} --chapter ${chapter} <<'__STDIN__'\n${JSON.stringify(drift)}\n__STDIN__`
    : ''
  const prompt = [
    `你在项目根目录。按顺序执行下面的命令（遥测 + first_review 备份，全部执行即可），最后返回单行 "done"。`,
    `若某条非 0 退出仍继续其余，最后返回 ERROR:<which>:<stderr 首行>。`,
    ``,
    `cd "${CWD}" && python -m src.bedrock collect-runtime --project ${project} --chapter ${chapter} --editing-rounds ${round} <<'__STDIN__'`,
    runtimeStdin,
    `__STDIN__`,
    `cd "${CWD}" && python -m src.bedrock export-chapter-json --project ${project} --chapter ${chapter} --stage first_review`,
    `cd "${CWD}" && python -m src.bedrock refresh-style-actual --project ${project}`,
    driftBlock.trim(),
  ].join('\n')
  try {
    const raw = stripFences(await agent(prompt, { label: 'telemetry', phase: 'Finalize' }))
    if (String(raw).startsWith('ERROR:')) log(`telemetry 部分失败（不阻塞）: ${raw}`)
  } catch (e) { log(`telemetry relay 异常（不阻塞）: ${e.message}`) }
}

async function pythonCli(cmdStr, opts = {}) {
  const sub = cmdStr.split(/\s+/)[0]
  const stdinBlock = opts.stdin != null
    ? `\n用带引号 heredoc 传入标准输入(分隔符 __STDIN__）：\n<<'__STDIN__'\n${opts.stdin}\n__STDIN__\n`
    : ''
  const prompt = [
    `你在项目根目录。执行命令，把【stdout 原文】逐字返回（无解释/围栏）。非 0 退出返回 ERROR:<code>:<stderr 首行>。`,
    ``,
    `cd "${CWD}" && python -m src.bedrock ${cmdStr}${stdinBlock}`,
  ].join('\n')
  const out = await agent(prompt, { label: `cli:${sub}`, phase: opts.phase || 'Load' })
  const s = typeof out === 'string' ? out : String(out ?? '')
  if (s.startsWith('ERROR:')) throw new Error(`pythonCli ${sub} 失败: ${s}`)
  return s
}

// ── prompts（每个编辑 agent 自带 Bash 跑 show-paragraphs 读当前正文，只读无信任问题）──

function rewritePrompt(ctx, project, chapter, instruction) {
  const prev = ctx.prev_chapter_tail
    ? [`【上一章收尾】（重写后本章开篇须自然承接，禁止复述）：${ctx.prev_chapter_tail}`, '']
    : []
  const canon = (ctx.characters && ctx.characters.length)
    ? [`【角色正典·严格遵守】代词/性别/称呼按下表不得擅改：` + JSON.stringify(ctx.characters.map(c => ({ name: c.name, pronoun: c.pronoun, gender: c.gender, role: c.role })))]
    : []
  const multi = (ctx.beat_contracts && ctx.beat_contracts.length > 1)
    ? [`【多 beat 章，共 ${ctx.beat_contracts.length} beat】每个 beat 内容块前单独起一行 @@beat:<beat_id>@@（按契约顺序，标记行单独成段），让系统正确归属段落。`]
    : []
  return [
    '# Edit 子代理 — 指令式整章重写',
    `先执行只读命令拿当前正文：cd "${CWD}" && python -m src.bedrock show-paragraphs --project ${project} --chapter ${chapter}`,
    '把返回 JSON 里每段的 text 按原顺序拼成当前正文。',
    '',
    ...prev,
    ...canon,
    ...multi,
    ...styleBlock(ctx),
    HYGIENE_RULES,
    '按下面【重写指令】改写整章，保持 beat 契约与 pov，3000–5000 字，不自报字数。',
    `重写指令：${instruction || '（未给出具体指令，做一次整体打磨重写）'}`,
    'beat 契约：' + JSON.stringify(ctx.beat_contracts, null, 2),
    '',
    '返回重写后的【整章正文】纯文本（段间空行），不裹 markdown 围栏，不写标题行。',
  ].join('\n')
}

function polishOnDemandPrompt(ctx, project, chapter, instruction) {
  return [
    '# Edit 子代理 — 按需正向润色',
    `先执行只读命令拿当前正文：cd "${CWD}" && python -m src.bedrock show-paragraphs --project ${project} --chapter ${chapter}`,
    '把返回 JSON 里每段 text 按序拼成当前正文。',
    '',
    '目标文风分布：' + JSON.stringify(ctx.fingerprint || {}, null, 2),
    ...styleBlock(ctx),
    `附加要求：${instruction || '（无，仅对准分布微调）'}`,
    HYGIENE_RULES,
    '保持剧情与字数，不增删段落，不破坏 beat；同时严格执行文风硬约束。',
    '返回润色后的【整章正文】纯文本，不裹围栏。',
  ].join('\n')
}

function surgicalPrompt(ctx, project, chapter, instruction) {
  return [
    '# Edit 子代理 — 段落级外科手术',
    `先执行只读命令拿当前段落（含 para_id）：cd "${CWD}" && python -m src.bedrock show-paragraphs --project ${project} --chapter ${chapter}`,
    '',
    '按下面指令对段落做【最小改动】。只输出一个 JSON 数组（ops），不要正文、不要解释、不要围栏。',
    `指令：${instruction}`,
    '',
    'op schema（任选组合）：',
    '  {"op":"update","para_id":N,"text":"新文本"}',
    '  {"op":"insert","after_seq":N,"text":"..."}   // after_seq=0 表章首',
    '  {"op":"delete","para_id":N}',
    '  {"op":"reorder","order":[para_id,...]}        // 必须是该章全部 para_id 的排列',
    '',
    '只返回 JSON 数组本身，例如：[{"op":"update","para_id":215,"text":"..."}]',
  ].join('\n')
}

function repairPrompt(report, project, chapter) {
  const lines = [
    '# Edit 子代理 — 定向修复（L2 违规）',
    `先执行只读命令拿当前正文：cd "${CWD}" && python -m src.bedrock show-paragraphs --project ${project} --chapter ${chapter}`,
    '把返回 JSON 里每段 text 按序拼成当前正文。',
    '',
    '违规清单（beat_id / kind / detail / fix_hint）：',
  ]
  for (const v of (report.beat_violations || [])) {
    lines.push(`  - beat${v.beat_id} [${v.kind}]: ${v.detail} → ${v.fix_hint}`)
  }
  lines.push('', '只改违规相关段落，不引入新违规，不压缩剧情。返回修订后的【整章正文】纯文本，不裹围栏。')
  return lines.join('\n')
}

function stripFences(s) {
  if (typeof s !== 'string') return String(s ?? '')
  let t = s.trim()
  const m = t.match(/^```[a-zA-Z]*\n([\s\S]*?)\n```$/)
  if (m) t = m[1]
  return t.trim()
}

// 跟踪最差轮文风漂移(取 styleCheck 结果,drifted 数最多者)。fed into finalize→mark-advisory-drift。
// 旧版读 report.drift(run-l2 输出)是死代码——L2 不吐 drift;现改吃真实 styleCheck 结果。
function _trackDrift(drift) {
  if (!drift || !drift.drifted) return
  if (drift.drifted.length >= driftCount(worstDrift)) worstDrift = drift
}
function driftCount(d) { return (d && d.drifted) ? d.drifted.length : 0 }
