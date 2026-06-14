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
  let round = 0
  const violationSignaturesByRound = []  // 跨轮比对，诊断 likely_rule_or_model_issue
  while (!report.passed_hard_gate && round < 3) {
    const sigs = report.beat_violations.map(v => `${v.beat_id}:${v.kind}`).sort().join(',')
    violationSignaturesByRound.push(sigs)
    // Edit repair：RepairPrompt（结构化字段）+ PolishPrompt
    await agent(editRepairPrompt(report), { label: `Edit-repair-r${round + 1}`, phase: 'L2+Repair' })
    report = await pythonCli(`run-l2 --project ${project} --chapter ${chapter}`)
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
    if (!after.passed_hard_gate) {
      await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`)
      log('polish introduced beat violation, flagged')
    }
  }

  // 5. Persist + Telemetry
  phase('Persist+Telemetry')
  const persisted = await pythonCli(`verify-persisted --project ${project} --chapter ${chapter} ${exportPath ? '--export-path ' + exportPath : ''}`)
  if (persisted !== 'True') {
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
// pythonCli：封装 `python -m src.bedrock <cmd>`，读 stdout/传 stdin
// （运行时辅助；端到端调通留 SP5）
async function pythonCli(_cmd, _opts) { throw new Error('pythonCli runtime not wired (SP5)') }
