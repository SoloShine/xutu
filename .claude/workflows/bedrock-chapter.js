export const meta = {
  name: 'bedrock-chapter',
  description: '磐石 V3 单章管线：Boot→Write→commit+L2→Revise(manifest 驱动定向修订,复测重喂≤2)→Consistency(角色正典 ops)→专名(ops)→Finalize',
  phases: [
    { title: 'Boot' },
    { title: 'Write' },
    { title: 'Revise' },
    { title: 'Consistency' },
    { title: 'Persist+Telemetry' },
  ],
}

// ── 设计原则 ─────────────────────────────────────────────
// 沙箱无 Node API：每条 CLI 必须经 agent。但绝不为减 agent 而破信任锚——
// L2 / verify-persisted 等 verdict 一律由【独立于写作 agent 的 relay】执行，
// 原文回传，由确定性 JS 解析。只压缩"纯转发"冗余：
//   - commit-paragraphs + run-l2 → 1 relay（同侧、相邻、commit 非判决）
//   - verify-persisted + collect-runtime + mark-advisory-drift → 1 finalize relay
// 写作/润色/修复 agent 不碰任何 verdict。一个 checkpoint 都不丢。
// ─────────────────────────────────────────────────────────

const CWD = 'D:/novel_test'

// 文风硬约束(基线 floor + 标点/句式 hygiene)。即便无 style 指纹也施加;有指纹时 Polish 再叠加对准。
// 来源:对标参考作品统计(notXisY≈0.15%、96%段无破折号)+ 用户反馈(标点半角混用、不是A是B滥用)。
const HYGIENE_RULES = [
  '【文风硬约束·必须遵守】(统计自对标参考作品)',
  '- 标点全角:中文正文一律 。,:;!? 已由系统归一,但你也要自觉,不要吐半角 , . : ; ! ?',
  '- 禁"不是A是B"句式及一切变体("不是x。是x,"/"并非…而是"/"不在于…在于"等)——一句都不许出现,这是偷懒句式,参考好作品仅 0.15%。',
  '- 慎用破折号(——):参考作品 96% 段落不用,非必要坚决不写;要转折用句号断句。',
  '- 段落短促、视角克制、不堆砌感官形容词;少用"地"字副词尾。',
].join('\n')

// drift 最差轮累积器（须在主流程调用前初始化，避 TDZ）
let worstDrift = {}

// Revise 复测重喂上限(收束原 repair≤3 + style≤2,合并取严的 2)。
const REVISE_MAX_ROUNDS = 2

const _args = typeof args === 'string' ? JSON.parse(args) : (args || {})
const { project, chapter, volume, exportPath } = _args

// 1. Boot（独立 relay：JS 需 ctx.fingerprint 门控 Polish）
phase('Boot')
const ctx = await bootContext(project, chapter, volume)
log(`boot: ${ctx.beat_contracts?.length || 0} beats, fingerprint=${ctx.fingerprint ? 'yes' : 'no'}`)

// 2. Write：ChapterWriter 产正文 → commit+L2 relay（verdict 由 relay 跑，JS 解析）
phase('Write')
let prose = extractProse(await agent(chapterWriterPrompt(ctx), { label: 'ChapterWriter', phase: 'Write' }))
let report = await commitAndL2(project, chapter, prose, 'Write')
_trackDrift(report)
log(`L2 r0 passed=${report.passed_hard_gate} violations=${(report.beat_violations || []).length} words=${report.metrics?.word_count}`)

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

// 4b. Consistency：角色正典一致性编辑（复刻 V1 EditAgent，每章跑）。
// 对刚写章节查代词/性别/称呼/设定一致性 → surgical ops 修 → 重 L2。ops-based：吐叙述→解析失败→跳过，不毁章。
phase('Consistency')
if (report.passed_hard_gate && ctx.characters && ctx.characters.length) {
  const opsRaw = extractProse(await agent(consistencyPrompt(ctx, project, chapter),
    { label: 'Edit-consistency', phase: 'Consistency' }))
  const ops = parseOpsList(opsRaw)
  if (ops && ops.length) {
    const preConsistencyProse = prose   // post-Polish 全文;Consistency ops 只动 DB 不动此串
    const after = await applyOpsAndL2(project, chapter, ops, 'consistency')
    _trackDrift(after)
    if (after.passed_hard_gate) {
      log(`consistency: ${ops.length} ops applied (代词/设定一致)`)
      report = after
    } else {
      // ops 破 L2 → 回退 pre-Consistency(重 commit prose)。+1 relay;0 新 agent。
      await commitAndL2(project, chapter, preConsistencyProse, 'consistency-revert')
      await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`, { phase: 'Consistency' })
      log(`consistency ops 破坏 L2 → 回退 pre-Consistency 版(${ops.length} ops 丢弃)`)
      // report 保持 pre-Consistency(仍 passed),不取 after
    }
  } else {
    log('consistency: 无需改动')
  }
}

// 4b2. Unit D:专名硬校验(确定性 relay,零 LLM)。Tier1 ops 经 edit-paragraphs 落(留 amendment+flag),Tier2 进 flag 供卷审。
if (report.passed_hard_gate) {
  const pnRaw = extractProse(await pythonCli(
    `check-proper-nouns --project ${project} --chapter ${chapter}`, { phase: 'Consistency' }))
  let pn
  try { pn = JSON.parse(pnRaw) } catch { pn = { ops: [], escalate: [] } }
  if (pn.ops && pn.ops.length) {
    await pythonCli(`edit-paragraphs --project ${project} --chapter ${chapter}`,
      { phase: 'Consistency', stdin: JSON.stringify(pn.ops) })
    log(`proper-nouns: ${pn.autoedit_count} 处自动改(已留 amendment+flag)`)
  }
  if (pn.escalate && pn.escalate.length) log(`proper-nouns: ${pn.escalate.length} 处歧义 escalate 供卷审`)
}

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

// 5. Finalize：verify-persisted + collect-runtime + mark-advisory-drift 一 relay 收尾
phase('Persist+Telemetry')
const persisted = await finalize(project, chapter, exportPath, round, worstDrift)
if (!persisted) {
  await pythonCli(`mark-forced-persist-failed --project ${project} --chapter ${chapter}`, { phase: 'Persist+Telemetry' })
  return { status: 'failed', reason: 'forced_persist_failed', rounds: round }
}
return { status: 'ok', chapter, rounds: round, passed: report.passed_hard_gate,
         words: report.metrics?.word_count }

// ── relay 与 prompt ──

async function bootContext(project, chapter, volume) {
  const raw = extractProse(await pythonCli(
    `boot-context --project ${project} --chapter ${chapter} --volume ${volume}`, { phase: 'Boot' }))
  try { return JSON.parse(raw) } catch { return { beat_contracts: [], fingerprint: null, _raw: raw } }
}

// run-l2 单命令→解析报告。verdict 独立单命令跑(信任锚),不与 commit 混跑——
// 免 agent 捏坏多命令 stdout 假阴性(曾导致 style-polish 误判破 beat + 末尾 mark 命令调坏)。
async function l2Report(project, chapter, phase = 'L2+Repair') {
  const raw = extractProse(await pythonCli(`run-l2 --project ${project} --chapter ${chapter}`, { phase }))
  try { return JSON.parse(raw) } catch { return { passed_hard_gate: false, beat_violations: [], _raw: raw } }
}

// commit 正文(stdin) → run-l2,各单命令。verdict 由 l2Report 独立跑,不经写作 agent。
async function commitAndL2(project, chapter, prose, label) {
  await pythonCli(`commit-paragraphs --project ${project} --chapter ${chapter}`,
    { phase: 'L2+Repair', stdin: prose })
  return await l2Report(project, chapter)
}

// 文风漂移测量 relay：style-check 单命令,回 JSON {drifted, target_source, metrics}。
async function styleCheck(project, chapter, volume) {
  const raw = extractProse(await pythonCli(
    `style-check --project ${project} --chapter ${chapter} --volume ${volume}`, { phase: 'Style' }))
  try { return JSON.parse(raw) } catch { return { drifted: [], ok: true } }
}

function pct(x) { return Math.round((x || 0) * 100) + '%' }

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

// edit-paragraphs(ops,stdin) → run-l2,各单命令(一致性编辑用;verdict 独立跑)。
async function applyOpsAndL2(project, chapter, ops, label) {
  await pythonCli(`edit-paragraphs --project ${project} --chapter ${chapter}`,
    { phase: 'Consistency', stdin: JSON.stringify(ops) })
  return await l2Report(project, chapter, 'Consistency')
}

// 解析一致性 agent 的 ops JSON 数组；非数组/解析失败 → null（→ 跳过，章节不动）。
function parseOpsList(raw) {
  const t = raw.trim()
  const i = t.indexOf('[')
  if (i < 0) return null
  let depth = 0, inStr = false, esc = false
  for (let j = i; j < t.length; j++) {
    const c = t[j]
    if (inStr) { if (esc) esc = false; else if (c === '\\') esc = true; else if (c === '"') inStr = false; continue }
    if (c === '"') inStr = true
    else if (c === '[') depth++
    else if (c === ']') { depth--; if (depth === 0) { try { const v = JSON.parse(t.slice(i, j + 1)); return Array.isArray(v) ? v : null } catch { return null } } }
  }
  return null
}

// 一致性编辑 prompt：读当前章 + 角色正典，查代词/性别/称呼/设定一致性，返 ops 修。
function consistencyPrompt(ctx, project, chapter) {
  const canon = ctx.characters.map(c => `${c.name}(代词${c.pronoun}${c.gender ? '/' + c.gender : ''},${c.role})`).join('； ')
  return [
    '# Edit 子代理 — 角色正典一致性检查（每章跑，复刻 V1 EditAgent）',
    `先读本章当前段落（只读，含 para_id）：cd "${CWD}" && python -m src.bedrock show-paragraphs --project ${project} --chapter ${chapter}`,
    '',
    `【角色正典·判据】${canon}`,
    '逐段检查并修正：',
    '  · 代词/性别：每个角色的他/她必须匹配正典（注意代词消解——"他"靠近某角色未必指该角色，要判指代）。',
    '  · 称呼/身份一致：角色头衔、职业、关系不得前后矛盾。',
    '  · 设定矛盾：与角色 personality/role 冲突的描写。',
    '**只改不一致处，不动其余。**代词消解要准（别把指代陆沉的"他"误改成"她"）。',
    '',
    '**返回一个 JSON ops 数组**（不要正文/解释/思考过程/围栏）：',
    '  [{"op":"update","para_id":N,"text":"修正后整段"}, {"op":"delete","para_id":N}]',
    '无不一致则返回 []。单段多处错用多个 update op。只返回数组本身。',
  ].join('\n')
}

// finalize：verify 判决由【独立单命令 relay】跑（信任锚），遥测/备份另起 relay。
// 旧版一条 relay 跑 4 命令序列却只回首条 stdout("True")——agent 不可靠地隔离首条输出，
// 偶尔把 "True" 与遥测输出混在一起→误判 forced_persist_failed（voidwright ch1 中招，
// 实际内容已落盘 L2 过）。单命令 relay 可靠回传 stdout；遥测失败不阻塞判决。
async function finalize(project, chapter, exportPath, round, drift) {
  const exportArg = exportPath ? ` --export-path ${exportPath}` : ''
  const verifyOut = extractProse(await pythonCli(
    `verify-persisted --project ${project} --chapter ${chapter}${exportArg}`,
    { phase: 'Persist+Telemetry' }))
  await telemetryRelay(project, chapter, round, drift)
  return verifyOut.trim() === 'True'
}

// 遥测 + 备份（collect-runtime / draft JSON / advisory drift）。返回值忽略，失败不阻塞 verify 判决。
async function telemetryRelay(project, chapter, round, drift) {
  const runtimeStdin = JSON.stringify({ invocations: [], llm_calls: [] })
  const driftBlock = (drift && Object.keys(drift).length)
    ? `\ncd "${CWD}" && python -m src.bedrock mark-advisory-drift --project ${project} --chapter ${chapter} <<'__STDIN__'\n${JSON.stringify(drift)}\n__STDIN__`
    : ''
  const prompt = [
    `你在项目根目录。按顺序执行下面的命令（遥测采集 + 备份，全部执行即可），最后返回单行 "done"。`,
    `若某条非 0 退出仍继续其余，最后返回 ERROR:<which>:<stderr 首行>。`,
    ``,
    `cd "${CWD}" && python -m src.bedrock collect-runtime --project ${project} --chapter ${chapter} --editing-rounds ${round} <<'__STDIN__'`,
    runtimeStdin,
    `__STDIN__`,
    `cd "${CWD}" && python -m src.bedrock export-chapter-json --project ${project} --chapter ${chapter} --stage draft`,
    `cd "${CWD}" && python -m src.bedrock refresh-style-actual --project ${project}`,
    driftBlock.trim(),
  ].join('\n')
  try {
    const raw = extractProse(await agent(prompt, { label: 'telemetry', phase: 'Persist+Telemetry' }))
    if (String(raw).startsWith('ERROR:')) log(`telemetry 部分失败（不阻塞）: ${raw}`)
  } catch (e) { log(`telemetry relay 异常（不阻塞）: ${e.message}`) }
}

// 通用单命令 relay（仅 Boot 与失败路径 mark-* 用）
async function pythonCli(cmdStr, opts = {}) {
  const sub = cmdStr.split(/\s+/)[0]
  const stdinBlock = opts.stdin != null
    ? `\n用带引号 heredoc 传入标准输入(分隔符 __STDIN__，禁止展开)：\n<<'__STDIN__'\n${opts.stdin}\n__STDIN__\n`
    : ''
  const prompt = [
    `你在项目根目录。执行下面命令，把【标准输出原文】逐字作为最终返回值（不要解释/围栏）。`,
    `若非 0 退出，返回 ERROR:<code>:<stderr 首行>。`,
    ``,
    `cd "${CWD}" && python -m src.bedrock ${cmdStr}${stdinBlock}`,
  ].join('\n')
  const out = await agent(prompt, { label: `cli:${sub}`, phase: opts.phase || 'Boot' })
  const s = typeof out === 'string' ? out : String(out ?? '')
  if (s.startsWith('ERROR:')) throw new Error(`pythonCli ${sub} 失败: ${s}`)
  return s
}

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

// Unit A0:正文定界提取。只认 ```prose 标签区;无则原样返回(交 commit 段 sanitize 防线 + L2 non_prose 兜底)。
function extractProse(s) {
  if (typeof s !== 'string') return String(s ?? '')
  const blocks = [...s.matchAll(/```prose[ \t]*\n([\s\S]*?)\n```/g)].map(m => m[1].trim())
  if (blocks.length) return blocks.sort((a, b) => b.length - a.length)[0]
  return s.trim()
}

// 跟踪最差轮文风漂移(取 styleCheck 结果,drifted 数最多者)。fed into finalize→mark-advisory-drift。
// 旧版读 report.drift(run-l2 输出)是死代码——L2 不吐 drift;改吃真实 styleCheck 结果。
function _trackDrift(drift) {
  if (!drift || !drift.drifted) return
  const worst = (worstDrift && worstDrift.drifted) ? worstDrift.drifted.length : 0
  if (drift.drifted.length >= worst) worstDrift = drift
}
