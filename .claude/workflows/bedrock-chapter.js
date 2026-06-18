export const meta = {
  name: 'bedrock-chapter',
  description: '磐石 V3 单章管线：Boot→Write→commit+L2→Repair(≤3轮)→Polish(指纹门控)→Consistency(角色正典)→Style(漂移测量+收敛)→Finalize',
  phases: [
    { title: 'Boot' },
    { title: 'Write' },
    { title: 'L2+Repair' },
    { title: 'Polish' },
    { title: 'Consistency' },
    { title: 'Style' },
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

const _args = typeof args === 'string' ? JSON.parse(args) : (args || {})
const { project, chapter, volume, exportPath } = _args

// 1. Boot（独立 relay：JS 需 ctx.fingerprint 门控 Polish）
phase('Boot')
const ctx = await bootContext(project, chapter, volume)
log(`boot: ${ctx.beat_contracts?.length || 0} beats, fingerprint=${ctx.fingerprint ? 'yes' : 'no'}`)

// 2. Write：ChapterWriter 产正文 → commit+L2 relay（verdict 由 relay 跑，JS 解析）
phase('Write')
let prose = stripFences(await agent(chapterWriterPrompt(ctx), { label: 'ChapterWriter', phase: 'Write' }))
let report = await commitAndL2(project, chapter, prose, 'Write')
_trackDrift(report)
log(`L2 r0 passed=${report.passed_hard_gate} violations=${(report.beat_violations || []).length} words=${report.metrics?.word_count}`)

// 3. L2 + Repair 循环（≤3 轮；签名比对、likely_rule_or_model 仍在 JS）
phase('L2+Repair')
let round = 0
const sigsByRound = []
while (!report.passed_hard_gate && round < 3) {
  sigsByRound.push((report.beat_violations || []).map(v => `${v.beat_id}:${v.kind}`).sort().join(','))
  prose = stripFences(await agent(editRepairPrompt(report, prose), { label: `Edit-repair-r${round + 1}`, phase: 'L2+Repair' }))
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
  prose = stripFences(await agent(editPolishPrompt(ctx, prose), { label: 'Edit-polish', phase: 'Polish' }))
  report = await commitAndL2(project, chapter, prose, 'polish')
  _trackDrift(report)
  if (!report.passed_hard_gate) {
    await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`, { phase: 'Polish' })
    log('polish introduced beat violation, flagged')
  }
} else {
  log('polish skipped (no fingerprint or L2 not passed)')
}

// 4b. Consistency：角色正典一致性编辑（复刻 V1 EditAgent，每章跑）。
// 对刚写章节查代词/性别/称呼/设定一致性 → surgical ops 修 → 重 L2。ops-based：吐叙述→解析失败→跳过，不毁章。
phase('Consistency')
if (report.passed_hard_gate && ctx.characters && ctx.characters.length) {
  const opsRaw = stripFences(await agent(consistencyPrompt(ctx, project, chapter),
    { label: 'Edit-consistency', phase: 'Consistency' }))
  const ops = parseOpsList(opsRaw)
  if (ops && ops.length) {
    const after = await applyOpsAndL2(project, chapter, ops, 'consistency')
    _trackDrift(after)
    if (!after.passed_hard_gate) {
      await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`, { phase: 'Consistency' })
      log(`consistency broke beat (${ops.length} ops) → flagged`)
      report = after
    } else {
      log(`consistency: ${ops.length} ops applied (代词/设定一致)`)
      report = after
    }
  } else {
    log('consistency: 无需改动')
  }
}

// 4c. Style：章级文风漂移测量 + 定向收敛闭环。
// 写后测本章标量指标 vs 目标(卷级→作品级→自洽滚动均值),明显飘→定向 style-polish 回喂具体
// 漂移维度→重 L2→复测。单章噪声大,只对明显偏离(dash/notXisY/修辞/对白比)动手,句长不硬卡。
phase('Style')
if (report.passed_hard_gate) {
  const drift = await styleCheck(project, chapter, volume)
  if (drift && drift.drifted && drift.drifted.length) {
    const hints = drift.drifted.map(d => `${d.hint}(实测${pct(d.actual)}/目标${pct(d.target)})`).join('；')
    log(`style drift: ${drift.drifted.length}项 [${drift.target_source}] → ${hints}`)
    const prose = stripFences(await agent(stylePolishPrompt(ctx, hints, project, chapter),
      { label: 'Edit-style', phase: 'Style' }))
    const after = await commitAndL2(project, chapter, prose, 'style')
    _trackDrift(after)
    if (after.passed_hard_gate) {
      report = after
      const recheck = await styleCheck(project, chapter, volume)
      log(`style 收敛后复测: ${recheck.drifted ? recheck.drifted.length : 0}/${drift.drifted.length}项仍飘`)
    } else {
      await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`, { phase: 'Style' })
      log('style-polish broke beat → flagged')
      report = after
    }
  } else {
    log(`style: 无明显漂移 [${(drift && drift.target_source) || '无目标'}]`)
  }
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
  const raw = stripFences(await pythonCli(
    `boot-context --project ${project} --chapter ${chapter} --volume ${volume}`, { phase: 'Boot' }))
  try { return JSON.parse(raw) } catch { return { beat_contracts: [], fingerprint: null, _raw: raw } }
}

// 单 agent：先 commit 正文(stdin)，再 run-l2，回传 run-l2 原始 stdout。verdict 不经写作 agent。
async function commitAndL2(project, chapter, prose, label) {
  const prompt = [
    `你在项目根目录工作。按顺序执行两条命令，把【第二条命令 run-l2 的标准输出原文】逐字作为最终返回值。`,
    `严格要求：只返回 run-l2 的 stdout（一段 JSON），不要解释、不要 markdown 围栏。`,
    `若任一命令非 0 退出，返回一行：ERROR:<which>:<stderr 首行>。`,
    ``,
    `cd "${CWD}" && python -m src.bedrock commit-paragraphs --project ${project} --chapter ${chapter} <<'__STDIN__'`,
    prose,
    `__STDIN__`,
    `cd "${CWD}" && python -m src.bedrock run-l2 --project ${project} --chapter ${chapter}`,
  ].join('\n')
  const raw = stripFences(await agent(prompt, { label: `commit+l2:${label}`, phase: 'L2+Repair' }))
  if (raw.startsWith('ERROR:')) throw new Error(`commitAndL2(${label}) 失败: ${raw}`)
  try { return JSON.parse(raw) } catch { return { passed_hard_gate: false, beat_violations: [], _raw: raw } }
}

// 文风漂移测量 relay：style-check 单命令,回 JSON {drifted, target_source, metrics}。
async function styleCheck(project, chapter, volume) {
  const raw = stripFences(await pythonCli(
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

// 单 agent：edit-paragraphs(ops) + run-l2，回传 run-l2 原文（一致性编辑用；verdict 不经编辑 agent）。
async function applyOpsAndL2(project, chapter, ops, label) {  const opsJson = JSON.stringify(ops)
  const prompt = [
    `你在项目根目录。按序执行两条命令，把【第二条 run-l2 的 stdout 原文】逐字返回（一段 JSON，无围栏/解释）。`,
    `若非 0 退出返回 ERROR:<which>:<stderr 首行>。`,
    ``,
    `cd "${CWD}" && python -m src.bedrock edit-paragraphs --project ${project} --chapter ${chapter} <<'__STDIN__'`,
    opsJson,
    `__STDIN__`,
    `cd "${CWD}" && python -m src.bedrock run-l2 --project ${project} --chapter ${chapter}`,
  ].join('\n')
  const raw = stripFences(await agent(prompt, { label: `editops+l2:${label}`, phase: 'Consistency' }))
  if (raw.startsWith('ERROR:')) throw new Error(`applyOpsAndL2(${label}) 失败: ${raw}`)
  try { return JSON.parse(raw) } catch { return { passed_hard_gate: false, beat_violations: [] } }
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
  const verifyOut = stripFences(await pythonCli(
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
    const raw = stripFences(await agent(prompt, { label: 'telemetry', phase: 'Persist+Telemetry' }))
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
  lines.push('', '下面是上一版整章正文。只改与违规相关段落，不引入新违规，不压缩剧情，保持其余原文。',
             '返回修订后的【整章正文】纯文本，不裹围栏。', '', '---上一版---', prevProse)
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
    '保持剧情与字数,不增删段落。',
    '返回润色后的【整章正文】纯文本，不裹围栏。', '', '---当前版---', prevProse,
  ].join('\n')
}

function stripFences(s) {
  if (typeof s !== 'string') return String(s ?? '')
  let t = s.trim()
  const m = t.match(/^```[a-zA-Z]*\n([\s\S]*?)\n```$/)
  if (m) t = m[1]
  return t.trim()
}

function _trackDrift(report) {
  if (!report || !report.drift || Object.keys(report.drift).length === 0) return
  const driftedCount = Object.values(report.drift).filter(d => d && d.drifted).length
  const worstCount = Object.values(worstDrift).filter(d => d && d.drifted).length
  if (driftedCount >= worstCount) worstDrift = report.drift
}
