# Polish re-repair + completed 蕴含 L2-clean — 设计文档

- **日期**:2026-06-20
- **背景**:字数下限硬门禁(第 8 缺陷)落地后,vigilia ch13 重写暴露:Repair 扩到 ≥3000 过 L2 → **Polish 削减修辞把字数削回 2946(<3000)且破坏 beat** → 工作流只 `mark-polish-broke-beat` 打 flag、**无 re-repair** → 章以破损态(`polish_broke_beat=1` + `word_count_below_floor`)结束,却 `status=completed`。
- **根因(两面)**:
  1. Polish/Consistency 阶段破坏 L2(beat 或 word_count)后,只 flag 不修(`bedrock-chapter.js:81-84, 99-102`)。
  2. `verify_chapter_persisted` 只查 `len(paragraphs)>0`,**不查 L2**(`persist_gate.py:10-15`)→ `completed`(verify 通过即置)不蕴含 L2-clean → 破损章可被当定稿导出。
- **目标**:Polish/Consistency 破坏后**回退**到阶段前 L2-pass 版(不加 agent);completed 必然 L2-clean。
- **硬约束:不增加常态 agent 数**(单章已 10+ agent,缺陷修复不得再加重)。re-repair 方案(每阶段 +2~4 agent)否决;改用 **agent-free 回退**。

---

## 设计

> **agent 预算**:三处改动常态 **0 新 agent**。仅 Polish/Consistency 破坏 L2 的罕见路径 +1 relay(回退重 commit)。不引入 re-repair 循环(那会给每章 +2~4 agent)。

### 1. Polish/Consistency 破坏 L2 → 回退到阶段前版本(0 新 agent)

**核心思路**:Polish 跑前的 `prose`/`report` 已过 L2(含 Repair 扩写的 ≥3000 字)。Polish 是**风格增强**,非必需。若 Polish 版破坏 L2(beat/word_count),**丢弃 Polish 输出、回退到 pre-Polish 版**——该版就在手里,无需 agent 重写。

**Polish 段(`bedrock-chapter.js:75-87`)改为**:
```js
phase('Polish')
if (report.passed_hard_gate && ctx.fingerprint) {
  const preProse = prose, preReport = report              // 阶段前 L2-pass 快照
  const polished = extractProse(await agent(editPolishPrompt(ctx, preProse),
    { label: 'Edit-polish', phase: 'Polish' }))
  const after = await commitAndL2(project, chapter, polished, 'polish')
  _trackDrift(after)
  if (after.passed_hard_gate) {
    prose = polished; report = after
    log('polish ok')
  } else {
    // Polish 破坏 L2(beat/word_count)→ 回退到 pre-Polish(已过 L2)。+1 relay 重 commit。
    await commitAndL2(project, chapter, preProse, 'polish-revert')
    prose = preProse; report = preReport
    await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`, { phase: 'Polish' })
    log('polish 破坏 L2 → 回退 pre-Polish 版(风格该轮未应用,正确性优先)')
  }
} else { log('polish skipped (no fingerprint or L2 not passed)') }
```
- **无震荡、无新 agent**:失败路径仅 +1 `commitAndL2` relay(回退重 commit pre-Prose);常态 Polish 通过则 0 新 agent。
- 代价:Polish 偶被丢弃(该轮风格未应用),但章保持 L2-clean + ≥3000。风格漂移仍被 `_trackDrift` 记录(advisory)。正确性 > 风格。

**Consistency 段(line 91-110)**:ops 应用后若破 L2,**不应用该批 ops**(回退)。Consistency 是 ops-based,`applyOpsAndL2` 失败时直接丢弃 ops、保留 pre-ops `report`/`prose`(已在内存,0 重 commit relay,因 ops 未真正落库前可判——若已落库则同 Polish 回退重 commit pre-ops)。改 `if (!after.passed_hard_gate)` 分支为回退而非仅 flag。

### 2. Polish prompt 预防约束(0 agent,降低破坏频率)

`editPolishPrompt`(`bedrock-chapter.js`)加约束行:
- "仅做风格微调(句式/对白/破折号/修辞密度对准指纹)。**不得删除段落、不得合并/拆分 beat 结构、不得降低汉字数 below 下限**。风格调整须在保持 beat 与字数的前提下进行。"
- 预防为主(减少 Polish 破坏发生),回退为兜底。

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

- **不增加常态 agent**:Polish/Consistency 通过则 0 新 agent;破坏时仅 +1 回退 relay。无 re-repair 循环。
- Polish 破坏 → 回退 pre-Polish(已过 L2,含 ≥3000 字);章保持 L2-clean,该轮风格未应用(可接受)。
- `mark-unresolved` 不再用于 Polish/Consistency(回退已保 L2-clean);仅主 L2+Repair 3 轮耗尽时用(既有语义不变)。
- **既有作品**:vigilia 24 章除 ch13(当前破损)外均 L2-clean;ch13 重跑后自愈。voidwright 等若有历史 L2-不过 completed 章,重跑 verify 会暴露(正确行为,非回归)。

---

## 测试策略

- **`tests/bedrock/test_persist_gate.py`(新或扩)**:
  - 有段落 + L2 过 → `verify_chapter_persisted=True`。
  - 有段落 + L2 不过(注入 word_count_below_floor / empty_beat)→ `False`。
  - 无段落 → `False`(既有语义不破)。
- **workflow**:Polish 回退逻辑——构造"Polish 破坏 L2"场景(模拟),断言回退到 pre-Polish、`polish_broke_beat` flag 置位、章仍 L2-pass。(JS 沙箱难直测,可抽纯函数或靠端到端。)
- **端到端回归**:vigilia ch13 重跑 → Polish 若削破 → 回退 pre-Polish(≥3000,L2-clean)→ 终态 `passed_hard_gate=True` + `status=completed` + 汉字 ≥3000。**全程 agent 数不增**(Polish 1 agent + 失败时 1 回退 relay)。ch17/22/24 同理。

## 影响面与回退

- 改动:`.claude/workflows/bedrock-chapter.js`(Polish/Consistency 回退 + Polish prompt 约束)、`src/bedrock/orchestration/persist_gate.py`(加 L2 要求)、`tests/bedrock/test_persist_gate.py`。
- 既有正文不动;completed 语义收紧(破损章不再 completed);常态 agent 数不增。
- 回退:独立 commit,可单独 revert。
