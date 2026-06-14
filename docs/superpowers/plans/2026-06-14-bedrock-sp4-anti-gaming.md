# 磐石 Bedrock SP4 — 抗博弈管线 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 单章抗博弈管线——L2 重算 bundle（硬门禁/advisory 分流）+ boot context 装配 + 强制落盘门禁 + 诊断标记 + delete_volume_fingerprint 助手 + CLI + agent 编排层（ChapterWriter/Edit prompt + Workflow JS）。

**Architecture:** Python-first。纯 Python 模块（checks/ 3 个重算 + orchestration/ 4 个 + style 扩展）先建可单测；agent 层（prompt 模板 + Workflow JS）后挂，端到端验证留 SP5。L2 重算是信任锚（每轮独立重算覆盖 agent 自报）。SP1 已有 `write_chapter_metrics`/`record_agent_invocation`/`record_llm_call`，故不建独立 telemetry 模块。

**Tech Stack:** Python 3.10+ stdlib（re/json/dataclasses/sqlite3/pathlib/os），pytest。Agent 层：Workflow JS + Markdown prompt 模板。

**前置:** SP1/2/3 完成（src/bedrock/ 76 测试，分支 bedrock-sp1）。spec: `docs/superpowers/specs/2026-06-14-bedrock-sp4-anti-gaming-design.md`。

---

## 文件结构

```
src/bedrock/
├── db/schema.sql              # +chapter_review_flag 表（Task 1）
├── checks/
│   ├── word_count.py          # Task 2
│   ├── grep_metrics.py        # Task 3
│   └── consumption.py         # Task 4
├── orchestration/             # 新建包（Task 5 起）
│   ├── __init__.py
│   ├── l2_pipeline.py         # Task 5
│   ├── boot_context.py        # Task 6
│   ├── persist_gate.py        # Task 7
│   └── review_flag.py         # Task 8
├── style/template_repo.py     # +delete_volume_fingerprint（Task 9）
└── __main__.py                # CLI 扩展（Task 10）
tests/bedrock/
├── test_word_count.py / test_grep_metrics.py / test_consumption.py
├── test_l2_pipeline.py / test_boot_context.py / test_persist_gate.py / test_review_flag.py
└── test_template_repo.py      # +delete 用例（Task 9 扩展）
.claude/templates/bedrock/     # Task 11
├── chapter_writer.md
└── edit_agent.md
.claude/workflows/bedrock-chapter.js  # Task 11
```

依赖链：Task 1（schema）→ Task 2/3/4（独立重算，并行可行但串行执行）→ Task 5（l2_pipeline 用 2/3/4 + SP2）→ Task 6/7（独立）→ Task 8（用 Task 1 表）→ Task 9（style 扩展）→ Task 10（CLI 用 5/6/7/8）→ Task 11（agent 层）。

---

## Task 1: chapter_review_flag schema

**Files:**
- Modify: `src/bedrock/db/schema.sql`（追加表，放在 style_template 表之前或之后均可）

- [ ] **Step 1: 追加表定义到 schema.sql**

在 `src/bedrock/db/schema.sql` 末尾追加：

```sql

-- ===== SP4 抗博弈管线：诊断标记（SP5 VolumeReview 消费）=====
CREATE TABLE IF NOT EXISTS chapter_review_flag (
    chapter_id INTEGER PRIMARY KEY REFERENCES chapter(id),
    l2_unresolved INTEGER NOT NULL DEFAULT 0,
    persisted_violations TEXT NOT NULL DEFAULT '[]',
    likely_rule_or_model_issue INTEGER NOT NULL DEFAULT 0,
    polish_broke_beat INTEGER NOT NULL DEFAULT 0,
    forced_persist_failed INTEGER NOT NULL DEFAULT 0,
    advisory_drift TEXT NOT NULL DEFAULT '{}',
    flagged_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

- [ ] **Step 2: 验证 schema 应用**

Run:
```bash
cd D:/novel_test && python -c "
from pathlib import Path
import tempfile
from src.bedrock.db.migrate import apply_migrations
from src.bedrock.db.connection import get_connection
d = Path(tempfile.mkdtemp())
apply_migrations(d)
conn = get_connection(d)
row = conn.execute(\"SELECT name FROM sqlite_master WHERE name='chapter_review_flag'\").fetchone()
print('TABLE EXISTS:', row is not None)
conn.close()
"
```
Expected: `TABLE EXISTS: True`

- [ ] **Step 3: 全量回归确认无破坏**

Run: `cd D:/novel_test && python -m pytest tests/bedrock/ -q`
Expected: 76 passed（新表不破坏既有测试）

- [ ] **Step 4: Commit**
```bash
git add src/bedrock/db/schema.sql
git commit -m "feat(bedrock): chapter_review_flag table (SP4 diagnostic flags)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: 字数重算（word_count）

**Files:**
- Create: `src/bedrock/checks/word_count.py`
- Test: `tests/bedrock/test_word_count.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_word_count.py
from src.bedrock.checks.word_count import compute_word_count


def test_empty_returns_zero():
    assert compute_word_count([]) == 0


def test_counts_chinese_chars_only():
    # 5 汉字 + 标点 + ASCII，只计汉字
    assert compute_word_count(["他来了，然后走了。"]) == 6


def test_multiple_paragraphs_summed():
    assert compute_word_count(["他来了。", "她走了。"]) == 6


def test_no_chinese_returns_zero():
    assert compute_word_count(["abc 123 !!!"]) == 0
```

- [ ] **Step 2: 跑确认失败**（ModuleNotFoundError）

Run: `cd D:/novel_test && python -m pytest tests/bedrock/test_word_count.py -v`

- [ ] **Step 3: 实现 `checks/word_count.py`**

```python
# src/bedrock/checks/word_count.py
import re

_CN_CHAR = re.compile(r"[一-鿿]")


def compute_word_count(paragraphs):
    """段落文本列表 → 汉字总数（排除标点/ASCII/空白）。空 → 0。"""
    return sum(len(_CN_CHAR.findall(p)) for p in paragraphs)
```

- [ ] **Step 4: 跑确认通过**（4 passed）+ 全量回归 → 76 + 4 = 80

- [ ] **Step 5: Commit**
```bash
git add src/bedrock/checks/word_count.py tests/bedrock/test_word_count.py
git commit -m "feat(bedrock): word_count recompute (chinese char count)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: grep 指标重算（grep_metrics）

**Files:**
- Create: `src/bedrock/checks/grep_metrics.py`
- Test: `tests/bedrock/test_grep_metrics.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_grep_metrics.py
from src.bedrock.checks.grep_metrics import compute_grep_metrics


def test_empty_returns_zeros():
    m = compute_grep_metrics([])
    assert m == {"notXisY_per_kchar": 0.0, "dash_per_kchar": 0.0, "period_density": 0.0}


def test_notXisY_counted():
    # 2 个 notXisY 句式，1000 汉字 → 0.002/kchar；这里少量汉字断言 >0 即可
    m = compute_grep_metrics(["不是因为他累，是因为他想家。不是因为天黑，是因为下雨。"])
    assert m["notXisY_per_kchar"] > 0


def test_dash_counted():
    m = compute_grep_metrics(["一段——带破折号——的文字。"])
    assert m["dash_per_kchar"] > 0


def test_period_density():
    # 3 句号 / N 汉字
    m = compute_grep_metrics(["他来了。她走了。天黑了。"])
    assert 0 < m["period_density"] < 1


def test_no_chinese_zero_density():
    m = compute_grep_metrics(["abc 123"])
    assert m["notXisY_per_kchar"] == 0.0
    assert m["dash_per_kchar"] == 0.0
    assert m["period_density"] == 0.0
```

- [ ] **Step 2: 跑确认失败**（ModuleNotFoundError）

- [ ] **Step 3: 实现 `checks/grep_metrics.py`**

```python
# src/bedrock/checks/grep_metrics.py
import re

_CN_CHAR = re.compile(r"[一-鿿]")
_NOTXISY = re.compile(r"不是.{1,15}[，。].{0,5}是")
_DASH = "——"
_PERIOD = "。"


def compute_grep_metrics(paragraphs):
    """段落文本列表 → grep 风格指标（authoritative，零 LLM）。
    返回 {
      notXisY_per_kchar: 否定转折句式计数/千字,
      dash_per_kchar: 破折号(——)计数/千字,
      period_density: 句号(。)数/汉字数,
    }。无汉字 → 全 0.0（period_density 防 0 除）。"""
    text = "".join(paragraphs)
    cn = len(_CN_CHAR.findall(text))
    if cn == 0:
        return {"notXisY_per_kchar": 0.0, "dash_per_kchar": 0.0, "period_density": 0.0}
    notxi = len(_NOTXISY.findall(text))
    dash = text.count(_DASH)
    period = text.count(_PERIOD)
    return {
        "notXisY_per_kchar": notxi / (cn / 1000),
        "dash_per_kchar": dash / (cn / 1000),
        "period_density": period / cn,
    }
```

- [ ] **Step 4: 跑确认通过**（5 passed）+ 全量回归 → 80 + 5 = 85

- [ ] **Step 5: Commit**
```bash
git add src/bedrock/checks/grep_metrics.py tests/bedrock/test_grep_metrics.py
git commit -m "feat(bedrock): grep metrics recompute (notXisY/dash/period)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: 悬链消费重算（consumption）

**Files:**
- Create: `src/bedrock/checks/consumption.py`
- Test: `tests/bedrock/test_consumption.py`

**前置依赖**（已确认存在）：`thread_consumption(chapter INTEGER, new_status TEXT)`、`suspense_thread(planted_at_beat REFERENCES beat(id))`、`chapter(global_number)`、`list_beats_in_chapter`。

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_consumption.py
from src.bedrock.db.connection import get_connection
from src.bedrock.checks.consumption import compute_consumption
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat, create_paragraph,
)


def _seed(conn):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=5, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="p")
    create_paragraph(conn, chapter_id=cid, seq=1, text="x。",
                     content_hash="h", beat_id=bid, role="narration")
    return vid, cid, bid


def _record(conn, thread_id, beat_id, new_status, chapter):
    conn.execute(
        "INSERT INTO thread_consumption(thread_id,beat_id,new_status,chapter) VALUES(?,?,?,?)",
        (thread_id, beat_id, new_status, chapter))
    conn.commit()


def _plant_thread(conn, tid, planted_at_beat):
    conn.execute(
        "INSERT INTO suspense_thread(id,content,thread_type,importance,origin,status,planted_at_beat) "
        "VALUES(?,?,?,?,?,?,?)",
        (tid, "c", "mystery", "high", "scheduled", "developing", planted_at_beat))
    conn.commit()


def test_no_consumption_returns_zeros(tmp_project):
    conn = get_connection(tmp_project)
    _, cid, _ = _seed(conn)
    consumed, balance = compute_consumption(conn, cid)
    assert consumed == 0.0
    assert balance == 0.0
    conn.close()


def test_consumed_weights(tmp_project):
    """resolved×1.0 + advanced×0.5 + partially_resolved×0.5 + abandoned×0.3"""
    conn = get_connection(tmp_project)
    _, cid, bid = _seed(conn)
    _plant_thread(conn, 1, bid); _plant_thread(conn, 2, bid)
    _plant_thread(conn, 3, bid); _plant_thread(conn, 4, bid)
    _record(conn, 1, bid, "resolved", 5)
    _record(conn, 2, bid, "advanced", 5)            # 注：advanced 不在 new_status CHECK？见下
    _record(conn, 3, bid, "partially_resolved", 5)
    _record(conn, 4, bid, "abandoned", 5)
    consumed, balance = compute_consumption(conn, cid)
    # 1.0 + 0.5 + 0.5 + 0.3 = 2.3
    assert abs(consumed - 2.3) < 1e-6
    conn.close()
```

> **注意 new_status CHECK**：schema.sql thread_consumption.new_status 允许 `('scheduled','planted','developing','mature','partially_resolved','resolved','abandoned')`。**没有 'advanced'**——推进用 `developing`/`mature` 表示。权重映射对应调整（见实现）。若测试里用了 'advanced' 会 IntegrityError，**改用 'developing' 权重 0.5**。

修正测试为合法状态：

```python
def test_consumed_weights(tmp_project):
    """resolved×1.0 + developing×0.5 + partially_resolved×0.5 + abandoned×0.3"""
    conn = get_connection(tmp_project)
    _, cid, bid = _seed(conn)
    for tid in (1, 2, 3, 4):
        _plant_thread(conn, tid, bid)
    _record(conn, 1, bid, "resolved", 5)
    _record(conn, 2, bid, "developing", 5)
    _record(conn, 3, bid, "partially_resolved", 5)
    _record(conn, 4, bid, "abandoned", 5)
    consumed, balance = compute_consumption(conn, cid)
    assert abs(consumed - 2.3) < 1e-6
    conn.close()


def test_balance_subtracts_new_planted(tmp_project):
    """balance = consumed − 本章新种悬链数。"""
    conn = get_connection(tmp_project)
    _, cid, bid = _seed(conn)
    _plant_thread(conn, 1, bid)   # 本章新种 1 条（planted_at_beat 在本章 beat）
    _record(conn, 1, bid, "resolved", 5)  # consumed 1.0
    consumed, balance = compute_consumption(conn, cid)
    assert abs(consumed - 1.0) < 1e-6
    assert abs(balance - 0.0) < 1e-6   # 1.0 − 1 = 0.0
    conn.close()


def test_balance_negative_when_only_planting(tmp_project):
    conn = get_connection(tmp_project)
    _, cid, bid = _seed(conn)
    _plant_thread(conn, 1, bid)
    _plant_thread(conn, 2, bid)   # 新种 2，无消费
    consumed, balance = compute_consumption(conn, cid)
    assert consumed == 0.0
    assert abs(balance - (-2.0)) < 1e-6
    conn.close()
```

- [ ] **Step 2: 跑确认失败**（ModuleNotFoundError）

- [ ] **Step 3: 实现 `checks/consumption.py`**

```python
# src/bedrock/checks/consumption.py
"""悬链消费重算（authoritative，零 LLM）。
权重：resolved×1.0 + developing×0.5 + mature×0.5 + partially_resolved×0.5 + abandoned×0.3
（abandoned 计 0.3 防批量凑配额；developing/mature 视为推进 0.5）
balance = consumed − 本章新种悬链数"""
from src.bedrock.repositories.plot_tree import list_beats_in_chapter

_WEIGHTS = {
    "resolved": 1.0,
    "developing": 0.5,
    "mature": 0.5,
    "partially_resolved": 0.5,
    "abandoned": 0.3,
}


def _global_chapter_number(conn, chapter_id):
    row = conn.execute("SELECT global_number FROM chapter WHERE id=?", (chapter_id,)).fetchone()
    return row["global_number"] if row else None


def compute_consumption(conn, chapter_id):
    """返回 (consumed, balance)。无记录 → (0.0, 0.0)。"""
    gnum = _global_chapter_number(conn, chapter_id)
    if gnum is None:
        return (0.0, 0.0)

    rows = conn.execute(
        "SELECT new_status FROM thread_consumption WHERE chapter=?", (gnum,)).fetchall()
    consumed = sum(_WEIGHTS.get(r["new_status"], 0.0) for r in rows)

    # 本章新种悬链 = planted_at_beat 落在本章某 beat 上的 suspense_thread 数
    beat_ids = [b["id"] for b in list_beats_in_chapter(conn, chapter_id)]
    planted = 0
    if beat_ids:
        placeholders = ",".join("?" * len(beat_ids))
        planted = conn.execute(
            f"SELECT COUNT(*) AS n FROM suspense_thread WHERE planted_at_beat IN ({placeholders})",
            beat_ids).fetchone()["n"]

    balance = consumed - planted
    return (consumed, balance)
```

- [ ] **Step 4: 跑确认通过**（4 passed）+ 全量回归 → 85 + 4 = 89

- [ ] **Step 5: Commit**
```bash
git add src/bedrock/checks/consumption.py tests/bedrock/test_consumption.py
git commit -m "feat(bedrock): suspense consumption recompute (consumed/balance)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: L2 bundle + L2Report（l2_pipeline）

**Files:**
- Create: `src/bedrock/orchestration/__init__.py`（空）
- Create: `src/bedrock/orchestration/l2_pipeline.py`
- Test: `tests/bedrock/test_l2_pipeline.py`

**依赖**：SP2 `check_beat_fulfillment`/`check_cross_volume_anchors`、Task 2/3/4、SP1 `list_paragraphs_in_chapter`/`get_chapter_metrics`。

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_l2_pipeline.py
from src.bedrock.db.connection import get_connection
from src.bedrock.orchestration.l2_pipeline import run_l2, L2Report
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat, create_paragraph,
)
from src.bedrock.repositories.outline import (
    save_volume_outline, lock_volume_outline, unlock_volume_outline, update_beat_contract,
)


def _seed_clean(conn):
    """一个 beat clean 的章节（角色出场 + 段落）。"""
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="林深出场")
    create_paragraph(conn, chapter_id=cid, seq=1, text="林深推开门走了进来。",
                     content_hash="h", beat_id=bid, role="narration")
    save_volume_outline(conn, vid, beat_contracts=[])
    lock_volume_outline(conn, vid)
    unlock_volume_outline(conn, vid, reason="setup", author="system")
    update_beat_contract(conn, vid, beat_id=bid,
                         new_contract={"purpose": "林深出场", "participating_characters": [], "advance_threads": []})
    return vid, cid, bid


def test_l2report_shape(tmp_project):
    conn = get_connection(tmp_project)
    _, cid, _ = _seed_clean(conn)
    # 标记 beat 为 written（create_beat 默认 planned，需推进状态——见实现注意）
    report = run_l2(conn, cid)
    assert isinstance(report, L2Report)
    assert "grep" in report.advisory
    assert "consumption" in report.advisory
    assert "word_count" in report.metrics
    assert isinstance(report.passed_hard_gate, bool)
    assert isinstance(report.drift, dict)
    conn.close()


def test_hard_gate_fails_on_unwritten_beat(tmp_project):
    """planned beat → unwritten_beat violation → passed_hard_gate False。"""
    conn = get_connection(tmp_project)
    _, cid, bid = _seed_clean(conn)
    # 不推进 beat 状态（保持 planned）
    # 删掉刚写的段落让 beat 真 planned
    conn.execute("DELETE FROM paragraph WHERE chapter_id=?", (cid,))
    conn.commit()
    report = run_l2(conn, cid)
    assert report.passed_hard_gate is False
    assert any(v.kind == "unwritten_beat" for v in report.beat_violations)
    conn.close()


def test_drift_detection(tmp_project):
    """declared word_count 与重算差超 10% → drift[word_count].drifted True。"""
    conn = get_connection(tmp_project)
    _, cid, _ = _seed_clean(conn)
    # 先写一个 declared（agent 自报 9999，实际约 10 → 远超 10% 偏差）
    from src.bedrock.repositories.telemetry import write_chapter_metrics
    write_chapter_metrics(conn, cid, word_count=9999, declared={"word_count_declared": 9999})
    report = run_l2(conn, cid)
    assert report.drift.get("word_count", {}).get("drifted") is True
    conn.close()


def test_advisory_populated(tmp_project):
    conn = get_connection(tmp_project)
    _, cid, _ = _seed_clean(conn)
    report = run_l2(conn, cid)
    assert "notXisY_per_kchar" in report.advisory["grep"]
    assert "consumed" in report.advisory["consumption"]
    conn.close()
```

> **beat 状态推进注意**：`create_beat` 创建的 beat 默认 `planned`。要让 beat "clean"，需把 beat 状态推进到 written（具体 repository 函数名由 plot_tree 提供——若 `create_beat` 后默认即 written 则无需；若需 `update_beat_status`/`mark_beat_written` 之类，实现时查 plot_tree.py）。`_seed_clean` 中若默认 planned，需在 seed 后推进状态。**实现 Step 3 前先读 `src/bedrock/repositories/plot_tree.py` 确认 beat 状态推进函数**；若无现成函数，seed 用 SQL `UPDATE beat SET status='written' WHERE id=?`。

- [ ] **Step 2: 跑确认失败**（ModuleNotFoundError）

- [ ] **Step 3: 实现 `orchestration/l2_pipeline.py`**

```python
# src/bedrock/orchestration/l2_pipeline.py
from dataclasses import dataclass, field
from src.bedrock.repositories.plot_tree import list_paragraphs_in_chapter
from src.bedrock.repositories.telemetry import get_chapter_metrics
from src.bedrock.checks.beat_fulfillment import check_beat_fulfillment
from src.bedrock.checks.cross_volume import check_cross_volume_anchors
from src.bedrock.checks.word_count import compute_word_count
from src.bedrock.checks.grep_metrics import compute_grep_metrics
from src.bedrock.checks.consumption import compute_consumption

DRIFT_THRESHOLD = 0.10  # |Δ|/recomputed > 10% → drifted


def _volume_id_of_chapter(conn, chapter_id):
    row = conn.execute("SELECT volume_id FROM chapter WHERE id=?", (chapter_id,)).fetchone()
    return row["volume_id"] if row else None


def _drift_metric(declared, recomputed):
    """单指标 drift 检测。返回 {declared, recomputed, drifted}。"""
    if declared is None or recomputed in (None, 0):
        return {"declared": declared, "recomputed": recomputed, "drifted": False}
    delta = abs(declared - recomputed)
    drifted = (delta / abs(recomputed)) > DRIFT_THRESHOLD
    return {"declared": declared, "recomputed": recomputed, "drifted": drifted}


@dataclass
class L2Report:
    beat_violations: list = field(default_factory=list)
    advisory: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    drift: dict = field(default_factory=dict)
    passed_hard_gate: bool = True


def run_l2(conn, chapter_id):
    """跑全部 L2 重算，分流硬门禁/advisory，检测 drift。纯 Python 零 LLM。"""
    volume_id = _volume_id_of_chapter(conn, chapter_id)
    paragraphs = [p["text"] for p in list_paragraphs_in_chapter(conn, chapter_id)]

    # 硬门禁：beat 兑现
    beat_violations = check_beat_fulfillment(conn, chapter_id)

    # advisory 重算
    grep = compute_grep_metrics(paragraphs)
    consumed, balance = compute_consumption(conn, chapter_id)
    cross = None
    if volume_id is not None:
        cross = check_cross_volume_anchors(conn, volume_id)

    # authoritative metrics
    wc = compute_word_count(paragraphs)
    total_beats = len([b for b in __import__(
        "src.bedrock.repositories.plot_tree", fromlist=["list_beats_in_chapter"]
    ).list_beats_in_chapter(conn, chapter_id)])
    unwritten = sum(1 for v in beat_violations if v.kind == "unwritten_beat")
    beat_yield = ((total_beats - unwritten) / total_beats) if total_beats else 0.0

    metrics = {
        "word_count": wc,
        "grep_metrics": grep,
        "threads_consumed": consumed,
        "consumption_balance": balance,
        "beat_yield_rate": beat_yield,
    }

    # drift：对比既有 chapter_metrics.declared_json
    drift = {}
    prev = get_chapter_metrics(conn, chapter_id)
    if prev is not None:
        import json
        declared = json.loads(prev["declared_json"]) if prev["declared_json"] else {}
        if "word_count_declared" in declared:
            drift["word_count"] = _drift_metric(declared["word_count_declared"], wc)

    advisory = {"grep": grep, "consumption": {"consumed": consumed, "balance": balance}}
    if cross is not None:
        advisory["cross_volume"] = cross

    return L2Report(
        beat_violations=beat_violations,
        advisory=advisory,
        metrics=metrics,
        drift=drift,
        passed_hard_gate=(len(beat_violations) == 0),
    )
```

- [ ] **Step 4: 跑确认通过**（4 passed）+ 全量回归 → 89 + 4 = 93

- [ ] **Step 5: Commit**
```bash
git add src/bedrock/orchestration/__init__.py src/bedrock/orchestration/l2_pipeline.py tests/bedrock/test_l2_pipeline.py
git commit -m "feat(bedrock): L2 pipeline bundle (hard gate + advisory + drift)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: boot context 装配

**Files:**
- Create: `src/bedrock/orchestration/boot_context.py`
- Test: `tests/bedrock/test_boot_context.py`

**依赖**：SP1 `list_beats_in_chapter`/`get_beat_contract`、SP3 `get_effective_fingerprint`、SP1 `character_secret`（reader_disclosure public 过滤）、`config/volume_type_matrix`。

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_boot_context.py
from src.bedrock.db.connection import get_connection
from src.bedrock.orchestration.boot_context import get_chapter_boot_context
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat, create_paragraph
from src.bedrock.repositories.outline import (
    save_volume_outline, lock_volume_outline, unlock_volume_outline, update_beat_contract,
)
from src.bedrock.style.template_repo import save_fingerprint


def _seed(conn):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="p")
    create_paragraph(conn, chapter_id=cid, seq=1, text="x。",
                     content_hash="h", beat_id=bid, role="narration")
    save_volume_outline(conn, vid, beat_contracts=[])
    lock_volume_outline(conn, vid)
    unlock_volume_outline(conn, vid, reason="setup", author="system")
    update_beat_contract(conn, vid, beat_id=bid,
                         new_contract={"purpose": "p", "participating_characters": [], "advance_threads": []})
    save_fingerprint(conn, scope="work", chapter_ids=[cid])
    return vid, cid


def test_boot_context_has_required_keys(tmp_project):
    conn = get_connection(tmp_project)
    vid, cid = _seed(conn)
    ctx = get_chapter_boot_context(conn, chapter_id=cid, volume_id=vid)
    assert "beat_contracts" in ctx
    assert "fingerprint" in ctx
    assert "constants" in ctx
    assert isinstance(ctx["beat_contracts"], list)
    conn.close()


def test_boot_context_no_fingerprint_handled(tmp_project):
    """无指纹时不抛（get_effective_fingerprint 返回 None）。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    save_volume_outline(conn, vid, beat_contracts=[])
    ctx = get_chapter_boot_context(conn, chapter_id=cid, volume_id=vid)
    assert ctx["fingerprint"] is None
    conn.close()


def test_boot_context_reader_secrets_filtered(tmp_project):
    """只含 reader_disclosure public 的 secret（visibility 过滤）。"""
    conn = get_connection(tmp_project)
    vid, cid = _seed(conn)
    # 插一条 public reader secret + 一条 secret_until（应被过滤）
    conn.execute(
        "INSERT INTO character_secret(character_id,key,value,vis_mode,vis_axis,vis_ref) "
        "VALUES(1,'pub','v','public','reader_disclosure','{}')")
    conn.execute(
        "INSERT INTO character_secret(character_id,key,value,vis_mode,vis_axis,vis_ref) "
        "VALUES(1,'sec','v','secret_until','reader_disclosure','{}')")
    conn.commit()
    ctx = get_chapter_boot_context(conn, chapter_id=cid, volume_id=vid)
    keys = [s["key"] for s in ctx["reader_disclosed_secrets"]]
    assert "pub" in keys
    assert "sec" not in keys
    conn.close()
```

- [ ] **Step 2: 跑确认失败**（ModuleNotFoundError）

- [ ] **Step 3: 实现 `orchestration/boot_context.py`**

```python
# src/bedrock/orchestration/boot_context.py
"""装配子代理启动上下文：beat 契约 + reader-disclosed secrets + StyleTemplate 指纹 + constants。"""
from src.bedrock.repositories.plot_tree import list_beats_in_chapter
from src.bedrock.repositories.outline import get_beat_contract
from src.bedrock.style.template_repo import get_effective_fingerprint


def _reader_disclosed_secrets(conn):
    """只取 reader_disclosure 轴 + public vis_mode 的 secret（不泄露 secret_until/faction）。"""
    rows = conn.execute(
        "SELECT character_id, key, value FROM character_secret "
        "WHERE vis_axis='reader_disclosure' AND vis_mode='public'").fetchall()
    return [dict(r) for r in rows]


def get_chapter_boot_context(conn, chapter_id, volume_id):
    """返回 {beat_contracts, reader_disclosed_secrets, fingerprint, constants}。"""
    beat_contracts = []
    for beat in list_beats_in_chapter(conn, chapter_id):
        c = get_beat_contract(conn, volume_id, beat["id"])
        if c:
            beat_contracts.append(c)

    fingerprint = get_effective_fingerprint(conn, volume_id)  # 两级 fallback，None 时不抛

    constants = {
        "drift_threshold": 0.10,
        "max_edit_rounds": 3,
        "word_count_target": (3000, 5000),
    }

    return {
        "beat_contracts": beat_contracts,
        "reader_disclosed_secrets": _reader_disclosed_secrets(conn),
        "fingerprint": fingerprint,
        "constants": constants,
    }
```

- [ ] **Step 4: 跑确认通过**（3 passed）+ 全量回归 → 93 + 3 = 96

- [ ] **Step 5: Commit**
```bash
git add src/bedrock/orchestration/boot_context.py tests/bedrock/test_boot_context.py
git commit -m "feat(bedrock): chapter boot context assembly

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: 强制落盘门禁（persist_gate）

**Files:**
- Create: `src/bedrock/orchestration/persist_gate.py`
- Test: `tests/bedrock/test_persist_gate.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_persist_gate.py
from src.bedrock.db.connection import get_connection
from src.bedrock.orchestration.persist_gate import verify_chapter_persisted
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat, create_paragraph,
)


def _seed(conn, write_paragraph=True):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    if write_paragraph:
        bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="p")
        create_paragraph(conn, chapter_id=cid, seq=1, text="x.",
                         content_hash="h", beat_id=bid, role="narration")
    return vid, cid


def test_persisted_when_paragraphs_exist(tmp_project):
    conn = get_connection(tmp_project)
    _, cid = _seed(conn, write_paragraph=True)
    assert verify_chapter_persisted(conn, cid) is True
    conn.close()


def test_not_persisted_when_no_paragraphs(tmp_project):
    conn = get_connection(tmp_project)
    _, cid = _seed(conn, write_paragraph=False)
    assert verify_chapter_persisted(conn, cid) is False
    conn.close()


def test_export_file_check_optional(tmp_project):
    """传 export_path：文件存在才 True；不传则只查 DB。"""
    import os
    conn = get_connection(tmp_project)
    _, cid = _seed(conn, write_paragraph=True)
    # 文件不存在 → False
    assert verify_chapter_persisted(conn, cid, export_path=str(tmp_project / "nope.txt")) is False
    # 文件存在 → True
    p = tmp_project / "ch.txt"; p.write_text("正文", encoding="utf-8")
    assert verify_chapter_persisted(conn, cid, export_path=str(p)) is True
    conn.close()
```

- [ ] **Step 2: 跑确认失败**（ModuleNotFoundError）

- [ ] **Step 3: 实现 `orchestration/persist_gate.py`**

```python
# src/bedrock/orchestration/persist_gate.py
import os
from src.bedrock.repositories.plot_tree import list_paragraphs_in_chapter


def verify_chapter_persisted(conn, chapter_id, export_path=None):
    """强制落盘门禁：paragraphs 入 DB（主，SSOT）+ 可选导出文件存在性。
    paragraphs 行数 == 0 → False（治 Vol15 未落盘）。
    export_path 传入且文件不存在 → False；不传则跳过文件检查。"""
    paragraphs = list_paragraphs_in_chapter(conn, chapter_id)
    if len(paragraphs) == 0:
        return False
    if export_path is not None and not os.path.exists(export_path):
        return False
    return True
```

- [ ] **Step 4: 跑确认通过**（3 passed）+ 全量回归 → 96 + 3 = 99

- [ ] **Step 5: Commit**
```bash
git add src/bedrock/orchestration/persist_gate.py tests/bedrock/test_persist_gate.py
git commit -m "feat(bedrock): forced-persist gate (paragraphs + optional export)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: 诊断标记写回（review_flag）

**Files:**
- Create: `src/bedrock/orchestration/review_flag.py`
- Test: `tests/bedrock/test_review_flag.py`

**依赖**：Task 1 的 `chapter_review_flag` 表。

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_review_flag.py
from src.bedrock.db.connection import get_connection
from src.bedrock.orchestration.review_flag import (
    mark_unresolved, mark_polish_broke_beat, mark_forced_persist_failed,
    get_review_flag,
)
from src.bedrock.checks.beat_fulfillment import BeatViolation
from src.bedrock.repositories.plot_tree import create_volume, create_chapter


def _seed(conn):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    return vid, cid


def test_mark_unresolved(tmp_project):
    conn = get_connection(tmp_project)
    _, cid = _seed(conn)
    viols = [BeatViolation(beat_id=1, kind="missing_character", detail="林深未出场", fix_hint="加林深")]
    mark_unresolved(conn, cid, viols, likely_rule_or_model_issue=True)
    flag = get_review_flag(conn, cid)
    assert flag["l2_unresolved"] == 1
    assert flag["likely_rule_or_model_issue"] == 1
    import json
    pv = json.loads(flag["persisted_violations"])
    assert len(pv) == 1
    assert pv[0]["kind"] == "missing_character"
    conn.close()


def test_mark_polish_broke_beat(tmp_project):
    conn = get_connection(tmp_project)
    _, cid = _seed(conn)
    mark_polish_broke_beat(conn, cid)
    assert get_review_flag(conn, cid)["polish_broke_beat"] == 1
    conn.close()


def test_mark_forced_persist_failed(tmp_project):
    conn = get_connection(tmp_project)
    _, cid = _seed(conn)
    mark_forced_persist_failed(conn, cid)
    assert get_review_flag(conn, cid)["forced_persist_failed"] == 1
    conn.close()


def test_get_review_flag_none_when_absent(tmp_project):
    conn = get_connection(tmp_project)
    _, cid = _seed(conn)
    assert get_review_flag(conn, cid) is None
    conn.close()
```

- [ ] **Step 2: 跑确认失败**（ModuleNotFoundError）

- [ ] **Step 3: 实现 `orchestration/review_flag.py`**

```python
# src/bedrock/orchestration/review_flag.py
"""chapter_review_flag 写回（SP5 VolumeReview 消费）。"""
import json
from dataclasses import asdict


def _beat_violation_to_dict(v):
    """BeatViolation dataclass → dict（含 fix_hint/detail）。"""
    try:
        return asdict(v)
    except TypeError:
        return {"beat_id": getattr(v, "beat_id", None), "kind": getattr(v, "kind", ""),
                "detail": getattr(v, "detail", ""), "fix_hint": getattr(v, "fix_hint", "")}


def _upsert(conn, chapter_id, fields):
    """INSERT OR UPDATE chapter_review_flag（保留既有列）。"""
    conn.execute(
        "INSERT INTO chapter_review_flag(chapter_id) VALUES(?) "
        "ON CONFLICT(chapter_id) DO NOTHING", (chapter_id,))
    set_clause = ", ".join(f"{k}=?" for k in fields)
    conn.execute(
        f"UPDATE chapter_review_flag SET {set_clause} WHERE chapter_id=?",
        [*fields.values(), chapter_id])
    conn.commit()


def mark_unresolved(conn, chapter_id, persisted_violations, likely_rule_or_model_issue):
    """3 轮重试耗尽：l2_unresolved=1 + persisted_violations JSON。"""
    pv = [_beat_violation_to_dict(v) for v in persisted_violations]
    _upsert(conn, chapter_id, {
        "l2_unresolved": 1,
        "persisted_violations": json.dumps(pv, ensure_ascii=False),
        "likely_rule_or_model_issue": 1 if likely_rule_or_model_issue else 0,
    })


def mark_polish_broke_beat(conn, chapter_id):
    _upsert(conn, chapter_id, {"polish_broke_beat": 1})


def mark_forced_persist_failed(conn, chapter_id):
    _upsert(conn, chapter_id, {"forced_persist_failed": 1})


def get_review_flag(conn, chapter_id):
    row = conn.execute(
        "SELECT * FROM chapter_review_flag WHERE chapter_id=?", (chapter_id,)).fetchone()
    return dict(row) if row else None
```

- [ ] **Step 4: 跑确认通过**（4 passed）+ 全量回归 → 99 + 4 = 103

- [ ] **Step 5: Commit**
```bash
git add src/bedrock/orchestration/review_flag.py tests/bedrock/test_review_flag.py
git commit -m "feat(bedrock): chapter_review_flag write helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: delete_volume_fingerprint 助手（SP3 carry-forward I1）

**Files:**
- Modify: `src/bedrock/style/template_repo.py`
- Modify: `tests/bedrock/test_template_repo.py`（追加用例）

- [ ] **Step 1: 追加失败测试到 test_template_repo.py**

在 `tests/bedrock/test_template_repo.py` 末尾追加（需更新顶部 import 加 `delete_volume_fingerprint`）：

```python
def test_delete_volume_fingerprint_clears_then_reinsert(tmp_project):
    """I1: save_fingerprint 卷级无 upsert。delete_volume_fingerprint 先清旧行再 save，保证一卷一行。"""
    from src.bedrock.style.template_repo import (
        save_fingerprint, delete_volume_fingerprint, get_effective_fingerprint,
    )
    conn = get_connection(tmp_project)
    vid, cid = _seed_paragraphs(conn, ["他来了。", "她走了。"])
    save_fingerprint(conn, scope="volume", chapter_ids=[cid], volume_id=vid)
    # 再 save 一次（无 upsert → 插第二行）
    save_fingerprint(conn, scope="volume", chapter_ids=[cid], volume_id=vid)
    # delete 后只剩待重插
    delete_volume_fingerprint(conn, volume_id=vid)
    rows = conn.execute("SELECT fingerprint FROM style_template").fetchall()
    vol_rows = [r for r in rows if json.loads(r["fingerprint"]).get("_scope") == "volume"
                and json.loads(r["fingerprint"]).get("_volume_id") == vid]
    assert len(vol_rows) == 0
    # 重新 save → 恰好一行
    save_fingerprint(conn, scope="volume", chapter_ids=[cid], volume_id=vid)
    vol_rows = [r for r in conn.execute("SELECT fingerprint FROM style_template").fetchall()
                if json.loads(r["fingerprint"]).get("_scope") == "volume"
                and json.loads(r["fingerprint"]).get("_volume_id") == vid]
    assert len(vol_rows) == 1
    conn.close()
```

> 顶部 import 需 `import json`（若已有则跳过）并加 `delete_volume_fingerprint`。`_seed_paragraphs` 已在该测试文件定义（Task 3 seed helper）。

- [ ] **Step 2: 跑确认失败**（ImportError: cannot import delete_volume_fingerprint）

- [ ] **Step 3: 在 `style/template_repo.py` 追加函数**

在 `src/bedrock/style/template_repo.py` 末尾追加：

```python
def delete_volume_fingerprint(conn, volume_id):
    """I1 upsert 助手：删除某 volume 的卷级指纹行（调用方在 save_fingerprint 前调）。
    作品级指纹不动。"""
    import json
    rows = conn.execute("SELECT id, fingerprint FROM style_template").fetchall()
    to_delete = []
    for r in rows:
        fp = json.loads(r["fingerprint"])
        if fp.get("_scope") == "volume" and fp.get("_volume_id") == volume_id:
            to_delete.append(r["id"])
    if to_delete:
        placeholders = ",".join("?" * len(to_delete))
        conn.execute(f"DELETE FROM style_template WHERE id IN ({placeholders})", to_delete)
        conn.commit()
```

- [ ] **Step 4: 跑确认通过**（新增 1 passed，原 5 仍过）+ 全量回归 → 103 + 1 = 104

- [ ] **Step 5: Commit**
```bash
git add src/bedrock/style/template_repo.py tests/bedrock/test_template_repo.py
git commit -m "feat(bedrock): delete_volume_fingerprint helper (SP3 I1 upsert)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: CLI 扩展

**Files:**
- Modify: `src/bedrock/__main__.py`（追加子命令）

**依赖**：Task 5/6/7/8。

- [ ] **Step 1: 读现有 `__main__.py` 结构**

Run: `cd D:/novel_test && cat src/bedrock/__main__.py`
确认子命令分发模式（argparse subparsers 或 if/elif），追加新命令时遵循同样模式。

- [ ] **Step 2: 追加 4 个子命令**

在 `src/bedrock/__main__.py` 中追加（按现有 subparser 模式）：
- `run-l2 --project P --chapter N` → `get_connection` + `run_l2(conn, cid)` → 打印 L2Report 摘要（passed_hard_gate / violation count / drift）
- `boot-context --project P --chapter N --volume V` → `get_chapter_boot_context` → JSON 打印
- `verify-persisted --project P --chapter N [--export-path PATH]` → `verify_chapter_persisted` → 打印 True/False
- `mark-unresolved --project P --chapter N --rule-or-model 0|1` → 读 stdin JSON violations + `mark_unresolved`

每个命令通过 `from src.bedrock.db.connection import get_connection` + `from src.bedrock.orchestration...` 调用。chapter N → chapter_id：`SELECT id FROM chapter WHERE global_number=?`。

具体实现依现有 `__main__.py` 的 argparse 结构对齐（**实现前先读，保持风格一致**）。

- [ ] **Step 3: 冒烟测试每个命令**

```bash
cd D:/novel_test
# 准备一个 seed 项目（用现有测试 fixture 思路或临时脚本）
python -m src.bedrock run-l2 --project <test_project> --chapter 1
python -m src.bedrock boot-context --project <test_project> --chapter 1 --volume 1
python -m src.bedrock verify-persisted --project <test_project> --chapter 1
```
Expected: 各命令无 traceback，输出合理（JSON 或摘要）。

> 若无现成 seed 项目，写一个临时 `python -c "..."` 脚本 init + seed 一章，跑通后删。**不强求自动化测试**（CLI 是薄封装，逻辑在已测的 Python 函数）。

- [ ] **Step 4: 全量回归** → 104（无新测试，CLI 不加单测）

- [ ] **Step 5: Commit**
```bash
git add src/bedrock/__main__.py
git commit -m "feat(bedrock): CLI for run-l2/boot-context/verify-persisted/mark-unresolved

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Agent 编排层（prompt 模板 + Workflow JS）

**Files:**
- Create: `.claude/templates/bedrock/chapter_writer.md`
- Create: `.claude/templates/bedrock/edit_agent.md`
- Create: `.claude/workflows/bedrock-chapter.js`

**说明**：端到端验证留 SP5。本 Task 只产出模板 + Workflow JS 骨架，人工 review 结构 + SP3 prompt 嵌入正确性。

- [ ] **Step 1: 写 ChapterWriter prompt 模板**

`.claude/templates/bedrock/chapter_writer.md`：

```markdown
# ChapterWriter 子代理

你为《绝地天通》（磐石 V3 管线）写一章初稿。

## 输入（boot context，由主编排注入）
- beat_contracts：本章 beat 契约列表（purpose / participating_characters / advance_threads）
- reader_disclosed_secrets：读者已知秘密（仅 public reader_disclosure，勿泄露 secret_until）
- fingerprint：StyleTemplate 目标分布（首次卷可能为 null → 按通用网文风格）
- constants：{drift_threshold, max_edit_rounds, word_count_target:(3000,5000)}

## 任务
1. 严格按 beat_contracts 顺序写段落，每个 beat 一段或多段
2. participating_characters 必须在对应 beat 段落出场（名字出现）
3. advance_threads 的悬链必须有实质推进（会由 L2 重算 cross-check，自报无效）
4. 字数 3000-5000 汉字
5. 风格：网文短段落、感官描写、第三人称有限视角；「不是X，是Y」句式每章≤5；破折号每千字≤3

## 输出
通过 CLI `write-paragraphs` 把段落写入 DB（按 beat 分段，content_hash 唯一）。
**不要**自报字数——系统会重算（authoritative），自报偏差>10% 会被 drift 标记。
```

- [ ] **Step 2: 写 Edit agent prompt 模板**

`.claude/templates/bedrock/edit_agent.md`：

```markdown
# Edit 子代理（润色 + 定向修复）

主编排会注入两类 prompt 之一（或两者）：

## A. PolishPrompt（正向润色，beat 已 clean 时）
- target_distribution：目标分布（句长/段落长/感官等直方图）——对准此分布修
- beat_contracts：保持剧情契约
- 要求：对准分布 / 保持剧情完整 / 不压缩字数 / 输出完整章节

## B. RepairPrompt（定向修复，beat 违规时）
- violations：BeatViolation[]（beat_id / kind / detail / fix_hint）——从结构化字段读完整 detail
- 要求：只改违规段落，不动其他 / 不引入新违规 / 不压缩剧情 / 输出完整章节

## 关键约束
- repair 时优先级：修复违规 > 润色。两者可同轮做，但不得因润色破坏已 clean 的 beat
- 修改通过 CLI `write-paragraphs` 写回 DB（覆盖该 beat 段落）
- **自报无效**：word_count/editing_corrections 由系统重算（L2 重算覆盖自报）
```

- [ ] **Step 3: 写 Workflow JS conductor**

`.claude/workflows/bedrock-chapter.js`（骨架，端到端跑通留 SP5）：

```javascript
export const meta = {
  name: 'bedrock-chapter',
  description: '磐石 V3 单章抗博弈管线：Boot→Write→L2→Edit(3轮软门禁)→Persist→Telemetry',
  phases: [
    { title: 'Boot' },
    { title: 'Write' },
    { title: 'L2+Repair' },
    { title: 'Polish' },
    { title: 'Persist+Telemetry' },
  ],
}

// args: { project, chapter, volume, exportPath }
export default async function ({ project, chapter, volume, exportPath }) {
  // 1. Boot（Python CLI，主编排采集）
  phase('Boot')
  const ctx = await pythonCli(`boot-context --project ${project} --chapter ${chapter} --volume ${volume}`)
  log('boot context assembled')

  // 2. Write（派生 ChapterWriter）
  phase('Write')
  const writeResult = await agent(chapterWriterPrompt(ctx), { label: 'ChapterWriter', phase: 'Write' })
  // 采集 token/tool（黑墙，从 SDK usage）——见 telemetry

  // 3. L2 + Repair 循环（≤3 轮）
  phase('L2+Repair')
  let report = await pythonCli(`run-l2 --project ${project} --chapter ${chapter}`)
  let round = 0
  const violationSignaturesByRound = []  // 跨轮比对，诊断 likely_rule_or_model_issue
  while (!report.passed_hard_gate && round < 3) {
    const sigs = report.beat_violations.map(v => `${v.beat_id}:${v.kind}`).sort().join(',')
    violationSignaturesByRound.push(sigs)
    // Edit repair：RepairPrompt（结构化字段）+ PolishPrompt
    await agent(editRepairPrompt(report), { label: `Edit-repair-r${round + 1}`, phase: 'L2+Repair' })
    report = await pythonCli(`run-l2 --project ${project} --chapter ${chapter}`)
    round++
  }
  // 诊断：同一签名多轮不变 → likely_rule_or_model_issue
  const likelyRuleOrModel = round === 3 && new Set(violationSignaturesByRound.slice(-2)).size === 1
      && !report.passed_hard_gate
  if (!report.passed_hard_gate) {
    await pythonCli(`mark-unresolved --project ${project} --chapter ${chapter} --rule-or-model ${likelyRuleOrModel ? 1 : 0}`,
                    { stdin: JSON.stringify(report.beat_violations) })
    log(`l2 unresolved after 3 rounds, likely_rule_or_model_issue=${likelyRuleOrModel}`)
  }

  // 4. Polish（beat clean 时）
  phase('Polish')
  if (report.passed_hard_gate) {
    await agent(editPolishPrompt(ctx), { label: 'Edit-polish', phase: 'Polish' })
    const after = await pythonCli(`run-l2 --project ${project} --chapter ${chapter}`)
    if (!after.passed_hard_gate) {
      await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${chapter}`)
      log('polish introduced beat violation, flagged')
    }
  }

  // 5. Persist + Telemetry
  phase('Persist+Telemetry')
  const persisted = await pythonCli(`verify-persisted --project ${project} --chapter ${chapter} ${exportPath ? '--export-path ' + exportPath : ''}`)
  if (persisted !== 'True') {
    await pythonCli(`mark-forced-persist-failed --project ${project} --chapter ${chapter}`)
    return { status: 'failed', reason: 'forced_persist_failed' }
  }
  // 遥测：用 SP1 record_agent_invocation / record_llm_call 落黑墙（token 从各 agent 汇报）
  await pythonCli(`collect-runtime --project ${project} --chapter ${chapter} --editing-rounds ${round}`,
                  { stdin: JSON.stringify({ invocations: [], llm_calls: [] }) })
  return { status: 'ok', chapter, rounds: round, passed: report.passed_hard_gate }
}

// 以下为 prompt 构造助手（从 SP3 结构化字段，非 to_string()——I2 落地）
function chapterWriterPrompt(ctx) { /* 嵌入 chapter_writer.md + ctx JSON */ }
function editRepairPrompt(report) {
  // 从 RepairPrompt.violations（含 detail/fix_hint）构造，非纯 to_string
}
function editPolishPrompt(ctx) {
  // 从 PolishPrompt.beat_contracts + target_distribution 构造
}
// pythonCli：封装 `python -m src.bedrock <cmd>`，读 stdout/传 stdin
```

- [ ] **Step 4: 人工 review**

通读三个文件，确认：
- prompt 模板嵌入 SP3 prompt 字段正确（RepairPrompt.violations 含 detail/fix_hint，非只 to_string——I2）
- Workflow JS 重试循环 ≤3、likely_rule_or_model_issue 跨轮比对逻辑正确
- persist 失败 → status=failed（强制落盘门禁）
- 编辑半径：`pythonCli`/`agent`/`phase`/`log` 是 Workflow 运行时提供（实际函数体留 SP5 端到端调通时填，**本 Task 只产骨架**）

- [ ] **Step 5: 全量回归**（agent 层不加单测）→ 104

- [ ] **Step 6: Commit**
```bash
git add .claude/templates/bedrock/chapter_writer.md .claude/templates/bedrock/edit_agent.md .claude/workflows/bedrock-chapter.js
git commit -m "feat(bedrock): agent orchestration layer (ChapterWriter/Edit prompts + Workflow JS)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review 自检

**1. Spec 覆盖**：
- §三① grep_metrics → Task 3 ✓
- §三② consumption → Task 4 ✓
- §三③ word_count → Task 2 ✓
- §三④ l2_pipeline + L2Report → Task 5 ✓
- §三⑤ boot_context → Task 6 ✓
- §三⑥ telemetry_collect → **YAGNI 砍除**（SP1 已有 write_chapter_metrics/record_agent_invocation/record_llm_call，Workflow JS 直接调；spec §三⑥ 的职责落到 Task 11 Workflow JS 的 collect-runtime 步骤）✓
- §三⑦ persist_gate → Task 7 ✓
- §三⑧ review_flag → Task 8 ✓
- §四一章流水线 → Task 11 Workflow JS ✓
- §五重试/诊断（drift 10%、likely_rule_or_model 跨轮比对）→ Task 5（drift）+ Task 8（mark）+ Task 11（跨轮比对）✓
- §六遥测字段 → Task 5 metrics + Task 11 collect-runtime（SP1 落库）✓
- §七 chapter_review_flag 表 → Task 1 ✓
- §八 SP3 carry-forward：I1 delete_volume_fingerprint → Task 9 ✓；I2/M3 结构化字段 → Task 11 prompt 构造 ✓
- §十测试策略：Python 单测主体（Task 2-9）+ agent 人工 review/smoke（Task 11）+ 端到端留 SP5 ✓

**2. Placeholder 扫描**：
- Task 5 Step 1 测试注释提到「beat 状态推进函数」需读 plot_tree.py 确认——**这是实现时验证点，非 placeholder**（已给 SQL fallback `UPDATE beat SET status='written'`）。
- Task 10/11 的 CLI/Workflow JS 依赖现有 `__main__.py` 结构对齐——**实现时先读**，非 placeholder。
- 无 TBD/TODO/「类似 Task N」省略。

**3. 类型/签名一致性**：
- `compute_word_count(paragraphs) -> int`（Task 2）
- `compute_grep_metrics(paragraphs) -> dict`（Task 3）
- `compute_consumption(conn, chapter_id) -> tuple[float,float]`（Task 4）
- `run_l2(conn, chapter_id) -> L2Report`（Task 5；L2Report 字段 beat_violations/advisory/metrics/drift/passed_hard_gate）
- `get_chapter_boot_context(conn, chapter_id, volume_id) -> dict`（Task 6）
- `verify_chapter_persisted(conn, chapter_id, export_path=None) -> bool`（Task 7）
- `mark_unresolved/mark_polish_broke_beat/mark_forced_persist_failed/get_review_flag`（Task 8）
- `delete_volume_fingerprint(conn, volume_id)`（Task 9）
- SP1 复用：`write_chapter_metrics`/`record_agent_invocation`/`record_llm_call`/`get_chapter_metrics`/`list_paragraphs_in_chapter`/`list_beats_in_chapter`/`get_beat_contract`（均存在）✓
- SP2 复用：`check_beat_fulfillment`/`check_cross_volume_anchors`/`BeatViolation`（均存在）✓
- SP3 复用：`get_effective_fingerprint`/`save_fingerprint`/`PolishPrompt`/`RepairPrompt`（均存在）✓

**4. 依赖顺序**：Task 1（schema）→ 2/3/4（独立重算）→ 5（用 2/3/4+SP2）→ 6/7（独立）→ 8（用 1）→ 9（style 扩展）→ 10（CLI 用 5/6/7/8）→ 11（agent 用全部）。满足依赖 ✓

**5. 测试增量**：76（SP1-3）→ +4(word)+5(grep)+4(consumption)+4(l2)+3(boot)+3(persist)+4(review)+1(delete) = **104 测试**（spec §十预估 107，差异：telemetry 模块砍除 −3）。符合预期。

---

## 执行交接

计划完成，保存于 `docs/superpowers/plans/2026-06-14-bedrock-sp4-anti-gaming.md`。两种执行方式：

**1. Subagent-Driven（推荐）** — 每 Task 派新子代理 + 两阶段 review（spec + code quality），任务间 review。

**2. Inline Execution** — 当前会话 executing-plans 批量 + checkpoint。

选哪种？
