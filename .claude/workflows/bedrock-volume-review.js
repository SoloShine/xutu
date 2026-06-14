import { execFileSync } from 'node:child_process'

export const meta = {
  name: 'bedrock-volume-review',
  description: '磐石 V3 卷级治理：旗章 Opus 复查 + 修正闭环 + 报告',
  phases: [
    { title: 'Gather' },
    { title: 'Review' },
    { title: 'Fix' },
    { title: 'Reverify' },
    { title: 'Report' },
  ],
}

// 每章一次修正尝试（spec §六，不无限重试）
const VR_FIX_ROUNDS = 1

// args: { project, volume, chapterRange: [start, end] }
export default async function ({ project, volume, chapterRange }) {
  // 1. Gather：读旗章 + watchdog + 跨卷门禁（VolumeReview 无论 blocking 都跑，spec §六.0）
  phase('Gather')
  const watchdog = await pythonCli(`run-watchdog --project ${project} --volume ${volume}`)
  const debt = await pythonCli(`cross-volume-debt --project ${project} --volume ${volume}`)
  const flagged = []
  for (let ch = chapterRange[0]; ch <= chapterRange[1]; ch++) {
    const flag = await pythonCli(`get-review-flag --project ${project} --chapter ${ch}`)
    if (flag && flag.has_flag) flagged.push({ chapter: ch, flag })
  }
  log(`gathered ${flagged.length} flagged chapters`)

  // 2. Review（第一遍）：派 Opus 复查旗章 → findings（含 is_actionable）
  phase('Review')
  const findings = await agent(volumeReviewPrompt(flagged, watchdog, debt),
                                { label: 'VolumeReview-Opus', phase: 'Review', model: 'opus' })

  // 3. Fix：对 is_actionable findings 派 Edit(Opus)（Reviewer ≠ Fixer；VR_FIX_ROUNDS=1）
  phase('Fix')
  const edited = []
  const actionable = findings.actionable || []
  for (const f of actionable.slice(0, VR_FIX_ROUNDS ? actionable.length : 0)) {
    await agent(semanticEditPrompt(f), { label: `Edit-fix-ch${f.chapter}`, phase: 'Fix', model: 'opus' })
    edited.push(f.chapter)
  }

  // 4. Reverify：L2 重跑（不得破坏 beat）+ VolumeReview 二次复查（L2 语义盲，必须 Opus 复查）
  phase('Reverify')
  const outcomes = {}
  for (const ch of edited) {
    const after = await pythonCli(`run-l2 --project ${project} --chapter ${ch}`)
    if (!after.passed_hard_gate) {
      await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${ch}`)
      outcomes[ch] = 'escalate_human'
      continue
    }
  }
  const toRecheck = edited.filter(ch => outcomes[ch] !== 'escalate_human')
  if (toRecheck.length > 0) {
    const recheck = await agent(volumeReviewRecheckPrompt(toRecheck, project),
                                { label: 'VolumeReview-recheck', phase: 'Reverify', model: 'opus' })
    for (const ch of toRecheck) {
      const v = recheck[ch]
      outcomes[ch] = v === 'verified' ? 'verified_fixed'
                   : v === 'regressed' ? 'escalate_human'
                   : 'edited_unverified'
    }
  }

  // 5. Report：写 review_report_vol{N}.md（三状态）
  phase('Report')
  await pythonCli(`write-review-report --project ${project} --volume ${volume}`,
                  { stdin: JSON.stringify({ findings, outcomes, watchdog, debt }) })
  return { status: 'ok', reviewed: flagged.length,
           verified_fixed: Object.values(outcomes).filter(o => o === 'verified_fixed').length,
           escalated: Object.values(outcomes).filter(o => o === 'escalate_human').length }
}

function volumeReviewPrompt(flagged, watchdog, debt) {
  // 嵌 volume_review.md + JSON context
  return [`# VolumeReview 子代理（Opus，旗驱动）`,
          `flagged_chapters:`, JSON.stringify(flagged, null, 2),
          `watchdog_findings:`, JSON.stringify(watchdog, null, 2),
          `cross_volume_debt:`, JSON.stringify(debt, null, 2),
          `输出结构化 findings（每章 issue_type/detail/fix_instruction/is_actionable，可修者归 actionable[]）。`].join('\n')
}
function volumeReviewRecheckPrompt(chapters, project) {
  return [`# VolumeReview 第二遍复查`,
          `复查这些已编辑的章（读其当前 paragraphs）：${JSON.stringify(chapters)}`,
          `每章输出 verified/unverified/regressed（JSON {chapter: verdict}）。`].join('\n')
}
function semanticEditPrompt(f) {
  // 语义修复 prompt：从 f.fix_instruction 构造（非 RepairPrompt/BeatViolation）。
  return [`# Edit 子代理 — 语义修复`,
          `章 ${f.chapter} 修复指令：${f.fix_instruction}`,
          `只改相关段落，不破坏已 clean 的 beat，不压缩剧情。写回 DB。`].join('\n')
}

// pythonCli：spawn `python -m src.bedrock <cmd>`，传 stdin，返回 stdout。
// - run-watchdog / cross-volume-debt / get-review-flag：stdout JSON → 自动 JSON.parse
// - run-l2：stdout JSON → 自动 JSON.parse（复用 bedrock-chapter 约定）
// - 其他：返回 trim 后的字符串
// 注意：cmdStr.split(/\s+/) 拆命令——假设路径无空格（Task 8 e2e 路径无空格）。
async function pythonCli(cmdStr, opts = {}) {
  const [sub, ...rest] = cmdStr.split(/\s+/)
  const out = execFileSync('python', ['-m', 'src.bedrock', sub, ...rest], {
    input: opts.stdin ? opts.stdin : undefined,
    encoding: 'utf-8',
    cwd: process.cwd(),
  })
  const trimmed = out.trim()
  if (sub === 'run-watchdog' || sub === 'cross-volume-debt' || sub === 'get-review-flag' || sub === 'run-l2') {
    try { return JSON.parse(trimmed) } catch { return trimmed }
  }
  return trimmed
}
