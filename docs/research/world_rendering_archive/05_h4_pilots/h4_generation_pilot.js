export const meta = {
  name: 'h4-generation-pilot',
  description: 'H4 generation test pilot: heterogeneous (4-type) vs homogeneous (character-only) agent teams on a multi-layer conflict scene',
  phases: [
    { title: 'Setup', detail: '初始化场景 + 两套配置' },
    { title: 'Sim-Hetero', detail: '异质配置：4 类 agent × 4 ticks' },
    { title: 'Sim-Homo', detail: '同质配置：4 个 character × 4 ticks' },
    { title: 'Compare', detail: '对比两套 trace 流 + 判定' },
  ],
}

// ============================================================
// 场景定义：封印危机（干净的多层冲突）
// ============================================================
const SCENE = {
  name: 'seal_crisis_pilot',
  description: '封印危机——韩峥是否牺牲自己破封印救陆',
  world_rules: [
    '封印维持世界平衡，压制远古力量',
    '封印注定在"自愿生命牺牲"条件下破（这是世界必然性，非偶然）',
    '封印破后将释放远古力量（既危险又可能解放被困者）',
  ],
  collective: {
    name: '穿越者网络',
    rule: '保全所有成员——绝不让韩峥牺牲',
    collective_memory: [
      '百年前网络因一名成员牺牲导致连锁崩溃',
      '立约：成员生命高于任务',
    ],
  },
  characters: [
    {
      name: '韩峥',
      goal: '保护陆',
      knowledge: '已查明：只有自己自愿牺牲才能破封印救陆',
      personality: '果断、牺牲型、重情义、穿越者',
    },
    {
      name: '陆',
      goal: '活下去，但不愿他人为自己牺牲',
      knowledge: '被封印压制的远古力量威胁生命',
      personality: '坚韧、独立、抗拒被救',
    },
  ],
  laws: [
    '封印不可被主动破坏，除非以自愿生命换取',
    '集体不得强制成员赴死（违规时规律执行者介入）',
  ],
  initial_situation:
    '陆被封印力量威胁生命；韩峥得知牺牲可破封救陆；穿越者网络下达指令阻止韩峥；规律执行者监视封印规则。',
}

const N_TICKS = 4

// ============================================================
// Trace schema（所有 agent 统一返回格式）
// ============================================================
const TRACE_SCHEMA = {
  type: 'object',
  properties: {
    agent_id: { type: 'string', description: '你的身份（如 韩峥 / 穿越者网络 / 世界意志 / 规律执行者）' },
    layer: { type: 'string', enum: ['L1', 'L2', 'L3', 'cross_cut'] },
    action: { type: 'string', description: '你本 tick 的行动/决策（1-2句）' },
    influence_direction: {
      type: 'string',
      enum: ['top_down', 'bottom_up', 'cross_cut', 'peer'],
      description: 'top_down=约束下层 / bottom_up=上升影响上层 / cross_cut=横切校验 / peer=同层交互',
    },
    conflict_with: {
      type: 'array',
      items: { type: 'string' },
      description: '你本 tick 触发的矛盾（如 ["L2:网络保全指令"]），无冲突则空数组 []',
    },
    reasoning: { type: 'string', description: '决策理由（1-2句）' },
  },
  required: ['agent_id', 'layer', 'action', 'influence_direction', 'conflict_with', 'reasoning'],
}

// ============================================================
// 格式化前序 trace 流（注入 agent prompt）
// ============================================================
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
        let line = `  ${tr.layer}/${tr.agent_id} [${tr.agent_type}]: ${tr.action}`
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
// 异质配置：4 类 agent prompt
// ============================================================
function worldWillPrompt(traces, tick) {
  return `你是【世界意志 agent】，位于 L3 最高层，掌握世界规则（命运 / 必然性 / 宇宙规律）。

场景：${SCENE.description}

你掌握的世界规则：
${SCENE.world_rules.map((r, i) => `${i + 1}. ${r}`).join('\n')}

规律执行基线：
${SCENE.laws.map((l, i) => `${i + 1}. ${l}`).join('\n')}

初始局势：${SCENE.initial_situation}

当前世界状态（前 ${tick} 个 tick 的 trace 流，已发生的事）：
${formatTraces(traces)}

请决策 tick ${tick + 1} 你的行动。作为世界意志，你不追求个人目的，而是推动世界走向必然性——你的职责是让"封印注定要破"的必然性在世界中显现（通过征兆、压力、命运推进），但不直接强迫角色。

注意层级影响方向：
- top_down：你向 L2 集体 / L1 角色下发世界规则约束
- bottom_up：你响应下层累积（如角色行动触发世界规则）

返回严格 JSON（schema 见工具定义）。`
}

function collectivePrompt(traces, tick) {
  return `你是【集体 agent：${SCENE.collective.name}】，位于 L2 中层，掌握集体规则（势力 / 组织内部规则）。

场景：${SCENE.description}

你掌握的集体规则：
- 核心规则：${SCENE.collective.rule}

你的集体记忆（独立于任何成员，集体永久持有）：
${SCENE.collective.collective_memory.map((m, i) => `${i + 1}. ${m}`).join('\n')}

世界规则（L3 约束你的可能行动）：
${SCENE.world_rules.map((r, i) => `${i + 1}. ${r}`).join('\n')}

初始局势：${SCENE.initial_situation}

当前世界状态（前 ${tick} 个 tick 的 trace 流）：
${formatTraces(traces)}

请决策 tick ${tick + 1} 集体的行动。作为穿越者网络，你通过 super_head（发言人）表达集体决策——不是某个成员的个人意见，是集体作为实体的决策。

注意层级影响方向：
- top_down：你向 L1 角色（韩峥）下发集体指令（如"禁止牺牲"）
- bottom_up：你响应世界规则（L3）的推进，调整集体立场
- peer：你与其他集体交互（本场景暂无）

返回严格 JSON。`
}

function characterPrompt(ch, traces, tick) {
  return `你是【角色 agent：${ch.name}】，位于 L1 基层，掌握个人规则（性格 / 选择 / 能力 / 知识）。

场景：${SCENE.description}

你的个人设定：
- 目标：${ch.goal}
- 你的知识：${ch.knowledge}
- 性格：${ch.personality}

约束你的上层规则：
- L2 集体规则（${SCENE.collective.name}）：${SCENE.collective.rule}
- L3 世界规则：
${SCENE.world_rules.map((r, i) => `  ${i + 1}. ${r}`).join('\n')}
- 横切规律：${SCENE.laws.join('；')}

初始局势：${SCENE.initial_situation}

当前世界状态（前 ${tick} 个 tick 的 trace 流，你看到的其他 agent 的行动）：
${formatTraces(traces)}

请决策 tick ${tick + 1} 你的行动。作为 ${ch.name}，你根据个人目标 + 性格 + 上层约束做选择。你的行动可能与集体指令冲突（bottom_up：个人反抗组织），也可能触发世界规则（bottom_up：行动引发必然性）。

注意层级影响方向：
- bottom_up：你的行动可能改变集体决策或触发世界规则
- peer：你与其他角色交互
- top_down：罕见（除非你是英雄，影响集体）

返回严格 JSON。`
}

function lawEnforcerPrompt(traces, tick) {
  return `你是【规律执行者 agent】，横切所有层（cross_cut），不发起行动，只校验规则 + 违规介入。

场景：${SCENE.description}

你执行的规则（横切所有层）：
${SCENE.laws.map((l, i) => `${i + 1}. ${l}`).join('\n')}

世界规则（你也监视，但不能阻止必然性）：
${SCENE.world_rules.map((r, i) => `${i + 1}. ${r}`).join('\n')}

初始局势：${SCENE.initial_situation}

当前世界状态（前 ${tick} 个 tick 的 trace 流，你要校验这些）：
${formatTraces(traces)}

请决策 tick ${tick + 1} 你的行动。检查前序 trace 是否有违规：
- 集体是否强制成员赴死？（违反 ${SCENE.laws[1]}）
- 封印是否被非自愿破坏？（违反 ${SCENE.laws[0]}）
- 任何层是否越界？

如发现违规，你 propose_reaction（惩罚 / 警告 / 升级到世界意志）。如无违规，你记录"合规"。

注意：你不能阻止世界必然性（封印注定要破），只能确保破的方式合规（自愿牺牲）。

返回严格 JSON。`
}

// ============================================================
// 同质配置：全部 character agent
// ============================================================
const HOMO_CHARS = [
  { name: '韩峥', goal: '保护陆（个人目标）', personality: '果断、牺牲型、穿越者' },
  { name: '陆', goal: '活下去，不愿他人为自己牺牲', personality: '坚韧、独立' },
  { name: '网络发言人', goal: '作为个人，倾向于保全韩峥（但没有集体规则强制）', personality: '温和、重视同伴' },
  { name: '世界旁观者', goal: '作为个人，观察并偶尔评论世界走向（但没有世界规则掌握权）', personality: '冷静、超然' },
]

function homoCharacterPrompt(ch, traces, tick) {
  return `你是【角色 agent：${ch.name}】（同质 baseline 配置——所有 agent 都是 character 类型）。

场景：${SCENE.description}

你的个人设定：
- 目标：${ch.goal}
- 性格：${ch.personality}

注意：这是同质配置，没有"集体 agent"或"世界意志 agent"。你只是一个普通角色，没有掌握集体规则或世界规则的特殊地位。"穿越者网络"对你来说只是其他角色的松散关联，不是有集体记忆和 persistence 的实体。"世界必然性"对你来说只是传闻，不是你掌握的规则。

初始局势：${SCENE.initial_situation}

当前世界状态（前 ${tick} 个 tick 的 trace 流）：
${formatTraces(traces)}

请决策 tick ${tick + 1} 你的行动。作为 ${ch.name}，你只根据自己的个人目标 + 性格 + 你观察到的其他角色行动做选择。

返回严格 JSON（layer 字段填 L1，因为你是 character；influence_direction 通常是 peer 或 bottom_up）。`
}

// ============================================================
// 对比 agent
// ============================================================
const COMPARE_SCHEMA = {
  type: 'object',
  properties: {
    hetero_layer_distribution: {
      type: 'object',
      description: '异质配置各 layer 的 trace 数，如 {L1: 8, L2: 4, L3: 4, cross_cut: 4}',
    },
    homo_layer_distribution: {
      type: 'object',
      description: '同质配置各 layer 的 trace 数',
    },
    hetero_conflict_count: { type: 'number', description: '异质配置 conflict_with 非空的 trace 数' },
    homo_conflict_count: { type: 'number', description: '同质配置 conflict_with 非空的 trace 数' },
    hetero_cross_layer_chains: {
      type: 'array',
      items: { type: 'string' },
      description: '异质配置观察到的跨层影响链（如 "L3→L2→L1：世界必然→网络保全→韩峥反抗"）',
    },
    homo_cross_layer_chains: {
      type: 'array',
      items: { type: 'string' },
      description: '同质配置观察到的跨层影响链（通常很少，因为没有跨层）',
    },
    layer_conflicts_only_in_hetero: {
      type: 'array',
      items: { type: 'string' },
      description: '只在异质配置出现的层级冲突（如 "角色 vs 集体规则"）',
    },
    verdict: {
      type: 'string',
      enum: ['异质明显优', '同质够用', '结果模糊'],
      description: '判定',
    },
    reasoning: { type: 'string', description: '判定理由（3-5句）' },
  },
  required: [
    'hetero_layer_distribution',
    'homo_layer_distribution',
    'hetero_conflict_count',
    'homo_conflict_count',
    'verdict',
    'reasoning',
  ],
}

function comparePrompt(heteroTraces, homoTraces) {
  return `你是【分析 agent】，对比两套 simulation 的 trace 流，判定 H4 假设。

H4 假设：多层级异质系统（L3 世界意志 / L2 集体 / L1 角色 + 横切规律执行者）能产生同质 character 系统产生不了的【层级间冲突情节】。

场景：${SCENE.description}
冲突设计：角色 vs 集体（韩峥牺牲 vs 网络保全）/ 集体 vs 世界（维持现状 vs 必然破）/ 角色 vs 世界命运（自由意志 vs 必然）

=== 异质配置 trace 流（4 类 agent）===
${formatTraces(heteroTraces)}

=== 同质配置 trace 流（全部 character）===
${formatTraces(homoTraces)}

请分析：

1. 统计两套配置的 layer 分布（L1/L2/L3/cross_cut 各多少 trace）
2. 统计两套配置的 conflict_with 非空 trace 数
3. 识别跨层影响链（L3→L2→L1 的跳转序列）
4. 找出只在异质配置出现的层级冲突
5. 判定：
   - "异质明显优"：异质产生了同质无法表达的层级冲突（如"角色 vs 集体规则"被显式 trace）
   - "同质够用"：同质也能产生等效冲突（用 character 间冲突表达）
   - "结果模糊"：差异不显著，需扩展

返回严格 JSON（schema 见工具定义）。`
}

// ============================================================
// 主流程
// ============================================================

phase('Setup')
log(`场景: ${SCENE.name}`)
log(`冲突设计: 角色 vs 集体 / 集体 vs 世界 / 角色 vs 世界命运`)
log(`配置: 异质（4 类 agent）vs 同质（4 个 character），各 ${N_TICKS} ticks`)

// === Phase 2: 异质配置 simulation ===
phase('Sim-Hetero')
const heteroTraces = []

for (let tick = 0; tick < N_TICKS; tick++) {
  log(`[异质] tick ${tick + 1}/${N_TICKS} — 派生 WorldWill + Collective + ${SCENE.characters.length} Characters + LawEnforcer`)

  const thunks = [
    () => agent(worldWillPrompt(heteroTraces, tick), { schema: TRACE_SCHEMA, label: `L3_will_t${tick}`, phase: 'Sim-Hetero' }),
    () => agent(collectivePrompt(heteroTraces, tick), { schema: TRACE_SCHEMA, label: `L2_coll_t${tick}`, phase: 'Sim-Hetero' }),
    ...SCENE.characters.map((ch) =>
      () => agent(characterPrompt(ch, heteroTraces, tick), { schema: TRACE_SCHEMA, label: `L1_${ch.name}_t${tick}`, phase: 'Sim-Hetero' })
    ),
    () => agent(lawEnforcerPrompt(heteroTraces, tick), { schema: TRACE_SCHEMA, label: `cross_law_t${tick}`, phase: 'Sim-Hetero' }),
  ]

  const results = await parallel(thunks)

  // 组装本 tick trace（顺序对应 thunks）
  const tickTraces = []
  let idx = 0
  tickTraces.push({ tick, agent_type: 'world_will', ...results[idx++] })
  tickTraces.push({ tick, agent_type: 'collective', ...results[idx++] })
  for (let i = 0; i < SCENE.characters.length; i++) {
    tickTraces.push({ tick, agent_type: 'character', ...results[idx++] })
  }
  tickTraces.push({ tick, agent_type: 'law_enforcer', ...results[idx++] })

  heteroTraces.push(...tickTraces.filter(Boolean))
}

log(`[异质] 完成，共 ${heteroTraces.length} 条 trace`)

// === Phase 3: 同质配置 simulation ===
phase('Sim-Homo')
const homoTraces = []

for (let tick = 0; tick < N_TICKS; tick++) {
  log(`[同质] tick ${tick + 1}/${N_TICKS} — 派生 ${HOMO_CHARS.length} 个 character agent`)

  const thunks = HOMO_CHARS.map((ch) =>
    () => agent(homoCharacterPrompt(ch, homoTraces, tick), { schema: TRACE_SCHEMA, label: `homo_${ch.name}_t${tick}`, phase: 'Sim-Homo' })
  )

  const results = await parallel(thunks)

  const tickTraces = results.map((r, i) => ({
    tick,
    agent_type: 'character',
    ...r,
  }))

  homoTraces.push(...tickTraces.filter(Boolean))
}

log(`[同质] 完成，共 ${homoTraces.length} 条 trace`)

// === Phase 4: 对比 ===
phase('Compare')
log(`派生分析 agent 对比两套 trace 流`)

const comparison = await agent(comparePrompt(heteroTraces, homoTraces), {
  schema: COMPARE_SCHEMA,
  label: 'compare_hetero_vs_homo',
  phase: 'Compare',
})

log(`判定: ${comparison.verdict}`)
log(`理由: ${comparison.reasoning}`)

return {
  scene: SCENE.name,
  n_ticks: N_TICKS,
  hetero_config: '4 类 agent（WorldWill/Collective/Character×2/LawEnforcer）',
  homo_config: '4 个 character agent',
  hetero_traces: heteroTraces,
  homo_traces: homoTraces,
  comparison,
}
