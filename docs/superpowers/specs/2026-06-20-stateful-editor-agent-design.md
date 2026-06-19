# Stateful Editor Agent(模式 2 固定编排 teams)— 设计文档

- **日期**:2026-06-20
- **背景**:Revise pass 收束(master `50669b7`)把 3 个全正文复写器合成 1 个 Revise 阶段,但 e2e 暴露根因——**轮间失忆(amnesia)**:JS 编排的每个 revise 轮是全新 agent,不记得上一轮试过什么、为什么失败,只能盲目重试(字数扩写常需 2 轮累进才过)。同时 Revise 阶段 ~9 个转发 relay(commit/run-l2/styleCheck)臃肿,单章 agent 数 ~17。
- **根因**:失忆不是"工作流模式"自带,是"离散一次性 `agent()` 调用"自带。每跨一次 agent 边界开新上下文 = 失忆一次。JS 编排 N 个失忆轮 = 反复修的来源。
- **目标**:Revise 槽位从"JS 驱动 N 个失忆 agent 轮"换成"**一个 stateful 工具型 editor agent,内部循环自纠错**"。editor 自带上下文记得自己改过什么、收敛而非盲重试;自带 Bash 直接调 CLI,relay 收敛。**工作流确定性骨架不动**(角色顺序/交接/最终判决仍在 JS)。
- **scope**:仅 stateful editor(+relay 收敛)。定性 reviewer panel 单独立项。Write/Consistency/专名/finalize 不动。
- **硬约束 / 两条红线**:
  1. **固定编排留在工作流 JS**——editor 只在 Revise 槽位内自治,不决定后续阶段。
  2. **收敛由确定性 gate 声明,agent 不自判完稿**——editor 读 `run-l2`/`style-check` **客观输出**判断,不是"我觉得行了";工作流 Finalize 再跑 `verify-persisted` 终审(双 gate)。

---

## 决策记录(已与用户确认)

- **scope = 仅 stateful editor(+relay)**;定性 reviewer panel 单独立项。
- **A. editor 管结构 + 文风双收敛**(完整替代现 Revise 的 L2-fix + style-converge),不分裂。
- **B. 通用 agent + 全 Bash + prompt 限定到 bedrock CLI**(不搭 restricted agentType)。理由:本地写作 DB 无敏感面,DB 层已强制写面经 repo;restricted agentType 边际安全收益低。
- **硬上限 = 5 次内部 commit**。

---

## 设计

### 1. 架构(一处替换,骨架不动)

工作流序列 Boot→Write→**Revise**→Consistency→专名→Finalize 不变;交接、最终 verify-persisted 判决不变。唯一改动:Revise 槽位从 JS while-loop(离散失忆 agent 轮)换成**一次** `agent(editorPrompt, { agentType: 'general-purpose' })` 调度,该 agent 内部带工具循环。

```
现状 Revise(JS 失忆轮):
  JS: manifest=buildManifest(...) ; while(!empty && round<2){ agent(revisePrompt)→新agent→返prose→commitAndL2→复测→喂下个新agent }

目标 Revise(stateful editor):
  JS: result = agent(editorPrompt(ctx, project, chapter), {agentType:'general-purpose', phase:'Revise'})
      → 一个 agent 内部:show-paragraphs 读现状 → 修订 → commit-paragraphs 落盘 → run-l2+style-check 复测 → 据客观结果继续/收敛 → 返回 result
```

editor 在自己上下文里迭代,记得上轮改了什么;JS 不再驱动迭代。

### 2. Editor agent 定义

**工具面**(自带 Bash,prompt 限定到下列 bedrock CLI;直接调,不经转发 relay):
- `show-paragraphs --project <p> --chapter N` — 读当前段落(DB 真相源)
- `run-l2 --project <p> --chapter N` — 结构自检(**确定性 gate**,只读)
- `style-check --project <p> --chapter N --volume V` — 文风漂移自测(确定性,只读)
- `commit-paragraphs --project <p> --chapter N`(stdin=整章正文)— 整章重写落盘(扩写/beat 重构用)
- `edit-paragraphs --project <p> --chapter N`(stdin=ops)— 局部定点改(代词/单段用,更安全)

> 写面经 repo 函数 + amendment 审计(CLAUDE.md 铁律),editor 无法绕过。

**收敛契约(客观,非自判)**:
- **硬收敛**:`run-l2.passed_hard_gate === true`。
- **软目标**(advisory,不阻塞):`style-check.drifted` 为空或达容忍。文风是 advisory——**correctness 严格优先于文风,绝不为文风破 L2**(沿用 Revise 收束的原则)。
- editor 内部分两相:**相 1** 确保 L2 过(修 beat / 扩字数);**相 2** 用剩余预算减文风漂移。**L2 过即收敛**,残留言风漂移记 advisory。
- **硬上限 5 次 commit**:到上限 L2 仍未过 → 返回未收敛,工作流走既有 `mark-unresolved`(章不 completed)。

**上下文边界**:editor 拿 boot-context(beat 契约 / 指纹 / 文风指令 / 正反例 / 角色正典)+ 章号 + 工具。**不**拿 writer 草稿推理(干净交接——角色间失忆是 feature)。prose 不内联传,editor 用 `show-paragraphs` 从 DB 读(DB 即真相)。

**返回(结构化,供 JS 决策)**:
```json
{ "converged": true|false, "iterations": <int>, "final_passed": true|false,
  "word_count": <int>, "final_l2_violations": [...], "style_drift_remaining": <int> }
```
JS 据 `converged`/`final_passed`:过 → 进 Consistency;不过 → `mark-unresolved`。

### 3. Editor prompt 结构(`editorPrompt(ctx, project, chapter, volume)`)

```
# 章节修订员(stateful,自带工具循环)
你在项目根 D:/novel_test。本章=<chapter> 卷=<volume> 已在 bedrock.db。
boot-context: <ctx JSON: beat契约/指纹/文风指令/正反例/角色>

【工具·只准用这些 bedrock CLI】
- 读现状:python -m src.bedrock show-paragraphs --project <p> --chapter N
- 结构自检(确定性,判过没过):python -m src.bedrock run-l2 --project <p> --chapter N
- 文风自测(确定性,advisory):python -m src.bedrock style-check --project <p> --chapter N --volume V
- 整章落盘:python -m src.bedrock commit-paragraphs --project <p> --chapter N  (stdin=整章正文,段间空行,不裹围栏)
- 定点改:python -m src.bedrock edit-paragraphs --project <p> --chapter N  (stdin=ops JSON)

【文风硬约束 + 正反例】<HYGIENE_RULES + style_examples>(沿用 chapterWriter/revisePrompt 的)

【迭代协议·必须遵守】
相 1(正确性优先):show-paragraphs 读现状 → run-l2 自检 → 若不过(beat/word_count_below_floor):
   - word_count 不足→commit-paragraphs 整章扩写(剧情骨架上增细节/感官/心理/对白,禁灌水)
   - beat 违规→定点修(edit-paragraphs 或整章重写)→ 重 run-l2 复测。**累进接受**:每次基于 DB 最新版继续,不回退丢进展。
   反复直到 run-l2.passed_hard_gate=true。
相 2(文风,advisory):L2 过后,style-check 自测 → 有漂移则最小改动收敛(删破折号/改"不是A是B"句式)→ 重 run-l2 确认**没破 L2**;若文风改动破了 L2→回退该改(用上一过 L2 版),停文风收敛。
收敛:run-l2.passed_hard_gate=true 即 converged(残留言风漂移可接受,advisory)。
硬上限:最多 5 次 commit-paragraphs/edit-paragraphs。到限 L2 仍未过→converged=false 退出。

【红线】收敛由 run-l2 客观输出判定,不得自判"我觉得行了"。不得绕过 CLI 直改 DB。
      破 L2 的文风改动必须回退。整章正文第一段必须是小说正文,无作者旁白。

【返回】收敛/到限后,最后输出一行 JSON:{"converged":..,"iterations":..,"final_passed":..,"word_count":..,"final_l2_violations":[..],"style_drift_remaining":..}
```

### 4. 与既有 Revise 代码的关系(收束后的状态 → 本次改动)

- **删** `bedrock-chapter.js` 的 Revise JS while-loop(三路分流那套,行 ~58-108)+ `REVISE_MAX_ROUNDS` 常量。
- **删** `buildManifest`(纯 JS,失语——editor 内部读 CLI 输出自行判断,不再需要 JS 装配 manifest)。
- **改** `revisePrompt` → `editorPrompt`(内容大部分沿用:HYGIENE_RULES / 扩写规则 / 正反例 / 正确性优先;增加工具面 + 迭代协议 + 返回契约)。
- **保留** `commitAndL2`/`styleCheck`/`extractProse`/`_trackDrift`/`pct`/`HYGIENE_RULES`/Consistency/专名/finalize 全部不动。
- Revise 段 JS 简化为:
```js
phase('Revise')
const editorRaw = extractProse(await agent(editorPrompt(ctx, project, chapter, volume),
  { label: 'Editor', phase: 'Revise' }))
let editor
try { editor = JSON.parse(editorRaw) } catch { editor = { converged: false, final_passed: false, style_drift_remaining: 0 } }
// 最坏兜底:editor 未按契约返回 JSON → 不信其自报,以 DB 实况为准
const report = await l2Report(project, chapter, 'Revise')   // 独立 relay 复核 L2(信任锚,不信 editor 自报)
// advisory 文风漂移:用 editor 自测返回的 style_drift_remaining 喂 worstDrift(供 finalize mark-advisory-drift)
if (editor.style_drift_remaining > 0)
  _trackDrift({ drifted: new Array(editor.style_drift_remaining), target_source: ctx.fingerprint ? 'editor' : null })
if (!report.passed_hard_gate) {
  await pythonCli(`mark-unresolved --project ${project} --chapter ${chapter} --rule-or-model 0`,
    { phase: 'Revise', stdin: JSON.stringify(report.beat_violations || []) })
  log(`editor 未收敛(L2 仍不过,${editor.iterations||'?'} 轮)→ mark-unresolved`)
} else {
  log(`editor 收敛: L2-clean${editor.style_drift_remaining ? `, 文风仍 ${editor.style_drift_remaining} 项漂移(advisory)` : ''}`)
}
```
> **关键:JS 不信 editor 自报的 `converged`**——以独立 `l2Report` relay 的 `run-l2` 客观结果为准。这是红线②的代码落点:即便 editor 幻觉自报收敛,JS 用独立 L2 复核,Finalize 还会 verify-persisted 再审。双 gate。
> **advisory 漂移流**:editor 内部 style-check 的结果经返回字段 `style_drift_remaining` 流回 JS → `_trackDrift` → finalize `mark-advisory-drift`(既有通路,不破)。不用再为 advisory 单独派 styleCheck relay。

### 5. 两条红线如何守

- **① 固定编排**:editor 只在 Revise 槽位;后续 Consistency/专名/Finalize 仍由 JS 按序触发,editor 不参与编排决策。
- **② 收敛由 gate 声明**:editor 内部以 `run-l2` 客观输出判过没过;JS 收尾用独立 `l2Report` relay 复核(不信自报);Finalize `verify-persisted` 终审(要求 L2 过)。三层客观判定,editor 无法靠"自报"蒙混。
- **信任锚**:写面经 CLI(repo+amendment);L2 零 LLM;editor 自跑 run-l2 是只读客观测量,改不了规则,无博弈面。

### 6. Relay 收敛(顺带落地)

editor 自带 Bash 直调 CLI,Revise 阶段原 ~9 个转发 relay(commit×3 + run-l2×3 + styleCheck×3)消失,变成 editor 内部工具调用(非独立 agent)。章总 agent 数 **~17 → ~6-7**(Boot + Write + Editor + Consistency + 专名 relay + finalize relay)。这是 agent 数下降主来源。

### 7. 错误处理

- 硬上限耗尽(5 次 L2 仍未过)→ editor 返回 converged=false → JS 独立 L2 复核确认 → `mark-unresolved`,章不 completed(正确升级)。
- editor 吐非正文 / commit 被拒(sanitize 防线)→ editor 内部读 run-l2 复测发现没更新 → 重试或到限退出。
- editor 跑飞(乱调工具)→ bounded:工具面就是 bedrock CLI,DB 层强制写面经 repo;最坏 5 次空转后 mark-unresolved,不毁 SSOT。
- editor 未按契约返回 JSON → JS catch 兜底,以独立 L2 复核 DB 实况为准(不信自报)。
- 文风改动破 L2 → editor 内部回退该改(prompt 指令);若仍破,JS 独立 L2 复核会抓到 → mark-unresolved 或按实况处理。

### 8. 不动的部分(明确边界)

- Write(ChapterWriter)单 pass 不动。
- Consistency / 专名 ops 不动。
- finalize 遥测/备份不动。
- **出 scope 但相关**:writer 持续欠产(见记忆)是 editor expand 被狠压的根因;writer 自检字数是下一个杠杆,单独立项。本次 editor 能兜住(自迭代扩写),治本在 writer 端。

---

## 测试 / 验证策略

JS 沙箱工作流,无 Python 单测;靠静态检 + 端到端 + 设计期 spike。

- **设计期 spike(先做)**:派一个最小带 Bash 的 editor agent,验证它能在沙箱里内部循环到 L2 过(确认模式 2 在本 harness 可行)。具体:对一个欠产章,用 editorPrompt 跑一次,观察它是否自主 show-paragraphs→run-l2→commit→复测→收敛。**spike 通过再全面铺**(避免在不可行假设上写完整实现)。
- **静态检**:`node --check`;grep 确认 Revise 段从 JS-loop 改为单 `agent()` 调度;`buildManifest` 删除;`editorPrompt` 取代 `revisePrompt`;三路分流 JS 删除。
- **Python 回归**:`pytest tests/bedrock/` 全绿(Python 零改)。
- **端到端**:重跑 vigilia ch13/ch1 → 期望 L2-clean + completed + **agent 数显著下降(~17→~7)**;editor 内部迭代收敛(不再失忆重试);JS 独立 L2 复核与 editor 自报一致。

---

## 影响面与回退

- **改动**:`.claude/workflows/bedrock-chapter.js`(Revise 段重写 + `buildManifest` 删 + `revisePrompt`→`editorPrompt`)。Python 零改。
- **不动**:paragraph 存储、L2、persist_gate、CLI、Write/Consistency/专名/finalize、既有 DB 章。
- **向后兼容**:既有章在 DB 不动;未来章走 stateful editor。
- **回退**:独立 commit(分支 `bedrock-stateful-editor`),可整体 revert。
- **风险**:① 通用 agent 全 Bash 跑飞 → bounded(DB 层 + 5 次上限 + 独立 L2 复核兜底)。② editor 不按契约返回 JSON → JS catch + 独立 L2 复核兜底。③ spike 若证明沙箱内工具循环不可行 → 回退到 Revise 收束现状(已合并 master),不损失既有成果。

---

## 文件结构

**修改(唯一文件):**
- `.claude/workflows/bedrock-chapter.js`
  - 删:Revise JS while-loop(三路分流)+ `REVISE_MAX_ROUNDS` + `buildManifest`。
  - 改:`revisePrompt` → `editorPrompt`(工具面 + 迭代协议 + 返回契约)。
  - 加:Revise 段单 `agent()` 调度 + 独立 `l2Report` relay 复核 + 收尾 mark-unresolved 分支。

**新建/测试:** 无 Python 新文件;spike + 静态检 + 端到端。

**Python:** 零改动。
