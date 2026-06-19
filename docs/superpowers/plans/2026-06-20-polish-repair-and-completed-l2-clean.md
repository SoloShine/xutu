# Polish 回退 + completed 蕴含 L2-clean Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish/Consistency 破坏 L2 时回退到阶段前 L2-pass 版(不加 agent);completed 蕴含 L2-clean。

**Architecture:** agent-free 回退——Polish/Consistency 破坏 L2 时丢弃其输出、回退到手里已有的 pre-stage `prose`(失败路径仅 +1 commit relay,常态 0 新 agent);`verify_chapter_persisted` 加 L2 通过要求,使 completed = 落盘 + L2-clean。

**Tech Stack:** Python 3 + pytest(`src/bedrock/`);Node 沙箱工作流(`.claude/workflows/bedrock-chapter.js`)。

**Spec:** `docs/superpowers/specs/2026-06-20-polish-repair-and-completed-l2-clean-design.md`

**实施:** 分支 `bedrock-polish-repair`。测试 `python -m pytest tests/bedrock/ -v`(从 D:/novel_test)。

**关键事实(已核实)**:
- `editPolishPrompt` 已含"保持剧情与字数,不增删段落"——但 LLM 仍违反(ch13 实证)。故 prompt 强化是次要,**回退是主保障**。
- Polish 阶段:`prose` 变量在 Polish 前已是 L2-pass 全文;Consistency 阶段:`prose` 变量在 Consistency 前是 post-Polish 全文(Consistency 只对 DB 段落做 ops,不动 `prose` 字符串)。故两阶段失败都能用手里 `prose` 回退(+1 commit relay)。
- `verify_chapter_persisted(conn, chapter_id, export_path)` 当前只查 `len(paragraphs)>0`。`run_l2(conn, chapter_id).passed_hard_gate` 是 L2 判定。

---

## File Structure

**修改:**
- `src/bedrock/orchestration/persist_gate.py` — `verify_chapter_persisted` 加 L2 要求。
- `.claude/workflows/bedrock-chapter.js` — Polish 段回退 + Consistency 段回退 + `editPolishPrompt` 强化。

**新建:**
- `tests/bedrock/test_persist_gate_l2.py` — verify-persisted L2 门禁测试。

---

## Task 1: `verify_chapter_persisted` 要求 L2 通过

**Files:**
- Modify: `src/bedrock/orchestration/persist_gate.py`
- Test: `tests/bedrock/test_persist_gate_l2.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_persist_gate_l2.py
"""verify_chapter_persisted 须 L2 通过(completed 蕴含 L2-clean)。"""
import pytest
from src.bedrock.orchestration.persist_gate import verify_chapter_persisted


@pytest.fixture
def seeded(tmp_path):
    """1 卷 1 章 1 beat(written)+ 段落 + style_template(word_count_target=[3000,5000])。"""
    import json
    from src.bedrock.db.connection import get_connection
    from src.bedrock.init_project import init_project
    from src.bedrock.repositories.plot_tree import (
        create_volume, create_chapter, create_beat, create_paragraph, mark_beats_written)
    proj = tmp_path / "p"
    init_project(proj, work_name="t", force=True)
    conn = get_connection(proj)
    vid = create_volume(conn, 1, "v", 1, 1, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t", status="writing")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="测试 beat 目的足够长十个字", pov_character_id=None)
    conn.execute("INSERT OR REPLACE INTO volume_outline(volume_id,status,beat_contracts) VALUES(?,'drafted',?)",
                 (vid, json.dumps([{"beat_id": bid, "purpose": "测试 beat 目的足够长十个字"}])))
    conn.execute("INSERT OR REPLACE INTO style_template(scope,volume_id,fingerprint,word_count_target) "
                 "VALUES('work',NULL,'{}','[3000, 5000]')")
    conn.commit()
    return conn, cid, bid


def test_verify_true_when_l2_passes(seeded):
    conn, cid, bid = seeded
    # ≥3000 汉字 + beat written → L2 过
    from src.bedrock.repositories.plot_tree import create_paragraph, mark_beats_written
    create_paragraph(conn, cid, 1, "正文内容在此。" * 700, "h", bid, "narration")  # 4200 汉字
    mark_beats_written(conn, [bid]); conn.commit()
    assert verify_chapter_persisted(conn, cid) is True


def test_verify_false_when_word_count_below_floor(seeded):
    """有段落但字数 <3000 → L2 不过(word_count_below_floor)→ verify False。"""
    conn, cid, bid = seeded
    from src.bedrock.repositories.plot_tree import create_paragraph, mark_beats_written
    create_paragraph(conn, cid, 1, "短正文。" * 50, "h", bid, "narration")  # ~150 汉字
    mark_beats_written(conn, [bid]); conn.commit()
    assert verify_chapter_persisted(conn, cid) is False


def test_verify_false_when_no_paragraphs(seeded):
    """无段落 → False(既有语义不破)。"""
    conn, cid, bid = seeded
    assert verify_chapter_persisted(conn, cid) is False
```

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/bedrock/test_persist_gate_l2.py -v`
Expected: FAIL(`test_verify_false_when_word_count_below_floor` 期望 False,但当前 verify 只查段落→返回 True)

- [ ] **Step 3: 实现**

`src/bedrock/orchestration/persist_gate.py` 全文替换为:
```python
# src/bedrock/orchestration/persist_gate.py
import os
from src.bedrock.repositories.plot_tree import list_paragraphs_in_chapter
from src.bedrock.orchestration.l2_pipeline import run_l2


def verify_chapter_persisted(conn, chapter_id, export_path=None):
    """强制落盘门禁:paragraphs 入 DB(主,SSOT)+ L2 硬门禁通过 + 可选导出文件存在。
    completed 蕴含 L2-clean:破损章(L2 不过,如 word_count_below_floor/beat 破)→ False。
    paragraphs == 0 → False;export_path 传入且不存在 → False。"""
    paragraphs = list_paragraphs_in_chapter(conn, chapter_id)
    if len(paragraphs) == 0:
        return False
    if not run_l2(conn, chapter_id).passed_hard_gate:
        return False
    if export_path is not None and not os.path.exists(export_path):
        return False
    return True
```

- [ ] **Step 4: 跑确认通过**

Run: `python -m pytest tests/bedrock/test_persist_gate_l2.py -v`
Expected: PASS(3/3)

- [ ] **Step 5: 回归既有 verify/persist 测试**

Run: `python -m pytest tests/bedrock/ -q -k "persist or status_lifecycle or verify"`
Expected: 全 PASS。`test_status_lifecycle.py`(Task 5)里 `test_verify_sets_completed` 的 fixture 若用 <3000 字短正文,现在 verify 会 False → 该测试需把正文补到 ≥3000 汉字(或断言适配)。以最小改动修正并记录。

- [ ] **Step 6: Commit**

```bash
git add src/bedrock/orchestration/persist_gate.py tests/bedrock/test_persist_gate_l2.py
```
(加任何适配的既有测试)。Message:
```
feat(bedrock): verify_chapter_persisted 要求 L2 通过(completed 蕴含 L2-clean)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

## Task 2: Polish 段失败回退 + editPolishPrompt 强化

**Files:**
- Modify: `.claude/workflows/bedrock-chapter.js`(Polish 段 line 75-87 + `editPolishPrompt`)

- [ ] **Step 1: Polish 段改为"失败回退 pre-Polish 版"**

定位当前 Polish 段(`phase('Polish')` 块,line 75-87):
```js
phase('Polish')
if (report.passed_hard_gate && ctx.fingerprint) {
  prose = extractProse(await agent(editPolishPrompt(ctx, prose), { label: 'Edit-polish', phase: 'Polish' }))
  report = await commitAndL2(project, chapter, prose, 'polish')
  _trackDrift(report)
  if (!report.passed_hard_gate) {
    await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`, { phase: 'Polish' })
    log('polish introduced beat violation, flagged')
  }
} else {
  log('polish skipped (no fingerprint or L2 not passed)')
}
```
替换为(回退到 pre-Polish,失败路径 +1 commit relay):
```js
phase('Polish')
if (report.passed_hard_gate && ctx.fingerprint) {
  const preProse = prose, preReport = report   // 阶段前 L2-pass 快照(含 Repair 扩写的 ≥3000 字)
  const polished = extractProse(await agent(editPolishPrompt(ctx, preProse), { label: 'Edit-polish', phase: 'Polish' }))
  const after = await commitAndL2(project, chapter, polished, 'polish')
  _trackDrift(after)
  if (after.passed_hard_gate) {
    prose = polished; report = after
    log('polish ok')
  } else {
    // Polish 破坏 L2(beat/word_count)→ 回退 pre-Polish(已过 L2)。+1 relay 重 commit;0 新 agent。
    await commitAndL2(project, chapter, preProse, 'polish-revert')
    prose = preProse; report = preReport
    await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`, { phase: 'Polish' })
    log('polish 破坏 L2 → 回退 pre-Polish 版(风格该轮未应用,正确性优先)')
  }
} else {
  log('polish skipped (no fingerprint or L2 not passed)')
}
```

- [ ] **Step 2: editPolishPrompt 强化预防约束**

定位 `function editPolishPrompt(ctx, prevProse)`,把行 `'保持剧情与字数,不增删段落。',` 替换为:
```js
    '保持剧情、beat 结构完整、汉字数不低于下限;不删段、不合并/拆分 beat、不降字数。仅做风格微调(句式/对白/破折号/修辞密度对准目标分布)。',
```
(其余行不动。此为预防,降低破坏频率;回退是主保障。)

- [ ] **Step 3: 静态确认**

Run:
```bash
grep -n "preProse\|polish-revert\|回退 pre-Polish" .claude/workflows/bedrock-chapter.js
grep -n "不删段、不合并" .claude/workflows/bedrock-chapter.js
```
Expected: Polish 段含 preProse 快照 + 回退分支;editPolishPrompt 含强化约束。JS 沙箱无 node,靠 grep + 目检(大括号/模板字面量平衡,未扰动 extractProse/commitAndL2)。

- [ ] **Step 4: Commit**

```bash
git add .claude/workflows/bedrock-chapter.js
git commit -m "fix(bedrock): Polish 破坏 L2 回退 pre-Polish 版 + prompt 强化(0 新 agent)"
```
End with:
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

---

## Task 3: Consistency 段失败回退

**Files:**
- Modify: `.claude/workflows/bedrock-chapter.js`(Consistency 段 line 91-110)

- [ ] **Step 1: Consistency 段改为"ops 破 L2 时回退"**

当前 Consistency 段(line 91-110)在 ops 破 L2 时 `report = after`(保留破损态)。`prose` 变量此时是 post-Polish、pre-Consistency 的全文(L2-pass)。改为破 L2 时回退(重 commit `prose`)。

定位块内:
```js
  if (ops && ops.length) {
    const after = await applyOpsAndL2(project, chapter, ops, 'consistency')
    _trackDrift(after)
    if (!after.passed_hard_gate) {
      await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`, { phase: 'Consistency' })
      log(`consistency broke beat (${ops.length} ops) → flagged`)
      report = after
    } else {
      log(`consistency: ${ops.length} ops applied (代词/设定一致)`)
      report = after
    }
  } else {
    log('consistency: 无需改动')
  }
```
替换为:
```js
  if (ops && ops.length) {
    const preConsistencyProse = prose   // post-Polish 全文,Consistency ops 只动 DB 不动此串
    const after = await applyOpsAndL2(project, chapter, ops, 'consistency')
    _trackDrift(after)
    if (after.passed_hard_gate) {
      log(`consistency: ${ops.length} ops applied (代词/设定一致)`)
      report = after
    } else {
      // ops 破 L2 → 回退 pre-Consistency(重 commit prose)。+1 relay;0 新 agent。
      await commitAndL2(project, chapter, preConsistencyProse, 'consistency-revert')
      await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`, { phase: 'Consistency' })
      log(`consistency ops 破坏 L2 → 回退 pre-Consistency 版(${ops.length} ops 丢弃)`)
      // report 保持 pre-Consistency(仍 passed),不取 after
    }
  } else {
    log('consistency: 无需改动')
  }
```
> 注:`report` 在破 L2 分支不更新(保持 pre-Consistency 的 passed 状态);`prose` 不变(本就是 pre-Consistency)。回退后 DB 与 `prose` 一致。

- [ ] **Step 2: 静态确认**

Run: `grep -n "consistency-revert\|回退 pre-Consistency" .claude/workflows/bedrock-chapter.js`
Expected: Consistency 段含回退分支。

- [ ] **Step 3: Commit**

```bash
git add .claude/workflows/bedrock-chapter.js
git commit -m "fix(bedrock): Consistency ops 破 L2 回退 pre-Consistency 版(0 新 agent)"
```
End with:
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

---

## Task 4: 端到端回归 — vigilia ch13 自愈

**Files:** 无新文件;运行验证

- [ ] **Step 1: 全 bedrock 套回归**

Run: `python -m pytest tests/bedrock/ -q`
Expected: 全 PASS(此前 316 + Task1 新 3;若 Task1 Step5 适配了既有测试,总数应稳定)。报告计数。

- [ ] **Step 2: ch13 重跑(Polish 破坏 → 回退 → L2-clean + completed)**

ch13 当前破损(polish_broke_beat=1 + word_count_below_floor + 2946字)。重跑工作流:
```
Workflow({ scriptPath: ".claude/workflows/bedrock-chapter.js",
           args: { project:"projects/vigilia", chapter:13, volume:2 } })
```
Expected(完成后核对):
- `python -m src.bedrock run-l2 --project projects/vigilia --chapter 13` → `passed_hard_gate=true`、无 `word_count_below_floor`、汉字 ≥3000。
- `status=completed`(verify 现要求 L2,通过才 completed)。
- 若该轮 Polish 又削破 → 日志见"polish 破坏 L2 → 回退 pre-Polish 版",终态仍 L2-clean。**全程未新增 repair agent**(Polish 1 agent + 失败时 1 回退 relay)。

- [ ] **Step 3: (确认 agent 数未增)核对 ch13 run 的 agent_count**

从 Workflow 完成通知的 usage 看 `agent_count`——应与普通章相当(约 11-16),**不应因本修复显著上升**(回退是 relay 不是新 agent)。

- [ ] **Step 4: Commit(若有测试调整)**

```bash
git add tests/bedrock/
git commit -m "test(bedrock): 适配 verify-persisted L2 要求的既有 fixture" --allow-empty
```
End with:
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

---

## Self-Review

**Spec 覆盖:**
- Polish/Consistency 破坏 L2 → 回退(agent-free)→ Task 2(Polish)+ Task 3(Consistency)✓
- Polish prompt 预防约束 → Task 2 Step 2 ✓
- verify_chapter_persisted 要求 L2 → Task 1 ✓
- 测试 + ch13 回归 → Task 1(tests)+ Task 4 ✓
- 硬约束"不增常态 agent" → 全部回退为 +1 relay(失败路径),常态 0 新 agent ✓

**类型/签名一致:** `verify_chapter_persisted(conn, chapter_id, export_path=None)→bool`、`run_l2(conn, chapter_id).passed_hard_gate`、`commitAndL2(project, chapter, prose, label)`、`applyOpsAndL2(project, chapter, ops, label)`、`editPolishPrompt(ctx, prevProse)` —— 各 Task 引用与实测吻合。

**需 impl 核实:** Task 1 Step 5——`test_status_lifecycle.py::test_verify_sets_completed` 若用短正文 fixture,新 L2 要求会使 verify False,需补长正文至 ≥3000 汉字(最小适配)。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-20-polish-repair-and-completed-l2-clean.md`. **建议分支 `bedrock-polish-repair`**。两种执行方式:

1. **Subagent-Driven(推荐)** — 每 Task 派新 subagent + 两阶段 review
2. **Inline Execution** — 本会话批量执行带 checkpoint

选哪种?
