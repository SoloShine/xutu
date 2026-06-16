// chapter-pipeline.js — 单章写作管线 workflow
// 用法: Workflow({ scriptPath: ".claude/workflows/chapter-pipeline.js", args: { project: "juedi_tiantong_v1", chapter: 138 } })
//
// 3-agent 串行管线: Write(含Boot) → Edit → Process(含Extract+Graph+Telemetry)
// 所有 5 个原始步骤完整覆盖，无遗漏。

export const meta = {
  name: 'chapter-pipeline',
  description: '单章写作管线: Write(Boot) → Edit → Process(Extract+Graph+Telemetry)',
  phases: [
    { title: 'Prepare', detail: '验证章节就绪状态' },
    { title: 'Write', detail: 'Boot上下文 + 写初稿 + 校验' },
    { title: 'Edit', detail: '风格审查 + 修正 + 校验' },
    { title: 'Process', detail: '提取JSON → 入图 → 遥测 → 完成验证' },
  ],
}

// ===== 参数 =====
const project = (args && args.project) || 'juedi_tiantong_v1'
const chapter = (args && args.chapter) || 138
const nn = String(chapter).padStart(2, '0')
const CLI = `cd D:/novel_test && python -m src.novel_kg.mcp_cli`
log(`Pipeline args: project=${project}, chapter=${chapter}`)

// ===== 返回值 Schema =====
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

const WRITE_RESULT_SCHEMA = {
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

const EDIT_RESULT_SCHEMA = {
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

const PROCESS_RESULT_SCHEMA = {
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

// ===================================================================
// Phase 1: Prepare — 验证章节就绪
// ===================================================================

phase('Prepare')

const prepResult = await agent(
  `验证项目 ${project} 第 ${chapter} 章是否就绪。

执行以下命令并报告结果：
1. ${CLI} verify_pipeline_step --project ${project} --chapter ${chapter} --step write
2. ${CLI} get_graph_stats --project ${project}

如果 verify 返回 ready: false，说明原因（可能缺少 outline entry 或前一章未完成）。
返回 JSON：{"status":"ok/partial/failed","chapter":${chapter},"details":"<描述>","issues":[]}`,
  { label: `ch${nn}-prepare`, phase: 'Prepare', schema: RESULT_SCHEMA }
)

if (!prepResult || prepResult.status === 'failed') {
  log(`Prepare FAILED: ${prepResult?.details || 'agent returned null'}`)
  return { status: 'failed', phase: 'prepare', chapter, details: prepResult?.details }
}
log(`Prepare OK — chapter ${chapter} ready to write`)

// ===================================================================
// Phase 2: Write — Boot + 写初稿 + validate + 字数检查
// ===================================================================

phase('Write')

const writeResult = await agent(
  `你是 WriteAgent，负责项目 ${project} 第 ${chapter} 章的 Boot + 写作。

严格按以下顺序执行，不可跳过任何步骤。

## Boot（获取上下文）
1. ${CLI} get_framework --project ${project} --chapter ${chapter}
   → 获取核心设定 + 当前卷大纲（按需切片）
2. ${CLI} get_boot_context --project ${project} --chapter ${chapter}
   → 获取大纲 + 前章结尾 + 线索召回索引
3. 检查 recall_index 中是否有与本章 outline.purpose 或 outline.key_events 相关的休眠线索
4. 如果有，对每个相关线索运行: ${CLI} recall_thread --project ${project} --thread-id <ID>
5. 如果需要回忆更早章节的弧线细节: ${CLI} recall_arc --project ${project} --chapter <N>

## 写初稿
1. ${CLI} get_writing_prompt --project ${project} --chapter ${chapter} --focused
   → 自动落盘到 prompts/ 目录
2. 根据写作 prompt 的结构化上下文写初稿

### 写作硬约束（必须全部满足）：
- **标题格式**: **第X卷 第N章 标题**（加粗，带卷标）
- **汉字数**: 3000-5000
- **风格**: 网文风格——短段落(2-4句)、感官描写、第三人称有限视角
- **否定转折**: 「不是X，是Y」句式每章不超过5处
- **破折号**: ——每千字不超过3处，尽量为0
- **句号密度**: 每千字15-25个句号
- **禁止**: 恐怖/阴森/诡异等直接情绪形容词、突然/忽然开头描述异常、直接解释世界观
- **参考来源**: 章末「参考来源：」引用真实出处 + 虚构部分标注「为虚构设定」

3. 保存到 projects/${project}/output/ch${nn}_generated.txt
4. ${CLI} validate_chapter --project ${project} --chapter ${chapter}
   → 如果校验失败，修改文件后重新校验，直到通过
5. ${CLI} count_chapter_words --project ${project} --chapter ${chapter}
   → 如果 < 3000，扩展正文；如果 > 5000，精简

## 返回
只返回以下 JSON，不要返回正文内容：
{"status":"ok","chapter":${chapter},"word_count":<汉字数>,"title":"<章节标题>","issues":[]}

如果未能完成写作：
{"status":"partial","chapter":${chapter},"details":"<具体问题>","word_count":0,"title":"","issues":["<问题>"]}`,
  { label: `ch${nn}-write`, phase: 'Write', schema: WRITE_RESULT_SCHEMA }
)

if (!writeResult || writeResult.status === 'failed') {
  log(`Write FAILED: ${writeResult?.details || 'agent returned null'}`)
  return { status: 'failed', phase: 'write', chapter, details: writeResult?.details }
}

const wordCount = writeResult.word_count || 0
log(`Write OK — ${wordCount} chars, title: "${writeResult.title || '?'}"`)

if (wordCount < 3000) {
  log(`WARNING: word count ${wordCount} < 3000 minimum. Consider expanding.`)
}

// ===================================================================
// Phase 3: Edit — 编辑审查 + 修正
// ===================================================================

phase('Edit')

const editResult = await agent(
  `你是 EditAgent，负责项目 ${project} 第 ${chapter} 章的编辑审查。

严格按以下顺序执行，不可跳过任何步骤。

## 编辑审查
1. ${CLI} verify_pipeline_step --project ${project} --chapter ${chapter} --step edit
   → 如果 ready: false，停止并报告错误
2. ${CLI} get_editing_prompt --project ${project} --chapter ${chapter}
   → 自动落盘到 prompts/ 目录
3. 读取 projects/${project}/output/ch${nn}_generated.txt

### 逐项检查清单（必须全部审查）：
| # | 检查项 | 标准 |
|---|--------|------|
| 1 | 否定转折句式(不是X，是Y) | ≤5处 |
| 2 | 破折号(——) | ≤3/千字，尽量0 |
| 3 | 句号密度 | 15-25个/千字 |
| 4 | 视角一致性 | 严格第三人称有限视角 |
| 5 | 感官描写 | 充分(视觉/听觉/触觉/温度) |
| 6 | 信息倾倒 | 无大段世界观说明 |
| 7 | 段落长度 | 2-4句为主 |
| 8 | 对话穿插 | 动作/环境描写穿插 |
| 9 | 禁止词 | 无恐怖/阴森/诡异/突然/忽然 |
| 10 | 悬疑手法 | 用精确事实制造，不用氛围渲染 |

**关键：改句式，不是换标点。碎片句合并为流畅长句，破折号改为逗号/冒号/删除。**

4. 修改后覆盖 projects/${project}/output/ch${nn}_generated.txt
5. ${CLI} validate_chapter --project ${project} --chapter ${chapter}
   → 如果失败，修改后重新校验直到通过

## 返回
只返回以下 JSON：
{"status":"ok","chapter":${chapter},"corrections":<修改处数>,"correction_types":"<类型列表>","issues":[]}`,
  { label: `ch${nn}-edit`, phase: 'Edit', schema: EDIT_RESULT_SCHEMA }
)

if (!editResult || editResult.status === 'failed') {
  log(`Edit FAILED: ${editResult?.details || 'agent returned null'}. Draft exists but unedited.`)
  // 不中断管线——初稿仍在，可以继续 Process
} else {
  log(`Edit OK — ${editResult.corrections || 0} corrections (${editResult.correction_types || 'none'})`)
}

// ===================================================================
// Phase 4: Process — Extract + Graph + Telemetry + Verify
// ===================================================================

phase('Process')

const processResult = await agent(
  `你是 ProcessAgent，负责项目 ${project} 第 ${chapter} 章的后处理。

严格按以下顺序执行，不可跳过任何步骤。

## 提取 JSON
1. ${CLI} verify_pipeline_step --project ${project} --chapter ${chapter} --step extract
   → 如果 ready: false，停止
2. ${CLI} get_extraction_prompt --project ${project} --chapter ${chapter} --compact
   → 自动落盘到 prompts/ 目录
3. 读取 projects/${project}/output/ch${nn}_generated.txt（终稿）
4. 按提取 prompt 的格式要求提取结构化 JSON
5. 保存到 projects/${project}/extractions/extraction_ch${nn}.json

## 入图
1. ${CLI} verify_pipeline_step --project ${project} --chapter ${chapter} --step graph
2. ${CLI} detect_conflicts --project ${project} --chapter ${chapter}
   → 如果有冲突，修正 extraction JSON 后重新检测
3. ${CLI} write_extraction --project ${project} --chapter ${chapter}
4. ${CLI} add_chapter_arc --project ${project} --chapter ${chapter} --purpose "<本章叙事目的>" --scenes "<场景序列>" --ending "<结尾锚点>"
5. ${CLI} get_graph_stats --project ${project} — 确认数据已写入

## 遥测
1. ${CLI} verify_pipeline_step --project ${project} --chapter ${chapter} --step telemetry
2. ${CLI} count_chapter_words --project ${project} --chapter ${chapter}
3. ${CLI} inject_chapter_metrics --project ${project} --chapter ${chapter} --editing-corrections <N> --editing-types "<类型>"
4. ${CLI} inject_agent_phase --project ${project} --chapter ${chapter} --phase writing --duration-ms <估计毫秒>
5. ${CLI} inject_agent_phase --project ${project} --chapter ${chapter} --phase extraction --duration-ms <估计毫秒>
6. ${CLI} generate_context_digest --project ${project} --chapter ${chapter} --word-count <字数>

## 最终验证
1. ${CLI} verify_chapter_complete --project ${project} --chapter ${chapter}
   → 如果 complete: false，检查 checks 数组中失败项，修复后重新验证
   → 必须通过才能返回 ok

## 返回
只返回以下 JSON：
{"status":"ok","chapter":${chapter},"events_count":<提取事件数>,"issues":[]}

如果有未解决的问题：
{"status":"partial","chapter":${chapter},"events_count":0,"details":"<问题>","issues":["<问题>"]}`,
  { label: `ch${nn}-process`, phase: 'Process', schema: PROCESS_RESULT_SCHEMA }
)

if (!processResult || processResult.status === 'failed') {
  log(`Process FAILED: ${processResult?.details || 'agent returned null'}`)
  return { status: 'failed', phase: 'process', chapter, details: processResult?.details }
}

log(`Process OK — ${processResult.events_count || '?'} events extracted, chapter complete`)

// ===================================================================
// 返回总结果
// ===================================================================

return {
  status: 'ok',
  chapter,
  project,
  write: { word_count: wordCount, title: writeResult.title },
  edit: { corrections: editResult?.corrections || 0 },
  process: { events_count: processResult.events_count },
}
