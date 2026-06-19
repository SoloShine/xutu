export const meta = {
  name: 'bedrock-volume-review',
  description: '磐石 V3 卷级治理（沙箱版）：Gather旗章+watchdog+跨卷欠债 → Opus复查 → Fix(真入库) → Reverify → Report',
  phases: [
    { title: 'Gather' },
    { title: 'Review' },
    { title: 'Fix' },
    { title: 'Reverify' },
    { title: 'Report' },
  ],
}

// ── 设计 ─────────────────────────────────────────────────
// 卷级 = 对已写完的一卷做跨章治理审判。核心抗博弈点：
//   1. Reviewer(Opus) ≠ Fixer(Opus Edit)：不同 agent 实例，防自审。
//   2. L2 语义盲 → 必须 Opus 复查 + L2 复核双层。
//   3. 每章只修 1 轮（VR_FIX_ROUNDS=1），修不了 escalate_human，不无限重试。
// 沙箱化修两处老毛病：① pythonCli 经 agent（无 execFileSync）；
//   ② Fix 的语义修复真入库（老版 Edit 产出无处落库）——用 commit-paragraphs。
//   ③ Gather/Reverify 的 CLI 批量化（一条 relay 跑多命令），省 agent。
// 信任锚：Reverify 的 run-l2 由独立 relay 跑，Fix agent 不碰 verdict。
// ─────────────────────────────────────────────────────────

const CWD = 'D:/novel_test'
const VR_FIX_ROUNDS = 1   // 每章一次修正尝试（spec §六，不无限重试）

// schemas（须在主流程引用前声明，避 const TDZ）
const FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    actionable: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          chapters: { type: 'array', items: { type: 'number' },
                      description: '该 finding 涉及的全部章号(跨章矛盾列多章;单章列一个)' },
          issue_type: { type: 'string' },
          detail: { type: 'string' },
          fix_instruction: { type: 'string' },
        },
        required: ['chapters', 'fix_instruction'],
      },
    },
    summary: { type: 'string' },
  },
  required: ['actionable'],
}
const RECHECK_SCHEMA = {
  type: 'array',
  items: {
    type: 'object',
    properties: {
      chapter: { type: 'number' },
      verdict: { type: 'string', enum: ['verified', 'regressed', 'unverified'] },
    },
    required: ['chapter', 'verdict'],
  },
}

const _args = typeof args === 'string' ? JSON.parse(args) : (args || {})
const { project, volume } = _args
const chapterRange = _args.chapterRange || []
if (!project || !volume || !Array.isArray(chapterRange) || chapterRange.length < 2) {
  throw new Error('需 args: {project, volume, chapterRange:[start,end]}')
}
const [chStart, chEnd] = chapterRange
const chapters = []
for (let ch = chStart; ch <= chEnd; ch++) chapters.push(ch)

// ===== 1. Gather：watchdog + 跨卷欠债 + 全章旗（一条 relay 批量跑） =====
phase('Gather')
const g = await gatherAll(project, volume, chapters)
const flagged = chapters.filter(ch => g.flags[ch] && g.flags[ch].has_flag)
log(`gathered: ${flagged.length}/${chapters.length} flagged, watchdog_blocking=${(g.watchdog && g.watchdog.blocking || []).length}, debt_blocking=${(g.debt && g.debt.blocking || []).length}`)

// ===== 2. Review：Opus 通读全卷（不只旗章）+ watchdog + 跨卷欠债 → findings =====
phase('Review')
const reviewRaw = stripFences(await agent(volumeReviewPrompt(project, volume, chapters, flagged, g.watchdog, g.debt),
  { label: 'VolumeReview-Opus', phase: 'Review', model: 'opus' }))
const findings = parseFindings(reviewRaw)
const actionable = (findings && findings.actionable) || []
log(`review: ${actionable.length} actionable findings (of ${chapters.length} chapters, ${flagged.length} flagged)`)

// ===== 3. Fix：逐章派独立 Edit(Opus) → 单章 ops(edit-paragraphs) =====
// 抗"消极处理"：finding.chapters 多章时，【每章一个独立 Fix agent】，单章消极/解析失败
// 不连累同 finding 的兄弟章（旧版一次调用全章，ch6 改了 ch8 被丢）。
// 守铁律8——每章仍是 ≤1 轮实质修复；这是"完成 finding 的全部目标章"，非重试。
phase('Fix')
const edited = []
const fixFailed = []
const noChange = []          // 合法空 ops（本章经判定无需改）——非 escalate，与解析失败严格区分
const chapterFindings = {}   // 章 → 当初被点名的问题上下文（供 Reverify 判据）
const fixList = VR_FIX_ROUNDS ? actionable : []
for (const f of fixList) {
  const targets = (Array.isArray(f.chapters) && f.chapters.length
    ? f.chapters : (f.chapter != null ? [f.chapter] : [])).map(Number)
  if (!targets.length) { continue }
  for (const ch of targets) {
    if (!chapterFindings[ch]) chapterFindings[ch] = []
    chapterFindings[ch].push({ issue_type: f.issue_type, detail: f.detail, fix_instruction: f.fix_instruction })
  }
  for (const ch of targets) {
    try {
      const opsRaw = stripFences(await agent(fixSinglePrompt(f, ch, project),
        { label: `Edit-fix-ch${ch}`, phase: 'Fix', model: 'opus' }))
      const ops = parseOpsList(opsRaw)
      if (ops === null) {                 // 解析失败/吐叙述 → 真 escalate，章节不动
        fixFailed.push(ch)
        log(`fix ch${ch}: 解析失败（吐叙述）→ escalate，章节不动`)
        continue
      }
      if (!ops.length) {                  // 合法空数组 = 本章经判定无需改（如跨章 finding 的上下文章）
        noChange.push(ch)
        log(`fix ch${ch}: 判定无需改动（空 ops），不 escalate`)
        continue
      }
      await applyOpsAndL2(project, ch, ops, `volfix-ch${ch}`)
      edited.push(ch)
      log(`fix ch${ch}: ${ops.length} ops applied`)
    } catch (e) {
      fixFailed.push(ch)
      log(`fix ch${ch} FAILED: ${e.message} → escalate，章节不动`)
    }
  }
  const done = targets.filter(c => edited.includes(c))
  if (done.length < targets.length)
    log(`finding ch${targets.join(',')}: 实改 ${done.length}/${targets.length}（余 escalate 或无需改）`)
}

// ===== 4. Reverify：L2 重跑（不得破坏 beat）+ Opus 二次复查 =====
phase('Reverify')
const outcomes = {}
for (const ch of fixFailed) outcomes[ch] = 'escalate_human'
for (const ch of noChange) outcomes[ch] = 'no_change_needed'

let l2results = {}
if (edited.length > 0) {
  l2results = await batchL2(project, edited)
  for (const ch of edited) {
    const rep = l2results[ch]
    if (!rep || !rep.passed_hard_gate) {
      await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${ch}`, { phase: 'Reverify' })
      outcomes[ch] = 'escalate_human'
      log(`ch${ch}: L2 broke beat after fix → escalate`)
    }
  }
}
const toRecheck = edited.filter(ch => outcomes[ch] !== 'escalate_human')
if (toRecheck.length > 0) {
  const recheckRaw = stripFences(await agent(recheckPrompt(project, toRecheck, chapterFindings),
    { label: 'VolumeReview-recheck', phase: 'Reverify', model: 'opus' }))
  const verdicts = {}
  for (const r of parseRecheck(recheckRaw)) verdicts[r.chapter] = r.verdict
  for (const ch of toRecheck) {
    const v = verdicts[ch]
    outcomes[ch] = v === 'verified' ? 'verified_fixed'
                 : v === 'regressed' ? 'escalate_human'
                 : 'edited_unverified'
  }
  log(`recheck: ${toRecheck.map(ch => `ch${ch}=${outcomes[ch]}`).join(', ')}`)
}

// ===== 5. Report：写 review_report_vol{N}.md（三状态） =====
phase('Report')
// 终稿备份：整卷各章 --stage final（卷审后终态快照，冗余备份）
await exportFinalAll(project, chapters)
await pythonCli(`write-review-report --project ${project} --volume ${volume}`,
  { phase: 'Report', stdin: JSON.stringify({ findings, outcomes, watchdog: g.watchdog, debt: g.debt }) })

const vals = Object.values(outcomes)
return {
  status: 'ok', volume,
  reviewed: flagged.length,
  fixed: edited.length,
  verified_fixed: vals.filter(o => o === 'verified_fixed').length,
  escalated: vals.filter(o => o === 'escalate_human').length,
  report: `${project}/review_report_vol${volume}.md`,
}

// ── relays ──

// 一条 relay 跑 watchdog + debt + 全章 get-review-flag，返回结构化对象。
async function gatherAll(project, volume, chapters) {
  const flagCmds = chapters.map(ch =>
    `cd "${CWD}" && python -m src.bedrock get-review-flag --project ${project} --chapter ${ch}`).join('\n')
  const prompt = [
    `你在项目根目录。按顺序执行下面全部命令，返回【一个 JSON 对象】，把每条命令的 stdout 原文作为对应键的字符串值（不要二次解析、不要概括）。`,
    `键约定："watchdog"、"debt"、"flag_<章号>"（章号见下）。若某命令非 0 退出，其值设为 "ERROR:<stderr 首行>"。`,
    `只返回该 JSON 对象，无围栏/解释。`,
    ``,
    `cd "${CWD}" && python -m src.bedrock run-watchdog --project ${project} --volume ${volume}`,
    `cd "${CWD}" && python -m src.bedrock cross-volume-debt --project ${project} --volume ${volume}`,
    flagCmds,
    `(以上 flag 命令对应键: ${chapters.map(ch => 'flag_' + ch).join(', ')})`,
  ].join('\n')
  const raw = stripFences(await agent(prompt, { label: 'gather', phase: 'Gather' }))
  if (raw.startsWith('ERROR:')) throw new Error(`gather 失败: ${raw}`)
  let obj
  try { obj = JSON.parse(raw) } catch { throw new Error(`gather 未返回合法 JSON: ${raw.slice(0, 200)}`) }
  const safe = (k) => { const v = obj[k]; if (typeof v !== 'string' || v.startsWith('ERROR:')) return null; try { return JSON.parse(v) } catch { return null } }
  const flags = {}
  for (const ch of chapters) flags[ch] = safe('flag_' + ch) || { has_flag: false }
  return { watchdog: safe('watchdog'), debt: safe('debt'), flags }
}

// 一条 relay 跑 edited 各章 run-l2，返回 {章号: L2报告}。
async function batchL2(project, edited) {
  const cmds = edited.map(ch =>
    `cd "${CWD}" && python -m src.bedrock run-l2 --project ${project} --chapter ${ch}`).join('\n')
  const prompt = [
    `你在项目根目录。按顺序执行下面全部命令，返回【一个 JSON 对象】，键为 "l2_<章号>"，值为该命令 stdout 原文（一段 JSON 字符串值，不二次解析）。`,
    `非 0 退出则值设为 "ERROR:<stderr 首行>"。只返回 JSON 对象，无围栏。`,
    ``,
    cmds,
    `(对应键: ${edited.map(ch => 'l2_' + ch).join(', ')})`,
  ].join('\n')
  const raw = stripFences(await agent(prompt, { label: 'batch-l2', phase: 'Reverify' }))
  if (raw.startsWith('ERROR:')) throw new Error(`batchL2 失败: ${raw}`)
  // relay 偶在 JSON 前加"全部 N 条命令..."之类前言;容错:从首个 { 起解析。
  const start = raw.indexOf('{')
  const jsonStr = start > 0 ? raw.slice(start) : raw
  let obj
  try { obj = JSON.parse(jsonStr) } catch { throw new Error(`batchL2 未返回合法 JSON: ${raw.slice(0, 200)}`) }
  const out = {}
  for (const ch of edited) {
    const v = obj['l2_' + ch]
    if (typeof v !== 'string' || v.startsWith('ERROR:')) { out[ch] = { passed_hard_gate: false }; continue }
    try { out[ch] = JSON.parse(v) } catch { out[ch] = { passed_hard_gate: false } }
  }
  return out
}

// 一条 relay：整卷各章 export-chapter-json --stage final（终稿快照，冗余备份）。
async function exportFinalAll(project, chapters) {
  const cmds = chapters.map(ch =>
    `cd "${CWD}" && python -m src.bedrock export-chapter-json --project ${project} --chapter ${ch} --stage final`).join('\n')
  const prompt = [
    `你在项目根目录。按顺序执行下面全部命令（每条导出一章终稿 JSON 备份）。`,
    `全部执行即可，返回单行 "done"，若有命令非 0 退出则返回 ERROR:<章号>:<stderr 首行>。`,
    ``,
    cmds,
  ].join('\n')
  const raw = stripFences(await agent(prompt, { label: 'export-final', phase: 'Report' }))
  if (raw.startsWith('ERROR:')) log(`终稿备份部分失败: ${raw}（继续）`)
  else log(`终稿备份: ${chapters.length} 章 → exports/json/*.final.json`)
}
async function applyOpsAndL2(project, chapter, ops, label) {
  const opsJson = JSON.stringify(ops)
  const prompt = [
    `你在项目根目录。按序执行两条命令，把【第二条 run-l2 的 stdout 原文】逐字返回（一段 JSON，无围栏/解释）。`,
    `若非 0 退出返回 ERROR:<which>:<stderr 首行>。`,
    ``,
    `cd "${CWD}" && python -m src.bedrock edit-paragraphs --project ${project} --chapter ${chapter} <<'__STDIN__'`,
    opsJson,
    `__STDIN__`,
    `cd "${CWD}" && python -m src.bedrock run-l2 --project ${project} --chapter ${chapter}`,
  ].join('\n')
  const raw = stripFences(await agent(prompt, { label: `editops+l2:${label}`, phase: 'Fix' }))
  if (raw.startsWith('ERROR:')) throw new Error(`applyOpsAndL2(${label}) 失败: ${raw}`)
  try { return JSON.parse(raw) } catch { return { passed_hard_gate: false } }
}
async function commitAndL2(project, chapter, prose, label) {
  const prompt = [
    `你在项目根目录。按序执行两条命令，把【第二条 run-l2 的 stdout 原文】逐字返回（一段 JSON，无围栏/解释）。`,
    `若非 0 退出返回 ERROR:<which>:<stderr 首行>。`,
    ``,
    `cd "${CWD}" && python -m src.bedrock commit-paragraphs --project ${project} --chapter ${chapter} <<'__STDIN__'`,
    prose,
    `__STDIN__`,
    `cd "${CWD}" && python -m src.bedrock run-l2 --project ${project} --chapter ${chapter}`,
  ].join('\n')
  const raw = stripFences(await agent(prompt, { label: `commit+l2:${label}`, phase: 'Fix' }))
  if (raw.startsWith('ERROR:')) throw new Error(`commitAndL2(${label}) 失败: ${raw}`)
  try { return JSON.parse(raw) } catch { return { passed_hard_gate: false } }
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
  const out = await agent(prompt, { label: `cli:${sub}`, phase: opts.phase || 'Report' })
  const s = typeof out === 'string' ? out : String(out ?? '')
  if (s.startsWith('ERROR:')) throw new Error(`pythonCli ${sub} 失败: ${s}`)
  return s
}

// ── prompts ──

function volumeReviewPrompt(project, volume, chapters, flagged, watchdog, debt) {
  const flagSet = new Set(flagged)
  const list = chapters.map(ch => flagSet.has(ch) ? `- ch${ch}（有留痕旗，重点看）` : `- ch${ch}`).join('\n')
  return [
    '# VolumeReview 子代理（Opus，整卷通读 + L2 语义盲补判）',
    `项目 ${project} 第 ${volume} 卷，全卷 ${chapters.length} 章已写完。L2 硬门禁只查 beat 结构（语义盲），`,
    `你的职责是通读【全卷】抓 L2 看不见的问题，分两类：`,
    '  · 章级语义：人物动机/设定矛盾/视角越界/信息倾倒/作者旁白泄漏/字数异常偏短',
    '  · 跨章连贯：人物语气与设定跨章是否一致、伏笔回收、节奏（信息揭示疏密）、上下章衔接',
    '',
    '## 通读全卷（只读，每章都读）',
    `对下面每一章执行：cd "${CWD}" && python -m src.bedrock show-paragraphs --project ${project} --chapter <N>，按序通读其段落。`,
    `全卷章清单：\n${list}`,
    '',
    '## 跨章证据',
    'watchdog_findings:', JSON.stringify(watchdog, null, 2),
    'cross_volume_debt:', JSON.stringify(debt, null, 2),
    '',
    '## 输出',
    '给出 actionable[]：每项含 **chapters(数组:该问题涉及的全部章号)** / issue_type / detail / fix_instruction（具体到可执行，指明每章改哪段）。',
    '**跨章问题(性别统一/人物身份/时间线正典/设定矛盾)必须把所有相关章都列进 chapters**——不要只标一个章。',
    '只把"确实该改且能改"的列入；纯风格偏好、模棱两可的不要列（每项触发 1 轮修复 + 复验）。',
    '无问题则 actionable 为空数组。注意：作者旁白泄漏类（"我将/下面…撰写"）请列出，系统有 guard 但可能漏。',
    '',
    '**最终返回值必须严格是一个 JSON 对象**（不要分析文字、不要 markdown 围栏），形如：',
    '{"actionable":[{"chapters":[5,9],"issue_type":"...","detail":"...","fix_instruction":"ch5改X/ch9改Y..."}],"summary":"整卷连贯性简评"}',
  ].join('\n')
}

function fixSinglePrompt(f, ch, project) {
  return [
    '# Edit 子代理 — 卷级语义修复（单章，Opus）',
    `目标章：ch${ch}。先读当前段落（只读，含 para_id）：`,
    `cd "${CWD}" && python -m src.bedrock show-paragraphs --project ${project} --chapter ${ch}`,
    '',
    `修复指令：${f.fix_instruction}`,
    `问题：${f.issue_type || '?'} — ${f.detail || ''}`,
    '',
    `**只针对 ch${ch} 做最小改动**（ops 尽量 ≤8；优先 update，慎用 delete）。`,
    '**硬约束（违反会被 L2 拒，整章 escalate）：**',
    '  · 不得删光某 beat 的全部段落；不得把 pov 角色名的所有出现删没（至少保留一处）。',
    '  · 改完自检：主要角色名仍在、无 beat 被掏空。',
    `  · 若该 finding 对 ch${ch} 确实无需改动（例如本章只是上下文章、或本就正确），返回 [] 并不改任何段。`,
    '',
    '**最终返回值必须严格是一个 JSON ops 数组**（不要正文/解释/思考过程/围栏）：',
    '  [{"op":"update","para_id":N,"text":"…"},{"op":"delete","para_id":N},{"op":"insert","after_seq":N,"text":"…"}]',
    'op：update(改文本) / delete(删段) / insert(after_seq 后插，0=章首)。只返回该数组本身。',
  ].join('\n')
}

function recheckPrompt(project, chapters, chapterFindings) {
  const lines = [
    '# VolumeReview 第二遍复查（Opus）',
    `复查这些已修复的章是否真的解决了【当初指出的问题】、且未引入新问题（L2 看不出语义，靠你判）。`,
    `对每章执行只读：cd "${CWD}" && python -m src.bedrock show-paragraphs --project ${project} --chapter <N>，通读。`,
    '',
    '## 每章当初被点名的问题（这就是你的判据，逐条对照）',
  ]
  for (const ch of chapters) {
    const fs = chapterFindings[ch] || []
    const desc = fs.length
      ? fs.map((f, i) => `(${i + 1})[${f.issue_type || '?'}] ${f.detail || ''} →修复指令:${f.fix_instruction || ''}`).join(' / ')
      : '（无原始 finding 记录）'
    lines.push(`- ch${ch}：${desc}`)
  }
  lines.push('',
    '逐条对照上面判据判定。每章给一个 verdict：',
    '  · verified：当初指出的问题确已解决，且无明显新问题',
    '  · regressed：未解决，或引入新问题/更糟',
    '  · unverified：信息不足（慎用，须在 reason 说明为何判不了）',
    '',
    '**最终返回值必须严格是一个 JSON 数组**（不要分析文字、不要围栏），形如：',
    '[{"chapter":N,"verdict":"verified","reason":"简述"}]')
  return lines.join('\n')
}

function stripFences(s) {
  if (typeof s !== 'string') return String(s ?? '')
  let t = s.trim()
  const m = t.match(/^```[a-zA-Z]*\n([\s\S]*?)\n```$/)
  if (m) t = m[1]
  return t.trim()
}

// 容错解析 Review/recheck 的文本 JSON（agent 可能前后带分析文字；抠出首个 {..} / [..]）。
function _extractFirstJson(s, open, close) {
  const i = s.indexOf(open)
  if (i < 0) return null
  let depth = 0, inStr = false, esc = false
  for (let j = i; j < s.length; j++) {
    const c = s[j]
    if (inStr) { if (esc) esc = false; else if (c === '\\') esc = true; else if (c === '"') inStr = false; continue }
    if (c === '"') inStr = true
    else if (c === open) depth++
    else if (c === close) { depth--; if (depth === 0) return s.slice(i, j + 1) }
  }
  return null
}
function parseFindings(raw) {
  const obj = _extractFirstJson(raw, '{', '}')
  if (!obj) return { actionable: [] }
  try { const f = JSON.parse(obj); f.actionable = Array.isArray(f.actionable) ? f.actionable : []; return f }
  catch { return { actionable: [] } }
}
function parseRecheck(raw) {
  const arr = _extractFirstJson(raw, '[', ']')
  if (!arr) return []
  try { const v = JSON.parse(arr); return Array.isArray(v) ? v : [] } catch { return [] }
}
// 解析 Fix agent 的单章 ops JSON 数组；非数组/解析失败 → null（→ escalate，章节不动）。
function parseOpsList(raw) {
  const arr = _extractFirstJson(raw, '[', ']')
  if (!arr) return null
  try {
    const v = JSON.parse(arr)
    return Array.isArray(v) ? v : null
  } catch { return null }
}

