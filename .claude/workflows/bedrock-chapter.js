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
  _trackDrift({ drifted: Array.from({ length: editor.style_drift_remaining }, () => ({ hint: 'editor 自报文风漂移项(详情见 editor 运行)' })), target_source: ctx.fingerprint ? 'editor' : null })
if (!report.passed_hard_gate) {
  await pythonCli(
    `mark-unresolved --project ${project} --chapter ${chapter} --rule-or-model 0`,
    { phase: 'Revise', stdin: JSON.stringify(report.beat_violations || []) })
  log(`editor 未收敛(L2 仍不过,${editor.iterations || '?'} 轮)→ mark-unresolved`)
} else {
  log(`editor 收敛: L2-clean${editor.style_drift_remaining ? `, 文风仍 ${editor.style_drift_remaining} 项漂移(advisory)` : ''}`)
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
      // ops 破 L2 → 回退 pre-Consistency。但若 prose 快照空(readCurrentProse 刷新失败),不回退(免清空章)——保 editor 终态。
      if (preConsistencyProse) {
        await commitAndL2(project, chapter, preConsistencyProse, 'consistency-revert')
        log(`consistency ops 破坏 L2 → 回退 pre-Consistency 版(${ops.length} ops 丢弃)`)
      } else {
        log(`consistency ops 破坏 L2,但 prose 快照空(刷新失败)→ 不回退,保 editor 终态`)
      }
      await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`, { phase: 'Consistency' })
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
    `style-check --project ${project} --chapter ${chapter} --volume ${volume}`, { phase: 'Revise' }))
  try { return JSON.parse(raw) } catch { return { drifted: [], ok: true } }
}

function pct(x) { return Math.round((x || 0) * 100) + '%' }

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
// stateful 工具型 editor agent 的 prompt(替代失梦 revisePrompt)。editor 自带 Bash 直调 bedrock CLI,
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
    'commit-paragraphs/edit-paragraphs 的 stdin 用管道传入(commit-paragraphs=整章正文;edit-paragraphs=ops JSON)——先写临时文件再 cat 管道,或 printf 管道。**不要用 heredoc**(本环境易失败,deliver 空/garbage)。例:cat /tmp/prose.txt | python -m src.bedrock commit-paragraphs --project ${project} --chapter ${chapter}',
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
