# 字数下限硬门禁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让字数下限成为 L2 硬门禁,欠产章在写作管线内被拦截并由 Repair 扩写达标。

**Architecture:** 在 `run_l2` 复用已算的 `wc` + 现有 `word_count_target` 源,追加 `word_count_below_floor` 违规(进既有 Repair 循环,自动 `passed=False`);`editRepairPrompt` 检测到该违规时切换为"扩写+防灌水"指令;writer prompt 加自检。

**Tech Stack:** Python 3 + sqlite3 + pytest(`src/bedrock/`);Node 沙箱工作流(`.claude/workflows/bedrock-chapter.js`);模板(`.claude/templates/bedrock/`)。

**Spec:** `docs/superpowers/specs/2026-06-20-word-count-floor-enforcement-design.md`

**实施:** 分支 `bedrock-wordcount`。测试运行 `python -m pytest tests/bedrock/ -v`(从 D:/novel_test,勿用裸 pytest)。

---

## File Structure

**修改:**
- `src/bedrock/orchestration/l2_pipeline.py` — `run_l2` 末尾追加 `word_count_below_floor` 违规(主)。
- `.claude/workflows/bedrock-chapter.js` — `editRepairPrompt` 条件扩写 + 防灌水。
- `.claude/templates/bedrock/chapter_writer.md` — 字数自检提示。

**新建:**
- `tests/bedrock/test_l2_word_count.py` — L2 字数门禁单元测试。

---

## Task 1: L2 `word_count_below_floor` 硬违规

**Files:**
- Modify: `src/bedrock/orchestration/l2_pipeline.py`(顶部 import + `run_l2` 末尾)
- Test: `tests/bedrock/test_l2_word_count.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_l2_word_count.py
"""L2 字数下限硬门禁:实测汉字数 < word_count_target[0] → word_count_below_floor 违规。"""
import sqlite3
import pytest
from src.bedrock.orchestration.l2_pipeline import run_l2


@pytest.fixture
def seeded(tmp_path):
    """建临时 bedrock 项目:1 卷 1 章 1 beat(written)+ style_template(word_count_target=[3000,5000])。
    复用 tests/bedrock 既有建模模式(init + create_volume/chapter/beat + volume_outline)。"""
    from src.bedrock.db.connection import get_connection
    from src.bedrock.init_project import init_project
    from src.bedrock.repositories.plot_tree import (
        create_volume, create_chapter, create_beat, create_paragraph, mark_beats_written)
    proj = tmp_path / "p"
    init_project(proj, name="t", force=True)
    conn = get_connection(proj)
    vid = create_volume(conn, 1, "v", 1, 1, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t", status="writing")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="测试 beat 目的足够长十个字", pov_character_id=None)
    # volume_outline(boot/run-l2 经 get_beat_contract 需要)
    import json
    conn.execute("INSERT OR REPLACE INTO volume_outline(volume_id,status,beat_contracts) VALUES(?,'drafted',?)",
                 (vid, json.dumps([{"beat_id": bid, "purpose": "测试 beat 目的足够长十个字"}])))
    # style_template:word_count_target=[3000,5000](work scope)
    conn.execute("INSERT OR REPLACE INTO style_template(scope,volume_id,fingerprint,word_count_target) "
                 "VALUES('work',NULL,'{}','[3000, 5000]')")
    conn.commit()
    return conn, cid, bid


def _set_prose(conn, cid, bid, text):
    from src.bedrock.repositories.plot_tree import create_paragraph, mark_beats_written
    conn.execute("DELETE FROM paragraph WHERE chapter_id=?", (cid,))
    create_paragraph(conn, cid, 1, text, "h", bid, "narration")
    mark_beats_written(conn, [bid])
    conn.commit()


def test_below_floor_flags(seeded):
    conn, cid, bid = seeded
    _set_prose(conn, cid, bid, "短正文。" * 50)   # ~200 汉字 < 3000
    rep = run_l2(conn, cid)
    kinds = [v.kind for v in rep.beat_violations]
    assert "word_count_below_floor" in kinds
    assert rep.passed_hard_gate is False


def test_at_floor_does_not_flag(seeded):
    conn, cid, bid = seeded
    _set_prose(conn, cid, bid, "正文内容。" * 400)  # ~1600 汉字? 需 ≥3000 → 用更长
    # 确保 ≥3000 汉字:每句 4 汉字,*800 = 3200
    _set_prose(conn, cid, bid, "正文内容在此。" * 800)
    rep = run_l2(conn, cid)
    kinds = [v.kind for v in rep.beat_violations]
    assert "word_count_below_floor" not in kinds


def test_empty_draft_not_flagged(seeded):
    """空稿(wc==0)由 unwritten_beat 兜,不重复报 word_count_below_floor。"""
    conn, cid, bid = seeded
    # 不写任何段落 → wc=0
    conn.execute("DELETE FROM paragraph WHERE chapter_id=?", (cid,))
    # beat 仍 planned(未 mark written)→ unwritten_beat 报,word_count 不报
    conn.commit()
    rep = run_l2(conn, cid)
    kinds = [v.kind for v in rep.beat_violations]
    assert "word_count_below_floor" not in kinds
    assert "unwritten_beat" in kinds


def test_default_floor_when_no_style_config(tmp_path):
    """无 style_template 行 → 兜底 floor=3000。"""
    from src.bedrock.db.connection import get_connection
    from src.bedrock.init_project import init_project
    from src.bedrock.repositories.plot_tree import (
        create_volume, create_chapter, create_beat, create_paragraph, mark_beats_written)
    import json
    proj = tmp_path / "p2"
    init_project(proj, name="t", force=True)
    conn = get_connection(proj)
    vid = create_volume(conn, 1, "v", 1, 1, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t", status="writing")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="测试 beat 目的足够长十个字", pov_character_id=None)
    conn.execute("INSERT OR REPLACE INTO volume_outline(volume_id,status,beat_contracts) VALUES(?,'drafted',?)",
                 (vid, json.dumps([{"beat_id": bid, "purpose": "测试 beat 目的足够长十个字"}])))
    create_paragraph(conn, cid, 1, "短。" * 100, "h", bid, "narration")  # ~100 汉字
    mark_beats_written(conn, [bid])
    # 不插 style_template → 兜底
    conn.commit()
    rep = run_l2(conn, cid)
    kinds = [v.kind for v in rep.beat_violations]
    assert "word_count_below_floor" in kinds   # 兜底 3000,100<3000
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/bedrock/test_l2_word_count.py -v`
Expected: FAIL(无 word_count_below_floor 规则,违规清单不含它)

- [ ] **Step 3: 实现**

在 `src/bedrock/orchestration/l2_pipeline.py` 顶部 import 区加:
```python
from src.bedrock.checks.beat_fulfillment import BeatViolation
from src.bedrock.style.template_repo import get_style_config
```
在 `run_l2` 函数内,**line 82 之后**(`beat_yield` 计算后)、**`metrics = {...}` 之前**或紧接其后(只要在 `return L2Report(...)` 之前、`wc` 与 `beat_violations` 已定义)插入:
```python
    # 字数下限硬门禁:实测汉字数 < word_count_target[0] → 违规(进 Repair 循环)。
    # 空稿(wc==0)由 unwritten_beat 兜,不重复报。无 style config → 兜底 3000。
    _DEFAULT_FLOOR = 3000
    _floor = _DEFAULT_FLOOR
    if volume_id is not None:
        try:
            _wct = get_style_config(conn, volume_id).get("word_count_target")
            if _wct:
                _floor = int(_wct[0])
        except Exception:
            pass
    if 0 < wc < _floor:
        beat_violations.append(BeatViolation(
            beat_id=beat_violations[0].beat_id if beat_violations else 0,
            kind="word_count_below_floor",
            detail=f"实测 {wc} 汉字 < 下限 {_floor} 汉字",
            fix_hint=f"扩写至 {_floor} 汉字以上:增场景细节/感官/心理/对白展开;禁灌水/重复/注水"))
```
> 注意:`passed_hard_gate=(len(beat_violations)==0)`(line 109)自动失效——追加后即 False。若你把插入点放在 line 109 之后会无效,**必须在 return 之前**。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/bedrock/test_l2_word_count.py -v`
Expected: PASS(4/4)。若 `test_at_floor_does_not_flag` 因字数没到 3000 失败,调整该测试的正文长度确保 ≥3000 汉字(实测 `compute_word_count` 只数汉字,标点不计)。

- [ ] **Step 5: 回归既有 L2 测试**

Run: `python -m pytest tests/bedrock/test_beat_fulfillment.py tests/bedrock/test_l2_word_count.py -q`
Expected: 全 PASS(既有 beat 测试的 fixture 若用了 <3000 字短正文,现在会多出 word_count_below_floor——若既有断言精确数违规数,需在那些测试的正文补长到 ≥3000 或断言改用 kind 集合;以实际为准,改最小)。

- [ ] **Step 6: Commit**

```bash
git add src/bedrock/orchestration/l2_pipeline.py tests/bedrock/test_l2_word_count.py
git commit -m "feat(bedrock): L2 字数下限硬门禁 word_count_below_floor"
```
End commit message with:
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

---

## Task 2: `editRepairPrompt` 条件扩写 + 防灌水

**Files:**
- Modify: `.claude/workflows/bedrock-chapter.js`(`editRepairPrompt` 函数)

- [ ] **Step 1: 改 editRepairPrompt**

定位 `function editRepairPrompt(report, prevProse)`(全文当前内容):
```js
function editRepairPrompt(report, prevProse) {
  const lines = ['# Edit 子代理 — 定向修复', '违规清单（beat_id / kind / detail / fix_hint）：']
  for (const v of (report.beat_violations || [])) {
    lines.push(`  - beat${v.beat_id} [${v.kind}]: ${v.detail} → ${v.fix_hint}`)
  }
  lines.push('', '下面是上一版整章正文。只改与违规相关段落，不引入新违规，不压缩剧情，保持其余原文。',
             '返回修订后的【整章正文】纯文本，不裹围栏。', '', '---上一版---', prevProse)
  return lines.join('\n')
}
```
替换为(检测 word_count_below_floor → 切扩写指令 + 防灌水):
```js
function editRepairPrompt(report, prevProse) {
  const lines = ['# Edit 子代理 — 定向修复', '违规清单（beat_id / kind / detail / fix_hint）：']
  for (const v of (report.beat_violations || [])) {
    lines.push(`  - beat${v.beat_id} [${v.kind}]: ${v.detail} → ${v.fix_hint}`)
  }
  const needExpand = (report.beat_violations || []).some(v => v.kind === 'word_count_below_floor')
  const rule = needExpand
    ? '本章字数不足(见 word_count_below_floor)。须【扩写】至下限以上:在现有剧情骨架上增场景细节/感官/心理/对白展开,丰富而非重复。不引入新违规,不压缩剧情。'
    : '下面是上一版整章正文。只改与违规相关段落,不引入新违规,不压缩剧情,保持其余原文。'
  lines.push('', rule)
  if (needExpand) {
    lines.push('【禁灌水】不得无信息扩写、不得重复同一意思、不得堆砌形容词、不得注水对话。扩写须服务于人物/氛围/情节推进;扩写后仍须过文风门禁(修辞密度/对白比/破折号)。')
  }
  lines.push('返回修订后的【整章正文】纯文本(段间空行),不裹围栏,不写标题行。', '', '---上一版---', prevProse)
  return lines.join('\n')
}
```

- [ ] **Step 2: 静态确认**

Run: `grep -n "needExpand\|word_count_below_floor" .claude/workflows/bedrock-chapter.js`
Expected: 显示 editRepairPrompt 内的 needExpand 检测 + anti-灌水行。
JS 沙箱无 node,不能执行;靠 grep + 目检。确认函数内 ` ```prose ` 围栏契约未被破坏(Task 3 早先改的 extractProse 仍正常——本 Task 只动 editRepairPrompt 文本)。

- [ ] **Step 3: Commit**

```bash
git add .claude/workflows/bedrock-chapter.js
git commit -m "feat(bedrock): editRepairPrompt 条件扩写+防灌水(word_count_below_floor)"
```
End with:
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

---

## Task 3: Writer prompt 字数自检

**Files:**
- Modify: `.claude/templates/bedrock/chapter_writer.md`(第 15 行)

- [ ] **Step 1: 强化字数要求**

定位第 15 行:`4. 字数 3000-5000 汉字`(或 Task3 早先后可能已改写;定位含"字数"的编号项)。替换为:
```markdown
4. 字数 3000-5000 汉字(**交稿前自检汉字数 ≥ 3000——系统 L2 硬卡,不足会被打回扩写**)
```
若该行已被先前改动包裹,确保保留既有 ```prose 围栏输出契约,仅改字数这一条。

- [ ] **Step 2: 验证未破坏围栏契约**

Run: `python -m src.bedrock boot-context --project projects/vigilia --chapter 1 --volume 1 | python -c "import sys,json;d=json.load(sys.stdin);print('constants wc:',d['constants']['word_count_target'])"`
Expected: 正常输出 constants(模板改动不影响 boot-context 数据流)。

- [ ] **Step 3: Commit**

```bash
git add .claude/templates/bedrock/chapter_writer.md
git commit -m "feat(bedrock): chapter_writer 字数自检提示(L2 硬卡)"
```
End with:
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

---

## Task 4: 端到端回归 — vigilia ch6(1714 字)被卡并扩写

**Files:** 无新文件;运行验证

- [ ] **Step 1: 确认 ch6 当前字数 < 3000(应被新门禁拦)**

Run:
```bash
python -m src.bedrock run-l2 --project projects/vigilia --chapter 6
```
Expected: 输出 JSON 的 `beat_violations` 含 `{"kind":"word_count_below_floor",...}`,`passed_hard_gate=false`(ch6 1714 字 < 3000)。证明新门禁对既有短章生效。

- [ ] **Step 2: 全 bedrock 测试套回归**

Run: `python -m pytest tests/bedrock/ -q`
Expected: 全 PASS(此前 ~312)。若既有测试因新增 word_count_below_floor 而失败(用了短正文 fixture),按 Task 1 Step 5 同样原则修正(补长正文或断言用 kind 集合)。报告最终计数。

- [ ] **Step 3: (可选,重)用修好的管线重写 ch6 验证扩写闭环**

> 这一步会覆盖 ch6 正文(已 completed)。若不想动既有稿,跳过本步,仅以 Step 1 证明门禁生效即可。
若执行:
```bash
# 用 bedrock-chapter-edit rewrite 重写 ch6 → 触发 L2 → Repair 扩写至 ≥3000
python -m src.bedrock commit-paragraphs --project projects/vigilia --chapter 6 < /dev/null  # 占位,实际走工作流
```
推荐走工作流:
```
Workflow({ scriptPath: ".claude/workflows/bedrock-chapter.js",
           args: { project:"projects/vigilia", chapter:6, volume:1 } })
```
Expected: L2 首检 word_count_below_floor → Repair 扩写 → 终态 `run-l2` 全绿且汉字数 ≥3000。验证 `passed_hard_gate=true`、字数回升。

- [ ] **Step 4: Commit(若有测试调整)**

```bash
git add tests/bedrock/
git commit -m "test(bedrock): 适配 word_count_below_floor 的既有 fixture" --allow-empty
```
End with:
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

---

## Self-Review

**Spec 覆盖:**
- L2 `word_count_below_floor` 硬违规(落 run_l2,复用 wc + style config,空稿不报,兜底 3000)→ Task 1 ✓
- editRepairPrompt 条件扩写 + 防灌水三重(prompt/style门禁/L2重检)→ Task 2 ✓
- writer prompt 自检 → Task 3 ✓
- 测试 + vigilia ch6 回归 → Task 1(tests) + Task 4 ✓
- 只卡下限不卡上限 / floor 源用现有 word_count_target / mark-unresolved 既有路径 → 设计内置,无需额外 Task ✓

**类型/签名一致:** `BeatViolation(beat_id, kind, detail, fix_hint)`、`get_style_config(conn, volume_id)["word_count_target"]` → `[low, high]`、`run_l2(conn, chapter_id)` 返 `L2Report.beat_violations`、`passed_hard_gate=(len(beat_violations)==0)` —— 各 Task 引用一致,与 l2_pipeline.py 实测作用域吻合。

**需 impl 核实:** Task 1 Step 5——既有 beat_fulfillment 测试若用短正文 fixture,新增违规可能撑破精确断言;以最小改动适配(补长正文 or kind 集合断言)。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-20-word-count-floor-enforcement.md`. **建议分支 `bedrock-wordcount`**。两种执行方式:

1. **Subagent-Driven(推荐)** — 每 Task 派新 subagent + 两阶段 review
2. **Inline Execution** — 本会话批量执行带 checkpoint

选哪种?
