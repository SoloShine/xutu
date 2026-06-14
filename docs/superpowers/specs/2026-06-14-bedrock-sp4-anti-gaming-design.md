# 磐石 Bedrock SP4 — 抗博弈管线 设计

**日期**: 2026-06-14
**状态**: SP4 设计（待 user review → writing-plans）
**代号**: 磐石 Bedrock（V3 小说管线）
**范围**: 单章抗博弈管线——L2 重算 bundle（硬门禁/advisory 分流）+ ChapterWriter/Edit 子代理编排（3 轮软门禁重试）+ 黑墙遥测采集 + 强制落盘门禁 + 诊断标记。SP4 才派生 agent（SP1/2/3 是纯 Python 库）。
**依赖**: SP1（ChapterMetrics/Runtime/agent_invocation/llm_call/tool_call 表 + paragraph/beat/outline）、SP2（`check_beat_fulfillment`/`check_cross_volume_anchors`/`BeatViolation`）、SP3（`generate_polish_prompt`/`generate_repair_prompt`/`PolishPrompt`/`RepairPrompt`/`save_fingerprint`）
**前置 spec**: `docs/superpowers/specs/2026-06-14-bedrock-design.md`（§4.1 流程、§4.2 L2、§4.3 L3、§4.4 L4 强制落盘、§4.5 抗博弈闭环）

---

## 一、背景

SP1 落数据骨架，SP2 落防漂移校验库（beat 兑现 + 跨卷锚点 + amendment/override），SP3 落风格指纹 + 结构化润色/修复 prompt。SP4 把这些**编排进一条可跑的抗博弈单章管线**：Write → L2 重算（信任锚）→ Edit 重试 → 强制落盘 → 遥测。SP4 是 V3 第一次派生 LLM 子代理（ChapterWriter + Edit）。

**抗博弈核心**（呼应历史铁证 A1/A4/B3，self-report 造假）：L2 重算是 Python 函数（零 LLM），每轮独立重算覆盖 agent 自报；advisory（自报）与 authoritative（重算）严格分离；agent 在被检查时无法"通过检查而非达标"，因为重算不看 agent 说啥。

**SP4 vs SP5 边界**：
- **SP4**：单章循环（Boot→Write→L2→Edit 重试→Persist→Telemetry）+ 诊断标记 + 强制落盘。**只标记，不复查**。
- **SP5**：VolumeReview 代理（读 SP4 标记 → 卷级复查 + 统一修改）+ statistical watchdog（跨章贴边走）+ LLM 语义抽查（代词/回收真实性/outline 合规）+ 跨卷悬链收敛门禁 + 系统性端到端测试。

---

## 二、设计原则

1. **Python-first build order** —— 纯 Python 重算/遥测/落盘门禁先建（可单测），agent 编排层（Workflow JS + prompt 模板）后挂。单测不依赖 LLM。
2. **L2 重算是信任锚** —— 每轮 Edit 后独立重算，agent 无法博弈客观量。硬门禁（beat 兑现）触发重试；advisory（grep/消费/cross_volume）只重算落库 + drift 标记，不阻断。
3. **软门禁，不硬阻断** —— 3 轮 Edit 重试耗尽 → 标记 `l2_unresolved` + 放行，卷级复查留 SP5。<4000 字纯规则问题三轮改不干净 = 规则或模型问题，标记 `likely_rule_or_model_issue` 供诊断，不盲目重试。
4. **黑墙遥测由编排层采集** —— agent token/工具/阶段由 Workflow JS 在子代理结束时从 SDK usage 汇报，Python 落库；agent 自报值进 `declared_json`（advisory）。
5. **强制落盘门禁** —— Vol15 未落盘 bug 的硬治：paragraphs 入 DB + 正文导出文件存在性双重校验，失败 → workflow `status=failed`。

---

## 三、组件设计（纯 Python，先建）

### ① grep 指标重算 — `checks/grep_metrics.py`

```python
def compute_grep_metrics(paragraphs: list[str]) -> dict:
    """从段落文本列表重算 grep 风格指标（authoritative，零 LLM）。
    返回 {
      "notXisY_per_kchar": float,   # 「不是X，是Y」否定转折句式计数/千字
      "dash_per_kchar": float,      # 破折号（——）计数/千字
      "period_density": float,      # 句号（。）密度 = 句号数/汉字数
    }
```

regex 固化（与 SP3 `lexicon.py` 的 notXisY 同源，破折号 `——`，句号 `。`）。空输入 → 全 0.0。汉字数复用 SP3 `extractor` 的 cn-len 规则（本地小工具函数，不反向依赖 style 包）。

### ② 悬链消费重算 — `checks/consumption.py`

```python
def compute_consumption(conn, chapter_id) -> tuple[float, float]:
    """从 thread_consumption 复算本章悬链消费（authoritative）。
    consumed = resolved×1.0 + advanced×0.5 + partially_resolved×0.5 + abandoned×0.3
    balance = consumed − new_threads_planted_in_chapter
    返回 (consumed, balance)。abandoned 计 0.3 防批量凑配额。"""
```

读 `thread_consumption`（SP1 表，按 chapter_id 过滤）的状态列 + 本章新种悬链计数。零悬链场景 → (0.0, 0.0)。

### ③ 字数重算 — `checks/word_count.py`

```python
def compute_word_count(paragraphs: list[str]) -> int:
    """汉字数（复用现有 _count_chinese_chars 正则逻辑）。空 → 0。"""
```

封装现有 `validators._count_chinese_chars` 逻辑为独立可测函数（不跨包依赖 novel_kg）。

### ④ L2 bundle — `orchestration/l2_pipeline.py`

```python
@dataclass
class L2Report:
    beat_violations: list          # SP2 BeatViolation[]（硬门禁集）
    advisory: dict                 # {"grep": {...}, "consumption": {...}, "cross_volume": {...}}
    metrics: dict                  # 写 chapter_metrics 的字段集（word_count/grep_metrics/...）
    drift: dict                    # {metric: {declared, recomputed, drifted: bool}}
    passed_hard_gate: bool         # len(beat_violations) == 0

def run_l2(conn, chapter_id) -> L2Report:
    """跑全部 L2 重算，分流硬门禁/advisory，检测 drift。
    1. beat = check_beat_fulfillment(conn, chapter_id)            # SP2 硬门禁
    2. paras = list_paragraphs_in_chapter(conn, chapter_id)
    3. grep = compute_grep_metrics(paras)                          # advisory
    4. consumed, balance = compute_consumption(conn, chapter_id)   # advisory
    5. cross = check_cross_volume_anchors(conn, volume_id)         # SP2 advisory
    6. wc = compute_word_count(paras)                              # authoritative
    7. drift = 对比 declared_json vs 重算值（阈值见 §五）
    返回 L2Report（passed_hard_gate = beat 空）"""
```

L2 bundle 是**纯 Python、确定性、可单测**——SP4 测试主体。

### ⑤ Boot context 装配 — `orchestration/boot_context.py`

```python
def get_chapter_boot_context(conn, chapter_id, volume_id) -> dict:
    """装配子代理启动上下文（替代 V1 散落 get_* 命令）：
    - beat 契约：list_beats_in_chapter → get_beat_contract
    - 角色可见信息：visibility 双轴过滤（character_epistemic / reader_disclosure，SP1 secrets）
    - StyleTemplate 指纹：get_effective_fingerprint（SP3 两级 fallback）
    - constants 硬约束：从 config/volume_type_matrix 取本卷类型配额"""
```

visibility 过滤复用 SP1 secrets 查询（不在此 spec 新建过滤逻辑，调现有 repository 函数）。

### ⑥ 黑墙遥测采集 — `orchestration/telemetry_collect.py`

```python
def write_chapter_metrics(conn, chapter_id, metrics: dict, declared: dict):
    """写 chapter_metrics（authoritative 主列 = 重算值；declared_json = agent 自报 blob）。"""

def write_runtime(conn, chapter_id, invocations: list[dict], llm_calls: list[dict],
                  editing_rounds: int, total_black_wall_ms: int):
    """写 chapter_runtime + agent_invocation + llm_call（黑墙，编排层采集）。"""
```

`metrics` 来自 `L2Report.metrics`；`declared` 来自子代理自报（word_count_declared / editing_corrections / editing_types）。`invocations`/`llm_calls` 由 Workflow JS 从 SDK usage 汇报传入。

### ⑦ 强制落盘门禁 — `orchestration/persist_gate.py`

```python
def verify_chapter_persisted(conn, chapter_id, export_path: str) -> bool:
    """双重校验：list_paragraphs_in_chapter 行数 > 0 AND os.path.exists(export_path)。
    任一不满足 → False → workflow status=failed + chapter_review_flag.forced_persist_failed=1。"""
```

### ⑧ 诊断标记写回 — `orchestration/review_flag.py`

```python
def mark_unresolved(conn, chapter_id, persisted_violations: list, likely_rule_or_model_issue: bool):
    """3 轮重试耗尽时写 chapter_review_flag（见 §七）。"""

def mark_polish_broke_beat(conn, chapter_id):
def mark_forced_persist_failed(conn, chapter_id):
```

---

## 四、一章流水线详述（Workflow JS 持循环）

```
for chapter in volume:
  1. Boot   get_chapter_boot_context(conn, ch, vol) → context dict
  2. Write  dispatch ChapterWriter subagent(context) → 写 paragraph 入 DB（按 beat 分段）
  3. L2     report = run_l2(conn, ch)
  4. Repair while not report.passed_hard_gate and round < 3:
              dispatch Edit(RepairPrompt(report.beat_violations) + PolishPrompt) → 写回
              report = run_l2(conn, ch)              # 每轮独立重算（信任锚）
              round += 1
            if not report.passed_hard_gate:
              mark_unresolved(ch, report.beat_violations, likely_rule_or_model_issue=<见§五>)
  5. Polish if report.passed_hard_gate:
              dispatch Edit(PolishPrompt) → 写回     # 正向润色（对准指纹）
              final = run_l2(conn, ch)
              if not final.passed_hard_gate: mark_polish_broke_beat(ch)
  6. Persist if not verify_chapter_persisted(conn, ch, export_path):
              mark_forced_persist_failed(ch); workflow status=failed; break
  7. Telemetry write_chapter_metrics(conn, ch, report.metrics, declared)
              write_runtime(conn, ch, invocations, llm_calls, editing_rounds=round, ...)
```

**成本**：典型 2 LLM/章（Write + 1 Edit[polish]）；beat 违规时最多 +2 Edit（共 3 轮 repair）。零 LLM 重算。

**严格串行**（继承 V2 管线铁律）：ChN persist + telemetry 成功后才能 dispatch ChN+1。

---

## 五、L2Report + 重试 + 诊断机制

**drift 检测阈值**：declared vs recomputed 偏差超 `|Δ|/recomputed > 0.1`（10%）→ `drifted=true`。起步 10%，可调（常量 `DRIFT_THRESHOLD`）。

**`likely_rule_or_model_issue` 判定**：3 轮重试后，`persisted_violations` 里存在同一 `(beat_id, kind)` 在多轮 L2Report 中**不变**（Workflow JS 跨轮比对 violation 签名集）→ `True`。这是"<4000 字纯规则问题三轮改不干净 = 规则/模型问题"的落地信号，供 SP5/人工优先诊断，**不触发第 4 轮重试**。

**Polish 破坏 beat**：polish pass 后 `run_l2` 若出现新 beat 违规 → `polish_broke_beat=1`（advisory 标记，不回滚 polish——回滚会丢正向润色收益；SP5 卷级复查时权衡）。

---

## 六、遥测字段映射

**chapter_metrics（authoritative，SP4 重算写主列）**：

| 列 | 来源 | 类别 |
|----|------|------|
| `word_count` | `compute_word_count` | authoritative |
| `grep_metrics` | `compute_grep_metrics` JSON | authoritative |
| `threads_consumed` | `compute_consumption[0]` | authoritative |
| `consumption_balance` | `compute_consumption[1]` | authoritative |
| `beat_yield_rate` | beat 兑现率（written/total，SP2 重算） | authoritative |
| `sentence_length_stats` / `sensory_density` / `dialogue_ratio` | 复用 SP3 `extract_fingerprint` 对应维度（指纹已算，直接取，不重算） | authoritative |
| `declared_json` | agent 自报（word_count_declared / editing_corrections / editing_types） | advisory blob |
| `source` | 固定 `'system_recomputed'`（SP1 CHECK） | — |

**chapter_runtime（黑墙，编排层采集）**：`total_black_wall_ms` / `tool_count` / `llm_tokens` / `llm_call_count` / `editing_rounds`（= 实际 Edit 派生次数）+ 子表 `agent_invocation`（per-agent start/end/black_wall_ms）/ `llm_call`（phase/model/tokens/duration）/ `tool_call`（tool/duration/error/decision）。

**遥测不存 drift 标记本身**——drift 在 `chapter_review_flag.advisory_drift` JSON（见 §七），SP5 读。

---

## 七、chapter_review_flag schema（SP4 唯一新增表）

SP1 遥测表已齐，flags 是治理状态（SP5 消费），独立成表更清晰（不污染 chapter_metrics 客观量）：

```sql
CREATE TABLE IF NOT EXISTS chapter_review_flag (
    chapter_id INTEGER PRIMARY KEY REFERENCES chapter(id),
    l2_unresolved INTEGER NOT NULL DEFAULT 0,            -- 3 轮重试后 beat 仍违规
    persisted_violations TEXT NOT NULL DEFAULT '[]',     -- 存活下来的 BeatViolation JSON
    likely_rule_or_model_issue INTEGER NOT NULL DEFAULT 0,  -- 同一违规多轮不变（诊断信号）
    polish_broke_beat INTEGER NOT NULL DEFAULT 0,        -- polish 后出现新 beat 违规
    forced_persist_failed INTEGER NOT NULL DEFAULT 0,    -- paragraphs/导出文件缺失
    advisory_drift TEXT NOT NULL DEFAULT '{}',           -- {metric: {declared, recomputed, drifted}}
    flagged_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

SP5 VolumeReview 读 `l2_unresolved=1` 的章做复查 + 统一修改；读 `likely_rule_or_model_issue=1` 做规则/模型诊断。

---

## 八、与 SP1/2/3 接口

**SP4 调用**：
- SP1 `list_paragraphs_in_chapter` / `list_beats_in_chapter` / `get_connection` / secrets visibility 查询 / `chapter_metrics`+`chapter_runtime`+子表写入（telemetry repository，若 SP1 已有则复用，否则 SP4 在 `repositories/telemetry.py` 扩展写函数）
- SP2 `check_beat_fulfillment`（硬门禁）/ `check_cross_volume_anchors`（advisory）/ `BeatViolation`
- SP3 `generate_polish_prompt` / `generate_repair_prompt`（Edit agent prompt 源）/ `get_effective_fingerprint`（boot context 指纹 + PolishPrompt）/ `save_fingerprint`

**SP3 carry-forward 落地**：
- **I1（卷指纹无 upsert）**：SP4 编排在 `save_fingerprint(scope="volume", ...)` 前先调 `delete_volume_fingerprint(conn, volume_id)`——**SP4 在 `style/template_repo.py` 加这个助手函数**（delete volume 行，再 save）。upsert 责任归 SP4 调用方。
- **I2/M3（RepairPrompt 结构化字段优先）**：SP4 Edit agent prompt 从 `RepairPrompt.violations`（含 detail）+ `PolishPrompt.beat_contracts` 结构化字段构造，`to_string()` 仅作 fallback。`generate_repair_prompt` 期望 SP2 `BeatViolation[]`（类型裸 list，SP4 传入时保证）。

---

## 九、文件结构

```
src/bedrock/
├── checks/
│   ├── grep_metrics.py        # ① grep 指标重算（新）
│   ├── consumption.py         # ② 悬链消费重算（新）
│   └── word_count.py          # ③ 字数重算（新）
├── orchestration/             # 新建包
│   ├── __init__.py
│   ├── l2_pipeline.py         # ④ L2 bundle + L2Report（新）
│   ├── boot_context.py        # ⑤ boot context 装配（新）
│   ├── telemetry_collect.py   # ⑥ 黑墙遥测采集（新）
│   ├── persist_gate.py        # ⑦ 强制落盘门禁（新）
│   └── review_flag.py         # ⑧ 诊断标记写回（新）
├── style/
│   └── template_repo.py       # +delete_volume_fingerprint（SP4 扩展，I1 落地）
└── __main__.py                # CLI 扩展：run_l2 / get_chapter_boot_context /
                               #   collect_telemetry / verify_chapter_persisted

.claude/templates/bedrock/     # agent 层（薄）
├── chapter_writer.md          # ChapterWriter 子代理 prompt（新）
└── edit_agent.md              # Edit 子代理 prompt（消费 SP3 prompt）（新）

.claude/workflows/
└── bedrock-chapter.js         # Workflow JS conductor（boot→Write→L2→Edit→persist→telemetry）（新）

tests/bedrock/
├── test_grep_metrics.py
├── test_consumption.py
├── test_word_count.py
├── test_l2_pipeline.py
├── test_boot_context.py
├── test_telemetry_collect.py
├── test_persist_gate.py
└── test_review_flag.py
```

**schema 改动**：仅新增 `chapter_review_flag` 表（§七）。chapter_metrics/runtime/子表零改动（SP1 已建）。

---

## 十、测试策略

**纯 Python 单测（SP4 测试主体，确定性，零 LLM）：**
- `grep_metrics`：构造已知文本断言 notXisY/破折号/句号密度精确值 + 空输入全 0
- `consumption`：构造 thread_consumption 行（resolved/advanced/partially_resolved/abandoned 混合），断言 consumed 公式（abandoned×0.3）+ balance + 零悬链边界
- `word_count`：复用现有断言基线 + 空
- `l2_pipeline`：seed beat 契约 + paragraphs，断言 L2Report 分流（beat 违规→hard_gate，grep/consumption/cross_volume→advisory）+ drift 检测（declared≠recomputed 超 10%）
- `boot_context`：断言 beat 契约 + visibility 过滤后角色 + 指纹 + constants 装配完整
- `telemetry_collect`：断言 chapter_metrics/runtime/agent_invocation/llm_call 行写入 + declared_json 与主列分离
- `persist_gate`：paragraphs 缺/导出文件缺 → False；齐 → True
- `review_flag`：mark_* 各标记写入 + chapter_review_flag 行正确

**Agent 层**：ChapterWriter/Edit prompt 模板人工 review（结构 + SP3 prompt 嵌入）；Workflow JS 跑一次 seed 项目冒烟（1 章 Write→L2→Edit→persist 全链路，人工观察）。

**端到端系统测试 → SP5**（顶层 §4.4 把"系统性端到端测试"放 SP5）。

**测试增量预估**：76（SP1-3）→ grep 4 + consumption 4 + word_count 2 + l2_pipeline 6 + boot_context 3 + telemetry 5 + persist_gate 3 + review_flag 4 ≈ **107 测试**。

---

## 十一、SP5 边界（明确，SP4 不做）

SP4 **不做**：
- VolumeReview 代理（读 `chapter_review_flag` 卷级复查 + 统一修改）
- statistical watchdog（跨章贴边走指纹，70%/85% 阈值起步）
- LLM 语义抽查（代词指代 / 回收真实性 / outline 合规——本质语义判断）
- 跨卷悬链收敛门禁（dispatch 下一卷前查 planned_resolve_volume）
- 系统性端到端测试

SP4 只产标记（`chapter_review_flag`）+ 强制落盘 + 黑墙遥测，SP5 消费。

---

## 十二、自检

**1. 顶层 spec 覆盖**：
- §4.1 流程（Boot→Write→L2→L3→L4）→ SP4 落 Boot/Write/L2/L3/强制落盘；L4 卷级留 SP5 ✓
- §4.2 L2 重算（word_count/grep/consumption/状态机/bigram）→ grep/consumption/word_count SP4 建；状态机已在 SP2 beat_fulfillment；bigram outline 匹配起步不做（advisory 层，可后置）✓
- §4.3 L3 Edit agent + StyleTemplate 指纹 → SP4 派生 Edit agent 调 SP3 prompt ✓
- §4.4 强制落盘门禁 → §三⑦ persist_gate ✓；watchdog/抽查/跨卷收敛 → SP5 ✓
- §4.5 抗博弈闭环五防线 → 结构(SP1)/L2(SP4)/L3(SP4 Edit)/L4(SP5)/可见性(SP1) 各司其职 ✓

**2. SP3 carry-forward**：I1 upsert（delete_volume_fingerprint 助手）/ I2 结构化字段优先 / M3 BeatViolation[] 传参 —— §八明确落地 ✓

**3. 范围内聚**：SP4 = 单章抗博弈管线，不卷入卷级治理（SP5）。一个实现计划可覆盖（Python 8 模块 + agent 层 3 文件）✓

**4. 待确认起步值**（常量化，可在 plan 调）：drift 阈值 10%、重试轮数 3、polish 是否总跑（起步：beat clean 则跑一次）✓
