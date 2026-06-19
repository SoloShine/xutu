# Bedrock V3 管线鲁棒性修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 vigilia 卷一测试暴露的 7 个系统级设计缺陷,让单章管线前置确定性校验、导出/watchdog/状态行为正确。

**Architecture:** 契约优先(定界提取压过正则检测)+ 三层纵深防污染 + 确定性校验前置到单章(专名/状态)+ watchdog 修 bug 与语义。所有新逻辑零 LLM、可单测。

**Tech Stack:** Python 3 + sqlite3 + pytest(后端 `src/bedrock/`);Node 沙箱工作流(`.claude/workflows/bedrock-chapter.js`);Jinja 模板(`.claude/templates/bedrock/`)。

**Spec:** `docs/superpowers/specs/2026-06-19-bedrock-pipeline-robustness-fixes-design.md`

**测试运行:** `pytest tests/bedrock/ -v`(pytest.ini 在仓库根)。CLI 调试:`cd D:/novel_test && python -m src.bedrock <cmd>`。

**实施建议:** 在独立 worktree/分支进行(如 `bedrock-robustness`),因改动跨信任锚区。每 Task 一个 commit。

---

## File Structure

**新建:**
- `src/bedrock/checks/prose_hygiene.py` — 元文本检测与清洗(确定性)。A1。
- `src/bedrock/checks/proper_nouns.py` — 专名白名单 + 形近变体分层检测(确定性)。D。
- `tests/bedrock/test_prose_hygiene.py` — A1 测试。
- `tests/bedrock/test_extract_prose.py` — A0 提取降级链测试(workflow 逻辑的纯 JS 可拆出测,见 Task 3)。
- `tests/bedrock/test_proper_nouns.py` — D 测试。
- `tests/bedrock/test_status_lifecycle.py` — B 测试。
- `tests/bedrock/test_watchdog_drift.py` — C 测试。

**修改:**
- `src/bedrock/checks/beat_fulfillment.py` — 加 `non_prose` 规则(A2)。
- `src/bedrock/__main__.py` — commit-paragraphs sanitize 防御(A1)、verify-persisted→completed + reopen(B)、ensure_flag 保底(A3)、新 CLI `mark-completed`/`check-proper-nouns`(B/D)、edit-paragraphs reopen(B)。
- `src/bedrock/orchestration/watchdog.py` — drift 计数 bug + bound + 同向门控(C)。
- `src/bedrock/orchestration/boot_context.py` — 注入 `inspirations` key(F)。
- `src/bedrock/repositories/outline.py` — `consume_inspiration` 补 return(F)。
- `src/bedrock/style/extractor.py` + `template_repo.py` — 维度 bound 元数据(C)。
- `.claude/workflows/bedrock-chapter.js` — `stripFences`→`extractProse`(A0)、Consistency 阶段挂 `check-proper-nouns`(D)。
- `.claude/templates/bedrock/chapter_writer.md` + `edit_agent.md` — prose 围栏契约 + 边界例(A0/E)。

---

## Task 1: prose_hygiene 元文本检测与清洗(Unit A1)

**Files:**
- Create: `src/bedrock/checks/prose_hygiene.py`
- Test: `tests/bedrock/test_prose_hygiene.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_prose_hygiene.py
from src.bedrock.checks.prose_hygiene import is_meta_paragraph, sanitize_prose

def test_detects_metric_self_report():
    assert is_meta_paragraph("草案现在符合指标要求：0个破折号，对话占比 35.7%")

def test_detects_polish_narration():
    assert is_meta_paragraph("润色版本已完成，剔除了所有“不是A是B”句式，删除了非必要的破折号。")

def test_detects_file_path():
    assert is_meta_paragraph("D:\\novel_test\\projects\\vigilia\\bedrock.db (truth source")
    assert is_meta_paragraph("导出路径 C:/x/y.db")

def test_detects_separator_only():
    assert is_meta_paragraph("---")
    assert is_meta_paragraph("***")

def test_does_not_flag_real_prose():
    assert not is_meta_paragraph("林昭把第十六个小时的工牌翻了过去。")
    assert not is_meta_paragraph("“准点。”她说，“您的窗口还有四十七分钟。”")

def test_sanitize_strips_leading_trailing_mid_meta_keeps_prose():
    raw = ("草案符合指标：0破折号。\n\n"
           "天没亮，林昭就醒了。\n\n"
           "她照了照镜子。\n\n"
           "D:\\novel_test\\projects\\vigilia\\bedrock.db")
    cleaned, removed, preview = sanitize_prose(raw)
    assert "天没亮" in cleaned and "照了照镜子" in cleaned
    assert "草案符合指标" not in cleaned and "bedrock.db" not in cleaned
    assert removed == 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/bedrock/test_prose_hygiene.py -v`
Expected: FAIL(模块不存在,ImportError)

- [ ] **Step 3: 实现 prose_hygiene.py**

```python
# src/bedrock/checks/prose_hygiene.py
"""正文卫生:检测并剥离 agent 泄入 paragraph 的元文本(指标自评/润色汇报/路径/分隔符)。
确定性,零 LLM。Unit A1 —— A0 定界提取的兜底,commit-paragraphs 与 L2 non_prose 共用。"""
import re

# 实测泄漏签名(vigilia ch2/3/6/8/10 + ch12 分隔符)
_META_PATTERNS = [
    re.compile(r"指标|破折号|对话占比|修辞.{0,3}密度|明喻.{0,4}像|检查破折号"),
    re.compile(r"草案.{0,6}符合|润色版本|符合.{0,4}要求|唯一的顾虑|我(删除|修改|调整)"),
    re.compile(r"[A-Za-z]:[\\/]|projects/[^ ]*\.db|\.db\b"),
    re.compile(r"^(-{3,}|\*{3,}|\* \* \*|—{2,})$"),          # 纯分隔符段
    re.compile(r"^```|```$"),                                  # 围栏残留
]

MIN_PROSE_CHARS = 500  # 清洗后正文下限(与 spec 阈值一致)


def is_meta_paragraph(text: str) -> bool:
    """单段是否为元文本(非正文)。空段视为 meta(将被剥除)。"""
    t = (text or "").strip()
    if not t:
        return True
    return any(p.search(t) for p in _META_PATTERNS)


def sanitize_prose(raw: str):
    """剥离所有 meta 段(leading/trailing/mid),返回 (cleaned, removed_count, preview)。
    preview = 移除段前 3 段截断,供日志。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", raw.strip()) if p.strip()]
    kept = [p for p in paras if not is_meta_paragraph(p)]
    removed = len(paras) - len(kept)
    preview = [p[:40] for p in paras if is_meta_paragraph(p)][:3]
    cleaned = "\n\n".join(kept)
    return cleaned, removed, preview
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/bedrock/test_prose_hygiene.py -v`
Expected: PASS(6/6)

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/checks/prose_hygiene.py tests/bedrock/test_prose_hygiene.py
git commit -m "feat(bedrock): prose_hygiene 元文本检测与清洗(Unit A1 兜底层)"
```

---

## Task 2: L2 non_prose 规则(Unit A2)

**Files:**
- Modify: `src/bedrock/checks/beat_fulfillment.py`
- Test: `tests/bedrock/test_beat_fulfillment.py`(追加)

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/bedrock/test_beat_fulfillment.py
from src.bedrock.checks.beat_fulfillment import check_beat_fulfillment

def test_non_prose_violation_for_meta_paragraph(db_chapter_with_one_beat):
    # fixture:一章一 beat(written),挂一段 meta 文本
    conn, chapter_id, beat_id = db_chapter_with_one_beat
    conn.execute("INSERT INTO paragraph(chapter_id,seq,beat_id,text,content_hash,role) "
                 "VALUES(?,?,?,?,'h','narration')",
                 (chapter_id, 1, beat_id, "润色版本已完成，剔除了所有破折号。"))
    conn.commit()
    violations = check_beat_fulfillment(conn, chapter_id)
    kinds = [v.kind for v in violations]
    assert "non_prose" in kinds
```

> 注:`db_chapter_with_one_beat` 若不存在,在 `tests/bedrock/conftest.py` 或本文件加一个建临时 db+volume+chapter+beat(written)的 fixture。参考既有 `test_beat_fulfillment.py` 里已有的 fixture 模式复用。

- [ ] **Step 2: 跑确认失败**

Run: `pytest tests/bedrock/test_beat_fulfillment.py::test_non_prose_violation_for_meta_paragraph -v`
Expected: FAIL(无 non_prose 规则)

- [ ] **Step 3: 在 check_beat_fulfillment 末尾加 non_prose 扫描**

在 `src/bedrock/checks/beat_fulfillment.py` 顶部加 import:
```python
from src.bedrock.checks.prose_hygiene import is_meta_paragraph
```

在 `check_beat_fulfillment` 函数 `return violations` 之前(或循环之后)加:
```python
    # 规则 non_prose:任何已入库段命中元文本 → 违规(A2 第三层兜底)
    for p in paragraphs:
        if is_meta_paragraph(p["text"]):
            violations.append(BeatViolation(
                beat_id=p["beat_id"] or (beats[0]["id"] if beats else 0),
                kind="non_prose",
                detail=f"段落 seq={p['seq']} 疑似 agent 元文本/工作日志:{p['text'][:30]}",
                fix_hint="删除该 meta 段,仅保留正文"))
```

- [ ] **Step 4: 跑确认通过**

Run: `pytest tests/bedrock/test_beat_fulfillment.py -v`
Expected: PASS(含新测试 + 既有不破)

- [ ] **Step 5: Commit**

```bash
git add src/bedrock/checks/beat_fulfillment.py tests/bedrock/test_beat_fulfillment.py
git commit -m "feat(bedrock): L2 新增 non_prose 规则(Unit A2 第三层兜底)"
```

---

## Task 3: 工作流 extractProse 提取降级链 + prompt 围栏契约(Unit A0)

**Files:**
- Modify: `.claude/workflows/bedrock-chapter.js`(替换 `stripFences`)
- Modify: `.claude/templates/bedrock/chapter_writer.md`、`edit_agent.md`
- Test: 纯函数抽到 Python 测(见下)

> 说明:工作流是 Node 沙箱,难直接单测。把 `extractProse` 的**降级判定**抽成一个可测的纯函数放进 Python(因 sanitize 已在 Python),JS 侧只做"取 prose 围栏区 + 调 Python sanitize 回退"。这里测 Python 侧的围栏提取。

- [ ] **Step 1: 写失败测试(围栏提取)**

```python
# tests/bedrock/test_extract_prose.py
from src.bedrock.checks.prose_hygiene import extract_prose_block

def test_extract_tagged_prose_block_ignores_outside():
    raw = "我先想了一下。\n```prose\n天没亮，林昭就醒了。\n```\n指标：0破折号。"
    assert extract_prose_block(raw) == "天没亮，林昭就醒了。"

def test_multiple_blocks_take_longest():
    raw = "```prose\n短。\n```\n```prose\n这是更长的正文段落。\n```"
    assert extract_prose_block(raw) == "这是更长的正文段落。"

def test_plain_fence_not_counted():
    # 普通三反引号围栏不算,返回 None(触发回退)
    assert extract_prose_block("```\n天没亮。\n```") is None

def test_no_block_returns_none():
    assert extract_prose_block("天没亮，林昭就醒了。") is None
```

- [ ] **Step 2: 跑确认失败**

Run: `pytest tests/bedrock/test_extract_prose.py -v`
Expected: FAIL(无 extract_prose_block)

- [ ] **Step 3: 在 prose_hygiene.py 加 extract_prose_block**

```python
# 追加到 src/bedrock/checks/prose_hygiene.py
_PROSE_BLOCK = re.compile(r"```prose[ \t]*\n(.*?)\n```", re.DOTALL)

def extract_prose_block(raw: str):
    """提取 ```prose 标签围栏区内容。多个取最长;无标签区返回 None(由调用方回退 sanitize)。"""
    matches = _PROSE_BLOCK.findall(raw or "")
    if not matches:
        return None
    return max(matches, key=len).strip()
```

- [ ] **Step 4: 跑确认通过**

Run: `pytest tests/bedrock/test_extract_prose.py -v`
Expected: PASS(4/4)

- [ ] **Step 5: 工作流替换 stripFences → extractProse(JS)**

在 `.claude/workflows/bedrock-chapter.js` 把:
```js
function stripFences(s) {
  if (typeof s !== 'string') return String(s ?? '')
  let t = s.trim()
  const m = t.match(/^```[a-zA-Z]*\n([\s\S]*?)\n```$/)
  if (m) t = m[1]
  return t.trim()
}
```
替换为:
```js
// Unit A0:正文定界提取。只认 ```prose 标签区;无则回退 prose_hygiene 清洗(JS 端做轻量回退,
// 重度清洗/拒绝由 commit-paragraphs 的 sanitize 防线 + L2 non_prose 兜底)。
function extractProse(s) {
  if (typeof s !== 'string') return String(s ?? '')
  const blocks = [...s.matchAll(/```prose[ \t]*\n([\s\S]*?)\n```/g)].map(m => m[1].trim())
  if (blocks.length) return blocks.sort((a, b) => b.length - a.length)[0]
  return s.trim()  // 无标签区:原样返回,交 commit 段 sanitize 防线 + L2 兜底
}
```
并把全文件 `stripFences(` 调用点(共约 9 处:Write/Repair/Polish/Consistency/style-polish/各 relay)替换为 `extractProse(`。**注意**:`commitAndL2` 里喂 `commit-paragraphs` 的 `prose` 变量必须经过 `extractProse`(已是,因 `prose = extractProse(await agent(...))`)。

- [ ] **Step 6: prompt 模板加围栏契约**

`chapter_writer.md` 第 18-20 行「输出」节改为:
```markdown
## 输出
把本章正文包进带标签围栏 ```prose，系统只入库围栏内文本：

```prose
<本章正文，逐 beat 段落>
```

**围栏外任何文本都会被丢弃**——不要写前言、指标点评、思考过程、文件路径、工作日志。
不要自报字数（系统重算 authoritative，偏差>10% 被 drift 标记）。
```
对 `edit_agent.md` 做同样「只输出 ```prose 围栏内正文」的契约补充(Polish/Repair/style-polish 共用)。

- [ ] **Step 7: 手测工作流装配(可选,正式回归在 Task 10)**

Run: `python -m src.bedrock boot-context --project projects/vigilia --chapter 1 --volume 1 | head`
Expected: 正常输出(未改 boot,仅确认未破坏)。JS 改动在 Task 10 端到端回归验证。

- [ ] **Step 8: Commit**

```bash
git add src/bedrock/checks/prose_hygiene.py tests/bedrock/test_extract_prose.py .claude/workflows/bedrock-chapter.js .claude/templates/bedrock/chapter_writer.md .claude/templates/bedrock/edit_agent.md
git commit -m "feat(bedrock): 正文定界契约 extractProse + prompt ```prose 围栏(Unit A0 主层)"
```

---

## Task 4: commit-paragraphs sanitize 防御 + ensure_flag 保底(Unit A1 写面 + A3)

**Files:**
- Modify: `src/bedrock/__main__.py`(commit-paragraphs handler + verify-persisted/persist 出口)
- Test: `tests/bedrock/test_cli_commit_sanitize.py`(新)

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_cli_commit_sanitize.py
import subprocess, sys
from pathlib import Path

def test_commit_strips_meta_and_persists_clean(tmp_path, seed_one_chapter_project):
    proj = seed_one_chapter_project(tmp_path)  # fixture:1 卷 1 章 1 beat(planned)
    raw = ("草案符合指标：0破折号。\n\n"
           "天没亮，林昭就醒了。这是足够长的正文，" + "字" * 600 +
           "。\n\nD:\\x\\projects\\p\\bedrock.db")
    r = subprocess.run([sys.executable, "-m", "src.bedrock", "commit-paragraphs",
                        "--project", str(proj), "--chapter", "1"],
                       input=raw, capture_output=True, text=True, cwd="D:/novel_test")
    assert r.returncode == 0, r.stderr
    # 落库段落无 meta
    import sqlite3
    c = sqlite3.connect(proj / "bedrock.db")
    texts = [row[0] for row in c.execute("SELECT text FROM paragraph")]
    assert any("天没亮" in t for t in texts)
    assert not any("草案符合指标" in t or "bedrock.db" in t for t in texts)
```

- [ ] **Step 2: 跑确认失败**

Run: `pytest tests/bedrock/test_cli_commit_sanitize.py -v`
Expected: FAIL(commit 未清洗,meta 入库)

- [ ] **Step 3: commit-paragraphs handler 接入 sanitize**

在 `src/bedrock/__main__.py` 的 commit-paragraphs 处理段,`_split_paragraphs(raw)` **之前**插入清洗。定位当前:
```python
    paras = _split_paragraphs(raw)
    if not paras:
        sys.exit("commit-paragraphs: stdin 无有效段落（空正文？）")
```
改为:
```python
    from src.bedrock.checks.prose_hygiene import sanitize_prose, MIN_PROSE_CHARS
    cleaned, removed, preview = sanitize_prose(raw)
    if removed:
        print(f"commit-paragraphs: 剥离 {removed} 段元文本 {preview}", file=sys.stderr)
    if len(cleaned) < MIN_PROSE_CHARS:
        sys.exit(f"commit-paragraphs: 拒绝入库——清洗后正文仅 {len(cleaned)} 字 "
                 f"(下限 {MIN_PROSE_CHARS})，疑似重度污染，请重交纯正文。")
    paras = _split_paragraphs(cleaned)
    if not paras:
        sys.exit("commit-paragraphs: stdin 无有效段落（空正文？）")
```
保留既有 `_looks_like_worklog` 整篇闸(在清洗前对 raw 判一次,重度污染直接拒)。

- [ ] **Step 4: persist 出口 ensure_flag 保底(A3)**

在 `src/bedrock/__main__.py` 的 `verify-persisted` 处理段(约 :638),`ok = verify_chapter_persisted(...)` **之后**加:
```python
        from src.bedrock.orchestration.review_flag import ensure_flag
        ensure_flag(conn, cid)  # A3:无条件保底 flag 行
```
若 `ensure_flag` 未导出,在 `review_flag.py` 暴露:`ensure_flag = _upsert` 的零参包装——实际 `_upsert(conn, chapter_id, {})` 即建行。在 review_flag.py 加:
```python
def ensure_flag(conn, chapter_id):
    """A3:无条件保证 flag 行存在(零违规/零 drift 也建)。"""
    _upsert(conn, chapter_id, {})
```

- [ ] **Step 5: 跑确认通过**

Run: `pytest tests/bedrock/test_cli_commit_sanitize.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/bedrock/__main__.py src/bedrock/orchestration/review_flag.py tests/bedrock/test_cli_commit_sanitize.py
git commit -m "feat(bedrock): commit-paragraphs sanitize 防御 + persist ensure_flag 保底(Unit A1/A3)"
```

---

## Task 5: 状态生命周期 verify→completed + reopen + mark-completed CLI(Unit B)

**Files:**
- Modify: `src/bedrock/__main__.py`(verify-persisted 置 completed;commit/edit-paragraphs reopen;新 CLI)
- Test: `tests/bedrock/test_status_lifecycle.py`(新)

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_status_lifecycle.py
import subprocess, sys, sqlite3

def _status(proj):
    c = sqlite3.connect(proj / "bedrock.db")
    return c.execute("SELECT status FROM chapter WHERE global_number=1").fetchone()[0]

def test_verify_sets_completed(tmp_path, written_chapter_project):
    proj = written_chapter_project(tmp_path)  # fixture:1 章 status=writing, 有正文, beat written
    subprocess.run([sys.executable, "-m", "src.bedrock", "verify-persisted",
                    "--project", str(proj), "--chapter", "1"], cwd="D:/novel_test", check=True)
    assert _status(proj) == "completed"

def test_edit_reopens_to_writing(tmp_path, completed_chapter_project):
    proj = completed_chapter_project(tmp_path)  # fixture:status=completed
    ops = '[{"op":"update","para_id":1,"text":"改一字。"}]'
    subprocess.run([sys.executable, "-m", "src.bedrock", "edit-paragraphs",
                    "--project", str(proj), "--chapter", "1"],
                   input=ops, text=True, cwd="D:/novel_test", check=True)
    assert _status(proj) == "writing"
```

- [ ] **Step 2: 跑确认失败**

Run: `pytest tests/bedrock/test_status_lifecycle.py -v`
Expected: FAIL(verify 不置 completed)

- [ ] **Step 3: verify-persisted 通过 → completed**

在 `verify-persisted` 处理段(Task 4 加的 ensure_flag 之后):
```python
        if ok:
            from src.bedrock.repositories.plot_tree import set_chapter_status
            set_chapter_status(conn, cid, "completed")
```
确认 `verify_chapter_persisted` 返回 bool(True=通过)。若是,直接用;若返回 dict,取其 pass 字段(impl 时核实 persist_gate.py 返回类型)。

- [ ] **Step 4: commit/edit-paragraphs 写入 → reopen writing**

在 `commit-paragraphs` handler 末尾(已有 `set_chapter_status(conn, chapter_id, "writing")`,确认保留)。
在 `edit-paragraphs` handler(op 应用成功后)加:
```python
        set_chapter_status(conn, cid, "writing")  # B:编辑即回退,需重 verify 才再 completed
```
(import `set_chapter_status` 已在文件头 :28)

- [ ] **Step 5: 新增 mark-completed CLI**

在 `__main__.py` subparser 区(参考既有 :463 `verify-persisted`、:481 `edit-paragraphs` 注册)加:
```python
    p_mc = sub.add_parser("mark-completed", help="人工/卷审后置章为 completed")
    p_mc.add_argument("--project", type=Path, required=True)
    p_mc.add_argument("--chapter", type=int, required=True)
```
分发区(参考 :657 `elif args.cmd == "edit-paragraphs":`)加:
```python
        elif args.cmd == "mark-completed":
            conn = get_connection(args.project)
            cid = _chapter_id(conn, args.chapter)
            set_chapter_status(conn, cid, "completed")
            print(f"ch{args.chapter} → completed")
```

- [ ] **Step 6: 跑确认通过**

Run: `pytest tests/bedrock/test_status_lifecycle.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/bedrock/__main__.py tests/bedrock/test_status_lifecycle.py
git commit -m "feat(bedrock): 状态生命周期 verify→completed + edit reopen + mark-completed CLI(Unit B)"
```

---

## Task 6: watchdog drift 修 bug + bound + 卷级同向门控(Unit C)

**Files:**
- Modify: `src/bedrock/orchestration/watchdog.py`
- Modify: `src/bedrock/style/extractor.py`、`template_repo.py`(维度 bound)
- Test: `tests/bedrock/test_watchdog_drift.py`(新)

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_watchdog_drift.py
import json, sqlite3
from src.bedrock.orchestration.watchdog import run_watchdog

def _flag(conn, cid, drifted, ok=True):
    conn.execute("INSERT OR IGNORE INTO chapter_review_flag(chapter_id) VALUES(?)", (cid,))
    conn.execute("UPDATE chapter_review_flag SET advisory_drift=? WHERE chapter_id=?",
                 (json.dumps({"drifted": drifted, "ok": ok}), cid))

def test_counts_real_drift_not_snapshot(tmp_path, one_volume_project):
    proj, vol_id, cids = one_volume_project(tmp_path)  # 3 章
    conn = sqlite3.connect(proj / "bedrock.db"); conn.row_factory = sqlite3.Row
    for cid in cids:
        _flag(conn, cid, drifted=[])   # 有快照但 drifted 空
    # 需 chapter_metrics 行(hug 检测用);建空 grep_metrics
    for cid in cids:
        conn.execute("INSERT OR IGNORE INTO chapter_metrics(chapter_id,grep_metrics) VALUES(?,?)",
                     (cid, "{}"))
    conn.commit()
    run_watchdog(conn, vol_id)
    row = conn.execute("SELECT watchdog_findings FROM volume_review WHERE volume_id=?", (vol_id,)).fetchone()
    find = json.loads(row["watchdog_findings"])
    assert find["drift_ratio"] == 0.0   # bug 修后:drifted 全空 → 0
    assert find["drift_flagged"] is False

def test_consecutive_same_direction_flags(tmp_path, one_volume_project):
    proj, vol_id, cids = one_volume_project(tmp_path)
    conn = sqlite3.connect(proj / "bedrock.db"); conn.row_factory = sqlite3.Row
    # 3 章连续 rhetoric_per_k 同向超阈
    d = [{"metric": "rhetoric_per_k", "actual": 6.0, "target": 1.69, "severity": 3.6}]
    for cid in cids:
        _flag(conn, cid, drifted=d, ok=False)
        conn.execute("INSERT OR IGNORE INTO chapter_metrics(chapter_id,grep_metrics) VALUES(?,?)", (cid, "{}"))
    conn.commit()
    run_watchdog(conn, vol_id)
    row = conn.execute("SELECT watchdog_findings,blocking FROM volume_review WHERE volume_id=?", (vol_id,)).fetchone()
    find = json.loads(row["watchdog_findings"])
    assert find["drift_flagged"] is True
    assert row["blocking"] == 1
```

- [ ] **Step 2: 跑确认失败**

Run: `pytest tests/bedrock/test_watchdog_drift.py -v`
Expected: FAIL(旧逻辑 drift_ratio=1.0)

- [ ] **Step 3: 加 bound 元数据(extractor/template_repo)**

在 `src/bedrock/style/extractor.py` 指纹维度定义处,为每维加 `bound`:
```python
# 维度 bound:upper=仅超算 drift;lower=仅低算;bidirectional=双向(对白比用宽松容差)
DIM_BOUNDS = {
    "dash_density": "upper",
    "dash": "upper",
    "rhetoric_per_k": "upper",
    "short_sent_rate": "upper",
    "notXisY_rate": "upper",
    "dialogue_ratio": "bidirectional",   # 容差在 watchdog 判定时用 [0.5×,1.5×]
}
```
(`template_repo.get_style_config` 返回时附带 `dim_bounds`,供 watchdog 取用。若指纹已含各维 target,这里补 bound 映射即可。)

- [ ] **Step 4: 重写 watchdog drift 段(修 bug + 同向门控)**

在 `src/bedrock/orchestration/watchdog.py` 把 drift 段(从 `drift_ratio = 0.0` 到 `drift_flagged = ...`)替换为:
```python
    # Unit C:计"真实 drift"(drifted 非空)而非"有快照";卷级同向连续门控。
    DIALOGUE_TOL = (0.5, 1.5)           # 对白比双向容差区间(× target)
    CONSEC_MIN = 3                       # 连续 ≥3 章同指标同方向才系统性

    # 收集每章真实 drifted 项(按 bound 过滤)
    per_chapter_drifts = []   # [{cid, [(metric, direction)]}]
    for cid in cids:
        row = conn.execute("SELECT advisory_drift FROM chapter_review_flag WHERE chapter_id=?",
                           (cid,)).fetchone()
        if row is None or not row["advisory_drift"] or row["advisory_drift"] == "{}":
            per_chapter_drifts.append((cid, []))
            continue
        d = json.loads(row["advisory_drift"])
        items = []
        for dv in d.get("drifted", []):
            items.append((dv["metric"], dv.get("severity", 0)))
        per_chapter_drifts.append((cid, items))

    # drift_ratio = 有真实 drift 的章占比(诊断用,不再直接 blocking)
    drift_ratio = sum(1 for _, items in per_chapter_drifts if items) / n if n else 0.0

    # 卷级同向连续:连续 ≥CONSEC_MIN 章、同一 metric 出现 → 系统性
    consecutive_hits = []
    for metric in _DRIFT_METRICS_OF_INTEREST:   # {"rhetoric_per_k","dialogue_ratio","dash_density","notXisY_rate","short_sent_rate"}
        run = 0
        for _, items in per_chapter_drifts:
            if any(m == metric for m, _ in items):
                run += 1
                if run >= CONSEC_MIN:
                    consecutive_hits.append(metric)
                    break
            else:
                run = 0
    drift_flagged = len(consecutive_hits) > 0

    blocking = any(f["flagged"] for f in hug_findings.values()) or drift_flagged
```
在模块头加常量:
```python
_DRIFT_METRICS_OF_INTEREST = {"rhetoric_per_k", "dialogue_ratio", "dash_density", "notXisY_rate", "short_sent_rate"}
```
并把 `findings_json` 增加 `consecutive_drift_metrics` 字段(供报告可读):
```python
    findings_json = json.dumps({
        "hug_findings": hug_findings,
        "drift_ratio": drift_ratio,
        "drift_flagged": drift_flagged,
        "consecutive_drift_metrics": consecutive_hits,
    }, ensure_ascii=False)
```
删除旧 `WATCHDOG_DRIFT_RATIO` 的 blocking 用法(常量可保留供报告,但不再决定 blocking)。

- [ ] **Step 5: 跑确认通过**

Run: `pytest tests/bedrock/test_watchdog_drift.py -v`
Expected: PASS(2/2)

- [ ] **Step 6: Commit**

```bash
git add src/bedrock/orchestration/watchdog.py src/bedrock/style/extractor.py src/bedrock/style/template_repo.py tests/bedrock/test_watchdog_drift.py
git commit -m "fix(bedrock): watchdog drift 计真实drift+bound区分+卷级同向门控(Unit C)"
```

---

## Task 7: 专名硬校验 check-proper-nouns(Unit D)

**Files:**
- Create: `src/bedrock/checks/proper_nouns.py`
- Modify: `src/bedrock/__main__.py`(新 CLI)、`.claude/workflows/bedrock-chapter.js`(Consistency hook)
- Test: `tests/bedrock/test_proper_nouns.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_proper_nouns.py
from src.bedrock.checks.proper_nouns import find_proper_noun_variants

def test_edit_distance_one_variant_to_canonical():
    # 白名单 周执;正文出现 周植(形近)→ tier1 单目标
    whitelist = {"chars": ["周执"], "places": ["北原"]}
    canonical_seen = {"周执", "北原"}   # 已在前文确立
    findings = find_proper_noun_variants("周植走了过来，北院也在。", whitelist, canonical_seen)
    by_tier = {"tier1": [], "tier2": []}
    for f in findings:
        by_tier[f["tier"]].append(f)
    # 周植→周执(tier1:单目标+已确立);北院→北原(tier2:北院是常用词,歧义)
    assert any(f["variant"] == "周植" and f["canonical"] == "周执" for f in by_tier["tier1"])
    assert any(f["variant"] == "北院" for f in by_tier["tier2"])

def test_no_variant_for_correct_name():
    whitelist = {"chars": ["周执"], "places": []}
    assert find_proper_noun_variants("周执笑了。", whitelist, {"周执"}) == []
```

- [ ] **Step 2: 跑确认失败**

Run: `pytest tests/bedrock/test_proper_nouns.py -v`
Expected: FAIL(模块不存在)

- [ ] **Step 3: 实现 proper_nouns.py**

```python
# src/bedrock/checks/proper_nouns.py
"""专名硬校验(确定性,零 LLM)。Unit D。
白名单=character.name+location.name;检测形近/音近变体;分层 Tier-1 自动改 / Tier-2 escalate。"""
import re

# 精选 confusable(可扩展):key=变体字, value=规范字(用于把变体还原后比对白名单)
_CONFUSABLE = {"植": "执", "直": "执", "院": "原", "苑": "原"}
# 歧义词:本身是常用词,即便形近白名单也只 escalate 不自动改(Tier-2)
_AMBIGUOUS = {"北院", "北苑", "中原"}


def _edit_distance_one(a: str, b: str) -> bool:
    """长度相同且恰好差 1 字(简化编辑距离,专名多 2-3 字够用)。"""
    if len(a) != len(b) or a == b:
        return False
    return sum(1 for x, y in zip(a, b) if x != y) == 1


def find_proper_noun_variants(text, whitelist, canonical_seen):
    """扫 text,返回变体 finding 列表。
    whitelist={"chars":[...],"places":[...]} ; canonical_seen=本章或前序已出现的规范名集合。
    finding={variant, canonical, tier, para_offset(占位,-1 由调用方填 para_id)}"""
    canon_all = list(whitelist.get("chars", [])) + list(whitelist.get("places", []))
    findings = []
    seen_spans = set()
    # 1) 滑窗扫白名单长度的 token(中文逐字)
    for canon in canon_all:
        L = len(canon)
        for i in range(len(text) - L + 1):
            tok = text[i:i + L]
            if tok == canon or tok in seen_spans:
                continue
            similar = (tok in _CONFUSABLE_apply_map(canon)) or _edit_distance_one(tok, canon)
            if not similar:
                continue
            # 候选规范名:tok 形近哪些白名单
            candidates = [c for c in canon_all if c != tok and (_edit_distance_one(tok, c) or tok in _CONFUSABLE_apply_map(c))]
            if not candidates:
                continue
            seen_spans.add(tok)
            if tok in _AMBIGUOUS or len(candidates) > 1:
                tier = "tier2"
                canonical = "|".join(candidates)
            elif candidates[0] in canonical_seen:
                tier = "tier1"
                canonical = candidates[0]
            else:
                tier = "tier2"           # 候选未在前文确立 → 不自动改
                canonical = candidates[0]
            findings.append({"variant": tok, "canonical": canonical, "tier": tier, "para_offset": i})
    return findings


def _CONFUSABLE_apply_map(canon):
    """canon 经 confusable 反向替换能生成的变体集合(如 周执→{周植,周直})。"""
    out = set()
    for i, ch in enumerate(canon):
        for bad, good in _CONFUSABLE.items():
            if good == ch:
                out.add(canon[:i] + bad + canon[i + 1:])
    return out
```

- [ ] **Step 4: 跑确认通过**

Run: `pytest tests/bedrock/test_proper_nouns.py -v`
Expected: PASS(2/2)

- [ ] **Step 5: 新增 check-proper-nouns CLI(扫描+Tier1 自动改+留痕+flag)**

`__main__.py` subparser 加:
```python
    p_pn = sub.add_parser("check-proper-nouns", help="专名硬校验:Tier1 自动改+留痕,Tier2 escalate")
    p_pn.add_argument("--project", type=Path, required=True)
    p_pn.add_argument("--chapter", type=int, required=True)
```
分发区加(产 ops JSON + flag,供工作流/卷审消费):
```python
        elif args.cmd == "check-proper-nouns":
            from src.bedrock.checks.proper_nouns import find_proper_noun_variants
            from src.bedrock.orchestration.review_flag import ensure_flag, _upsert
            from src.bedrock.repositories.character import list_characters
            from src.bedrock.repositories.worldbook import list_locations
            from src.bedrock.repositories.plot_tree import list_paragraphs_in_chapter, update_paragraph
            conn = get_connection(args.project)
            cid = _chapter_id(conn, args.chapter)
            chars = [r["name"] for r in list_characters(conn)]
            places = [r["name"] for r in list_locations(conn)]
            # canonical_seen:本章 + 前序章 已出现的白名单名
            seen = set(chars) | set(places)
            paras = list_paragraphs_in_chapter(conn, cid)
            ops, escalate, autoedit = [], [], []
            for p in paras:
                fs = find_proper_noun_variants(p["text"], {"chars": chars, "places": places}, seen)
                for f in fs:
                    if f["tier"] == "tier1":
                        new_text = p["text"].replace(f["variant"], f["canonical"])
                        ops.append({"op": "update", "para_id": p["para_id"], "text": new_text})
                        autoedit.append({"para_id": p["para_id"], "old": f["variant"], "new": f["canonical"]})
                    else:
                        escalate.append({"para_id": p["para_id"], "variant": f["variant"], "canonical": f["canonical"]})
            ensure_flag(conn, cid)
            if autoedit:
                _upsert(conn, cid, {"proper_noun_autoedit": json.dumps(autoedit, ensure_ascii=False)})
            # 输出 ops(供 apply)+ escalate(供 flag)
            print(json.dumps({"ops": ops, "escalate": escalate, "autoedit_count": len(autoedit)},
                             ensure_ascii=False))
```
> 注:`list_characters`/`list_locations` 函数名以仓库实际为准(impl 时核实 `repositories/character.py`、`worldbook.py` 导出名;若为 `list_all_characters` 等则相应调整)。Tier1 的实际 update 由工作流调 edit-paragraphs 落(见 Step 6),CLI 这里产 ops 不直接改,避免双重写入。

- [ ] **Step 6: 工作流 Consistency 阶段挂 check-proper-nouns**

`.claude/workflows/bedrock-chapter.js` Consistency phase(现 LLM consistency agent 之后,约 :104),加 relay:
```js
  // Unit D:专名硬校验(确定性 relay)。Tier1 ops 经 edit-paragraphs 落,Tier2 进 flag 供卷审。
  const pnRaw = stripFences(await pythonCli(
    `check-proper-nouns --project ${project} --chapter ${chapter}`, { phase: 'Consistency' }))
  let pn
  try { pn = JSON.parse(pnRaw) } catch { pn = { ops: [], escalate: [] } }
  if (pn.ops && pn.ops.length) {
    await pythonCli(`edit-paragraphs --project ${project} --chapter ${chapter}`,
      { phase: 'Consistency', stdin: JSON.stringify(pn.ops) })
    log(`proper-nouns: ${pn.autoedit_count} 处自动改(已留 amendment+flag)`)
  }
  if (pn.escalate && pn.escalate.length) log(`proper-nouns: ${pn.escalate.length} 处歧义 escalate 供卷审`)
```
(`pythonCli` / `stripFences`(现 `extractProse`)签名同文件既有;CLI 文本输出不含围栏,用 extractProse 等价于 trim,安全。)

- [ ] **Step 7: 跑确认通过 + 手测 CLI**

Run: `pytest tests/bedrock/test_proper_nouns.py -v` → PASS
Run(手测,vigilia ch7 有"周植"):`python -m src.bedrock check-proper-nouns --project projects/vigilia --chapter 7`
Expected: 输出含 `周植→周执` 的 ops/escalate(vigilia 卷审已修过 ch7,若已无变体则 escalate/ops 为空——正常,说明已净)。

- [ ] **Step 8: Commit**

```bash
git add src/bedrock/checks/proper_nouns.py src/bedrock/__main__.py .claude/workflows/bedrock-chapter.js tests/bedrock/test_proper_nouns.py
git commit -m "feat(bedrock): 专名硬校验 check-proper-nouns 分层 Tier1自动改/Tier2 escalate(Unit D)"
```

---

## Task 8: 文风边界例 —— 风格化油腔 vs 出戏游戏术语(Unit E)

**Files:**
- Modify: `projects/vigilia/bedrock.db`(经 repo `set_style_config`,非裸 SQL)
- 脚本: `scripts/add_style_boundary_example.py`(一次性,跑完删)

- [ ] **Step 1: 写一次性脚本**

```python
# scripts/add_style_boundary_example.py
import sys; from pathlib import Path
sys.path.insert(0, '.')
from src.bedrock.db.connection import get_connection
from src.bedrock.style.template_repo import set_style_config, _row_by_scope
import json
conn = get_connection(Path('projects/vigilia'))
row = _row_by_scope(conn, 'work', None)
se = json.loads(row['style_examples'])
# 追加第 6 对(风格化油腔 vs 出戏游戏术语),不覆盖既有 5 对
se.setdefault('good', []).append(
  "风格化油腔贴合本作(✓ 学这种):林昭盯着钟摆的刀,脑子里飘过一条弹幕——'这反派开场白真长。'弹幕救不了她,惯性可以;她一矮身,刀锋削掉三根头发。'我的发型。'她心痛,'你赔。'——吐槽服务于刻画她的清醒与疏离,不跨出世界观。")
se.setdefault('bad', []).append(
  "出戏游戏术语(✗ 避免这种):林昭开启大招,钟摆进入 Boss战二阶段,血条见了底,她连放三个怪量把对面控死,这剧情简直像开了金手指Mod。——Boss战/怪量/大招/血条/Mod 是跨次元游戏黑话,把读者甩出故事;油腔谐音梗须用本作世界观内的隐喻。")
set_style_config(conn, 'work', None, style_examples=se)
conn.close()
print('added boundary example; good=', len(se['good']), 'bad=', len(se['bad']))
```

- [ ] **Step 2: 跑脚本**

Run: `python scripts/add_style_boundary_example.py`
Expected: `added boundary example; good= 6 bad= 6`

- [ ] **Step 3: 验证 boot-context 注入**

Run: `python -m src.bedrock boot-context --project projects/vigilia --chapter 1 --volume 1 | python -c "import sys,json;d=json.load(sys.stdin);print(len(d['style_examples']['good']),len(d['style_examples']['bad']))"`
Expected: `6 6`

- [ ] **Step 4: 删脚本 + Commit(DB 变更不进 git,但脚本删除与说明可记)**

```bash
rm scripts/add_style_boundary_example.py
git commit --allow-empty -m "feat(bedrock): vigilia 文风边界例 风格化油腔vs出戏游戏术语(Unit E;DB变更经repo)"
```

---

## Task 9: 灵感池注入 boot-context + consume 返回值(Unit F)

**Files:**
- Modify: `src/bedrock/orchestration/boot_context.py`
- Modify: `src/bedrock/repositories/outline.py`
- Test: `tests/bedrock/test_boot_context.py`(追加)

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/bedrock/test_boot_context.py
def test_boot_context_includes_inspirations(tmp_path, project_with_raw_inspiration):
    proj = project_with_raw_inspiration(tmp_path)  # fixture:1 章 + 1 条 raw 灵感
    from src.bedrock.orchestration.boot_context import build_boot_context
    import sqlite3
    conn = sqlite3.connect(proj / 'bedrock.db'); conn.row_factory = sqlite3.Row
    ctx = build_boot_context(conn, chapter_id=1, volume_id=1)
    assert 'inspirations' in ctx
    assert any(i['status'] == 'raw' for i in ctx['inspirations'])

def test_consume_inspiration_returns_row(tmp_path, project_with_raw_inspiration):
    from src.bedrock.repositories.outline import add_inspiration, consume_inspiration
    import sqlite3
    conn = sqlite3.connect(project_with_raw_inspiration(tmp_path) / 'bedrock.db')
    conn.row_factory = sqlite3.Row
    iid = add_inspiration(conn, content='x', type='scene')
    r = consume_inspiration(conn, iid, 'chapter', 1)
    assert r is not None and r['status'] == 'consumed'
```

- [ ] **Step 2: 跑确认失败**

Run: `pytest tests/bedrock/test_boot_context.py -v`
Expected: FAIL(无 inspirations key / consume 返 None)

- [ ] **Step 3: boot_context 注入 inspirations**

在 `src/bedrock/orchestration/boot_context.py` 的 build 函数,return dict 加:
```python
        "inspirations": _available_inspirations(conn),
```
并加 helper:
```python
def _available_inspirations(conn):
    """Unit F:注入未消费(raw/refined/partial)灵感,作 writer 可选素材池。"""
    rows = conn.execute(
        "SELECT id, type, content FROM inspiration "
        "WHERE status IN ('raw','refined','partial') ORDER BY id").fetchall()
    return [{"id": r["id"], "type": r["type"], "content": r["content"], "status": "raw"}
            for r in rows]
```
> 注:`build_boot_context` 实际函数名/签名以文件内为准(:86 处 docstring 提到 return dict);impl 时核实函数名,把 key 加入其 return。

- [ ] **Step 4: consume_inspiration 补 return**

`src/bedrock/repositories/outline.py` `consume_inspiration` 末尾(`conn.commit()` 后)加:
```python
    return dict(conn.execute("SELECT * FROM inspiration WHERE id=?",
                             (inspiration_id,)).fetchone())
```

- [ ] **Step 5: 跑确认通过**

Run: `pytest tests/bedrock/test_boot_context.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/bedrock/orchestration/boot_context.py src/bedrock/repositories/outline.py tests/bedrock/test_boot_context.py
git commit -m "feat(bedrock): boot-context 注入 inspirations + consume 返回值(Unit F)"
```

---

## Task 10: 端到端回归(vigilia ch5 重写 + voidwright watchdog)

**Files:** 无新文件;验证既有

- [ ] **Step 1: vigilia ch5 端到端(最脏:机翻腔+专名错+无flag,已被卷审 rewrite 过,此处验证管线新防线)**

ch5 已被卷审 rewrite,正文已净。改用一个**构造的脏输入**验证新管线防线,而非重跑 ch5(避免覆盖已审稿)。在 `tests/bedrock/e2e/test_robustness_regression.py`:
```python
def test_pipeline_rejects_meta_pollution(tmp_path, fresh_vigilia_chapter):
    """构造 agent 吐 prose+meta 的输入,验证 A0/A1/A2 三层至少一层拦住 meta 入库。"""
    proj, cid = fresh_vigilia_chapter(tmp_path)  # 一空章
    import subprocess, sys, sqlite3
    raw = "```prose\n" + ("林昭笑了。" * 200) + "\n```\n指标：0破折号，对话占比35%。"  # 围栏外 meta
    subprocess.run([sys.executable, "-m", "src.bedrock", "commit-paragraphs",
                    "--project", str(proj), "--chapter", "99"],  # chapter 99 见 fixture
                   input=raw, text=True, cwd="D:/novel_test", check=True)
    c = sqlite3.connect(proj / "bedrock.db")
    texts = [r[0] for r in c.execute("SELECT text FROM paragraph")]
    assert not any("对话占比" in t or "破折号" in t for t in texts)   # meta 未入库
```

- [ ] **Step 2: 跑回归**

Run: `pytest tests/bedrock/e2e/test_robustness_regression.py tests/bedrock/ -v`
Expected: PASS

- [ ] **Step 3: voidwright watchdog 回归(既有作品 drift_ratio 回落)**

Run: `python -m src.bedrock run-watchdog --project projects/voidwright --volume 1`
Expected: `drift_ratio` 显著低于 1.0(此前因 bug ≈1.0);`drift_flagged` 仅在真有连续同向时为 true。

- [ ] **Step 4: vigilia 全卷 diagnose 确认无破坏**

Run: `python -m src.bedrock diagnose --project projects/vigilia --book`
Expected: 无报错;ch1-12 落盘正常。

- [ ] **Step 5: Commit**

```bash
git add tests/bedrock/e2e/test_robustness_regression.py
git commit -m "test(bedrock): 鲁棒性修复端到端回归(Unit 全)"
```

---

## Self-Review(写完后自检)

**Spec 覆盖:**
- A0 定界契约 → Task 3 ✓ | A1 检测/清洗 → Task 1 + Task 4(commit)✓ | A2 L2 non_prose → Task 2 ✓ | A3 ensure_flag → Task 4 ✓
- B 状态生命周期 → Task 5 ✓
- C watchdog → Task 6 ✓
- D 专名 → Task 7 ✓
- E 边界例 → Task 8 ✓
- F 灵感池 → Task 9 ✓
- 回归 → Task 10 ✓

**类型/签名一致性:** `set_chapter_status(conn, chapter_id, status)`、`ensure_flag`、`is_meta_paragraph`/`sanitize_prose`/`extract_prose_block`、`find_proper_noun_variants`、`BeatViolation(beat_id,kind,detail,fix_hint)`、`consume_inspiration` 返回 —— 各 Task 间引用一致。

**需 impl 时核实的点(已在对应 Task 标注):** `verify_chapter_persisted` 返回类型(bool/dict)、`list_characters`/`list_locations` 导出名、`build_boot_context` 函数名、`chapter_metrics` 列名。这些是"读一眼即定"的核实,非设计缺口。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-19-bedrock-pipeline-robustness-fixes.md`. **建议在独立 worktree/分支 `bedrock-robustness` 实施**(跨信任锚区改动)。两种执行方式:

1. **Subagent-Driven(推荐)** — 每 Task 派新 subagent,任务间两阶段 review,快迭代
2. **Inline Execution** — 本会话内按 executing-plans 批量执行,带 checkpoint

选哪种?
