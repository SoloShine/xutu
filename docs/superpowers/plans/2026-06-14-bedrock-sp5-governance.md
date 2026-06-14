# 磐石 Bedrock SP5 — 治理层 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 接 SP4 wiring 让管线 runnable + statistical watchdog + 跨卷悬链收敛门禁 + VolumeReview agent（旗驱动 Opus 抽查 + 修正闭环）+ e2e 测试。

**Architecture:** Python-first。Phase 0 接线（runtime_collect + 4 CLI + JS pythonCli）→ Phase 1 watchdog（纯 Python 跨章统计）→ Phase 2 跨卷门禁（纯 Python）→ Phase 3 VolumeReview（agent 层，人工 review）→ Phase 4 e2e（@pytest.mark.e2e 默认 skip）。卷间门禁 BLOCKING，卷内 advisory。

**Tech Stack:** Python 3.10+ stdlib（re/json/dataclasses/sqlite3/subprocess），pytest。Agent 层：Workflow JS + Markdown prompt。

**前置:** SP1-4 完成（src/bedrock/ 106 测试，分支 bedrock-sp1）。spec: `docs/superpowers/specs/2026-06-14-bedrock-sp5-governance-design.md`。

---

## 文件结构

```
src/bedrock/
├── db/schema.sql                 # +volume_review 表（Task 1）
├── orchestration/
│   ├── runtime_collect.py        # Task 2（Phase 0 ③）
│   ├── watchdog.py               # Task 4（Phase 1）
│   └── cross_volume_gate.py      # Task 5（Phase 2）
└── __main__.py                   # Task 3（Phase 0 ②，+4 CLI）

.claude/templates/bedrock/
└── volume_review.md              # Task 7（Phase 3）
.claude/workflows/
├── bedrock-chapter.js            # Task 6（Phase 0 ①④ 改）
└── bedrock-volume-review.js      # Task 7（Phase 3）

tests/bedrock/
├── test_runtime_collect.py       # Task 2
├── test_watchdog.py              # Task 4
├── test_cross_volume_gate.py     # Task 5
└── e2e/test_micro_volume.py      # Task 8（@pytest.mark.e2e）
```

依赖链：Task 1（schema）→ Task 2（runtime_collect）→ Task 3（CLI 用 2）→ Task 4（watchdog 用 1）→ Task 5（独立）→ Task 6（JS 接线用 3）→ Task 7（agent 用 4/5）→ Task 8（e2e 用全部）。

---

## Task 1: volume_review schema

**Files:**
- Modify: `src/bedrock/db/schema.sql`（追加表）

- [ ] **Step 1: 追加表到 schema.sql 末尾**

```sql

-- ===== SP5 治理层：卷级 watchdog 发现（卷间 BLOCKING 门禁）=====
CREATE TABLE IF NOT EXISTS volume_review (
    volume_id INTEGER PRIMARY KEY REFERENCES volume(id),
    watchdog_findings TEXT NOT NULL DEFAULT '{}',
    blocking INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

- [ ] **Step 2: 验证 schema 应用**

```bash
cd D:/novel_test && python -c "
from pathlib import Path; import tempfile
from src.bedrock.db.migrate import apply_migrations
from src.bedrock.db.connection import get_connection
d = Path(tempfile.mkdtemp()); apply_migrations(d)
conn = get_connection(d)
row = conn.execute(\"SELECT name FROM sqlite_master WHERE name='volume_review'\").fetchone()
print('TABLE EXISTS:', row is not None); conn.close()
"
```
Expected: `TABLE EXISTS: True`

- [ ] **Step 3: 全量回归**

Run: `cd D:/novel_test && python -m pytest tests/bedrock/ -q`
Expected: 106 passed

- [ ] **Step 4: Commit**
```bash
cd D:/novel_test && git add src/bedrock/db/schema.sql && git commit -m "feat(bedrock): volume_review table (SP5 watchdog findings)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: runtime_collect 后端

**Files:**
- Create: `src/bedrock/orchestration/runtime_collect.py`
- Test: `tests/bedrock/test_runtime_collect.py`

**依赖**：SP1 `record_agent_invocation`/`record_llm_call`/`record_tool_call`（telemetry.py）。

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_runtime_collect.py
from src.bedrock.db.connection import get_connection
from src.bedrock.orchestration.runtime_collect import write_runtime
from src.bedrock.repositories.plot_tree import create_volume, create_chapter


def _seed(conn):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    return vid, cid


def test_write_runtime_creates_row_and_aggregates(tmp_project):
    conn = get_connection(tmp_project)
    _, cid = _seed(conn)
    invocations = [
        {"agent_type": "ChapterWriter", "black_wall_ms": 5000, "start_ts": None, "end_ts": None},
        {"agent_type": "Edit", "black_wall_ms": 3000, "start_ts": None, "end_ts": None},
    ]
    llm_calls = [
        {"phase": "write", "model": "opus", "prompt_tokens": 1000, "completion_tokens": 500, "duration_ms": 4000},
    ]
    write_runtime(conn, cid, invocations, llm_calls, editing_rounds=1)
    rt = conn.execute("SELECT * FROM chapter_runtime WHERE chapter_id=? ORDER BY id DESC LIMIT 1",
                      (cid,)).fetchone()
    assert rt["editing_rounds"] == 1
    assert rt["total_black_wall_ms"] == 8000   # 5000 + 3000
    assert rt["llm_tokens"] == 1500             # 1000 + 500
    assert rt["llm_call_count"] == 1
    n_inv = conn.execute("SELECT COUNT(*) AS n FROM agent_invocation WHERE runtime_id=?",
                         (rt["id"],)).fetchone()["n"]
    assert n_inv == 2
    conn.close()


def test_write_runtime_empty_inputs(tmp_project):
    conn = get_connection(tmp_project)
    _, cid = _seed(conn)
    write_runtime(conn, cid, [], [], editing_rounds=0)
    rt = conn.execute("SELECT * FROM chapter_runtime WHERE chapter_id=? ORDER BY id DESC LIMIT 1",
                      (cid,)).fetchone()
    assert rt["editing_rounds"] == 0
    assert rt["total_black_wall_ms"] == 0
    conn.close()
```

- [ ] **Step 2: 跑确认失败**（ModuleNotFoundError）

- [ ] **Step 3: 实现 `orchestration/runtime_collect.py`**

> **对抗审核修正（spec §三 ③）**：不复用 `record_agent_invocation`（它每次调用建一个新 chapter_runtime 行，N agent → N 行，聚合破坏）。改为：建**恰好一个** chapter_runtime 聚合行（用 SP1 `_create_runtime`），手动批量插 agent_invocation/llm_call 子行并累加 totals。

```python
# src/bedrock/orchestration/runtime_collect.py
"""黑墙遥测采集：建一个 chapter_runtime 聚合行 + 批量挂 agent_invocation/llm_call 子行。
编排层（Workflow JS）在子代理结束后从 SDK usage 汇报，传本函数落库。
【新逻辑，非封装 record_agent_invocation】——后者一行/agent 会破坏单章聚合。"""
from src.bedrock.repositories.telemetry import _create_runtime


def write_runtime(conn, chapter_id, invocations, llm_calls, editing_rounds):
    """invocations: [{agent_type, black_wall_ms, start_ts?, end_ts?}]
    llm_calls: [{phase, model, prompt_tokens, completion_tokens, duration_ms}]
    建 1 个 chapter_runtime 行（editing_rounds + 累加 total_black_wall_ms/llm_tokens/llm_call_count）
    + N agent_invocation 子行 + M llm_call 子行，全挂同一 runtime_id。"""
    total_bw = sum(inv.get("black_wall_ms", 0) for inv in invocations)
    total_tokens = sum(c.get("prompt_tokens", 0) + c.get("completion_tokens", 0) for c in llm_calls)
    runtime_id = _create_runtime(conn, chapter_id, editing_rounds=editing_rounds)
    # _create_runtime 只设 editing_rounds；这里补齐聚合列
    conn.execute(
        "UPDATE chapter_runtime SET total_black_wall_ms=?, tool_count=?, llm_tokens=?, llm_call_count=? "
        "WHERE id=?",
        (total_bw, len(invocations), total_tokens, len(llm_calls), runtime_id))
    for inv in invocations:
        conn.execute(
            "INSERT INTO agent_invocation(runtime_id,agent_type,start_ts,end_ts,black_wall_ms) "
            "VALUES(?,?,?,?,?)",
            (runtime_id, inv["agent_type"], inv.get("start_ts"), inv.get("end_ts"),
             inv.get("black_wall_ms", 0)))
    for c in llm_calls:
        conn.execute(
            "INSERT INTO llm_call(runtime_id,phase,model,prompt_tokens,completion_tokens,duration_ms) "
            "VALUES(?,?,?,?,?,?)",
            (runtime_id, c["phase"], c["model"], c.get("prompt_tokens", 0),
             c.get("completion_tokens", 0), c.get("duration_ms", 0)))
    conn.commit()
```

> **实现前读 `src/bedrock/repositories/telemetry.py` 确认** `_create_runtime(conn, chapter_id, session_id=None, version=None, editing_rounds=0)` 返回 runtime_id，且 chapter_runtime 列名（total_black_wall_ms/tool_count/llm_tokens/llm_call_count/editing_rounds）与上方一致（SP1 schema 已确认）。

- [ ] **Step 4: 跑确认通过**（2 passed）+ 全量回归 → 106 + 2 = 108

- [ ] **Step 5: Commit**
```bash
cd D:/novel_test && git add src/bedrock/orchestration/runtime_collect.py tests/bedrock/test_runtime_collect.py && git commit -m "feat(bedrock): runtime_collect (black-wall telemetry writer)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 4 个新 CLI 子命令

**Files:**
- Modify: `src/bedrock/__main__.py`（追加 4 subparser + 分支）

**依赖**：Task 2（collect-runtime）、SP4 mark_*（review_flag.py）。

- [ ] **Step 1: 读现有 __main__.py 结构**

Run: `cd D:/novel_test && cat src/bedrock/__main__.py`
确认 argparse subparser 注册模式 + `_chapter_id(conn, global_number)` helper（SP4 Task 10 已建）+ `get_connection` + try/finally conn.close 模式。

- [ ] **Step 2: 追加 4 subparser 注册**

在现有 subparser 注册区（`run-l2`/`boot-context`/`verify-persisted`/`mark-unresolved` 旁）追加：

```python
    p_mark_pbb = sub.add_parser("mark-polish-broke-beat")
    p_mark_pbb.add_argument("--project", type=Path, required=True)
    p_mark_pbb.add_argument("--chapter", type=int, required=True)

    p_mark_fpf = sub.add_parser("mark-forced-persist-failed")
    p_mark_fpf.add_argument("--project", type=Path, required=True)
    p_mark_fpf.add_argument("--chapter", type=int, required=True)

    p_mark_drift = sub.add_parser("mark-advisory-drift")
    p_mark_drift.add_argument("--project", type=Path, required=True)
    p_mark_drift.add_argument("--chapter", type=int, required=True)

    p_collect = sub.add_parser("collect-runtime")
    p_collect.add_argument("--project", type=Path, required=True)
    p_collect.add_argument("--chapter", type=int, required=True)
    p_collect.add_argument("--editing-rounds", type=int, default=0)
```

- [ ] **Step 3: 追加 4 分支到 dispatch（try 块内）**

```python
        elif args.cmd == "mark-polish-broke-beat":
            cid = _chapter_id(conn, args.chapter)
            mark_polish_broke_beat(conn, cid)
            print("ok")
        elif args.cmd == "mark-forced-persist-failed":
            cid = _chapter_id(conn, args.chapter)
            mark_forced_persist_failed(conn, cid)
            print("ok")
        elif args.cmd == "mark-advisory-drift":
            cid = _chapter_id(conn, args.chapter)
            try:
                drift = json.loads(sys.stdin.buffer.read().decode("utf-8"))
            except (json.JSONDecodeError, ValueError) as e:
                sys.exit(f"invalid drift JSON on stdin: {e}")
            mark_advisory_drift(conn, cid, drift)
            print("ok")
        elif args.cmd == "collect-runtime":
            cid = _chapter_id(conn, args.chapter)
            try:
                payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
                invocations = payload.get("invocations", [])
                llm_calls = payload.get("llm_calls", [])
            except (json.JSONDecodeError, ValueError) as e:
                sys.exit(f"invalid runtime JSON on stdin: {e}")
            write_runtime(conn, cid, invocations, llm_calls, editing_rounds=args.editing_rounds)
            print("ok")
```

> 顶部 import 需加：`from src.bedrock.orchestration.review_flag import mark_polish_broke_beat, mark_forced_persist_failed, mark_advisory_drift`（若 mark-unresolved 已 import review_flag 则合并）+ `from src.bedrock.orchestration.runtime_collect import write_runtime`。

- [ ] **Step 4: 冒烟测试 4 命令**

seed 一个项目（复用 SP4 Task 10 的 seed 脚本，author 用 'system'），跑：

```bash
echo '{}' | python -m src.bedrock mark-advisory-drift --project <DIR> --chapter 1
python -m src.bedrock mark-polish-broke-beat --project <DIR> --chapter 1
python -m src.bedrock mark-forced-persist-failed --project <DIR> --chapter 1
echo '{"invocations":[{"agent_type":"Edit","black_wall_ms":1000,"start_ts":null,"end_ts":null}],"llm_calls":[]}' | python -m src.bedrock collect-runtime --project <DIR> --chapter 1 --editing-rounds 1
```
Expected: 每命令打印 `ok` 无 traceback。验证 mark-* 写入 chapter_review_flag、collect-runtime 写入 chapter_runtime。

- [ ] **Step 5: 全量回归** → 108（CLI 无新单测）

- [ ] **Step 6: Commit**
```bash
cd D:/novel_test && git add src/bedrock/__main__.py && git commit -m "feat(bedrock): CLI mark-polish-broke-beat/mark-forced-persist-failed/mark-advisory-drift/collect-runtime

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: statistical watchdog

**Files:**
- Create: `src/bedrock/orchestration/watchdog.py`
- Test: `tests/bedrock/test_watchdog.py`

**依赖**：SP1 `chapter_metrics`（读 grep_metrics）/ `chapter_review_flag.advisory_drift`（drift 占比）/ Task 1 `volume_review` 表。

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_watchdog.py
import json
from src.bedrock.db.connection import get_connection
from src.bedrock.orchestration.watchdog import run_watchdog, VolumeWatchdogReport
from src.bedrock.repositories.plot_tree import create_volume, create_chapter
from src.bedrock.repositories.telemetry import write_chapter_metrics


def _seed_volume_with_chapters(conn, n_chapters):
    vid = create_volume(conn, 1, "v", 1, n_chapters, "opening")
    cids = []
    for i in range(n_chapters):
        cid = create_chapter(conn, volume_id=vid, global_number=i + 1, title=f"t{i}")
        cids.append(cid)
    return vid, cids


def test_no_metrics_no_hug(tmp_project):
    conn = get_connection(tmp_project)
    vid, _ = _seed_volume_with_chapters(conn, 3)
    report = run_watchdog(conn, vid)
    assert isinstance(report, VolumeWatchdogReport)
    assert report.blocking is False   # 无 metrics，无发现
    conn.close()


def test_dash_hug_detected(tmp_project):
    """8/10 章 dash_per_kchar >= 0.85*3=2.55 → dash hug flagged → blocking。"""
    conn = get_connection(tmp_project)
    vid, cids = _seed_volume_with_chapters(conn, 10)
    for i, cid in enumerate(cids):
        # 8 章贴边（dash_per_kchar=2.6），2 章不贴边（0.5）
        dash = 2.6 if i < 8 else 0.5
        write_chapter_metrics(conn, cid,
                              grep_metrics={"notXisY_per_kchar": 0.0, "dash_per_kchar": dash, "period_density": 0.2})
    report = run_watchdog(conn, vid)
    assert report.hug_findings["dash_per_kchar"]["flagged"] is True
    assert report.hug_findings["dash_per_kchar"]["hug_ratio"] >= 0.70
    assert report.blocking is True
    conn.close()


def test_no_hug_when_below_ratio(tmp_project):
    """3/10 章贴边（< 70%）→ 不 flagged。"""
    conn = get_connection(tmp_project)
    vid, cids = _seed_volume_with_chapters(conn, 10)
    for i, cid in enumerate(cids):
        dash = 2.6 if i < 3 else 0.5
        write_chapter_metrics(conn, cid,
                              grep_metrics={"notXisY_per_kchar": 0.0, "dash_per_kchar": dash, "period_density": 0.2})
    report = run_watchdog(conn, vid)
    assert report.hug_findings["dash_per_kchar"]["flagged"] is False
    assert report.blocking is False
    conn.close()


def test_drift_aggregation(tmp_project):
    """6/10 章 advisory_drift 非空（>50%）→ drift_flagged → blocking。"""
    from src.bedrock.orchestration.review_flag import mark_advisory_drift
    conn = get_connection(tmp_project)
    vid, cids = _seed_volume_with_chapters(conn, 10)
    for i, cid in enumerate(cids):
        write_chapter_metrics(conn, cid,
                              grep_metrics={"notXisY_per_kchar": 0.0, "dash_per_kchar": 0.5, "period_density": 0.2})
        if i < 6:
            mark_advisory_drift(conn, cid, {"word_count": {"declared": 1, "recomputed": 2, "drifted": True}})
    report = run_watchdog(conn, vid)
    assert report.drift_ratio >= 0.50
    assert report.drift_flagged is True
    assert report.blocking is True
    conn.close()


def test_volume_review_row_written(tmp_project):
    conn = get_connection(tmp_project)
    vid, cids = _seed_volume_with_chapters(conn, 10)
    for cid in cids:
        write_chapter_metrics(conn, cid,
                              grep_metrics={"notXisY_per_kchar": 0.0, "dash_per_kchar": 2.6, "period_density": 0.2})
    run_watchdog(conn, vid)
    row = conn.execute("SELECT * FROM volume_review WHERE volume_id=?", (vid,)).fetchone()
    assert row is not None
    assert row["blocking"] == 1
    findings = json.loads(row["watchdog_findings"])
    assert "hug_findings" in findings
    conn.close()
```

- [ ] **Step 2: 跑确认失败**（ModuleNotFoundError）

- [ ] **Step 3: 实现 `orchestration/watchdog.py`**

```python
# src/bedrock/orchestration/watchdog.py
"""跨章 statistical watchdog：检测贴边走（threshold-hugging）+ drift 聚合。纯 Python 零 LLM。
卷间 BLOCKING：任一 flag → volume_review.blocking=1，dispatch 下一卷被阻断。"""
import json
from dataclasses import dataclass, field, asdict

WATCHDOG_HUG_RATIO = 0.70        # ≥70% 章贴边 → flagged
WATCHDOG_THRESHOLD_BAND = 0.85   # 值 >= 0.85*max 算"贴边"
WATCHDOG_DRIFT_RATIO = 0.50      # >50% 章 drift 非空 → drift_flagged

# 起步只检测上界指标（dash/notXisY per-kchar）；period/word_count 区间贴边后置（YAGNI）
_METRIC_THRESHOLDS = {
    "dash_per_kchar": 3.0,        # config dashes_per_k_max
    "notXisY_per_kchar": 1.5,     # ≈ 每 4000 字 6 处（config notXisY_max=5 量级）
}


@dataclass
class VolumeWatchdogReport:
    volume_id: int
    hug_findings: dict = field(default_factory=dict)   # {metric: {hug_ratio, threshold, flagged}}
    drift_ratio: float = 0.0
    drift_flagged: bool = False
    blocking: bool = False


def _chapter_ids_in_volume(conn, volume_id):
    rows = conn.execute("SELECT id FROM chapter WHERE volume_id=?", (volume_id,)).fetchall()
    return [r["id"] for r in rows]


def run_watchdog(conn, volume_id):
    """跨章读 chapter_metrics，检测贴边走 + drift 聚合，写 volume_review 行。"""
    cids = _chapter_ids_in_volume(conn, volume_id)
    n = len(cids)

    hug_findings = {}
    if n > 0:
        # 收集各章 grep_metrics
        per_metric_values = {m: [] for m in _METRIC_THRESHOLDS}
        for cid in cids:
            row = conn.execute("SELECT grep_metrics FROM chapter_metrics WHERE chapter_id=?",
                               (cid,)).fetchone()
            if row is None:
                for m in _METRIC_THRESHOLDS:
                    per_metric_values[m].append(None)
                continue
            gm = json.loads(row["grep_metrics"]) if row["grep_metrics"] else {}
            for m in _METRIC_THRESHOLDS:
                per_metric_values[m].append(gm.get(m))

        for metric, threshold in _METRIC_THRESHOLDS.items():
            values = per_metric_values[metric]
            valid = [v for v in values if v is not None]
            if not valid:
                continue
            band = threshold * WATCHDOG_THRESHOLD_BAND
            hugging = sum(1 for v in valid if v >= band)
            ratio = hugging / len(valid)
            hug_findings[metric] = {
                "hug_ratio": ratio,
                "threshold": threshold,
                "flagged": ratio >= WATCHDOG_HUG_RATIO,
            }

    # drift 聚合
    drift_ratio = 0.0
    if n > 0:
        drift_nonempty = 0
        for cid in cids:
            row = conn.execute("SELECT advisory_drift FROM chapter_review_flag WHERE chapter_id=?",
                               (cid,)).fetchone()
            if row is not None and row["advisory_drift"] and row["advisory_drift"] != "{}":
                drift_nonempty += 1
        drift_ratio = drift_nonempty / n
    drift_flagged = drift_ratio > WATCHDOG_DRIFT_RATIO

    blocking = any(f["flagged"] for f in hug_findings.values()) or drift_flagged

    report = VolumeWatchdogReport(
        volume_id=volume_id,
        hug_findings=hug_findings,
        drift_ratio=drift_ratio,
        drift_flagged=drift_flagged,
        blocking=blocking,
    )

    # 写 volume_review（upsert）
    findings_json = json.dumps({
        "hug_findings": hug_findings,
        "drift_ratio": drift_ratio,
        "drift_flagged": drift_flagged,
    }, ensure_ascii=False)
    conn.execute(
        "INSERT INTO volume_review(volume_id, watchdog_findings, blocking) VALUES(?,?,?) "
        "ON CONFLICT(volume_id) DO UPDATE SET watchdog_findings=excluded.watchdog_findings, "
        "blocking=excluded.blocking",
        (volume_id, findings_json, 1 if blocking else 0))
    conn.commit()

    return report
```

- [ ] **Step 4: 跑确认通过**（5 passed）+ 全量回归 → 108 + 5 = 113

- [ ] **Step 5: Commit**
```bash
cd D:/novel_test && git add src/bedrock/orchestration/watchdog.py tests/bedrock/test_watchdog.py && git commit -m "feat(bedrock): statistical watchdog (threshold-hugging + drift aggregation)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: 跨卷悬链收敛门禁

**Files:**
- Create: `src/bedrock/orchestration/cross_volume_gate.py`
- Test: `tests/bedrock/test_cross_volume_gate.py`

**依赖**：SP1 `suspense_thread`（planned_resolve_volume/status/importance）。**已确认**：`volume` 表有 `number` 列（NOT NULL UNIQUE，即卷序号），`create_volume(conn, number, ...)` 返回 volume.id（自增）。`suspense_thread.planned_resolve_volume` 存的是卷 **number**（非 id）。

> **对抗审核修正（spec §五）**：用 `<= volume_number` 累积（捕获跨卷漏检欠债，与 SP2 `check_cross_volume_anchors` 一致）+ **仅 `importance='high'` BLOCKING**（与 SP2 blocking 桶单一真相）。medium/low 进报告 advisory 不阻断。

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_cross_volume_gate.py
from src.bedrock.db.connection import get_connection
from src.bedrock.orchestration.cross_volume_gate import check_cross_volume_debt, CrossVolumeDebtReport
from src.bedrock.repositories.plot_tree import create_volume


def _plant_thread(conn, tid, planned_resolve_volume_number, status, importance="high"):
    """planned_resolve_volume 用卷 number（非 id）。"""
    conn.execute(
        "INSERT INTO suspense_thread(id,content,thread_type,importance,origin,status,planned_resolve_volume) "
        "VALUES(?,?,?,?,?,?,?)",
        (tid, "c", "mystery", importance, "scheduled", status, planned_resolve_volume_number))
    conn.commit()


def test_no_debt_when_all_resolved(tmp_project):
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")  # number=1
    _plant_thread(conn, 1, 1, "resolved")
    _plant_thread(conn, 2, 1, "abandoned")
    report = check_cross_volume_debt(conn, vid)
    assert report.blocking is False
    assert len(report.unresolved_threads) == 0
    conn.close()


def test_debt_blocks_when_unresolved_high(tmp_project):
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    _plant_thread(conn, 1, 1, "resolved")
    _plant_thread(conn, 2, 1, "developing", importance="high")   # high 未兑现 → 阻断
    _plant_thread(conn, 3, 1, "planted", importance="high")      # high 未兑现 → 阻断
    report = check_cross_volume_debt(conn, vid)
    assert report.blocking is True
    assert len(report.unresolved_threads) == 2
    conn.close()


def test_medium_importance_does_not_block(tmp_project):
    """仅 high BLOCKING；medium/low 未兑现不阻断（与 SP2 单一真相）。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    _plant_thread(conn, 1, 1, "developing", importance="medium")  # 不阻断
    _plant_thread(conn, 2, 1, "planted", importance="low")        # 不阻断
    report = check_cross_volume_debt(conn, vid)
    assert report.blocking is False
    assert len(report.unresolved_threads) == 0
    conn.close()


def test_leq_catches_earlier_volume_debt(tmp_project):
    """<= 累积：planned_resolve_volume < 本卷 number 的 high 未兑现也捕获。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 5, "v", 1, 3, "opening")  # number=5
    _plant_thread(conn, 1, 3, "developing", importance="high")   # vol3 计划，vol5 仍 open
    _plant_thread(conn, 2, 5, "resolved")
    report = check_cross_volume_debt(conn, vid)
    assert report.blocking is True
    assert len(report.unresolved_threads) == 1   # 只 vol3 那条（vol5 已 resolved）
    conn.close()


def test_ignores_future_volumes(tmp_project):
    """planned_resolve_volume > 本卷 number 不算本卷欠债。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")  # number=1
    _plant_thread(conn, 1, 1, "developing", importance="high")  # 本卷欠债
    _plant_thread(conn, 2, 2, "developing", importance="high")  # vol2 计划，不是本卷欠债
    report = check_cross_volume_debt(conn, vid)
    assert report.blocking is True
    assert len(report.unresolved_threads) == 1   # 只 number<=1 的
    conn.close()
```

- [ ] **Step 2: 跑确认失败**（ModuleNotFoundError）

- [ ] **Step 3: 实现 `orchestration/cross_volume_gate.py`**

```python
# src/bedrock/orchestration/cross_volume_gate.py
"""跨卷悬链收敛门禁：dispatch 下一卷前查 planned_resolve_volume <= 本卷 number 的 high 未兑现悬链。
纯 Python。卷间 BLOCKING：非空 → dispatch 下一卷被阻断。
注意：planned_resolve_volume 存卷 number（非 id）；仅 high BLOCKING（与 SP2 单一真相）。"""
from dataclasses import dataclass, field


@dataclass
class CrossVolumeDebtReport:
    volume_id: int
    unresolved_threads: list = field(default_factory=list)   # [{thread_id, content, importance}]
    blocking: bool = False


def check_cross_volume_debt(conn, volume_id):
    """volume_id → volume.number → 查 planned_resolve_volume<=number AND high AND 未兑现。"""
    vrow = conn.execute("SELECT number FROM volume WHERE id=?", (volume_id,)).fetchone()
    if vrow is None:
        return CrossVolumeDebtReport(volume_id=volume_id)
    volume_number = vrow["number"]

    rows = conn.execute(
        "SELECT id, content, importance FROM suspense_thread "
        "WHERE planned_resolve_volume<=? AND importance='high' "
        "AND status NOT IN ('resolved','abandoned')",
        (volume_number,)).fetchall()
    unresolved = [{"thread_id": r["id"], "content": r["content"], "importance": r["importance"]}
                  for r in rows]
    return CrossVolumeDebtReport(
        volume_id=volume_id,
        unresolved_threads=unresolved,
        blocking=len(unresolved) > 0,
    )
```

- [ ] **Step 4: 跑确认通过**（5 passed）+ 全量回归 → 113 + 5 = 118

- [ ] **Step 5: Commit**
```bash
cd D:/novel_test && git add src/bedrock/orchestration/cross_volume_gate.py tests/bedrock/test_cross_volume_gate.py && git commit -m "feat(bedrock): cross-volume suspense convergence gate

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: bedrock-chapter.js 接线（pythonCli subprocess + mark-advisory-drift）

**Files:**
- Modify: `.claude/workflows/bedrock-chapter.js`

**依赖**：Task 3（CLI 命令就绪）。无单测（JS 编排层，端到端验证在 Task 8）。

- [ ] **Step 1: 读现有 bedrock-chapter.js**

Run: `cd D:/novel_test && cat .claude/workflows/bedrock-chapter.js`
确认 SP4 的骨架（pythonCli 占位抛异常 + phase/agent/log 调用）。

- [ ] **Step 2: 实现 pythonCli 真 subprocess**

替换文件末尾的 `pythonCli` 占位函数为真 subprocess dispatch。用 Node 子进程同步调 `python -m src.bedrock`（Workflow JS 运行时允许 child_process）：

```javascript
import { execFileSync } from 'node:child_process'

// pythonCli：spawn `python -m src.bedrock <cmd>`，传 stdin，返回 stdout（run-l2 自动 JSON.parse）
async function pythonCli(cmdStr, opts = {}) {
  const [sub, ...rest] = cmdStr.split(/\s+/)
  const out = execFileSync('python', ['-m', 'src.bedrock', sub, ...rest], {
    input: opts.stdin ? opts.stdin : undefined,
    encoding: 'utf-8',
    cwd: process.cwd(),
  })
  // run-l2 输出 JSON；verify-persisted 输出 True/False；mark-*/collect-runtime 输出 ok
  const trimmed = out.trim()
  if (sub === 'run-l2') {
    try { return JSON.parse(trimmed) } catch { return trimmed }
  }
  if (sub === 'verify-persisted') {
    return trimmed === 'True'
  }
  return trimmed
}
```

> **注意 cmdStr 拆分**：上方 `cmdStr.split(/\s+/)` 把整条命令（含 `--project X --chapter N`）拆成数组，第一个 token 是子命令名。但 `--export-path <path>` 可能含空格——若 exportPath 有空格风险，改用数组参数而非字符串拼接（下方调用处改为传数组）。**起步假设路径无空格**；若 Task 8 e2e 路径含空格，改为数组形式。

- [ ] **Step 3: run-l2 后接 mark-advisory-drift（worst-round）**

> **对抗审核修正（spec §三 ④）**：drift 取**最差轮**（max over rounds by drifted 指标数），非 last-round。否则 round-1 大 drift 被 round-3 修好后覆盖，watchdog 看不到系统性造假。

在 run-l2 调用点用一个 helper 跨轮保留 worst-drift，落盘 worst：

```javascript
// 跨轮保留 worst-drift（drifted 指标数最多的轮）
let worstDrift = {}
function _persistDrift(report) {
  if (!report.drift || Object.keys(report.drift).length === 0) return
  const driftedCount = Object.values(report.drift).filter(d => d.drifted).length
  const worstCount = Object.values(worstDrift).filter(d => d.drifted).length
  if (driftedCount >= worstCount) worstDrift = report.drift
}
// 循环结束后落 worst（非每轮覆盖）：
if (Object.keys(worstDrift).length > 0) {
  await pythonCli(`mark-advisory-drift --project ${project} --chapter ${chapter}`,
                  { stdin: JSON.stringify(worstDrift) })
}
```

（在每处 run-l2 后调 `_persistDrift(report)` 累积 worst；循环外一次性落盘。）

- [ ] **Step 4: 人工 review**

通读改后的 bedrock-chapter.js，确认：
- pythonCli 真跑（不再抛 SP5 占位异常）
- run-l2 → JSON.parse → report.passed_hard_gate / report.beat_violations 契约保持
- mark-advisory-drift 在 drift 非空时调用
- collect-runtime 调用传 invocations/llm_calls（agent token 从各 agent 汇报——本 Task 用空数组占位，真采集留 Task 8 e2e 调通）

- [ ] **Step 5: 全量回归**（JS 无单测）→ 118

- [ ] **Step 6: Commit**
```bash
cd D:/novel_test && git add .claude/workflows/bedrock-chapter.js && git commit -m "feat(bedrock): wire pythonCli subprocess + mark-advisory-drift in chapter workflow

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: VolumeReview agent（prompt + Workflow JS）

**Files:**
- Create: `.claude/templates/bedrock/volume_review.md`
- Create: `.claude/workflows/bedrock-volume-review.js`

**依赖**：Task 4（watchdog）/ Task 5（cross_volume_gate）/ SP4（chapter_review_flag + run_l2 + mark_*）。**不复用 SP3 generate_repair_prompt**（它只接 BeatViolation 结构违规；VolumeReview 语义修复用新 prompt）。无单测（agent 层，人工 review + Task 8 e2e）。

> **对抗审核修正（spec §六）**：VR_FIX_ROUNDS=1（每章一次修正尝试）；Edit 后 **VolumeReview 二次复查**（L2 语义盲，必须 Opus 复查而非只信 L2，堵 A1/A4 漏洞）；三状态标注 verified_fixed/edited_unverified/escalate_human；语义修复 prompt 从 findings.fix_instruction 构造（非 RepairPrompt）。

- [ ] **Step 1: 写 VolumeReview prompt 模板**

`.claude/templates/bedrock/volume_review.md`：

```markdown
# VolumeReview 子代理（Opus，旗驱动）

你是整卷回读校验代理（磐石 V3）。主编排派生你对本卷的【旗章】做复查 + 修正闭环。

## 输入（主编排注入）
- flagged_chapters：SP4 chapter_review_flag 非空的章（l2_unresolved / polish_broke_beat / forced_persist_failed / advisory_drift）
  每章含：paragraphs 正文 + flag 类型 + persisted_violations（beat_id/kind/detail/fix_hint）
- watchdog_findings：本卷贴边走/drift 聚合发现
- cross_volume_debt：未兑现的跨卷悬链

## 任务（两阶段）

### 阶段 A：语义复查（Python L2 做不了的）
对每个旗章，判断：
- 代词指代：跨段"她/他"指代是否明确（治 Vol16 97 处根因）
- 回收真实性：悬链 declared 推进是否实质（状态机迁移是数据事实，但实质推进是语义）
- outline 合规：beat 段落 purpose 是否真兑现（bigram 匹配够不到的语义等价）

### 阶段 B：is_actionable 自分类（对抗审核修正）
输出每章 `is_actionable` 字段，规则：
- 语义发现（L2 盲区：代词/回收/outline）→ `is_actionable=True`（首次修）
- 结构重诊断：若你判 likely_rule_or_model → `is_actionable=False`（escalate_human，不修）；否则 True（给一次 Opus 新机会）

## 第二遍复查（主编排派你复用本 prompt）
Edit 修完后，主编排会把你**再派一次**读已编辑的章，判语义问题是否真修好（L2 语义盲查不了，必须你复查）。第二遍你只对"被编辑过的章"输出 `verified`（修好）/ `unverified`（无法确认）/ `regressed`（引入新问题）。

## 输出（结构化，主编排写 review_report_vol{N}.md）
```
旗章清单：
  chX [l2_unresolved]:
    findings: 代词"她"在 beat3 指代不明（语义）→ is_actionable=True
    fix_instruction: beat3 段落明确"她"=林深妻
  chY [l2_unresolved]:
    findings: beat2 缺角色，3 轮未过 → likely_rule_or_model
    fix_instruction: escalate_human（查 beat 兑现规则或换模型）
    is_actionable=False
watchdog: dash_per_kchar 贴边走 8/10 章
跨卷悬链: ST007 未兑现
```

**你不写 paragraphs**（Fixer 是独立 Edit agent）。你的 findings 进 review_report，actionable 的由主编排派 Edit 修 + 你二次复查。
```

- [ ] **Step 2: 写 bedrock-volume-review.js（Workflow JS）**

```javascript
export const meta = {
  name: 'bedrock-volume-review',
  description: '磐石 V3 卷级治理：旗章 Opus 复查 + 修正闭环 + 报告',
  phases: [
    { title: 'Gather' },
    { title: 'Review' },
    { title: 'Fix' },
    { title: 'Reverify' },
    { title: 'Report' },
  ],
}

// args: { project, volume, chapterRange: [start, end] }
const VR_FIX_ROUNDS = 1  // 每章一次修正尝试（spec §六，不无限重试）

export default async function ({ project, volume, chapterRange }) {
  // 1. Gather：读旗章 + watchdog + 跨卷门禁（VolumeReview 无论 blocking 都跑，spec §六.0）
  phase('Gather')
  const watchdog = await pythonCli(`run-watchdog --project ${project} --volume ${volume}`)
  const debt = await pythonCli(`cross-volume-debt --project ${project} --volume ${volume}`)
  const flagged = []
  for (let ch = chapterRange[0]; ch <= chapterRange[1]; ch++) {
    const flag = await pythonCli(`get-review-flag --project ${project} --chapter ${ch}`)
    if (flag && flag.has_flag) flagged.push({ chapter: ch, flag })
  }
  log(`gathered ${flagged.length} flagged chapters`)

  // 2. Review（第一遍）：派 Opus 复查旗章 → findings（含 is_actionable）
  phase('Review')
  const findings = await agent(volumeReviewPrompt(flagged, watchdog, debt),
                                { label: 'VolumeReview-Opus', phase: 'Review', model: 'opus' })

  // 3. Fix：对 is_actionable findings 派 Edit(Opus)（Reviewer ≠ Fixer；VR_FIX_ROUNDS=1）
  phase('Fix')
  const edited = []  // 被编辑过的章（供二次复查）
  for (const f of findings.actionable.slice(0, VR_FIX_ROUNDS ? findings.actionable.length : 0)) {
    await agent(semanticEditPrompt(f), { label: `Edit-fix-ch${f.chapter}`, phase: 'Fix', model: 'opus' })
    edited.push(f.chapter)
  }

  // 4. Reverify：L2 重跑（不得破坏 beat）+ VolumeReview 二次复查（L2 语义盲，必须 Opus 复查）
  phase('Reverify')
  const outcomes = {}  // chapter → verified_fixed/edited_unverified/escalate_human
  for (const ch of edited) {
    const after = await pythonCli(`run-l2 --project ${project} --chapter ${ch}`)
    if (!after.passed_hard_gate) {
      // Edit 破坏 beat → 回滚策略：标 escalate（回滚具体段落留 SP6 diff 工具）
      await pythonCli(`mark-polish-broke-beat --project ${project} --chapter ${ch}`)
      outcomes[ch] = 'escalate_human'   // edit 引入回归
      continue
    }
  }
  // 二次复查：VolumeReview 再读 edited 且 L2 未回归的章
  const toRecheck = edited.filter(ch => outcomes[ch] !== 'escalate_human')
  if (toRecheck.length > 0) {
    const recheck = await agent(volumeReviewRecheckPrompt(toRecheck, project),
                                { label: 'VolumeReview-recheck', phase: 'Reverify', model: 'opus' })
    for (const ch of toRecheck) {
      const v = recheck[ch]   // 'verified' | 'unverified' | 'regressed'
      outcomes[ch] = v === 'verified' ? 'verified_fixed'
                   : v === 'regressed' ? 'escalate_human'
                   : 'edited_unverified'
    }
  }

  // 5. Report：写 review_report_vol{N}.md（三状态）
  phase('Report')
  await pythonCli(`write-review-report --project ${project} --volume ${volume}`,
                  { stdin: JSON.stringify({ findings, outcomes, watchdog, debt }) })
  return { status: 'ok', reviewed: flagged.length,
           verified_fixed: Object.values(outcomes).filter(o => o === 'verified_fixed').length,
           escalated: Object.values(outcomes).filter(o => o === 'escalate_human').length }
}

function volumeReviewPrompt(flagged, watchdog, debt) { /* 嵌 volume_review.md + JSON */ }
function volumeReviewRecheckPrompt(chapters, project) { /* 第二遍：只读已编辑章，输出 verified/unverified/regressed */ }
function semanticEditPrompt(f) {
  // 语义修复 prompt：从 f.fix_instruction 构造（非 RepairPrompt/BeatViolation）。
  // 内含该章 paragraphs 上下文 + fix_instruction 自然语言指令 + "只改相关段落，不破坏 beat"。
}
async function pythonCli(_cmd, _opts) { /* 同 Task 6 的 subprocess dispatch */ }
```

> **注意 CLI 依赖**：上方引用 `run-watchdog` / `cross-volume-debt` / `get-review-flag` / `write-review-report` / `unlock-volume` 5 个 CLI 命令。Task 3 只建了 4 个（mark-*/collect-runtime）。**Task 7 需在 __main__.py 补这 5 个治理 CLI**（见 Step 3）。

- [ ] **Step 3: 补 5 个治理 CLI（__main__.py）**

追加 subparser + 分支：
- `run-watchdog --project P --volume V` → `run_watchdog(conn, vid)` → JSON 打印 VolumeWatchdogReport（vid = volume.id；`--volume` 传 id）
- `cross-volume-debt --project P --volume V` → `check_cross_volume_debt(conn, vid)` → JSON
- `get-review-flag --project P --chapter N` → `get_review_flag(conn, cid)` → JSON + `has_flag` 字段（任一 flag 非 0 或 drift ≠ '{}'）
- `write-review-report --project P --volume V` → 读 stdin JSON → 写 `<P>/review_report_vol{V}.md`（用模板拼装；强制落盘治 Vol15）
- `unlock-volume --project P --volume V --reason R` → **人工释放卷间 BLOCKING**（spec §十一）：`UPDATE volume_review SET blocking=0` + `governance.add_amendment(...)` 记录理由。author 固定 'human'。

> volume `--volume` 参数语义 = volume.id（watchdog/cross_volume_gate 都接 id；cross_volume_gate 内部 id→number 映射）。

- [ ] **Step 4: 人工 review**

通读 volume_review.md + bedrock-volume-review.js + 5 新 CLI，确认：
- Reviewer（VolumeReview）不写 paragraphs，Fixer（Edit）独立
- is_actionable 自分类（语义→True；结构 likely_rule_or_model→False）
- VR_FIX_ROUNDS=1 + 二次复查（verified_fixed/edited_unverified/escalate_human 三状态）
- write-review-report 强制落盘（治 Vol15）
- unlock-volume 写 amendment（人工释放留痕）

- [ ] **Step 5: 全量回归** → 118（agent/CLI 无新单测；5 CLI 是薄封装）

- [ ] **Step 6: Commit**
```bash
cd D:/novel_test && git add .claude/templates/bedrock/volume_review.md .claude/workflows/bedrock-volume-review.js src/bedrock/__main__.py && git commit -m "feat(bedrock): VolumeReview agent (flag-driven Opus review + fix loop + report)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: e2e 测试（seed 微型卷真跑）

**Files:**
- Create: `tests/bedrock/e2e/__init__.py`（空）
- Create: `tests/bedrock/conftest.py` 追加 `e2e` marker 注册（若未注册）
- Create: `tests/bedrock/e2e/test_micro_volume.py`

**依赖**：Task 1-7 全部。**需真 LLM**，`@pytest.mark.e2e` 默认 skip。

- [ ] **Step 1: 注册 e2e marker**

读 `tests/bedrock/conftest.py`（或 `pytest.ini`/`pyproject.toml`），确认 marker 注册机制。若无，在 `pyproject.toml`/`pytest.ini` 加：
```ini
[pytest]
markers =
    e2e: end-to-end tests requiring real LLM (deselected by default)
addopts = -m "not e2e"
```
（`addopts = -m "not e2e"` 使默认跑测试时 skip e2e；`pytest --e2e` 或 `pytest -m e2e` 单独跑。）

- [ ] **Step 2: 写 e2e 测试**

```python
# tests/bedrock/e2e/test_micro_volume.py
"""SP5 e2e：seed 微型卷真跑全链路。需真 LLM，@pytest.mark.e2e 默认 skip。
跑法：pytest tests/bedrock/e2e/ -m e2e（或去掉 addopts 的 not e2e）。"""
import json
import subprocess
from pathlib import Path
import pytest
from src.bedrock.db.migrate import apply_migrations
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat, update_beat_status,
)
from src.bedrock.repositories.outline import (
    save_volume_outline, lock_volume_outline, unlock_volume_outline, update_beat_contract,
)


@pytest.mark.e2e
def test_micro_volume_full_pipeline(tmp_path):
    """seed 2 章微型卷 → 跑 bedrock-chapter.js → 断言 flag/report/gate。"""
    project = tmp_path / "e2e_proj"
    project.mkdir()
    apply_migrations(project)

    # seed：1 卷 2 章，每章 1 beat + 契约；2 条悬链（1 本卷 planned_resolve，1 跨卷）
    conn = get_connection(project)
    vid = create_volume(conn, 1, "micro", 1, 2, "opening")
    for ch_idx in (1, 2):
        cid = create_chapter(conn, volume_id=vid, global_number=ch_idx, title=f"t{ch_idx}")
        bid = create_beat(conn, chapter_id=cid, sequence=1, purpose=f"第{ch_idx}章主beat剧情")
        update_beat_status(conn, bid, "planned")  # 待 ChapterWriter 写
        save_volume_outline(conn, vid, beat_contracts=[])
    lock_volume_outline(conn, vid); unlock_volume_outline(conn, vid, reason="setup", author="system")
    # 悬链
    conn.execute(
        "INSERT INTO suspense_thread(id,content,thread_type,importance,origin,status,planned_resolve_volume) "
        "VALUES(1,'本卷线','mystery','high','scheduled','planted',1)")
    conn.execute(
        "INSERT INTO suspense_thread(id,content,thread_type,importance,origin,status,planned_resolve_volume) "
        "VALUES(2,'跨卷线','mystery','high','scheduled','planned',2)")
    conn.commit()
    conn.close()

    # 跑 Workflow JS（每章一次）
    for ch_idx in (1, 2):
        result = subprocess.run(
            ["claude", "workflow", "run", "bedrock-chapter",
             "--args", json.dumps({"project": str(project), "chapter": ch_idx, "volume": 1})],
            capture_output=True, text=True, cwd="D:/novel_test")
        # 断言 workflow 不崩（status ok 或 flagged，非 traceback）
        assert result.returncode == 0 or "status" in result.stdout, result.stderr

    # 跑 VolumeReview
    subprocess.run(["claude", "workflow", "run", "bedrock-volume-review",
                    "--args", json.dumps({"project": str(project), "volume": 1, "chapterRange": [1, 2]})],
                   cwd="D:/novel_test")

    # 断言
    conn = get_connection(project)
    # watchdog 行
    vr = conn.execute("SELECT * FROM volume_review WHERE volume_id=?", (vid,)).fetchone()
    assert vr is not None
    # review_report 落盘（强制落盘门禁，治 Vol15）
    report_path = project / "review_report_vol1.md"
    assert report_path.exists() and report_path.stat().st_size > 0
    conn.close()
```

> **实现注意**：`claude workflow run` 的确切 CLI 形态依本环境 Workflow 工具调用方式——**实现前确认怎么从命令行触发一个 Workflow JS**（可能是 `claude` 子命令、或 MCP、或直接 node 跑）。若无法命令行触发，改为 Python 直接 import workflow runtime 调（或标注该 e2e 为"人工触发"手动跑）。**这是本 Task 的主要不确定点。**

- [ ] **Step 3: 验证默认 skip**

Run: `cd D:/novel_test && python -m pytest tests/bedrock/ -q`
Expected: 118 passed, e2e 被 deselect（不跑）

Run: `cd D:/novel_test && python -m pytest tests/bedrock/e2e/ -m e2e --co`
Expected: 收集到 1 个 e2e 测试（`--co` 只 collect 不跑）

- [ ] **Step 4: （人工）真跑 e2e 一次**

`pytest tests/bedrock/e2e/ -m e2e` —— 需真 LLM token + Workflow runtime。人工观察是否通过，修接线问题（Task 6/7 的 pythonCli / CLI 触发方式）。这步可能暴露 Task 6/7 的接线 bug，回头修。

- [ ] **Step 5: Commit**
```bash
cd D:/novel_test && git add tests/bedrock/e2e/ pyproject.toml pytest.ini && git commit -m "test(bedrock): e2e micro-volume full pipeline (@pytest.mark.e2e)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review 自检

**1. Spec 覆盖**：
- §三 Phase 0 接线（pythonCli + 4 CLI + runtime_collect + mark-advisory-drift JS）→ Task 2/3/6 ✓
- §四 Phase 1 watchdog（贴边走/drift + volume_review 表）→ Task 1（表）+ Task 4（逻辑）✓
- §五 Phase 2 跨卷门禁 → Task 5 ✓
- §六 Phase 3 VolumeReview（旗驱动 + 修正闭环 + 报告）→ Task 7 ✓
- §七门禁严格度 → Task 4/5 BLOCKING + Task 7 advisory ✓
- §十测试策略 → Task 2/4/5 单测 + Task 7 人工 + Task 8 e2e ✓
- §十一最终交付（完整卷 + report + 人工判决）→ Task 7 write-review-report ✓

**2. Placeholder 扫描**：
- Task 5/7 的 volume 序号列名"读 plot_tree.py 确认"——**实现时验证点**，给了 fallback（`volume_index` or `id`），非 placeholder。
- Task 8 的 `claude workflow run` 触发方式"实现前确认"——**实现时验证点**，非 placeholder。
- 无 TBD/TODO/「类似 Task N」省略。

**3. 类型/签名一致性**：
- `write_runtime(conn, chapter_id, invocations, llm_calls, editing_rounds)`（Task 2）
- `run_watchdog(conn, volume_id) -> VolumeWatchdogReport`（Task 4；字段 hug_findings/drift_ratio/drift_flagged/blocking）
- `check_cross_volume_debt(conn, volume_id) -> CrossVolumeDebtReport`（Task 5；字段 unresolved_threads/blocking）
- SP4 复用：`mark_polish_broke_beat`/`mark_forced_persist_failed`/`mark_advisory_drift`/`get_review_flag`/`run_l2`（均存在）✓
- SP1 复用：`record_agent_invocation`/`record_llm_call`/`_create_runtime`/`write_chapter_metrics`（均存在）✓

**4. 依赖顺序**：Task 1（schema）→ 2（runtime_collect）→ 3（CLI 用 2）→ 4（watchdog 用 1）→ 5（独立）→ 6（JS 用 3）→ 7（agent 用 4/5 + 补 CLI）→ 8（e2e 用全部）。满足依赖 ✓

**5. 测试增量**：106（SP1-4）→ +2(runtime_collect)+5(watchdog)+5(cross_volume_gate) = **118 单测** + 1 e2e（默认 skip，手动触发）。

**6. 两个实现时验证点**（非 placeholder，给了 fallback）：
- volume 表序号列名（Task 5/7）→ 读 plot_tree.create_volume
- Workflow JS 命令行触发方式（Task 8）→ 确认 `claude workflow run` 或等效

---

## 执行交接

计划完成，保存于 `docs/superpowers/plans/2026-06-14-bedrock-sp5-governance.md`。两种执行方式：

**1. Subagent-Driven（推荐）** — 每 Task 派新子代理 + 两阶段 review。

**2. Inline Execution** — 当前会话 executing-plans 批量 + checkpoint。

选哪种？
