// volume-pipeline.js — 整卷写作管线 workflow
// 用法: Workflow({ scriptPath: ".claude/workflows/volume-pipeline.js",
//          args: { project: "juedi_tiantong_v1", volume: 10, startChapter: 138, endChapter: 151, volumeName: "苏醒" } })
//
// 串行章节(3 agents/chapter) + 整卷回读校验(1 agent)
// 每章 Write→Edit→Process 严格串行，章间 verify_chapter_complete 门禁
// 支持 resumeFromRunId 中断续写

export const meta = {
  name: 'volume-writing-pipeline',
  description: '整卷写作管线: 串行章节(Write→Edit→Process) + 整卷回读校验',
  phases: [
    { title: 'Prepare', detail: '验证全部章节大纲就绪 + 图谱状态' },
    { title: 'Write', detail: 'Boot + 写初稿 + 校验' },
    { title: 'Edit', detail: '风格审查 + 修正' },
    { title: 'Process', detail: '提取 → 入图 → 遥测 → 验证' },
    { title: 'Review', detail: '整卷回读校验 + 报告' },
  ],
}

// ===== 参数 =====
const project = (args && args.project) || 'juedi_tiantong_v1'
const volume = (args && args.volume) || 10
const startChapter = (args && args.startChapter) || 138
const endChapter = (args && args.endChapter) || 151
const volumeName = (args && args.volumeName) || '苏醒'

const totalChapters = endChapter - startChapter + 1
const CLI = `cd D:/novel_test && python -m src.novel_kg.mcp_cli`

// 中文数字转换（1-99，覆盖全书17卷）
const CN = ['零','一','二','三','四','五','六','七','八','九']
function toChinese(n) {
  if (n < 10) return CN[n]
  if (n === 10) return '十'
  if (n < 20) return '十' + CN[n - 10]
  const tens = Math.floor(n / 10), ones = n % 10
  return CN[tens] + '十' + (ones ? CN[ones] : '')
}
const volumeCN = '第' + toChinese(volume) + '卷'

log(`=== ${volumeCN}「${volumeName}」 ch${startChapter}-ch${endChapter} (${totalChapters}章) ===`)

// ===== Schema 定义 =====
const RESULT_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['ok', 'partial', 'failed'] },
    chapter: { type: 'number' },
    details: { type: 'string' },
    issues: { type: 'array', items: { type: 'string' } },
  },
  required: ['status', 'chapter'],
}
const WRITE_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['ok', 'partial', 'failed'] },
    chapter: { type: 'number' },
    word_count: { type: 'number' },
    title: { type: 'string' },
    details: { type: 'string' },
    issues: { type: 'array', items: { type: 'string' } },
  },
  required: ['status', 'chapter', 'word_count', 'title'],
}
const EDIT_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['ok', 'partial', 'failed'] },
    chapter: { type: 'number' },
    corrections: { type: 'number' },
    correction_types: { type: 'string' },
    details: { type: 'string' },
    issues: { type: 'array', items: { type: 'string' } },
  },
  required: ['status', 'chapter', 'corrections'],
}
const PROCESS_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['ok', 'partial', 'failed'] },
    chapter: { type: 'number' },
    events_count: { type: 'number' },
    details: { type: 'string' },
    issues: { type: 'array', items: { type: 'string' } },
  },
  required: ['status', 'chapter', 'events_count'],
}
const REVIEW_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['ok', 'partial', 'failed'] },
    volume: { type: 'number' },
    chapters_reviewed: { type: 'number' },
    issues_found: { type: 'number' },
    issues_fixed: { type: 'number' },
    details: { type: 'string' },
    issues: { type: 'array', items: { type: 'string' } },
  },
  required: ['status', 'volume', 'chapters_reviewed'],
}

// ===== Agent Prompt 模板 =====
function writePrompt(ch, nn) {
  return `你是 WriteAgent，负责项目 ${project} 第 ${ch} 章的 Boot + 写作。

严格按以下顺序执行，不可跳过任何步骤。

## Boot（获取上下文）
1. ${CLI} get_framework --project ${project} --chapter ${ch}
   → 获取核心设定 + 当前卷大纲（按需切片）
2. ${CLI} get_boot_context --project ${project} --chapter ${ch}
   → 获取大纲 + 前章结尾 + 线索召回索引
3. 检查 recall_index 中是否有与本章 outline.purpose 或 outline.key_events 相关的休眠线索
4. 如果有，对每个相关线索运行: ${CLI} recall_thread --project ${project} --thread-id <ID>
5. 如果需要回忆更早章节的弧线细节: ${CLI} recall_arc --project ${project} --chapter <N>

## 写初稿
1. ${CLI} get_writing_prompt --project ${project} --chapter ${ch} --focused
   → 自动落盘到 prompts/ 目录
2. 根据写作 prompt 的结构化上下文写初稿

### 写作硬约束（必须全部满足）：
- **标题格式**: **${volumeCN} 第${ch}章 标题**（必须中文数字卷名如"${volumeCN}"，加粗。禁止用"第${volume}卷"数字格式。禁止在标题中包含markdown加粗标记以外的格式）
- **汉字数**: 3000-5000
- **风格**: 网文风格——短段落(2-4句)、感官描写、第三人称有限视角
- **风格**: 网文风格——短段落(2-4句)、感官描写、第三人称有限视角

### 句式硬约束（grep 自检，不通过必须改）：
| 规则 | 上限 | 改写方法 |
|------|------|---------|
| 「不是X，是Y」否定转折 | ≤5处/章 | 去否定词、改为肯定陈述、合并为一句 |
| 破折号（——） | ≤1处/千字，尽量0 | 改逗号/冒号/句号，或调整语序 |
| 句号密度 | 15-25个/千字 | 过低→拆分长句；过高→合并碎片句 |

### 句式 good/bad 示例：
❌ 那不是光，是一种从未被命名的色彩。→ ✅ 光呈现为一种从未被命名的色彩。
❌ 不是因为恐惧，是他看着的东西太大了。→ ✅ 他的手在抖——他正在看着的东西太大了。
❌ 不是语言，不是信息，不是任何...意图。→ ✅ 超越了语言、信息、任何可翻译的范畴。
❌ 三种频率——掌心、古神、T-1——同时激活。→ ✅ 掌心、古神、T-1三种频率同时激活。
❌ 沉默。沉默有重量。他感觉到了。掌心在振动。→ ✅ 沉默压下来时有重量——他感觉到了，掌心在振动。

- **禁止**: 恐怖/阴森/诡异等直接情绪形容词、突然/忽然开头描述异常、直接解释世界观、角色在叙事中引用章节数字
- **参考来源**: 章末「参考来源：」引用真实出处 + 虚构部分标注「为虚构设定」

3. 保存到 projects/${project}/output/ch${nn}_generated.txt
4. ${CLI} validate_chapter --project ${project} --chapter ${ch}
   → 如果校验失败，修改文件后重新校验，直到通过
5. ${CLI} count_chapter_words --project ${project} --chapter ${ch}
   → 如果 < 3000，扩展正文；如果 > 5000，精简

## 返回
只返回以下 JSON，不要返回正文内容：
{"status":"ok","chapter":${ch},"word_count":<汉字数>,"title":"<章节标题>","issues":[]}

如果未能完成写作：
{"status":"partial","chapter":${ch},"details":"<具体问题>","word_count":0,"title":"","issues":["<问题>"]}`
}

function editPrompt(ch, nn) {
  return `你是 EditAgent，负责项目 ${project} 第 ${ch} 章的编辑审查。

严格按以下顺序执行，不可跳过任何步骤。

## 编辑审查
1. ${CLI} verify_pipeline_step --project ${project} --chapter ${ch} --step edit
   → 如果 ready: false，停止并报告错误
2. ${CLI} get_editing_prompt --project ${project} --chapter ${ch}
   → 自动落盘到 prompts/ 目录
3. 读取 projects/${project}/output/ch${nn}_generated.txt

### 逐项检查清单（必须全部审查）：
| # | 检查项 | 标准 |
|---|--------|------|
| 1 | 否定转折句式(不是X，是Y) | ≤5处，grep验证 |
| 2 | 破折号(——) | ≤1/千字，尽量0，grep验证 |
| 3 | 句号密度 | 15-25个/千字，grep验证 |
| 4 | 视角一致性 | 严格第三人称有限视角 |
| 5 | 感官描写 | 充分(视觉/听觉/触觉/温度) |
| 6 | 信息倾倒 | 无大段世界观说明 |
| 7 | 段落长度 | 2-4句为主 |
| 8 | 对话穿插 | 动作/环境描写穿插 |
| 9 | 禁止词 | 无恐怖/阴森/诡异/突然/忽然 |
| 10 | 悬疑手法 | 用精确事实制造，不用氛围渲染 |

**编辑后硬性自检（不可跳过。任一项超标必须回正文继续改）：**
```
# 1. 不是X是Y 计数(上限5)
grep -cP '不是.{1,20}是' projects/${project}/output/ch${nn}_generated.txt
# 2. 破折号 计数(上限=汉字数/1000)
python -c "import re; t=open('projects/${project}/output/ch${nn}_generated.txt').read(); c=len(re.findall(r'[一-鿿]',t)); d=t.count('——'); print(f'chars={c} dashes={d} perK={d/c*1000:.1f}')"
# 3. 句号密度自检：汉字数/1000*25=句号上限
```
如果句号密度>25/千字，检查连续3句以上<15汉字→合并碎片句。

**参考 Step 1 中的 good/bad 示例进行改写。****关键：改句式，不是换标点。碎片句合并为流畅长句，破折号改为逗号/冒号/删除。**

4. 修改后覆盖 projects/${project}/output/ch${nn}_generated.txt
5. ${CLI} validate_chapter --project ${project} --chapter ${ch}
   → 如果失败，修改后重新校验直到通过

## 返回
只返回以下 JSON：
{"status":"ok","chapter":${ch},"corrections":<修改处数>,"correction_types":"<类型列表>","issues":[]}`
}

function processPrompt(ch, nn) {
  return `你是 ProcessAgent，负责项目 ${project} 第 ${ch} 章的后处理。

严格按以下顺序执行，不可跳过任何步骤。

## 提取 JSON
1. ${CLI} verify_pipeline_step --project ${project} --chapter ${ch} --step extract
   → 如果 ready: false，停止
2. ${CLI} get_extraction_prompt --project ${project} --chapter ${ch} --compact
   → 自动落盘到 prompts/ 目录
3. 读取 projects/${project}/output/ch${nn}_generated.txt（终稿）
4. 按提取 prompt 的格式要求提取结构化 JSON
5. 保存到 projects/${project}/extractions/extraction_ch${nn}.json

## 入图
1. ${CLI} verify_pipeline_step --project ${project} --chapter ${ch} --step graph
2. ${CLI} detect_conflicts --project ${project} --chapter ${ch}
   → 如果有冲突，修正 extraction JSON 后重新检测
3. ${CLI} write_extraction --project ${project} --chapter ${ch}
4. ${CLI} add_chapter_arc --project ${project} --chapter ${ch} --purpose "<本章叙事目的>" --scenes "<场景序列>" --ending "<结尾锚点>"
5. ${CLI} get_graph_stats --project ${project} — 确认数据已写入

## 遥测
1. ${CLI} verify_pipeline_step --project ${project} --chapter ${ch} --step telemetry
2. ${CLI} count_chapter_words --project ${project} --chapter ${ch}
3. ${CLI} inject_chapter_metrics --project ${project} --chapter ${ch} --editing-corrections <N> --editing-types "<类型>"
4. ${CLI} inject_agent_phase --project ${project} --chapter ${ch} --phase writing --duration-ms <估计毫秒>
5. ${CLI} inject_agent_phase --project ${project} --chapter ${ch} --phase extraction --duration-ms <估计毫秒>
6. ${CLI} generate_context_digest --project ${project} --chapter ${ch} --word-count <字数>

## 最终验证
1. ${CLI} verify_chapter_complete --project ${project} --chapter ${ch}
   → 如果 complete: false，检查 checks 数组中失败项，修复后重新验证
   → 必须通过才能返回 ok

## 返回
只返回以下 JSON：
{"status":"ok","chapter":${ch},"events_count":<提取事件数>,"issues":[]}

如果有未解决的问题：
{"status":"partial","chapter":${ch},"events_count":0,"details":"<问题>","issues":["<问题>"]}`
}

// ===================================================================
// Phase 1: Prepare — 验证全部章节大纲就绪
// ===================================================================

phase('Prepare')

const prepResult = await agent(
  `验证项目 ${project} 第${volume}卷「${volumeName}」全部 ${totalChapters} 章是否就绪。

执行以下检查：
1. ${CLI} get_graph_stats --project ${project}
2. 对每一章检查大纲条目是否存在:
${Array.from({ length: totalChapters }, function (_, i) { return '   - ch' + (startChapter + i) + ': ' + CLI + ' verify_pipeline_step --project ' + project + ' --chapter ' + (startChapter + i) + ' --step write' }).join('\n')}

报告：
- 图谱当前状态（节点数等）
- 哪些章节 ready，哪些 not ready（附原因）
- 前一章(ch${startChapter - 1})的 verify_chapter_complete 是否通过

返回 JSON：
{"status":"ok/partial/failed","chapter":${startChapter},"details":"<摘要>","issues":["<问题列表>"]}`,
  { label: 'vol-prepare', phase: 'Prepare', schema: RESULT_SCHEMA }
)

if (!prepResult || prepResult.status === 'failed') {
  log(`Prepare FAILED: ${prepResult?.details || 'agent returned null'}`)
  return { status: 'failed', phase: 'prepare', volume, details: prepResult?.details }
}
log(`Prepare OK — all chapters ready`)

// ===================================================================
// Phase 2-4: 章节循环（严格串行）
// ===================================================================

const results = []
let failedAt = null

for (let ch = startChapter; ch <= endChapter; ch++) {
  const nn = String(ch).padStart(2, '0')
  const idx = ch - startChapter + 1
  log(`\n━━━ [${idx}/${totalChapters}] Chapter ${ch} (ch${nn}) ━━━`)

  // --- Stage A: Write ---
  phase('Write')
  const wr = await agent(writePrompt(ch, nn), { label: `ch${nn}-write`, phase: 'Write', schema: WRITE_SCHEMA })

  if (!wr || wr.status === 'failed') {
    log(`✗ ch${nn} WRITE FAILED: ${wr?.details || 'agent returned null'}`)
    failedAt = { phase: 'write', chapter: ch, details: wr?.details }
    break
  }
  const wc = wr.word_count || 0
  log(`✓ ch${nn} written: ${wc} chars — "${wr.title || '?'}"`)
  if (wc < 3000) { log(`  ⚠ word count ${wc} < 3000`) }

  // --- Stage B: Edit ---
  phase('Edit')
  const er = await agent(editPrompt(ch, nn), { label: `ch${nn}-edit`, phase: 'Edit', schema: EDIT_SCHEMA })

  if (!er || er.status === 'failed') {
    log(`⚠ ch${nn} EDIT FAILED (draft exists, continuing): ${er?.details || 'null'}`)
  } else {
    log(`✓ ch${nn} edited: ${er.corrections || 0} corrections`)
  }

  // --- Stage C: Process ---
  phase('Process')
  const pr = await agent(processPrompt(ch, nn), { label: `ch${nn}-process`, phase: 'Process', schema: PROCESS_SCHEMA })

  if (!pr || pr.status === 'failed') {
    log(`✗ ch${nn} PROCESS FAILED: ${pr?.details || 'agent returned null'}`)
    failedAt = { phase: 'process', chapter: ch, details: pr?.details }
    break
  }
  log(`✓ ch${nn} complete: ${pr.events_count || '?'} events`)

  // 记录本章结果
  results.push({
    chapter: ch,
    title: wr.title,
    word_count: wc,
    corrections: er?.corrections || 0,
    events_count: pr.events_count,
  })
}

// 如果有章节失败，报告但继续到 Review（已完成的章节仍可回读）
if (failedAt) {
  log(`\n✗ Pipeline stopped at ch${failedAt.chapter} (${failedAt.phase}): ${failedAt.details}`)
  if (results.length === 0) {
    return { status: 'failed', volume, failedAt, completed: 0 }
  }
  log(`  ${results.length}/${totalChapters} chapters completed before failure. Proceeding to review.`)
}

// ===================================================================
// Phase 5: Volume Review — 整卷回读校验
// ===================================================================

phase('Review')
const completedChapters = results.length

if (completedChapters === 0) {
  log('No chapters completed, skipping review.')
  return { status: 'failed', volume, completed: 0 }
}

const chapterFiles = results.map(function (r) {
  return 'projects/' + project + '/output/ch' + String(r.chapter).padStart(2, '0') + '_generated.txt'
}).join('\n  ')

const reviewResult = await agent(
  `你是整卷回读校验代理。项目 ${project}，${volumeCN}「${volumeName}」，已完成 ${completedChapters} 章。

## Phase 1: 逐章通读
按顺序读取以下全部章节正文，逐章完整阅读：
  ${chapterFiles}

### 检查维度：
**一致性**: 代词错误(参照 handoff.md 代词注意事项)、设定矛盾(频率体系/疤痕机制/光流系统)、时间线、空间逻辑、称呼一致、前章衔接
**合理性**: 情节推进节奏、人物行为逻辑、信息揭示节奏、伏笔回收
**风格**: 跨章重复意象/比喻/句式、视角越界、信息倾倒
**衔接**: 上卷(ch${startChapter - 1})结尾 → 本卷开头是否自然

### 代词注意（历史教训）：
- 拾=她, 许巍=他, 陆=她, 陈默=他, 周=他(记忆碎片化), 芬=她(1.3倍深层频率), 渊=他
- 绥=人族组织调度者

## Phase 2: 问题分级（含量化阈值）

| 级别 | 定义 | 处理 |
|------|------|------|
| 严重 | 设定矛盾、代词错误、影响理解的逻辑错误、风格指标严重超标 | 必须修复 |
| 中等 | 明显但不致命的不一致、叙事跳跃、风格指标超标 | 修复 |
| 轻微 | 可忽略的重复、微小瑕疵 | 记录不修复 |

### 风格指标量化阈值（必须按此分级，不可主观判断）：
| 指标 | 轻微(记录) | 中等(必须修) | 严重(必须修) |
|------|-----------|-------------|-------------|
| 不是X是Y | 6-7处 | 8-12处 | ≥13处 |
| 破折号 | 1-2/千字 | 2-4/千字 | ≥4/千字 |
| 句号密度 | 25-30/千字 | 30-40/千字 | ≥40/千字 |
| 极短句碎片 | — | 连续≥5句<15汉字 | 连续≥8句<15汉字 |

### 风格修复 good/bad 判定：
✅ 可豁免（信息核心就是否定+重新定义）：
  "这不是一个实体，这是一个代谢系统。" ← 整章核心揭示
  "最大的孤独不是被讨厌，是不被知道存在。" ← 主题句

❌ 必须修（修辞惯性，可用其他句式）：
  "不是语言，不是信息，不是任何...意图。" ← 改写为"超越了语言、信息、任何可翻译的范畴"
  "零延迟从来不是通讯，是'在场'。" ← 改写为"零延迟的本质是'在场'"

修正策略：先区分"可豁免"和"必须修"，只修后者。修完重新grep验证。## Phase 3: 逐章修复
对严重和中等问题做最小化修改（不重写整章），记录修改前后对比。

## Phase 4: 写入报告
将完整校验报告写入 projects/${project}/review_report_vol${volume}.md，包含：
- 发现并修复的问题（文件名+行号+修改前后）
- 验证通过项
- 风格指标总览（汉字数/不是X是Y/破折号 逐章统计）
- 叙事连贯性评估（时间线+角色弧线+悬念线）
- 与前卷衔接检查
- 遗留问题（待后续卷处理）
- 总结

返回 JSON：
{"status":"ok","volume":${volume},"chapters_reviewed":${completedChapters},"issues_found":<总数>,"issues_fixed":<修复数>,"issues_deferred":<遗留数>,"details":"<摘要>"}`,
  { label: `vol${volume}-review`, phase: 'Review', schema: REVIEW_SCHEMA }
)

if (!reviewResult || reviewResult.status === 'failed') {
  log(`Review FAILED: ${reviewResult?.details || 'agent returned null'}`)
} else {
  log(`\n✓ Review OK — ${reviewResult.issues_found || '?'} issues found, ${reviewResult.issues_fixed || '?'} fixed`)
}

// ===================================================================
// 最终汇总
// ===================================================================

const totalWords = results.reduce(function (s, r) { return s + r.word_count }, 0)
const totalEvents = results.reduce(function (s, r) { return s + (r.events_count || 0) }, 0)

log(`\n${'='.repeat(50)}`)
log(`第${volume}卷「${volumeName}」完成报告`)
log(`${'='.repeat(50)}`)
results.forEach(function (r) {
  log(`  ch${String(r.chapter).padStart(2,'0')} "${r.title}" — ${r.word_count}字, ${r.events_count}事件, ${r.corrections}修正`)
})
log(`---`)
log(`章数: ${completedChapters}/${totalChapters}`)
log(`总字数: ${totalWords}`)
log(`总事件: ${totalEvents}`)
if (failedAt) { log(`失败于: ch${failedAt.chapter} (${failedAt.phase})`) }
if (reviewResult) { log(`回读校验: ${reviewResult.issues_found}问题 / ${reviewResult.issues_fixed}修复`) }
log(`${'='.repeat(50)}`)

return {
  status: failedAt ? 'partial' : 'ok',
  volume,
  volumeName,
  completed: completedChapters,
  total: totalChapters,
  totalWords,
  totalEvents,
  chapters: results,
  failedAt,
  review: reviewResult ? {
    issues_found: reviewResult.issues_found,
    issues_fixed: reviewResult.issues_fixed,
    report: 'projects/' + project + '/review_report_vol' + volume + '.md',
  } : null,
}
