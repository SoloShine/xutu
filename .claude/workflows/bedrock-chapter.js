export const meta = {
  name: 'bedrock-chapter',
  description: '磐石 V3 单章抗博弈管线（沙箱精简版）：Boot→Write→commit+L2→Repair(≤3轮)→Polish(指纹门控)→Finalize',
  phases: [
    { title: 'Boot' },
    { title: 'Write' },
    { title: 'L2+Repair' },
    { title: 'Polish' },
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

// 单 agent：verify-persisted(判决) + collect-runtime(遥测) + mark-advisory-drift(若有)。
// 回传 verify-persisted 的 True/False。
async function finalize(project, chapter, exportPath, round, drift) {
  const exportArg = exportPath ? ` --export-path ${exportPath}` : ''
  const runtimeStdin = JSON.stringify({ invocations: [], llm_calls: [] })
  const driftBlock = (drift && Object.keys(drift).length)
    ? `\ncd "${CWD}" && python -m src.bedrock mark-advisory-drift --project ${project} --chapter ${chapter} <<'__STDIN__'\n${JSON.stringify(drift)}\n__STDIN__`
    : ''
  const prompt = [
    `你在项目根目录。按顺序执行下面的命令序列，只把【第一条命令 verify-persisted 的 stdout（True 或 False）】作为最终返回值。`,
    `其余命令必须执行但输出忽略。不要解释、不要围栏。若非 0 退出返回 ERROR:<which>:<stderr 首行>。`,
    ``,
    `cd "${CWD}" && python -m src.bedrock verify-persisted --project ${project} --chapter ${chapter}${exportArg}`,
    `cd "${CWD}" && python -m src.bedrock collect-runtime --project ${project} --chapter ${chapter} --editing-rounds ${round} <<'__STDIN__'`,
    runtimeStdin,
    `__STDIN__`,
    `cd "${CWD}" && python -m src.bedrock export-chapter-json --project ${project} --chapter ${chapter} --stage draft`,
    driftBlock.trim(),
  ].join('\n')
  const raw = stripFences(await agent(prompt, { label: 'finalize', phase: 'Persist+Telemetry' }))
  if (raw.startsWith('ERROR:')) throw new Error(`finalize 失败: ${raw}`)
  return raw.trim() === 'True'
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
  const multi = (ctx.beat_contracts && ctx.beat_contracts.length > 1)
    ? [`【多 beat 章，共 ${ctx.beat_contracts.length} 个 beat】每个 beat 的内容块**前面**单独起一行写标记 @@beat:<beat_id>@@（beat_id 见各 beat 契约），按契约顺序。这样系统才能把段落正确归属到对应 beat。标记行单独成段（前后空行），不要混入正文。`,
       'beat 契约(注意每个的 beat_id)：' + JSON.stringify(ctx.beat_contracts, null, 2), '']
    : []
  return [
    '# ChapterWriter 子代理（磐石 V3）',
    'boot context:', JSON.stringify(ctx, null, 2),
    '',
    ...prev,
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
    '下面是当前正文。对准分布做文风微调，保持剧情与字数，不增删段落。',
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
