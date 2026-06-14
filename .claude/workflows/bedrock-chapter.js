import { execFileSync } from 'node:child_process'

export const meta = {
  name: 'bedrock-chapter',
  description: '磐石 V3 单章抗博弈管线：Boot→Write→L2→Edit(3轮软门禁)→Persist→Telemetry',
  phases: [
    { title: 'Boot' },
    { title: 'Write' },
    { title: 'L2+Repair' },
    { title: 'Polish' },
    { title: 'Persist+Telemetry' },
  ],
}

// args: { project, chapter, volume, exportPath }
export default async function ({ project, chapter, volume, exportPath }) {
  // 1. Boot（Python CLI，主编排采集）
  phase('Boot')
  const ctx = await pythonCli(`boot-context --project ${project} --chapter ${chapter} --volume ${volume}`)
  log('boot context assembled')

  // 2. Write（派生 ChapterWriter）
  phase('Write')
  const writeResult = await agent(chapterWriterPrompt(ctx), { label: 'ChapterWriter', phase: 'Write' })
  // 采集 token/tool（黑墙，从 SDK usage）——见 telemetry

  // 3. L2 + Repair 循环（≤3 轮）
  phase('L2+Repair')
  let report = await pythonCli(`run-l2 --project ${project} --chapter ${chapter}`)
  _trackDrift(report)
  let round = 0
  const violationSignaturesByRound = []  // 跨轮比对，诊断 likely_rule_or_model_issue
  while (!report.passed_hard_gate && round < 3) {
    const sigs = report.beat_violations.map(v => `${v.beat_id}:${v.kind}`).sort().join(',')
    violationSignaturesByRound.push(sigs)
    // Edit repair：RepairPrompt（结构化字段）+ PolishPrompt
    await agent(editRepairPrompt(report), { label: `Edit-repair-r${round + 1}`, phase: 'L2+Repair' })
    report = await pythonCli(`run-l2 --project ${project} --chapter ${chapter}`)
    _trackDrift(report)
    round++
  }
  // 诊断：同一签名多轮不变 → likely_rule_or_model_issue
  const likelyRuleOrModel = round === 3 && new Set(violationSignaturesByRound.slice(-2)).size === 1
      && !report.passed_hard_gate
  if (!report.passed_hard_gate) {
    await pythonCli(`mark-unresolved --project ${project} --chapter ${chapter} --rule-or-model ${likelyRuleOrModel ? 1 : 0}`,
                    { stdin: JSON.stringify(report.beat_violations) })
    log(`l2 unresolved after 3 rounds, likely_rule_or_model_issue=${likelyRuleOrModel}`)
  }

  // 4. Polish（beat clean 时）
  phase('Polish')
  if (report.passed_hard_gate) {
    await agent(editPolishPrompt(ctx), { label: 'Edit-polish', phase: 'Polish' })
    const after = await pythonCli(`run-l2 --project ${project} --chapter ${chapter}`)
    _trackDrift(after)
    if (!after.passed_hard_gate) {
      await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`)
      log('polish introduced beat violation, flagged')
    }
  }

  // 章节定稿前：落最差轮 drift（watchdog 识别系统性自报造假，而非 last-round 被修好的假象）
  await _flushDrift(project, chapter)

  // 5. Persist + Telemetry
  phase('Persist+Telemetry')
  const persisted = await pythonCli(`verify-persisted --project ${project} --chapter ${chapter} ${exportPath ? '--export-path ' + exportPath : ''}`)
  if (persisted !== true) {
    await pythonCli(`mark-forced-persist-failed --project ${project} --chapter ${chapter}`)
    return { status: 'failed', reason: 'forced_persist_failed' }
  }
  // 遥测：用 SP1 record_agent_invocation / record_llm_call 落黑墙（token 从各 agent 汇报）
  await pythonCli(`collect-runtime --project ${project} --chapter ${chapter} --editing-rounds ${round}`,
                  { stdin: JSON.stringify({ invocations: [], llm_calls: [] }) })
  return { status: 'ok', chapter, rounds: round, passed: report.passed_hard_gate }
}

// prompt 构造助手（从 SP3 结构化字段，非 to_string()——I2 落地）
function chapterWriterPrompt(ctx) {
  return [
    '# ChapterWriter 子代理',
    'boot context:', JSON.stringify(ctx, null, 2),
    '按 beat_contracts 写段落，角色出场 + 悬链推进，3000-5000 字。不自报字数（系统重算）。',
  ].join('\n')
}
function editRepairPrompt(report) {
  // 从 RepairPrompt.violations（含 detail/fix_hint）构造，非纯 to_string
  const lines = ['# Edit 子代理 — 定向修复', '违规清单（beat_id / kind / detail / fix_hint）：']
  for (const v of report.beat_violations) {
    lines.push(`  - beat${v.beat_id} [${v.kind}]: ${v.detail} → ${v.fix_hint}`)
  }
  lines.push('只改违规段落，不引入新违规，不压缩剧情。')
  return lines.join('\n')
}
function editPolishPrompt(ctx) {
  // 从 PolishPrompt.beat_contracts + target_distribution 构造
  return [
    '# Edit 子代理 — 正向润色',
    '目标分布:', JSON.stringify(ctx.fingerprint || {}, null, 2),
    '本章 beat 契约:', JSON.stringify(ctx.beat_contracts, null, 2),
    '对准分布修，保持剧情，不压缩字数。',
  ].join('\n')
}
// 最差轮 drift 累积器（模块级单例，跨 run-l2 调用保留；每次 Workflow 调用独立 JS 模块加载）
// 对抗审核修正：drift 取最差轮（max over rounds by drifted 指标数），非 last-round。
// 否则 round-1 大 drift 被 round-3 修好后覆盖，watchdog 看不到系统性造假。
let worstDrift = {}
function _trackDrift(report) {
  if (!report || !report.drift || Object.keys(report.drift).length === 0) return
  const driftedCount = Object.values(report.drift).filter(d => d && d.drifted).length
  const worstCount = Object.values(worstDrift).filter(d => d && d.drifted).length
  // >= 保留更晚轮的同分情况（同样代表系统性问题未被消除）
  if (driftedCount >= worstCount) worstDrift = report.drift
}
async function _flushDrift(project, chapter) {
  if (Object.keys(worstDrift).length === 0) return Promise.resolve()
  return pythonCli(`mark-advisory-drift --project ${project} --chapter ${chapter}`,
                   { stdin: JSON.stringify(worstDrift) })
}

// pythonCli：spawn `python -m src.bedrock <cmd>`，传 stdin，返回 stdout。
// - run-l2：stdout 为 JSON → 自动 JSON.parse
// - verify-persisted：stdout 为 'True'/'False' → 返回 bool
// - 其他：返回 trim 后的字符串
// 注意：cmdStr.split(/\s+/) 拆命令——若路径含空格会出错；起步假设路径无空格
// （Task 8 e2e 路径无空格），若风险则改数组形式。
async function pythonCli(cmdStr, opts = {}) {
  const [sub, ...rest] = cmdStr.split(/\s+/)
  const out = execFileSync('python', ['-m', 'src.bedrock', sub, ...rest], {
    input: opts.stdin ? opts.stdin : undefined,
    encoding: 'utf-8',
    cwd: process.cwd(),
  })
  const trimmed = out.trim()
  if (sub === 'run-l2') {
    try { return JSON.parse(trimmed) } catch { return trimmed }
  }
  if (sub === 'verify-persisted') {
    return trimmed === 'True'
  }
  return trimmed
}
