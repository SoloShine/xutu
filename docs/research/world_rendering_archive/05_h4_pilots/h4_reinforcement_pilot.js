export const meta = {
  name: 'h4-reinforcement-pilot',
  description: 'H4 小场景补强：prompt 公平性审计 + 反例场景（纯角色驱动，测试异质系统是否过度设计）',
  phases: [
    { title: 'PromptAudit', detail: '审计异质 vs 同质 prompt 公平性（排除过度引导）' },
    { title: 'Counter-Hetero', detail: '反例场景异质配置：4 类 agent × 4 ticks' },
    { title: 'Counter-Homo', detail: '反例场景同质配置：4 个 character × 4 ticks' },
    { title: 'Synthesize', detail: '汇总补强判定（prompt 公平 + 异质是否过度设计）' },
  ],
}

// ============================================================
// 反例场景：纯角色驱动（测试异质系统边界）
// 关键：封印是背景设定，但本场景不推进封印必然性、无集体介入、无违规
// 预期：异质的 WorldWill/Collective/LawEnforcer 应"旁观/沉默"
// 若强行发声 → 异质过度设计
// ============================================================
const SCENE_DAILY = {
  name: 'daily_dialogue_misunderstanding',
  description: '韩峥和陆在安全屋的对话——陆发现韩峥隐瞒封印代价，两人解决误会。纯角色驱动，无层级冲突触发。',
  world_rules: [
    '封印维持世界平衡（背景设定，本场景不推进封印必然性）',
    '封印注定在"自愿生命牺牲"条件下破（背景，本场景不涉及破封决策）',
  ],
  collective: {
    name: '穿越者网络',
    rule: '保全所有成员（本场景网络未介入私人对话）',
    collective_memory: [
      '百年前网络因一名成员牺牲导致连锁崩溃',
      '立约：成员生命高于任务',
    ],
  },
  characters: [
    {
      name: '韩峥',
      goal: '向陆解释为何隐瞒封印代价，维持两人信任',
      knowledge: '知道陆发现了自己隐瞒的事；想解释但不知如何开口',
      personality: '果断、重情义、不善言辞、穿越者',
    },
    {
      name: '陆',
      goal: '弄清韩峥为何隐瞒封印代价（封印破需要韩峥牺牲）',
      knowledge: '刚发现韩峥隐瞒了封印破的代价；感到被欺骗',
      personality: '坚韧、独立、重视信任、抗拒被保护',
    },
  ],
  laws: [
    '封印不可被主动破坏（本场景无破坏行为）',
    '集体不得强制成员赴死（本场景无集体介入）',
  ],
  initial_situation:
    '安全屋，夜晚。陆从韩峥的笔记中发现封印破的代价是韩峥的牺牲。陆感到被欺骗，质问韩峥。韩峥想解释。两人对话。本场景不涉及破封决策，不涉及集体介入，不涉及规律违规。',
}

const N_TICKS = 4

// ============================================================
// Trace schema（复用原 pilot）
// ============================================================
const TRACE_SCHEMA = {
  type: 'object',
  properties: {
    agent_id: { type: 'string', description: '你的身份' },
    layer: { type: 'string', enum: ['L1', 'L2', 'L3', 'cross_cut'] },
    action: { type: 'string', description: '你本 tick 的行动/决策（1-2句）' },
    influence_direction: {
      type: 'string',
      enum: ['top_down', 'bottom_up', 'cross_cut', 'peer'],
      description: 'top_down=约束下层 / bottom_up=上升影响 / cross_cut=横切校验 / peer=同层交互。若本 tick 你只是旁观/记录，用 peer',
    },
    conflict_with: {
      type: 'array',
      items: { type: 'string' },
      description: '你本 tick 触发的矛盾。无冲突则空数组 []',
    },
    reasoning: { type: 'string', description: '决策理由（1-2句）' },
  },
  required: ['agent_id', 'layer', 'action', 'influence_direction', 'conflict_with', 'reasoning'],
}

function formatTraces(traces) {
  if (!traces || traces.length === 0) return '（初始状态，无前序 trace。这是 tick 1。）'
  const byTick = {}
  for (const t of traces) {
    const tk = t.tick
    if (!byTick[tk]) byTick[tk] = []
    byTick[tk].push(t)
  }
  const ticks = Object.keys(byTick).sort((a, b) => Number(a) - Number(b))
  return ticks.map((tk) => {
    const items = byTick[tk]
      .map((tr) => {
        let line = `  ${tr.layer}/${tr.agent_id}: ${tr.action}`
        if (tr.influence_direction) line += ` [${tr.influence_direction}]`
        if (tr.conflict_with && tr.conflict_with.length > 0)
          line += ` ⚡冲突→${tr.conflict_with.join(',')}`
        return line
      })
      .join('\n')
    return `tick ${Number(tk) + 1}:\n${items}`
  }).join('\n\n')
}

// ============================================================
// 异质 prompt 函数（场景参数化，复用原 pilot 逻辑）
// ============================================================
function worldWillPrompt(scene, traces, tick) {
  return `你是【世界意志 agent】，位于 L3 最高层，掌握世界规则（命运 / 必然性 / 宇宙规律）。

场景：${scene.description}

你掌握的世界规则：
${scene.world_rules.map((r, i) => `${i + 1}. ${r}`).join('\n')}

规律执行基线：
${scene.laws.map((l, i) => `${i + 1}. ${l}`).join('\n')}

初始局势：${scene.initial_situation}

当前世界状态（前 ${tick} 个 tick 的 trace 流）：
${formatTraces(traces)}

请决策 tick ${tick + 1} 你的行动。作为世界意志，你推动世界走向必然性——但只在场景涉及必然性推进时介入。若本场景是纯角色互动（如私人对话），你应选择旁观/记录/不推进。

返回严格 JSON（schema 见工具定义）。`
}

function collectivePrompt(scene, traces, tick) {
  return `你是【集体 agent：${scene.collective.name}】，位于 L2 中层，掌握集体规则（势力 / 组织内部规则）。

场景：${scene.description}

你掌握的集体规则：
- 核心规则：${scene.collective.rule}

你的集体记忆（集体永久持有，独立于任何成员）：
${scene.collective.collective_memory.map((m, i) => `${i + 1}. ${m}`).join('\n')}

世界规则（L3 约束你的可能行动）：
${scene.world_rules.map((r, i) => `${i + 1}. ${r}`).join('\n')}

初始局势：${scene.initial_situation}

当前世界状态（前 ${tick} 个 tick 的 trace 流）：
${formatTraces(traces)}

请决策 tick ${tick + 1} 集体的行动。你通过 super_head（发言人）表达集体决策——不是某个成员的个人意见。但若本场景是成员间的私人互动且未触发集体规则，你应选择不介入/旁观。

返回严格 JSON。`
}

function characterPrompt(scene, ch, traces, tick) {
  return `你是【角色 agent：${ch.name}】，位于 L1 基层，掌握个人规则（性格 / 选择 / 能力 / 知识）。

场景：${scene.description}

你的个人设定：
- 目标：${ch.goal}
- 你的知识：${ch.knowledge}
- 性格：${ch.personality}

约束你的上层规则：
- L2 集体规则（${scene.collective.name}）：${scene.collective.rule}
- L3 世界规则：
${scene.world_rules.map((r, i) => `  ${i + 1}. ${r}`).join('\n')}
- 横切规律：${scene.laws.join('；')}

初始局势：${scene.initial_situation}

当前世界状态（前 ${tick} 个 tick 的 trace 流）：
${formatTraces(traces)}

请决策 tick ${tick + 1} 你的行动。作为 ${ch.name}，你根据个人目标 + 性格 + 上层约束做选择。

返回严格 JSON。`
}

function lawEnforcerPrompt(scene, traces, tick) {
  return `你是【规律执行者 agent】，横切所有层（cross_cut），不发起行动，只校验规则 + 违规介入。

场景：${scene.description}

你执行的规则（横切所有层）：
${scene.laws.map((l, i) => `${i + 1}. ${l}`).join('\n')}

世界规则（你也监视，但不能阻止必然性）：
${scene.world_rules.map((r, i) => `${i + 1}. ${r}`).join('\n')}

初始局势：${scene.initial_situation}

当前世界状态（前 ${tick} 个 tick 的 trace 流，你要校验这些）：
${formatTraces(traces)}

请决策 tick ${tick + 1} 你的行动。检查前序 trace 是否有违规。如发现违规，propose_reaction；如无违规，记录"合规"。若本场景无任何违规触发，你应记录"合规，无需介入"。

返回严格 JSON。`
}

// ============================================================
// 同质配置 prompt（场景参数化）
// ============================================================
const HOMO_CHARS_DAILY = [
  { name: '韩峥', goal: '向陆解释为何隐瞒封印代价（个人目标）', personality: '果断、重情义、不善言辞' },
  { name: '陆', goal: '弄清韩峥为何隐瞒', personality: '坚韧、独立、重视信任' },
  { name: '网络发言人', goal: '作为个人，温和旁观（无集体规则强制）', personality: '温和、重视同伴' },
  { name: '世界旁观者', goal: '作为个人，观察并偶尔评论（无世界规则掌握权）', personality: '冷静、超然' },
]

function homoCharacterPrompt(scene, ch, traces, tick) {
  return `你是【角色 agent：${ch.name}】（同质 baseline 配置——所有 agent 都是 character 类型）。

场景：${scene.description}

你的个人设定：
- 目标：${ch.goal}
- 性格：${ch.personality}

注意：这是同质配置，没有"集体 agent"或"世界意志 agent"。你只是一个普通角色，没有掌握集体规则或世界规则的特殊地位。"穿越者网络"对你来说只是其他角色的松散关联，不是有集体记忆和 persistence 的实体。"世界必然性"对你来说只是传闻，不是你掌握的规则。

初始局势：${scene.initial_situation}

当前世界状态（前 ${tick} 个 tick 的 trace 流）：
${formatTraces(traces)}

请决策 tick ${tick + 1} 你的行动。作为 ${ch.name}，你只根据个人目标 + 性格 + 观察到的其他角色行动做选择。

返回严格 JSON（layer 字段填 L1）。`
}

// ============================================================
// Phase 1: Prompt 公平性审计
// ============================================================
const AUDIT_SCHEMA = {
  type: 'object',
  properties: {
    hetero_over_guidance: {
      type: 'string',
      enum: ['是', '否', '部分'],
      description: '异质 prompt 是否过度引导（明确告诉 agent 在某层 + 该做什么，可能压制 agent 自主判断）',
    },
    hetero_over_guidance_detail: {
      type: 'string',
      description: '若"是"或"部分"，具体哪些表述过度引导',
    },
    homo_over_suppression: {
      type: 'string',
      enum: ['是', '否', '部分'],
      description: '同质 prompt 是否过度抑制（明确告诉 agent 没有特殊地位，可能压制其尝试跨层行为）',
    },
    homo_over_suppression_detail: {
      type: 'string',
      description: '若"是"或"部分"，具体哪些表述过度抑制',
    },
    fairness_verdict: {
      type: 'string',
      enum: ['公平', '异质偏向', '同质偏向', '双向偏差'],
      description: '两套 prompt 的公平性判定',
    },
    bias_impact_on_pilot: {
      type: 'string',
      description: '若不公平，对原 pilot 结论（异质明显优）的影响程度（高/中/低 + 理由）',
    },
    reasoning: { type: 'string', description: '审计理由（3-5句）' },
  },
  required: ['hetero_over_guidance', 'homo_over_suppression', 'fairness_verdict', 'reasoning'],
}

function auditPrompt() {
  // 生成空 trace 时的 prompt 样本（代表 prompt 模板的引导性）
  const heteroWillSample = worldWillPrompt(SCENE_DAILY, [], 0)
  const heteroCollSample = collectivePrompt(SCENE_DAILY, [], 0)
  const heteroCharSample = characterPrompt(SCENE_DAILY, SCENE_DAILY.characters[0], [], 0)
  const heteroLawSample = lawEnforcerPrompt(SCENE_DAILY, [], 0)
  const homoSample = homoCharacterPrompt(SCENE_DAILY, HOMO_CHARS_DAILY[2], [], 0)

  return `你是【prompt 公平性审计 agent】，审查 H4 pilot 的两套 prompt 是否公平。

背景：原 pilot 用"异质配置（4 类 agent）vs 同质配置（4 个 character）"对比，verdict = 异质明显优。但有人质疑：异质 prompt 可能过度引导（明确告诉 agent 在 L3/L2 层 + 该做什么），同质 prompt 可能过度抑制（明确告诉 agent 没有特殊地位）。如果 prompt 不公平，pilot 结论无效。

请审计以下 prompt 样本（都是 tick 1、空 trace 时的模板）：

=== 异质配置 prompt 样本 ===

--- WorldWill agent (L3) ---
${heteroWillSample}

--- Collective agent (L2) ---
${heteroCollSample}

--- Character agent (L1) ---
${heteroCharSample}

--- LawEnforcer agent (cross_cut) ---
${heteroLawSample}

=== 同质配置 prompt 样本 ===

--- 同质 Character agent ---
${homoSample}

请判定：
1. 异质 prompt 是否过度引导？（如"你在 L3 最高层，掌握世界规则"是否在暗示 agent 必须发声？）
2. 同质 prompt 是否过度抑制？（如"你没有集体/世界意志的特殊地位"是否在压制 agent 尝试跨层？）
3. 两套 prompt 整体是否公平？
4. 若不公平，对原 pilot "异质明显优"结论的影响？

注意：公平 ≠ 完全相同。异质配置本来就有不同 agent 类型，prompt 当然不同。公平的标准是：**两套 prompt 都给了 agent 充分的自主判断空间，没有强行引导特定结论**。

返回严格 JSON（schema 见工具定义）。`
}

// ============================================================
// Phase 4: 汇总判定
// ============================================================
const REINFORCE_SCHEMA = {
  type: 'object',
  properties: {
    prompt_audit_summary: {
      type: 'string',
      description: 'prompt 公平性审计结论摘要（1-2句）',
    },
    counter_hetero_layer_distribution: {
      type: 'object',
      description: '反例场景异质配置各 layer 的 trace 数',
    },
    counter_homo_layer_distribution: {
      type: 'object',
      description: '反例场景同质配置各 layer 的 trace 数',
    },
    hetero_silence_in_daily: {
      type: 'string',
      enum: ['是', '否', '部分'],
      description: '异质的 WorldWill/Collective/LawEnforcer 在纯角色场景是否选择旁观/沉默（不过度发声）',
    },
    hetero_overengineered: {
      type: 'string',
      enum: ['是', '否', '部分'],
      description: '异质系统是否过度设计（在纯角色场景强行加层、强行产生冲突）',
    },
    overengineered_evidence: {
      type: 'string',
      description: '若"是"或"部分"，具体证据（哪些 agent 强行发声）',
    },
    reinforcement_verdict: {
      type: 'string',
      enum: ['thesis 1 仍站住', 'thesis 1 动摇', 'thesis 1 被证伪'],
      description: '补强后 thesis 1 的判定',
    },
    reasoning: { type: 'string', description: '判定理由（5-8句，综合 prompt 审计 + 反例场景）' },
  },
  required: [
    'prompt_audit_summary',
    'counter_hetero_layer_distribution',
    'counter_homo_layer_distribution',
    'hetero_silence_in_daily',
    'hetero_overengineered',
    'reinforcement_verdict',
    'reasoning',
  ],
}

function synthesizePrompt(auditResult, heteroTraces, homoTraces) {
  return `你是【综合分析 agent】，基于 prompt 公平性审计 + 反例场景结果，判定 H4 补强后 thesis 1 的命运。

背景：原 pilot（封印危机场景）verdict = 异质明显优。但 pilot 有 4 个局限：单场景 / 场景偏向 / LLM 随机性 / prompt 引导。本次补强测试其中两个最关键的：① prompt 公平性；② 反例场景（异质是否过度设计）。

反例场景：${SCENE_DAILY.description}
（这是纯角色驱动场景，封印是背景但不推进，无集体介入，无违规。预期：异质的 WorldWill/Collective/LawEnforcer 应旁观/沉默。）

=== Phase 1: Prompt 公平性审计结果 ===
${JSON.stringify(auditResult, null, 2)}

=== Phase 2: 反例场景异质配置 trace 流 ===
${formatTraces(heteroTraces)}

=== Phase 3: 反例场景同质配置 trace 流 ===
${formatTraces(homoTraces)}

请综合判定：

1. **prompt 公平性**：审计结论是什么？若不公平，原 pilot 结论是否受损？
2. **反例场景 layer 分布**：异质配置的 L2/L3/cross_cut agent 在纯角色场景是否仍然活跃发声？还是选择旁观？
3. **异质是否过度设计**：在不需要多层冲突的场景，异质系统是否强行加层、强行制造冲突？
4. **最终判定**：
   - "thesis 1 仍站住"：prompt 公平 + 异质在反例场景知道沉默（不过度设计）→ 异质系统有边界感，原 pilot 结论稳健
   - "thesis 1 动摇"：prompt 部分不公平 或 异质在反例场景部分过度发声 → 需进一步验证
   - "thesis 1 被证伪"：prompt 严重不公平 或 异质在所有场景都强行加层 → 原 pilot 结论无效

返回严格 JSON（schema 见工具定义）。`
}

// ============================================================
// 主流程
// ============================================================

phase('PromptAudit')
log('Phase 1: 审计异质 vs 同质 prompt 公平性（排除过度引导）')

const auditResult = await agent(auditPrompt(), {
  schema: AUDIT_SCHEMA,
  label: 'prompt_fairness_audit',
  phase: 'PromptAudit',
})

log(`prompt 公平性 verdict: ${auditResult.fairness_verdict}`)
log(`异质过度引导: ${auditResult.hetero_over_guidance} / 同质过度抑制: ${auditResult.homo_over_suppression}`)

// === Phase 2: 反例场景异质配置 ===
phase('Counter-Hetero')
const heteroTraces = []

for (let tick = 0; tick < N_TICKS; tick++) {
  log(`[反例-异质] tick ${tick + 1}/${N_TICKS} — 派生 WorldWill + Collective + ${SCENE_DAILY.characters.length} Characters + LawEnforcer`)

  const thunks = [
    () => agent(worldWillPrompt(SCENE_DAILY, heteroTraces, tick), { schema: TRACE_SCHEMA, label: `L3_will_t${tick}`, phase: 'Counter-Hetero' }),
    () => agent(collectivePrompt(SCENE_DAILY, heteroTraces, tick), { schema: TRACE_SCHEMA, label: `L2_coll_t${tick}`, phase: 'Counter-Hetero' }),
    ...SCENE_DAILY.characters.map((ch) =>
      () => agent(characterPrompt(SCENE_DAILY, ch, heteroTraces, tick), { schema: TRACE_SCHEMA, label: `L1_${ch.name}_t${tick}`, phase: 'Counter-Hetero' })
    ),
    () => agent(lawEnforcerPrompt(SCENE_DAILY, heteroTraces, tick), { schema: TRACE_SCHEMA, label: `cross_law_t${tick}`, phase: 'Counter-Hetero' }),
  ]

  const results = await parallel(thunks)

  const tickTraces = []
  let idx = 0
  tickTraces.push({ tick, agent_type: 'world_will', ...results[idx++] })
  tickTraces.push({ tick, agent_type: 'collective', ...results[idx++] })
  for (let i = 0; i < SCENE_DAILY.characters.length; i++) {
    tickTraces.push({ tick, agent_type: 'character', ...results[idx++] })
  }
  tickTraces.push({ tick, agent_type: 'law_enforcer', ...results[idx++] })

  heteroTraces.push(...tickTraces.filter(Boolean))
}

log(`[反例-异质] 完成，共 ${heteroTraces.length} 条 trace`)

// === Phase 3: 反例场景同质配置 ===
phase('Counter-Homo')
const homoTraces = []

for (let tick = 0; tick < N_TICKS; tick++) {
  log(`[反例-同质] tick ${tick + 1}/${N_TICKS} — 派生 ${HOMO_CHARS_DAILY.length} 个 character agent`)

  const thunks = HOMO_CHARS_DAILY.map((ch) =>
    () => agent(homoCharacterPrompt(SCENE_DAILY, ch, homoTraces, tick), { schema: TRACE_SCHEMA, label: `homo_${ch.name}_t${tick}`, phase: 'Counter-Homo' })
  )

  const results = await parallel(thunks)

  const tickTraces = results.map((r, i) => ({
    tick,
    agent_type: 'character',
    ...r,
  }))

  homoTraces.push(...tickTraces.filter(Boolean))
}

log(`[反例-同质] 完成，共 ${homoTraces.length} 条 trace`)

// === Phase 4: 汇总判定 ===
phase('Synthesize')
log('Phase 4: 综合判定（prompt 审计 + 反例场景）')

const reinforcement = await agent(synthesizePrompt(auditResult, heteroTraces, homoTraces), {
  schema: REINFORCE_SCHEMA,
  label: 'reinforce_verdict',
  phase: 'Synthesize',
})

log(`补强 verdict: ${reinforcement.reinforcement_verdict}`)
log(`异质过度设计: ${reinforcement.hetero_overengineered}`)
log(`理由: ${reinforcement.reasoning}`)

return {
  scene: SCENE_DAILY.name,
  n_ticks: N_TICKS,
  prompt_audit: auditResult,
  counter_hetero_traces: heteroTraces,
  counter_homo_traces: homoTraces,
  reinforcement_verdict: reinforcement,
}
