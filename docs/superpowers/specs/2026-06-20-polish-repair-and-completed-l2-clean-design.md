# Polish re-repair + completed 蕴含 L2-clean — 设计文档

- **日期**:2026-06-20
- **背景**:字数下限硬门禁(第 8 缺陷)落地后,vigilia ch13 重写暴露:Repair 扩到 ≥3000 过 L2 → **Polish 削减修辞把字数削回 2946(<3000)且破坏 beat** → 工作流只 `mark-polish-broke-beat` 打 flag、**无 re-repair** → 章以破损态(`polish_broke_beat=1` + `word_count_below_floor`)结束,却 `status=completed`。
- **根因(两面)**:
  1. Polish/Consistency 阶段破坏 L2(beat 或 word_count)后,只 flag 不修(`bedrock-chapter.js:81-84, 99-102`)。
  2. `verify_chapter_persisted` 只查 `len(paragraphs)>0`,**不查 L2**(`persist_gate.py:10-15`)→ `completed`(verify 通过即置)不蕴含 L2-clean → 破损章可被当定稿导出。
- **目标**:Polish/Consistency 破坏后自动 re-repair 收敛;修不好的不 completed;completed 必然 L2-clean。

---

## 设计

### 1. 抽 `repairToPass` 复用 helper(DRY)

**落点**:`.claude/workflows/bedrock-chapter.js`。

现有 L2+Repair 循环(约 line 57-72)与"Polish 后修复"同构。抽 helper:
```js
// 收敛到 L2 通过:复用 editRepairPrompt(word_count_below_floor→扩写 / beat 违规→修 beat)。
// 返回 {prose, report, rounds}。不收敛时由调用方 mark-unresolved。
async function repairToPass(project, chapter, prose, report, maxRounds, label) {
  let round = 0
  while (!report.passed_hard_gate && round < maxRounds) {
    prose = extractProse(await agent(editRepairPrompt(report, prose),
      { label: `${label}-r${round + 1}`, phase: label }))
    report = await commitAndL2(project, chapter, prose, `${label}-r${round + 1}`)
    _trackDrift(report)
    round++
    log(`${label} r${round}: passed=${report.passed_hard_gate} violations=${(report.beat_violations||[]).length}`)
  }
  return { prose, report, rounds: round }
}
```
主 L2+Repair phase 改为调 `repairToPass(..., 3, 'L2+Repair')`,保留 `likely_rule_or_model` 签名判定 + `mark-unresolved`(3 轮耗尽)。`agent`/`extractProse`/`commitAndL2`/`_trackDrift`/`log` 均为文件内既有 helper/全局。

### 2. post-Polish / post-Consistency re-repair

**Polish 段(line 75-87)**:commit+L2 后 `!passed` → `repairToPass(..., 2, 'polish-repair')`;仍 `!passed` → `mark-polish-broke-beat`(审计)+ `mark-unresolved`(不再静默继续)。改后:
```js
phase('Polish')
if (report.passed_hard_gate && ctx.fingerprint) {
  prose = extractProse(await agent(editPolishPrompt(ctx, prose), { label: 'Edit-polish', phase: 'Polish' }))
  report = await commitAndL2(project, chapter, prose, 'polish')
  _trackDrift(report)
  if (!report.passed_hard_gate) {
    const rp = await repairToPass(project, chapter, prose, report, 2, 'polish-repair')
    prose = rp.prose; report = rp.report
    if (!report.passed_hard_gate) {
      await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`, { phase: 'Polish' })
      await pythonCli(`mark-unresolved --project ${project} --chapter ${chapter} --rule-or-model 0`,
        { phase: 'Polish', stdin: JSON.stringify(report.beat_violations || []) })
      log('polish broke L2, re-repair 未收敛 → unresolved')
    } else log('polish-repair 收敛')
  }
} else { log('polish skipped (no fingerprint or L2 not passed)') }
```
**Consistency 段(line 91-110)**:同理,ops 破 L2 后 `repairToPass(..., 2, 'consistency-repair')`;不收敛 → `mark-unresolved`。

**无震荡**:re-repair 输出直进 L2,不重跑 Polish;扩写一轮回 ≥3000,封顶 2 轮。`mark-unresolved` 与既有不可解违规同路径(不毁章、不假完成)。

### 3. `verify_chapter_persisted` 要求 L2 通过 → completed 蕴含 L2-clean

**落点**:`src/bedrock/orchestration/persist_gate.py`。
```python
from src.bedrock.orchestration.l2_pipeline import run_l2

def verify_chapter_persisted(conn, chapter_id, export_path=None):
    """强制落盘门禁:paragraphs 入 DB + L2 硬门禁通过(+ 可选导出文件存在)。
    completed 蕴含 L2-clean:破损章(L2 不过)→ False → 不置 completed。"""
    paragraphs = list_paragraphs_in_chapter(conn, chapter_id)
    if len(paragraphs) == 0:
        return False
    if not run_l2(conn, chapter_id).passed_hard_gate:
        return False
    if export_path is not None and not os.path.exists(export_path):
        return False
    return True
```
- 效果:Finalize 调 verify → L2 不过 → False → **不置 completed** + 走既有 `mark-forced-persist-failed`(`__main__.py` verify-persisted handler,Task 5 已接 completed 转换 + Task 4 ensure_flag)。破损章无法 completed/导出。
- `mark-completed`(人工 CLI,Task 5)仍是显式覆盖(人工担保 L2-clean),不受影响。
- 依赖:`persist_gate → l2_pipeline`(l2_pipeline 不依赖 persist_gate,**无环**)。

### 4. 边界

- re-repair 上限:主循环 3 / post-Polish、post-Consistency 各 2。
- 不收敛 → `mark-unresolved`(既有路径);章节保留已写正文,不假完成、不导出为定稿。
- **既有作品**:vigilia 24 章除 ch13(当前破损)外均 L2-clean;ch13 重跑后自愈。voidwright 等若有历史 L2-不过 completed 章,重跑 verify 会暴露(正确行为,非回归——它们本就不该 completed)。

---

## 测试策略

- **`tests/bedrock/test_persist_gate.py`(新或扩)**:
  - 有段落 + L2 过 → `verify_chapter_persisted=True`。
  - 有段落 + L2 不过(注入 word_count_below_floor / empty_beat)→ `False`。
  - 无段落 → `False`(既有语义不破)。
- **workflow**:`repairToPass` 抽取后,主 L2+Repair 行为不变(既有 chapter 端到端测试 / 手测一章确认 0 轮首过仍正常)。
- **端到端回归**:vigilia ch13 重跑 → Polish 若削破 → polish-repair 修回 → 终态 `passed_hard_gate=True` + `status=completed` + 汉字 ≥3000。ch17/22/24 同理。

## 影响面与回退

- 改动:`.claude/workflows/bedrock-chapter.js`(抽 helper + Polish/Consistency re-repair)、`src/bedrock/orchestration/persist_gate.py`(加 L2 要求)、`tests/bedrock/test_persist_gate.py`。
- 既有正文不动;completed 语义收紧(破损章不再 completed)。
- 回退:独立 commit,可单独 revert。
