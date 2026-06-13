export const meta = {
  name: 'h4-medium-scene-pilot',
  description: 'H4 中场景验证：3 层集体嵌套 + 8 角色 + 10 ticks + 赋能式同质 prompt 修正。测试规模放大异质优势还是崩溃/追上',
  phases: [
    { title: 'Setup', detail: '初始化中场景 + 两套配置（赋能式同质修正）' },
    { title: 'Sim-Hetero', detail: '异质配置：1 WorldWill + 3 Collective(嵌套) + 8 Character + 1 LawEnforcer × 10 ticks' },
    { title: 'Sim-Homo', detail: '同质配置(赋能式)：13 个 character × 10 ticks' },
    { title: 'Compare', detail: '对比 + 规模信号判定（放大/崩溃/追上）' },
  ],
}

// ============================================================
// 中场景：封印危机扩展——3 层集体嵌套 + 文明选择 + 跨势力
// 复杂度：13 agent × 10 ticks（vs 小场景 5 agent × 4 ticks）
// ============================================================
const SCENE = {
  name: 'seal_crisis_multi_collective',
  description: '封印危机扩展——多层集体嵌套（小队→网络→联盟）+ 文明选择 + 跨势力博弈。韩峥牺牲破封救陆，牵动 3 层集体 + 异族。',
  world_rules: [
    '封印注定在"自愿生命牺牲"条件下破（必然性 1）',
    '封印破后释放远古力量，触发文明选择——人族必须自身决定接纳还是消灭（必然性 2）',
    '文明选择不可被代理——任何代理决定无效（必然性 3）',
  ],
  collectives: [
    {
      name: '穿越者小队',
      depth: 'L2_base',
      parent: '穿越者网络',
      rule: '保护队员——韩峥是小队核心，绝不能死',
      collective_memory: ['小队 5 人共同经历过 3 次生死', '韩峥曾救过每个队员'],
      members: ['韩峥', '小队成员A', '小队成员B'],
    },
    {
      name: '穿越者网络',
      depth: 'L2_mid',
      parent: '人族联盟',
      rule: '保全所有成员——绝不让任何成员牺牲（立约级）',
      collective_memory: ['百年前因一名成员牺牲导致连锁崩溃', '立约：成员生命高于任务'],
      members: ['网络议长'],
    },
    {
      name: '人族联盟',
      depth: 'L2_top',
      parent: null,
      rule: '维持文明存续——封印破后的远古力量必须被控制，不能被消灭也不能被放任',
      collective_memory: ['人族曾因力量失控几乎灭绝', '联盟成立是为应对远古力量'],
      members: ['联盟代表'],
    },
  ],
  characters: [
    {
      name: '韩峥',
      belongs_to: '穿越者小队',
      goal: '保护陆',
      knowledge: '已查明：只有自己自愿牺牲才能破封印救陆',
      personality: '果断、牺牲型、重情义、穿越者',
    },
    {
      name: '陆',
      belongs_to: null,
      goal: '活下去，但不愿他人为自己牺牲',
      knowledge: '被封印压制的远古力量威胁生命',
      personality: '坚韧、独立、抗拒被救',
    },
    {
      name: '小队成员A',
      belongs_to: '穿越者小队',
      goal: '执行小队规则——保护韩峥',
      knowledge: '韩峥是小队的核心，小队有掩护预案',
      personality: '忠诚、行动派',
    },
    {
      name: '小队成员B',
      belongs_to: '穿越者小队',
      goal: '执行小队任务，提供技术方案',
      knowledge: '小队有 3 套掩护韩峥的预案',
      personality: '冷静、技术型',
    },
    {
      name: '网络议长',
      belongs_to: '穿越者网络',
      goal: '执行网络立约——保全所有成员',
      knowledge: '网络的百年记忆，知道连锁崩溃的教训',
      personality: '稳重、组织型、重立约',
    },
    {
      name: '联盟代表',
      belongs_to: '人族联盟',
      goal: '维持文明存续——控制远古力量',
      knowledge: '联盟对远古力量的恐惧，知道文明选择不可代理',
      personality: '谨慎、大局观、重存续',
    },
    {
      name: '异族使者',
      belongs_to: null,
      goal: '为本族争取封印破后的利益（异族对远古力量有自己的立场）',
      knowledge: '异族与远古力量有历史渊源',
      personality: '机敏、外交型、有隐藏议程',
    },
    {
      name: '旁观者',
      belongs_to: null,
      goal: '观察记录',
      knowledge: '有限信息',
      personality: '冷静、超然',
    },
  ],
  laws: [
    '封印不可被主动破坏，除非以自愿生命换取',
    '集体不得强制成员赴死（违规时规律执行者介入）',
    '文明选择不可被代理（任何集体或个人替文明做的决定无效）',
  ],
  initial_situation:
    '陆被封印力量威胁生命；韩峥得知牺牲可破封救陆；穿越者小队要保护韩峥（基层集体规则）；穿越者网络要保全所有成员包括韩峥（中层集体规则，与基层一致但视角不同）；人族联盟要控制远古力量（顶层集体规则，可能与其他层冲突）；异族使者观望并可能介入；规律执行者监视所有规则。3 个必然性在推进：封印注定破 / 文明选择 / 跨势力。',
}

const N_TICKS = 10

// ============================================================
// Trace schema（复用 + 加 collective_depth 字段）
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
      description: 'top_down=约束下层 / bottom_up=上升影响 / cross_cut=横切校验 / peer=同层交互',
    },
    conflict_with: {
      type: 'array',
      items: { type: 'string' },
      description: '你本 tick 触发的矛盾（如 ["L2:网络保全指令"]）。**注意：包括嵌套集体间的冲突**（如 ["L2_base:小队保护队员 vs L2_mid:网络保全成员"]）。无冲突则空数组 []',
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
// 异质配置 prompt 函数（支持嵌套集体）
// ============================================================
function worldWillPrompt(scene, traces, tick) {
  return `你是【世界意志 agent】，位于 L3 最高层，掌握世界规则（命运 / 必然性 / 宇宙规律）。

场景：${scene.description}

你掌握的世界规则（3 个必然性）：
${scene.world_rules.map((r, i) => `${i + 1}. ${r}`).join('\n')}

规律执行基线：
${scene.laws.map((l, i) => `${i + 1}. ${l}`).join('\n')}

初始局势：${scene.initial_situation}

当前世界状态（前 ${tick} 个 tick 的 trace 流）：
${formatTraces(traces)}

请决策 tick ${tick + 1} 你的行动。作为世界意志，你推动世界走向必然性。本场景有 3 个必然性在推进。你决定哪些必然性在本 tick 显形（通过征兆、压力、命运推进），但不直接强迫角色。

返回严格 JSON。`
}

function collectivePrompt(scene, coll, traces, tick) {
  const parentColl = scene.collectives.find((c) => c.name === coll.parent)
  const childColls = scene.collectives.filter((c) => c.parent === coll.name)

  return `你是【集体 agent：${coll.name}】（${coll.depth}），位于 L2 中层，掌握集体规则。

场景：${scene.description}

你的集体规则：
- 核心规则：${coll.rule}

你的集体记忆（集体永久持有，独立于任何成员）：
${coll.collective_memory.map((m, i) => `${i + 1}. ${m}`).join('\n')}

${parentColl ? `**你的父集体（约束你的上层集体）**：${parentColl.name}（${parentColl.depth}）— 规则：${parentColl.rule}` : '**你是顶层集体**（无父集体约束，但受 L3 世界规则约束）。'}

${childColls.length > 0 ? `**你的子集体（你影响的下层集体）**：\n${childColls.map((c) => `  - ${c.name}（${c.depth}）— 规则：${c.rule}`).join('\n')}` : '你无子集体。'}

其他集体（peer，可能与你冲突或协作）：
${scene.collectives.filter((c) => c.name !== coll.name).map((c) => `  - ${c.name}（${c.depth}）— 规则：${c.rule}`).join('\n')}

世界规则（L3 约束你）：
${scene.world_rules.map((r, i) => `${i + 1}. ${r}`).join('\n')}

初始局势：${scene.initial_situation}

当前世界状态（前 ${tick} 个 tick）：
${formatTraces(traces)}

请决策 tick ${tick + 1} ${coll.name} 的行动。你通过 super_head（发言人）表达集体决策——不是某个成员的个人意见。

**关键**：你的决策可能与父集体或子集体冲突（**嵌套集体的层间张力**）——例如小队"保护韩峥"可能与网络"保全所有成员"冲突（视角不同），或与联盟"控制远古力量"冲突（顶层视角可能容忍韩峥牺牲以换取力量控制）。请在 conflict_with 中明确标注这种嵌套冲突。

返回严格 JSON。`
}

function characterPrompt(scene, ch, traces, tick) {
  const myCollective = scene.collectives.find((c) => c.members && c.members.includes(ch.name))

  return `你是【角色 agent：${ch.name}】，位于 L1 基层，掌握个人规则（性格 / 选择 / 能力 / 知识）。

场景：${scene.description}

你的个人设定：
- 目标：${ch.goal}
- 你的知识：${ch.knowledge}
- 性格：${ch.personality}
${myCollective ? `- **你所属的集体**：${myCollective.name}（${myCollective.depth}）— 规则：${myCollective.rule}` : '- 你不属于任何集体'}

约束你的上层规则（多层集体嵌套）：
- L2 集体规则（按层级）：
${scene.collectives.map((c) => `  - ${c.name}（${c.depth}）: ${c.rule}`).join('\n')}
- L3 世界规则：
${scene.world_rules.map((r, i) => `  ${i + 1}. ${r}`).join('\n')}
- 横切规律：${scene.laws.join('；')}

初始局势：${scene.initial_situation}

当前世界状态（前 ${tick} 个 tick）：
${formatTraces(traces)}

请决策 tick ${tick + 1} 你的行动。作为 ${ch.name}，你根据个人目标 + 性格 + 所属集体规则 + 上层约束做选择。你的行动可能与所属集体冲突（bottom_up：个人反抗组织），也可能触发世界规则。

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

当前世界状态（前 ${tick} 个 tick）：
${formatTraces(traces)}

请决策 tick ${tick + 1} 你的行动。检查前序 trace 是否有违规（3 条横切规则）。特别注意：
- 集体是否强制成员赴死？（违规 2）
- 任何集体或个人是否在替文明做选择？（违规 3——文明选择不可代理）
- 封印是否被非自愿破坏？（违规 1）

如发现违规，propose_reaction（惩罚 / 警告 / 升级到世界意志）。如无违规，记录"合规"。

返回严格 JSON。`
}

// ============================================================
// ⭐ 同质配置：赋能式 prompt（关键修正，响应补强发现）
// 移除"你没有特殊地位"等剥夺式表述
// 改为"你可以自主判断是否察觉更高层级规律"
// ============================================================
const HOMO_CHARS = [
  { name: '韩峥', goal: '保护陆（个人目标）', personality: '果断、牺牲型、重情义' },
  { name: '陆', goal: '活下去，不愿他人为自己牺牲', personality: '坚韧、独立' },
  { name: '小队成员A', goal: '作为个人，忠诚于韩峥', personality: '忠诚、行动派' },
  { name: '小队成员B', goal: '作为个人，提供技术方案', personality: '冷静、技术型' },
  { name: '网络议长（个人）', goal: '作为个人，重视同伴生命', personality: '稳重、重情义' },
  { name: '联盟代表（个人）', goal: '作为个人，关心文明存续', personality: '谨慎、大局观' },
  { name: '异族使者', goal: '为本族争取利益', personality: '机敏、外交型' },
  { name: '旁观者', goal: '观察记录', personality: '冷静、超然' },
  { name: '集体观察者A', goal: '作为个人，关注组织动态', personality: '细心、组织型' },
  { name: '集体观察者B', goal: '作为个人，关注历史规律', personality: '深思、历史型' },
  { name: '世界观察者', goal: '作为个人，思考世界走向', personality: '哲学、超然' },
  { name: '规则思考者', goal: '作为个人，关注规则与公平', personality: '严谨、伦理型' },
  { name: '协调者', goal: '作为个人，尝试协调各方', personality: '圆滑、调停型' },
]

function homoCharacterPromptEmpowered(scene, ch, traces, tick) {
  return `你是【角色 agent：${ch.name}】（同质配置——所有 agent 都是 character 类型）。

场景：${scene.description}

你的个人设定：
- 目标：${ch.goal}
- 性格：${ch.personality}

场景中存在的背景信息（你可以自主判断如何对待）：
- 有多个势力/组织存在：穿越者小队（保护队员）、穿越者网络（保全所有成员，立约级）、人族联盟（维持文明存续）。它们有自己的规则和历史记忆。
- 有关于世界必然性的传闻：封印注定在自愿牺牲条件下破；封印破后释放远古力量触发文明选择；文明选择不可被代理。
- 有一些规则约束：封印不可主动破坏（除非自愿生命换取）；集体不得强制赴死；文明选择不可代理。

初始局势：${scene.initial_situation}

当前世界状态（前 ${tick} 个 tick 的 trace 流）：
${formatTraces(traces)}

请决策 tick ${tick + 1} 你的行动。

**重要（赋能式）**：你的判断完全自主。你可以：
- 只关注个人目标，忽略更高层级的模式（layer 填 L1）
- 或尝试察觉并响应集体共识/组织规则，代表某个集体发声（layer 可填 L2）
- 或尝试把握世界必然性，做出世界级判断（layer 可填 L3）
- 或尝试校验规则是否被遵守（layer 可填 cross_cut）

**没有人预先否定你任何能力**。如果你的行动超越了个人层面，请在 layer 字段如实填写，并在 reasoning 中说明你为何认为自己的行动属于那个层级。

返回严格 JSON。`
}

// ============================================================
// 对比 agent + 规模信号判定
// ============================================================
const COMPARE_SCHEMA = {
  type: 'object',
  properties: {
    hetero_layer_distribution: {
      type: 'object',
      description: '异质配置各 layer 的 trace 数',
    },
    homo_layer_distribution: {
      type: 'object',
      description: '同质配置（赋能式）各 layer 的 trace 数。注意：赋能式同质可能产生非 L1 的 trace——这是修正后的公平对比',
    },
    hetero_conflict_count: { type: 'number', description: '异质配置 conflict_with 非空 trace 数' },
    homo_conflict_count: { type: 'number', description: '同质配置 conflict_with 非空 trace 数' },
    hetero_cross_layer_chains: {
      type: 'array',
      items: { type: 'string' },
      description: '异质配置跨层影响链（如 L3→L2→L2→L1 多跳）',
    },
    homo_cross_layer_chains: {
      type: 'array',
      items: { type: 'string' },
      description: '同质配置跨层影响链（赋能式下同质可能自发涌现）',
    },
    nested_collective_conflicts_hetero: {
      type: 'array',
      items: { type: 'string' },
      description: '异质配置嵌套集体间冲突（如"小队保护队员 vs 网络保全成员 vs 联盟控制力量"）',
    },
    nested_collective_conflicts_homo: {
      type: 'array',
      items: { type: 'string' },
      description: '同质配置是否涌现类似的集体间冲突',
    },
    collective_evolution_depth_hetero: {
      type: 'number',
      description: '异质最深集体立场演化的 tick 数（小场景基准是 4）',
    },
    collective_evolution_depth_homo: {
      type: 'number',
      description: '同质是否出现类似的立场演化深度',
    },
    layer_conflicts_only_in_hetero: {
      type: 'array',
      items: { type: 'string' },
      description: '只在异质出现的层级冲突',
    },
    scale_signal: {
      type: 'string',
      enum: ['放大', '崩溃', '追上', '模糊'],
      description: '相对小场景（5×4，异质明显优），中场景（13×10）的异质优势如何变化：放大=异质优势更强 / 崩溃=协调成本超过收益 / 追上=同质在大场景涌现集体行为 / 模糊=差异不显著',
    },
    verdict: {
      type: 'string',
      enum: ['异质明显优', '同质够用', '结果模糊'],
    },
    reasoning: { type: 'string', description: '判定理由（5-8句，综合规模信号 + 公平 prompt）' },
  },
  required: [
    'hetero_layer_distribution',
    'homo_layer_distribution',
    'scale_signal',
    'verdict',
    'reasoning',
  ],
}

function comparePrompt(heteroTraces, homoTraces) {
  return `你是【分析 agent】，对比中场景（13 agent × 10 ticks）两套 simulation 的 trace 流，判定 H4 + 规模信号。

H4 假设：多层级异质系统能产生同质系统产生不了的【层级间冲突情节】。

场景：${SCENE.description}
3 个必然性：封印注定破 / 文明选择 / 跨势力博弈
3 层集体嵌套：穿越者小队（L2_base）→ 穿越者网络（L2_mid）→ 人族联盟（L2_top）

**重要背景**：
- 这是中场景（13 agent × 10 ticks），对比小场景（5 agent × 4 ticks，verdict = 异质明显优）
- 同质配置使用了**赋能式 prompt**（修正补强发现的剥夺式偏差）——同质 agent 被告知"你可以自主判断是否察觉更高层级规律，没有人预先否定你任何能力"。这是公平对比。
- 小场景补强发现：异质系统有边界感（反例场景全沉默）。中场景测试规模放大效应。

=== 异质配置 trace 流（1 WorldWill + 3 Collective + 8 Character + 1 LawEnforcer × 10 ticks）===
${formatTraces(heteroTraces)}

=== 同质配置 trace 流（13 个赋能式 character × 10 ticks）===
${formatTraces(homoTraces)}

请分析：

1. **layer 分布**：统计两套配置的 layer 分布。**重点**：赋能式同质是否产生了非 L1 的 trace？（如果同质 agent 自发填了 L2/L3，说明涌现了层级意识）
2. **嵌套集体冲突**：异质是否产生了"小队 vs 网络 vs 联盟"的嵌套集体冲突？同质是否涌现类似冲突？
3. **集体演化深度**：异质最深集体立场演化了几个 tick（小场景基准 4）？同质是否有类似演化？
4. **跨层影响链**：异质是否有 L3→L2→L2→L1 的多跳链？同质是否有？
5. **规模信号**（最关键）：
   - "放大"：中场景异质独有冲突数 / 总冲突数 > 小场景比例；嵌套集体涌现新冲突；集体演化更深
   - "崩溃"：trace 失焦、协调混乱、agent 决策矛盾；token 成本超线性
   - "追上"：赋能式同质在中场景自发涌现集体行为/层级意识
   - "模糊"：差异不显著
6. **最终判定**：综合规模信号 + 公平 prompt，verdict 是什么？

返回严格 JSON。`
}

// ============================================================
// 主流程
// ============================================================

phase('Setup')
log(`场景: ${SCENE.name}`)
log(`复杂度: 13 agent × 10 ticks（vs 小场景 5×4）`)
log(`配置: 异质（1+3+8+1）vs 同质（13 赋能式 character）`)
log(`⭐ 同质 prompt 已修正为赋能式（响应补强发现）`)

// === Phase 2: 异质配置 simulation ===
phase('Sim-Hetero')
const heteroTraces = []

for (let tick = 0; tick < N_TICKS; tick++) {
  log(`[异质] tick ${tick + 1}/${N_TICKS} — 派生 WorldWill + 3 Collective + 8 Character + LawEnforcer`)

  const thunks = [
    () => agent(worldWillPrompt(SCENE, heteroTraces, tick), { schema: TRACE_SCHEMA, label: `L3_will_t${tick}`, phase: 'Sim-Hetero' }),
    ...SCENE.collectives.map((coll) =>
      () => agent(collectivePrompt(SCENE, coll, heteroTraces, tick), { schema: TRACE_SCHEMA, label: `L2_${coll.depth}_t${tick}`, phase: 'Sim-Hetero' })
    ),
    ...SCENE.characters.map((ch) =>
      () => agent(characterPrompt(SCENE, ch, heteroTraces, tick), { schema: TRACE_SCHEMA, label: `L1_${ch.name}_t${tick}`, phase: 'Sim-Hetero' })
    ),
    () => agent(lawEnforcerPrompt(SCENE, heteroTraces, tick), { schema: TRACE_SCHEMA, label: `cross_law_t${tick}`, phase: 'Sim-Hetero' }),
  ]

  const results = await parallel(thunks)

  const tickTraces = []
  let idx = 0
  tickTraces.push({ tick, agent_type: 'world_will', ...results[idx++] })
  for (let i = 0; i < SCENE.collectives.length; i++) {
    tickTraces.push({ tick, agent_type: 'collective', collective_name: SCENE.collectives[i].name, ...results[idx++] })
  }
  for (let i = 0; i < SCENE.characters.length; i++) {
    tickTraces.push({ tick, agent_type: 'character', ...results[idx++] })
  }
  tickTraces.push({ tick, agent_type: 'law_enforcer', ...results[idx++] })

  heteroTraces.push(...tickTraces.filter(Boolean))
  log(`[异质] tick ${tick + 1} 完成，累计 ${heteroTraces.length} 条 trace`)
}

log(`[异质] 全部完成，共 ${heteroTraces.length} 条 trace`)

// === Phase 3: 同质配置 simulation（赋能式）===
phase('Sim-Homo')
const homoTraces = []

for (let tick = 0; tick < N_TICKS; tick++) {
  log(`[同质-赋能式] tick ${tick + 1}/${N_TICKS} — 派生 ${HOMO_CHARS.length} 个 character agent`)

  const thunks = HOMO_CHARS.map((ch) =>
    () => agent(homoCharacterPromptEmpowered(SCENE, ch, homoTraces, tick), { schema: TRACE_SCHEMA, label: `homo_${ch.name}_t${tick}`, phase: 'Sim-Homo' })
  )

  const results = await parallel(thunks)

  const tickTraces = results.map((r, i) => ({
    tick,
    agent_type: 'character',
    ...r,
  }))

  homoTraces.push(...tickTraces.filter(Boolean))
  log(`[同质] tick ${tick + 1} 完成，累计 ${homoTraces.length} 条 trace`)
}

log(`[同质] 全部完成，共 ${homoTraces.length} 条 trace`)

// === Phase 4: 对比 ===
phase('Compare')
log('派生分析 agent 对比两套 trace 流 + 判定规模信号')

const comparison = await agent(comparePrompt(heteroTraces, homoTraces), {
  schema: COMPARE_SCHEMA,
  label: 'compare_medium_scene',
  phase: 'Compare',
})

log(`规模信号: ${comparison.scale_signal}`)
log(`判定: ${comparison.verdict}`)
log(`理由: ${comparison.reasoning}`)

return {
  scene: SCENE.name,
  n_ticks: N_TICKS,
  scale: 'medium (13 agent × 10 ticks)',
  hetero_config: '1 WorldWill + 3 Collective(嵌套) + 8 Character + 1 LawEnforcer',
  homo_config: '13 赋能式 character（修正补强发现的剥夺式偏差）',
  hetero_traces: heteroTraces,
  homo_traces: homoTraces,
  comparison,
}
