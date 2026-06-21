# Stateful Writer Agent(step ①,模式 2)— 设计文档

- **日期**:2026-06-21
- **背景**:stateful editor(master `93f3237`)消灭了 Revise 阶段的轮间失忆。但 **Write 阶段仍是一次性 agent**——ChapterWriter 恒欠产(2200~2800 字 vs 3000 floor)且偶发破 beat,把结构问题**甩给 editor 补**。这是"源头错、末端补",交接处丢 writer 草稿上下文,且 editor 每章都被迫先修结构再做 style。
- **根因**:writer 一次性产稿,无自纠;欠产/破 beat 全后置到 editor。
- **目标**:Write 段从"一次性 `chapterWriterPrompt` → JS `commitAndL2`"改为**一个 stateful 工具型 writer agent**(与 editor 同构),内部循环:写→commit→run-l2 自检→若结构(字数/beat)不过则扩/修→复测→收敛。**源头修结构**,editor 收到结构-clean 稿,主业转 style。
- **scope**:仅 writer 自纠**结构**(字数 ≥ floor + L2 beat)。style 仍归 editor,专名 phase 不动,editor 角色不变。step②(砍 relay + 专名/style 并入)/ step③(editor 转定性)后续做。
- **硬约束 / 红线**:
  1. **L2 终审确定性不动**——writer 自跑 run-l2 是只读客观测量(改不了规则),JS 用独立 l2Report 复核(不信 writer 自报),editor 之后 + finalize verify-persisted 再独立验。多 gate。
  2. **2-agent 冗余纠偏**——writer 自纠结构 + editor 兜底(再验 L2 + 做 style);任一出错另一可拦。
- **字数下限来源**:`style_template.word_count_target`(工作台 Style 视图已可配),boot-context 已装配、run-l2 已读。**非硬编码,不需补工作台**。
- **agent cap**:writer 硬上限 3 / editor 5(均 prompt 自律 + JS 独立 L2 兜底)。可调,后续按需。

---

## 决策记录(已与用户确认)

- **scope = writer 仅自纠结构**(字数 + L2 beat);style/专名不动,editor 角色不变。
- **硬上限 = 3 次 commit**(writer 源头 + editor 兜底,取紧;editor 保持 5)。
- **工具面 = `commit-paragraphs` + `run-l2` + `show-paragraphs` 三样**(与 editor 同构;show-paragraphs 用于多 beat 章保归属 + commit 被拒时确认 DB 实况,见独立审查)。
- **无需 spike**——stateful 工具循环模式已由 editor 验证可行,writer 同款。
- **不碰工作台**——字数目标走既有 style_template,cap 硬编码 prompt。

---

## 设计

### 1. 架构(Write 段替换,余不动)

工作流序列 Boot→**Write**→Revise→Consistency→专名→Finalize 不变;editor/Consistency/专名/finalize 全不动。唯一改动:Write 槽位从"一次性 agent + JS commitAndL2"换成"一次 `agent(writerPrompt)` stateful 自纠循环"。

```
现状 Write:  agent(chapterWriterPrompt) → 返 prose → JS commitAndL2(commit relay + run-l2 relay) → 进 editor
目标 Write:  agent(writerPrompt + 工具) → writer 内部: 写草稿→commit→run-l2 自检→若字数/beat 不过→扩/修→复测→收敛 → 返 JSON
             JS: 独立 l2Report 复核(信任锚) + readCurrentProse 刷新 → 进 editor
```

### 2. Writer agent 定义

**工具面**(自带 Bash,prompt 限定;**pipe 传 stdin**——editor spike 教训,heredoc 在本环境失败):
- `commit-paragraphs --project <p> --chapter N`(stdin=整章正文,段间空行,不裹围栏)——落盘
- `run-l2 --project <p> --chapter N`——结构自检(确定性,返 word_count + word_count_below_floor + beat 违规)
- `show-paragraphs --project <p> --chapter N`——读 DB 当前段落(重写时保 beat 归属 / commit 被 sanitize 拒时确认 DB 实况)

> writer 多从自己上下文重写草稿,但**保留 show-paragraphs**(与 editor 同构):多 beat 章重写时需保 `@@beat:N@@` 归属;若某轮 commit 被 sanitize 拒(writer 自以为 ok 但 DB 没变),不读 DB 无法发现"没更新"(run-l2 不返回正文)。run-l2 是收敛尺子。写面经 commit-paragraphs(repo + amendment),无绕过。

**收敛契约(客观,非自判)**:`run-l2.passed_hard_gate === true`(字数 ≥ floor + 无 beat 违规)。**style 不在 writer 范围**(交 editor)。硬上限 **3 次 commit**。

**循环**:写草稿 → commit-paragraphs → run-l2 →
- `word_count_below_floor` → 整章扩写(剧情骨架增细节/感官/心理/对白;**禁灌水**)
- beat 违规 → 修(edit-paragraphs 或整章重写)→ 重 run-l2 复测
- 累进接受(凭 stateful 上下文记忆上一轮 + 需要时 show-paragraphs 重读 DB 真相,不回退丢进展)
- 反复直到 passed_hard_gate=true 或到 3 次上限。

**返回(镜像 editor)**:`{converged, iterations, final_passed, word_count, final_l2_violations}`。

### 3. `writerPrompt(ctx, project, chapter, volume)`

= 现有 `chapterWriterPrompt` **全部内容**(角色正典/文风指令/正反例/HYGIENE_RULES/beat 契约/读者已知秘密/多 beat `@@beat:N@@` 标记/字数目标 3000–5000/禁元文本开场白 等)**追加**:
- 工具面(commit-paragraphs + run-l2,pipe stdin 示例)
- 迭代协议(写→commit→run-l2→扩/修→复测,硬上限 3,收敛由 run-l2 客观判,不自判)
- 禁灌水约束
- 红线(收敛由 run-l2 输出判;破 L2 的改动必须修;第一段必须是正文)
- JSON 返回契约(最后一行 `{"converged":..,"iterations":..,"final_passed":..,"word_count":..,"final_l2_violations":[..]}`)

结构同 `editorPrompt`(已合并 master)。

### 4. JS Write 段(镜像 Revise/editor 接线)

```js
phase('Write')
const writerRaw = extractProse(await agent(writerPrompt(ctx, project, chapter, volume),
  { label: 'Writer', phase: 'Write' }))
// writer 常在 JSON 行前后带叙述,逐行找最后一个可解析 {...}(复用 extractEditorJson);仅遥测,收敛判定走下面独立 l2Report。
let writer = extractEditorJson(writerRaw) || { converged: false, final_passed: false, iterations: 0 }
report = await l2Report(project, chapter, 'Write')   // 独立 relay 复核 L2(信任锚,不信 writer 自报)
prose = await readCurrentProse(project, chapter)     // writer 改了 DB,刷新 JS 侧 prose(供下游 Consistency 回退快照)
// 注:round 仍在 Revise 段声明(=editor.iterations)喂 finalize 遥测;此处不重复声明(避 const 冲突)。writer 迭代数进日志。
if (!report.passed_hard_gate) {
  // mark-unresolved 仅设 review 旗,不阻流;终审 verify-persisted 独立再跑 L2 兜底,破损章不会 completed。
  await pythonCli(
    `mark-unresolved --project ${project} --chapter ${chapter} --rule-or-model 0`,
    { phase: 'Write', stdin: JSON.stringify(report.beat_violations || []) })
  log(`writer 未收敛(L2 仍不过,${writer.iterations || '?'} 轮)→ mark-unresolved`)
} else {
  log(`writer 收敛: 结构 clean, ${writer.word_count || '?'} 字 → 进 editor`)
}
```
> 与 editor 接线完全对称。`report`/`prose` 是模块作用域 `let`(原 Write 段声明),此处重赋值;`round` 仍在 Revise 段 const 声明(Write 段不重复声明,避 `const` 冲突)。`l2Report`/`readCurrentProse`/`extractEditorJson`/`extractProse`/`pythonCli` 均既有。
> **注**:Write 段此处刷新的 `prose` 之后**必被 Revise 段的 `readCurrentProse` 再覆盖**——属预期(editor 一定在 writer 之后跑,editor 版才是最新)。Write 段这行只在"editor 不改 DB"的退化情形下有独立效果,但保留它使两段对称、且 writer 未收敛走 mark-unresolved 时 Consistency 仍读到正确 prose。

### 5. 红线 + defense-in-depth

- **L2 确定性**:writer 自跑 run-l2 是只读客观(改不了规则);JS 独立 l2Report 复核(不信 writer.converged);editor 之后还会再独立跑 L2(editor 自检)+ finalize verify-persisted 终审。**writer/editor/finalize 三道独立 L2**,writer 自报结构上无法影响任何 gate。
- **冗余纠偏**:writer 自纠结构,editor 兜底再验 + 做 style。任一环节结构出错,下游拦得住。
- **写面**:经 commit-paragraphs(repo + amendment),无绕过。

### 6. 不改的部分(明确边界)

- editor(stateful,做 L2 确认 + style)、Consistency(ops)、专名(确定性 phase)、finalize 全不动。
- step②(砍 relay + 专名/style 并入 agent loop)、step③(editor 转纯定性 reviewer)后续做。
- 工作台不动(字数目标已走 style_template)。

---

## 错误处理

- 硬上限耗尽(3 次 L2 仍未过)→ writer 返 converged=false → JS 独立 l2Report 确认 → mark-unresolved(章不 completed,正确升级)。
- writer 吐非正文 / commit 被拒(sanitize 防线)→ writer 内部读 run-l2 复测发现没更新 → 重试或到限退出。
- writer 跑飞(乱调工具)→ bounded:工具面就是 commit-paragraphs/run-l2,DB 层强制写面经 repo;最坏 3 次空转后 mark-unresolved,不毁 SSOT。
- writer 未按契约返 JSON → `extractEditorJson` 取末行 JSON,取不到 fallback;JS 以独立 l2Report 实况为准(不信自报)。

---

## 测试 / 验证策略

JS 沙箱工作流,无 Python 单测;靠静态检 + 端到端(无需 spike,模式已由 editor 验证)。

- **静态检**:`node --check`;grep 确认 Write 段从 commitAndL2 改为单 `agent()` + writerPrompt;chapterWriterPrompt 内容并入 writerPrompt;`commitAndL2` 若 Write 后无其他调用方则评估保留/删(Consistency 回退仍用 commitAndL2,**保留**)。
- **Python 回归**:`pytest tests/bedrock/` 全绿(Python 零改)。
- **端到端**:重跑 vigilia ch13/ch1 → 期望:
  - writer 自纠结构(欠产 draft → 扩到 ≥ floor + L2 clean,迭代 ≤3)。
  - editor 之后 run-l2 确认已 clean(结构上 no-op),主业转 style。
  - 终态 L2-clean + completed。
  - **writer 不再把欠产甩给 editor**(editor 不再被迫先修字数)。

---

## 影响面与回退

- **改动**:`.claude/workflows/bedrock-chapter.js`(Write 段重写 + `chapterWriterPrompt`→`writerPrompt` 内容扩充)。Python 零改。
- **不动**:editor/Consistency/专名/finalize、paragraph 存储、L2、persist_gate、CLI、工作台、既有 DB 章。
- **向后兼容**:既有章在 DB 不动;未来章走 stateful writer。
- **回退**:独立 commit(分支 `bedrock-stateful-writer`),可整体 revert。
- **风险**:① writer 自纠扩写可能灌水 → 禁灌水 prompt + editor/style-check 后置拦。② writer 不按契约返 JSON → extractEditorJson + 独立 l2Report 兜底。③ 模式已由 editor 验证,风险低。

---

## 文件结构

**修改(唯一文件):** `.claude/workflows/bedrock-chapter.js`
- 改:`chapterWriterPrompt` → `writerPrompt`(原内容 + 工具面/迭代协议/返回契约)。
- 改:Write 段(commitAndL2 → 单 `agent(writerPrompt)` + 独立 l2Report 复核 + readCurrentProse 刷新 + mark-unresolved 分支)。
- 保留:`commitAndL2`(Consistency 回退仍用)、`l2Report`/`readCurrentProse`/`extractEditorJson`/`extractProse`/`pythonCli`/`HYGIENE_RULES`。

**新建/测试:** 无 Python 新文件;静态检 + 端到端。

**Python:** 零改动。
