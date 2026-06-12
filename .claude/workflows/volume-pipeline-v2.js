// volume-pipeline-v2.js — 悬链驱动整卷写作管线
// 用法: Workflow({ scriptPath: ".claude/workflows/volume-pipeline-v2.js",
//          args: { project: "juedi_tiantong_v1", volume: 13, startChapter: 178, endChapter: 189, volumeName: "边界" } })
//
// vs v1: 单体 ChapterAgent (Write/SelfEdit/Extract), 悬链成熟度驱动, grep触发改写, 二元阈值强CLI门禁
// 每章1 agent (非3 agent), 全部完成后再 VolumeReview v2

export const meta = {
  name: 'volume-pipeline-v2',
  description: '悬链驱动管线: 单体ChapterAgent(写+编+提取) + 卷级悬链平衡校验',
  phases: [
    { title: 'Prepare', detail: '验证大纲就绪 + 图谱悬链基线' },
    { title: 'Chapter', detail: '单体ChapterAgent: Boot/Write/SelfEdit/Extract/Graph/Telemetry' },
    { title: 'Review', detail: '整卷回读 + 悬链收支表 + 问题修复' },
  ],
}

const project = (args && args.project) || 'juedi_tiantong_v1'
const volume = (args && args.volume) || 13
const startChapter = (args && args.startChapter) || 178
const endChapter = (args && args.endChapter) || 189
const volumeName = (args && args.volumeName) || '边界'

const totalChapters = endChapter - startChapter + 1
const CLI = 'cd D:/novel_test && python -m src.novel_kg.mcp_cli'

const CN = ['零','一','二','三','四','五','六','七','八','九']
function toChinese(n) {
  if (n < 10) return CN[n]
  if (n === 10) return '十'
  if (n < 20) return '十' + CN[n - 10]
  const tens = Math.floor(n / 10), ones = n % 10
  return CN[tens] + '十' + (ones ? CN[ones] : '')
}
const volumeCN = '第' + toChinese(volume) + '卷'

log('=== ' + volumeCN + '「' + volumeName + '」 ch' + startChapter + '-ch' + endChapter + ' (' + totalChapters + '章) v2管线 ===')

const CHAPTER_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['ok', 'partial', 'failed'] },
    chapter: { type: 'number' },
    word_count: { type: 'number' },
    title: { type: 'string' },
    events_count: { type: 'number' },
    threads_consumed: { type: 'number' },
    threads_planted: { type: 'number' },
    consumption_balance: { type: 'number' },
    grep_before: {
      type: 'object',
      properties: {
        notXisY: { type: 'number' },
        dashes_per_k: { type: 'number' },
        periods_per_k: { type: 'number' },
      },
    },
    grep_after: {
      type: 'object',
      properties: {
        notXisY: { type: 'number' },
        dashes_per_k: { type: 'number' },
        periods_per_k: { type: 'number' },
      },
    },
    issues: { type: 'array', items: { type: 'string' } },
  },
  required: ['status', 'chapter', 'word_count', 'title', 'grep_before', 'grep_after'],
}

const REVIEW_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['ok', 'partial', 'failed'] },
    volume: { type: 'number' },
    chapters_reviewed: { type: 'number' },
    issues_found: { type: 'number' },
    issues_fixed: { type: 'number' },
    suspense_balance: {
      type: 'object',
      properties: {
        baseline_mature: { type: 'number' },
        end_mature: { type: 'number' },
        baseline_pruning: { type: 'number' },
        end_pruning: { type: 'number' },
        abandoned: { type: 'number' },
        resolved: { type: 'number' },
        advanced: { type: 'number' },
        planted: { type: 'number' },
        net: { type: 'number' },
      },
    },
    details: { type: 'string' },
    issues: { type: 'array', items: { type: 'string' } },
  },
  required: ['status', 'volume', 'chapters_reviewed'],
}

// ChapterAgent v2 prompt — embedded for workflow portability
function chapterAgentPrompt(ch, nn) {
  var p = []
  p.push('你是小说写作管线代理（ChapterAgent v2）。独立完成第' + ch + '章的完整管线。')
  p.push('')
  p.push('核心变更（vs v1）：单体代理、悬链成熟度驱动、grep触发改写（非禁止列表）、强CLI门禁。')
  p.push('')
  p.push('---')
  p.push('## 0. 启动')
  p.push('')
  p.push('依次执行以下命令。不要跳过，不要并行：')
  p.push('1. ' + CLI + ' verify_pipeline_step --project ' + project + ' --chapter ' + ch + ' --step write')
  p.push('   ready: false 则停止并报告')
  p.push('2. ' + CLI + ' get_framework --project ' + project + ' --chapter ' + ch)
  p.push('3. ' + CLI + ' get_boot_context --project ' + project + ' --chapter ' + ch)
  p.push('   → 获取大纲条目 + 前章结尾 + 悬链成熟度分组')
  p.push('')
  p.push('### 悬链成熟度解读')
  p.push('| 组 | 定义 | 语义 |')
  p.push('|---|------|------|')
  p.push('| mature | >=10章前种植 | 已成熟，建议在本章回收或推进 |')
  p.push('| developing | 5-9章前 | 发育中，应至少推进一级 |')
  p.push('| recent | <5章前 | 近期种植，追踪即可 |')
  p.push('| pruning_candidates | >=50章前种植且从未推进 | 故事已超越,应在提取时标记abandoned |')
  p.push('')
  p.push('卷级硬约束(VolumeReview验证,非章级强制): 每卷mature必须下降>=floor(卷章数/3), 修剪>=10条pruning_candidates, 全卷播种<=回收+推进')
  p.push('章级软指导: new_thread_quota为宽松上限, consumption_balance允许-1到+3, 不强求每章net>=0')
  p.push('')
  p.push('4. 从mature组选与本章相关线程(建议1-2条,设置章/高潮章按叙事需要调整)')
  p.push('5. 对选中线程执行: ' + CLI + ' recall_thread --project ' + project + ' --thread-id <ID>')
  p.push('6. 如需更早章节弧线: ' + CLI + ' recall_arc --project ' + project + ' --chapter <N>')
  p.push('修剪操作(提取阶段): 扫描pruning_candidates, 对故事已不需要回答的旧线运行 update_suspense_thread --status abandoned')
  p.push('')
  p.push('---')
  p.push('## 1. 写作')
  p.push('')
  p.push(CLI + ' get_writing_prompt --project ' + project + ' --chapter ' + ch + ' --focused')
  p.push('自动落盘到 projects/' + project + '/prompts/writing_ch' + nn + '.txt')
  p.push('')
  p.push('### 写作硬约束')
  p.push('| 约束 | 标准 |')
  p.push('|------|------|')
  p.push('| 标题 | **' + volumeCN + ' 第' + ch + '章 标题** |')
  p.push('| 汉字数 | 3000-5000 |')
  p.push('| 风格 | 网文: 短段落(2-4句)、感官描写、第三人称有限视角 |')
  p.push('| 章末 | 参考来源: 真实出处 + 虚构标注 |')
  p.push('')
  p.push('### 其他约束')
  p.push('- 禁止: 恐怖/阴森/诡异/突然/忽然')
  p.push('- 禁止: 角色在叙事中引用章节数字')
  p.push('- 禁止: 大段世界观说明(信息通过感知/对话/事件渗透)')
  p.push('')
  p.push('写作阶段不检查句式约束。写完进入自编辑阶段再修。')
  p.push('')
  p.push('---')
  p.push('## 2. 自编辑')
  p.push('')
  p.push('### Step 1: 跑 grep（不可跳过，粘贴原始输出）')
  p.push('')
  p.push('将终端输出原样粘贴到自检报告中（不要概括、不要重写、不要只报数字）：')
  p.push('# 命令1：否定转折密度')
  p.push("grep -cP '不是.{1,20}是' projects/" + project + '/output/ch' + nn + '_generated.txt')
  p.push('# 命令2：破折号密度')
  p.push("python -c \"import re; t=open('projects/" + project + "/output/ch" + nn + "_generated.txt').read(); c=len(re.findall(r'[一-鿿]',t)); d=t.count('——'); print(f'chars={c} dashes={d} perK={d/c*1000:.1f}')\"")
  p.push('# 命令3：句号密度')
  p.push("python -c \"import re; t=open('projects/" + project + "/output/ch" + nn + "_generated.txt').read(); c=len(re.findall(r'[一-鿿]',t)); s=t.count('。'); print(f'chars={c} periods={s} perK={s/c*1000:.1f}')\"")
  p.push('')
  p.push('粘贴格式(不可省略): [grep命令1原始输出] / [python命令2原始输出] / [python命令3原始输出]')
  p.push('')
  p.push('### Step 2: 阈值判断（二元：通过/不通过，无模糊地带）')
  p.push('')
  p.push('| 指标 | 通过(无需修) | 必须修 |')
  p.push('|------|------------|--------|')
  p.push('| 不是X是Y | <=5 | >=6 |')
  p.push('| 破折号/K | <=1/K | >=2/K |')
  p.push('| 句号/K | <=30/K | >30/K |')
  p.push('| 句号碎片 | 连续<15汉字句组数<4 | 连续<15汉字句组数>=4→合并至少一半 |')
  p.push('')
  p.push('句号>30/K硬红灯必须修。25-30/K:统计连续<15汉字句的组数,>=4组则必须合并至少一半。')
  p.push('')
  p.push('### Step 3: 超标则用替代结构改写')
  p.push('')
  p.push('不是X是Y超标(>=6)时: 必须改写至少(当前计数-5)处。每次改写使用不同替代结构:')
  p.push('A.去否定→直接肯定: 那不是光→光呈现为一种从未被命名的色彩')
  p.push('B.递进排除→超越/大于: 不是语言,不是信息→超越了语言、信息、任何可翻译的范畴')
  p.push('C.功能重述→新定义: 这不是实体→它只是一个过程。呼吸不需要被制造,只是运行')
  p.push('D.因果倒装→结果前置: 不是因为恐惧→他的手在抖——他正在看着的东西太大了')
  p.push('E.跳出二元→既非也非: 不是敌人也不是盟友→既非敌人也非盟友,不属于是/不是的范畴')
  p.push('')
  p.push('改写约束: 至少用3种不同替代结构; 禁止只改标点(不是X,是Y->不是X。是Y=无效); 核心揭示豁免每章最多1处且须标注行号和理由,其余一律改写')
  p.push('')
  p.push('### Step 4: 改写后重跑grep,硬循环门')
  p.push('')
  p.push('重复循环直到全部通过:{ 跑grep→检查4项(notX<=5,dash<=1,period<=30,碎片<4)→全部是则跳出→有任一不通过则编辑(只修超标项)→回到grep }')
  p.push('每轮只修当前仍超标的项。报告含全部轮次: 第一轮:...→... 第二轮:...→... ✅全部通过')
  p.push('')
  p.push('### Step 5: 质量自检')
  p.push('- [ ] 段落2-4句为主 / 视角第三人称有限 / 感官>=3种 / 对话有穿插')
  p.push('- [ ] 代词: 对照handoff.md(拾=她,舟=她,陆=她,T-1=无性别)')
  p.push('')
  p.push('修改后覆盖 projects/' + project + '/output/ch' + nn + '_generated.txt')
  p.push('')
  p.push('---')
  p.push('## 3. 提取JSON')
  p.push('')
  p.push(CLI + ' verify_pipeline_step --project ' + project + ' --chapter ' + ch + ' --step extract')
  p.push(CLI + ' get_extraction_prompt --project ' + project + ' --chapter ' + ch + ' --compact')
  p.push('保存到 projects/' + project + '/extractions/extraction_ch' + nn + '.json')
  p.push('')
  p.push('### 悬链消费(必须填写)')
  p.push('在提取JSON的顶层字段中增加 thread_updates, new_threads, consumption_balance。')
  p.push('')
  p.push('约束:')
  p.push('- 卷级硬: 全卷播种<=回收+推进, new_threads.length<=quota为宽松上限')
  p.push('- 章级软: consumption_balance允许-1到+3')
  p.push('- 公式(统一): consumed=(resolved*1)+(advanced+partially_resolved+abandoned)*0.5, balance=consumed-new_threads.length')
  p.push('- 修剪: 扫描pruning_candidates,对故事已不需要的旧线标记abandoned。每卷累计修剪>=10条')
  p.push('')
  p.push('提取JSON写完后必须逐条运行update_suspense_thread更新旧线状态和修剪(非可选)。')
  p.push('')
  p.push('---')
  p.push('## 4. 入图 + 遥测 + 最终验证')
  p.push('')
  p.push('依次执行:')
  p.push('1. detect_conflicts => 有冲突则修正')
  p.push('2. write_extraction => add_chapter_arc')
  p.push('3. count_chapter_words => inject_chapter_metrics => inject_agent_phase => generate_context_digest')
  p.push('4. 硬门禁: validate_chapter => verify_chapter_complete(必须全部通过)')
  p.push('')
  p.push('---')
  p.push('## 返回')
  p.push('只返回JSON:')
  p.push('{"status":"ok|partial|failed","chapter":' + ch + ',"word_count":<N>,"title":"<T>","events_count":<N>,"threads_consumed":<N>,"threads_planted":<N>,"consumption_balance":<N>,"grep_before":{"notXisY":<N>,"dashes_per_k":<N>,"periods_per_k":<N>},"grep_after":{"notXisY":<N>,"dashes_per_k":<N>,"periods_per_k":<N>},"issues":[]}')

  return p.join('\n')
}

// ===================================================================
// Phase 1: Prepare
// ===================================================================

phase('Prepare')

var prepChecks = ''
for (var i = 0; i < totalChapters; i++) {
  prepChecks += '   ch' + (startChapter + i) + ': ' + CLI + ' verify_pipeline_step --project ' + project + ' --chapter ' + (startChapter + i) + ' --step write\n'
}

const prepResult = await agent(
  '验证项目 ' + project + ' 第' + volume + '卷「' + volumeName + '」全部 ' + totalChapters + ' 章是否就绪。\n' +
  '\n依次执行:\n' +
  '1. ' + CLI + ' get_graph_stats --project ' + project + '\n' +
  '2. ' + CLI + ' get_suspense_maturity --project ' + project + ' --chapter ' + startChapter + '\n' +
  '   记录基线 mature 条数\n' +
  '3. 逐章检查大纲条目:\n' + prepChecks +
  '\n报告: 图谱状态、悬链成熟度基线、哪些章节ready/not ready。\n' +
  '\n返回JSON: {"status":"ok|partial|failed","details":"<摘要>","suspense_baseline_mature":<N>,"issues":["<issue>"]}',
  { label: 'vol-prepare', phase: 'Prepare', schema: {
    type: 'object',
    properties: {
      status: { type: 'string', enum: ['ok', 'partial', 'failed'] },
      details: { type: 'string' },
      suspense_baseline_mature: { type: 'number' },
      issues: { type: 'array', items: { type: 'string' } },
    },
    required: ['status'],
  }}
)

if (!prepResult || prepResult.status === 'failed') {
  log('Prepare FAILED: ' + (prepResult ? prepResult.details : 'agent returned null'))
  return { status: 'failed', phase: 'prepare', volume: volume, details: prepResult ? prepResult.details : 'null' }
}
var baselineMature = prepResult.suspense_baseline_mature || 0
log('Prepare OK — baseline mature threads: ' + baselineMature)

// ===================================================================
// Phase 2: 章节循环 (严格串行, 1 agent/chapter, 失败自动重试1次)
// ===================================================================

var results = []
var failedAt = null

for (var ch = startChapter; ch <= endChapter; ch++) {
  var nn = String(ch).padStart(2, '0')
  var idx = ch - startChapter + 1
  log('\n--- [' + idx + '/' + totalChapters + '] Chapter ' + ch + ' (ch' + nn + ') ---')

  phase('Chapter')

  var cr = await agent(chapterAgentPrompt(ch, nn), {
    label: 'ch' + nn,
    phase: 'Chapter',
    schema: CHAPTER_SCHEMA,
  })

  if (!cr || cr.status === 'failed') {
    log('FAILED ch' + nn + ': ' + (cr ? cr.details : 'agent returned null') + ' — retrying once...')
    var retry = await agent(chapterAgentPrompt(ch, nn), {
      label: 'ch' + nn + '-retry',
      phase: 'Chapter',
      schema: CHAPTER_SCHEMA,
    })
    if (!retry || retry.status === 'failed') {
      log('Retry also failed. Stopping pipeline.')
      failedAt = { phase: 'chapter', chapter: ch, details: retry ? retry.details : 'double failure' }
      break
    }
    cr = retry
    log('Retry OK')
  }

  var wc = cr.word_count || 0
  log('ch' + nn + ': ' + wc + ' chars — "' + (cr.title || '?') + '"')
  log('  悬链 consumed=' + (cr.threads_consumed || 0) + ' planted=' + (cr.threads_planted || 0) + ' balance=' + (cr.consumption_balance || 0))
  if (cr.grep_before && cr.grep_after) {
    log('  grep: notXisY ' + (cr.grep_before.notXisY || 0) + '→' + (cr.grep_after.notXisY || 0) + ' dash/K ' + (cr.grep_before.dashes_per_k || 0) + '→' + (cr.grep_after.dashes_per_k || 0))
  }
  if (wc < 3000) { log('  WARNING: word count ' + wc + ' < 3000') }

  results.push({
    chapter: ch,
    title: cr.title,
    word_count: wc,
    events_count: cr.events_count || 0,
    threads_consumed: cr.threads_consumed || 0,
    threads_planted: cr.threads_planted || 0,
    consumption_balance: cr.consumption_balance || 0,
    grep_before: cr.grep_before || {},
    grep_after: cr.grep_after || {},
  })

  if (cr.issues && cr.issues.length > 0) {
    log('  issues: ' + cr.issues.join('; '))
  }
}

// ===================================================================
// Phase 3: Volume Review v2
// ===================================================================

phase('Review')
var completedChapters = results.length

if (completedChapters === 0) {
  log('No chapters completed, skipping review.')
  return { status: 'failed', volume: volume, completed: 0 }
}

var chapterFiles = results.map(function (r) {
  return 'projects/' + project + '/output/ch' + String(r.chapter).padStart(2, '0') + '_generated.txt'
}).join('\n  ')

var chapterSummary = results.map(function (r) {
  return 'ch' + String(r.chapter).padStart(2, '0') + ': consumed=' + r.threads_consumed + ' planted=' + r.threads_planted + ' balance=' + r.consumption_balance
}).join('\n')

const reviewResult = await agent(
  '你是整卷回读校验代理(VolumeReviewAgent v2)。项目 ' + project + ', ' + volumeCN + '「' + volumeName + '」, 已完成 ' + completedChapters + ' 章。\n' +
  '\n## 启动\n' +
  '1. 读取 projects/' + project + '/handoff.md\n' +
  '2. 运行悬链基线: ' + CLI + ' get_suspense_maturity --project ' + project + ' --chapter ' + startChapter + '\n' +
  '   卷前基线参考: ' + baselineMature + ' 条(Prepare阶段记录)\n' +
  '3. 逐章通读全部正文:\n' +
  '  ' + chapterFiles + '\n' +
  '\n## 风格信号（逐章独立跑grep，交叉验证ChapterAgent自报数字）\n' +
  '对每章正文运行以下命令，对比ChapterAgent返回的grep_after数字是否一致:\n' +
  "grep -cP '不是.{1,20}是' projects/" + project + '/output/chXX_generated.txt\n' +
  '以及破折号密度和句号密度（python oneliner）。\n' +
  '\n' +
  '| 指标 | 通过 | 必须修 |\n' +
  '|------|------|--------|\n' +
  '| 不是X是Y | <=5 | >=6 |\n' +
  '| 破折号/K | <=1/K | >=2/K |\n' +
  '| 句号/K | 15-25/K | <15或>30/K |\n' +
  '\n' +
  '阈值二元：通过或不通过。不存在"轻微超标"。"核心揭示"豁免每章最多1处且必须在报告中逐条标注理由。\n' +
  '如果ChapterAgent自报grep_after与实际grep结果不一致，标记为严重问题并实际修复。\n' +
  '\n## 代词+设定一致性\n' +
  '对照handoff.md代词表(拾=她, 舟=她, 陆=她, T-1=无性别)。\n' +
  '\n## 悬链收支表（交叉验证）\n' +
  '各章报告汇总:\n' +
  chapterSummary + '\n' +
  '\n' +
  '卷后运行 get_suspense_maturity --chapter ' + (endChapter + 1) + '，对比卷前基线 ' + baselineMature + ':\n' +
  '- mature条数从基线→终值应下降 >= floor(' + totalChapters + '/3) = ' + Math.floor(totalChapters / 3) + '条\n' +
  '- pruning_candidates应减少 >= 10条(标记abandoned)\n' +
  '- 全卷播种 <= 全卷回收+推进\n' +
  '- 逐一检查 extraction JSON 中 thread_updates 是否确实执行了 update_suspense_thread（含修剪操作）\n' +
  '\n| 指标 | 通过标准 | 实际 | 结果 |\n' +
  '|------|---------|------|------|\n' +
  '| mature减少 | >= ' + Math.floor(totalChapters / 3) + ' | ? | |\n' +
  '| 修剪执行 | >=10 | ? | |\n' +
  '| 全卷播种 | <=回收+推进 | ? | |\n' +
  '\n## 修复+报告\n' +
  '红灯风格+设定矛盾+代词错误做最小化修改。\n' +
  '完整报告写入 projects/' + project + '/review_report_vol' + volume + '.md。\n' +
  '\n返回JSON: {"status":"ok","volume":' + volume + ',"chapters_reviewed":' + completedChapters + ',"issues_found":<N>,"issues_fixed":<N>,"suspense_balance":{"baseline_mature":<N>,"end_mature":<N>,"resolved":<N>,"advanced":<N>,"planted":<N>,"net":<N>},"details":"<summary>"}',
  { label: 'vol' + volume + '-review', phase: 'Review', schema: REVIEW_SCHEMA }
)

if (!reviewResult || reviewResult.status === 'failed') {
  log('Review FAILED: ' + (reviewResult ? reviewResult.details : 'agent returned null'))
} else {
  log('\nReview OK — ' + (reviewResult.issues_found || '?') + ' issues found, ' + (reviewResult.issues_fixed || '?') + ' fixed')
  if (reviewResult.suspense_balance) {
    var sb = reviewResult.suspense_balance
    log('  悬链 baseline=' + (sb.baseline_mature || '?') + ' end=' + (sb.end_mature || '?') + ' resolved=' + (sb.resolved || '?') + ' planted=' + (sb.planted || '?') + ' pruned=' + (sb.abandoned || '?') + ' net=' + (sb.net || '?'))
  }
}

// ===================================================================
// Final summary
// ===================================================================

var totalWords = results.reduce(function (s, r) { return s + (r.word_count || 0) }, 0)
var totalEvents = results.reduce(function (s, r) { return s + (r.events_count || 0) }, 0)
var totalConsumed = results.reduce(function (s, r) { return s + (r.threads_consumed || 0) }, 0)
var totalPlanted = results.reduce(function (s, r) { return s + (r.threads_planted || 0) }, 0)
var netBalance = results.reduce(function (s, r) { return s + (r.consumption_balance || 0) }, 0)

log('\n' + '='.repeat(50))
log(volumeCN + '「' + volumeName + '」完成报告 (v2管线)')
log('='.repeat(50))
results.forEach(function (r) {
  log('  ch' + String(r.chapter).padStart(2, '0') + ' "' + (r.title || '?') + '" — ' + (r.word_count || 0) + '字, ' + (r.events_count || 0) + '事件')
  log('    悬链:' + (r.threads_consumed || 0) + '/' + (r.threads_planted || 0))
})
log('---')
log('章数: ' + completedChapters + '/' + totalChapters)
log('总字数: ' + totalWords)
log('悬链消费: ' + totalConsumed + '条 / 播种: ' + totalPlanted + '条 / 净收支: ' + netBalance)
if (failedAt) { log('失败于: ch' + failedAt.chapter + ' (' + failedAt.phase + ')') }
if (reviewResult) { log('回读校验: ' + (reviewResult.issues_found || '?') + '问题 / ' + (reviewResult.issues_fixed || '?') + '修复') }
log('='.repeat(50))

return {
  status: failedAt ? 'partial' : 'ok',
  volume: volume,
  volumeName: volumeName,
  completed: completedChapters,
  total: totalChapters,
  totalWords: totalWords,
  totalConsumed: totalConsumed,
  totalPlanted: totalPlanted,
  netBalance: netBalance,
  chapters: results,
  failedAt: failedAt,
  review: reviewResult ? {
    issues_found: reviewResult.issues_found,
    issues_fixed: reviewResult.issues_fixed,
    suspense_balance: reviewResult.suspense_balance,
    report: 'projects/' + project + '/review_report_vol' + volume + '.md',
  } : null,
}
