# 磐石 Bedrock SP5 — 治理层 设计

**日期**: 2026-06-14
**状态**: SP5 设计（待 user review → writing-plans）
**代号**: 磐石 Bedrock（V3 小说管线）
**范围**: 接 SP4 遗留 wiring（pythonCli subprocess + 3 CLI + mark-advisory-drift）让管线 runnable + statistical watchdog（跨章贴边走/drift）+ 跨卷悬链收敛门禁 + VolumeReview agent（旗驱动 Opus 抽查 + 修正闭环）+ 系统性 e2e 测试。V3 最后一个核心管线 SP。
**依赖**: SP1（chapter_metrics/runtime/suspense_thread/volume_outline）、SP2（check_cross_volume_anchors/BeatViolation）、SP3（prompt 生成）、SP4（run_l2/L2Report/chapter_review_flag/mark_*/persist_gate/bedrock-chapter.js 骨架）
**前置 spec**: `docs/superpowers/specs/2026-06-14-bedrock-design.md`（§4.4 L4 审计、§八 待确认 #1 watchdog 阈值）

---

## 一、背景

SP4 落了单章抗博弈管线（Boot→Write→L2→Edit 3 轮软门禁→Persist→Telemetry）+ 诊断标记（chapter_review_flag），但**刻意推迟了 runnable wiring**（pythonCli 是抛异常的占位、3 个 mark-* CLI 未暴露、mark-advisory-drift 未接 JS）。SP5 先接线让管线真跑，再加卷级治理（watchdog + 跨卷门禁 + VolumeReview），最后 e2e 验证。

**SP5 = SP1-5 五个核心管线 SP 的收尾。** SP6（工具层：Web 编辑器/VS Code 插件/导出）延后。

**最终交付模型**：完整一卷（章节已写 + VolumeReview 能修的已修）+ `review_report_vol{N}.md`（修不了的建议）→ **人工判决**（human-in-the-loop 最终门禁）。

---

## 二、设计原则

1. **Python-first** —— watchdog/跨卷门禁是纯 Python 客观重算（零 LLM），是 BLOCKING 门禁；LLM（VolumeReview/Opus）只做 Python 做不了的语义判断，全 advisory。
2. **卷间 BLOCKING，卷内 advisory** —— 强制落盘（SP4 已有）是唯一卷内 BLOCKING；watchdog + 跨卷悬链收敛是卷间 BLOCKING（dispatch 下一卷前）；VolumeReview LLM 抽查全 advisory。
3. **Reviewer 独立于 Fixer**（抗博弈）—— VolumeReview（Opus 审查）与 Edit（Opus 修复）是分离的子代理，呼应 L2 重算与 Edit 分离的 SP4 模式。
4. **语义 vs 结构区分修正** —— 语义发现（代词/回收/outline，L2 盲区）首次修（Edit Opus）；结构死结（l2_unresolved 过 3 轮）Opus 重诊断给一次新机会，仍失败 = likely_rule_or_model → escalate 人工，不无限重试。
5. **接线最小侵入** —— Phase 0 只补 SP4 缺口（pythonCli 真跑 + CLI + JS 调），不改 SP4 已测逻辑。

---

## 三、Phase 0：接 SP4 遗留 wiring

让 `bedrock-chapter.js` 从骨架变成可真跑。

### ① pythonCli subprocess dispatch（JS 侧）

`bedrock-chapter.js` 的 `pythonCli` 占位替换为真 subprocess：spawn `python -m src.bedrock <cmd> --project ... --chapter ...`，读 stdout、传 stdin（mark-unresolved/mark-advisory-drift 用）。`run-l2` stdout 是 JSON（SP4 已定），JS `JSON.parse`。`verify-persisted` stdout 是 "True"/"False"。

### ② 4 个新 CLI 子命令（`__main__.py` 扩展）

- `mark-polish-broke-beat --project P --chapter N` → `mark_polish_broke_beat(conn, cid)`
- `mark-forced-persist-failed --project P --chapter N` → `mark_forced_persist_failed(conn, cid)`
- `mark-advisory-drift --project P --chapter N` → 读 stdin drift JSON + `mark_advisory_drift(conn, cid, drift)`（UTF-8 解 stdin，同 SP4 mark-unresolved 模式）
- `collect-runtime --project P --chapter N --editing-rounds R` → 读 stdin `{invocations[], llm_calls[]}` JSON + `write_runtime(conn, cid, ...)`

### ③ runtime_collect 后端 — `orchestration/runtime_collect.py`

```python
def write_runtime(conn, chapter_id, invocations, llm_calls, editing_rounds):
    """封装 SP1 record_agent_invocation + record_llm_call。
    invocations: [{agent_type, black_wall_ms, start_ts, end_ts}]
    llm_calls: [{phase, model, prompt_tokens, completion_tokens, duration_ms}]
    editing_rounds 写 chapter_runtime.editing_rounds。"""
```

### ④ bedrock-chapter.js 接 mark-advisory-drift

SP4 的 JS 在 run_l2 后未调 mark-advisory-drift。Phase 0 补：每轮 run_l2 后若 `report.drift` 非空 → `pythonCli("mark-advisory-drift ...", {stdin: JSON.stringify(report.drift)})`。

---

## 四、Phase 1：statistical watchdog（纯 Python）

### `orchestration/watchdog.py`

```python
@dataclass
class VolumeWatchdogReport:
    volume_id: int
    hug_findings: dict      # {metric: {hug_ratio, threshold, flagged: bool}}
    drift_ratio: float      # advisory_drift 非空章占比
    drift_flagged: bool
    blocking: bool          # 任一 flag → True

def run_watchdog(conn, volume_id) -> VolumeWatchdogReport:
    """跨章读 chapter_metrics，检测贴边走 + drift 聚合。纯 Python 零 LLM。"""
```

**贴边走检测**：对每个有 config 阈值的指标（`dash_per_kchar_max`、`notXisY_per_chapter_max`、`period_density` 区间、`word_count_target`），算各章实际值落在"阈值 85% 带"内的比例。**≥70% 章聚在该带** → 该 metric `flagged=True`（呼应 Vol17 句号 11/12 章偏高）。

**drift 聚合**：读本章 `chapter_review_flag.advisory_drift` 非空的占比，**>50%** → `drift_flagged=True`（系统性自报造假）。

**起步常量**（可调，`orchestration/watchdog.py` 模块级）：`WATCHDOG_HUG_RATIO=0.70`、`WATCHDOG_THRESHOLD_BAND=0.85`、`WATCHDOG_DRIFT_RATIO=0.50`。指标阈值从 `config/config.py` 读（与 ChapterWriter 风格约束同源）。

### `volume_review` 表（schema 新增，唯一新表）

```sql
CREATE TABLE IF NOT EXISTS volume_review (
    volume_id INTEGER PRIMARY KEY REFERENCES volume(id),
    watchdog_findings TEXT NOT NULL DEFAULT '{}',   -- VolumeWatchdogReport JSON
    blocking INTEGER NOT NULL DEFAULT 0,            -- 卷间门禁状态
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

watchdog 写一行；`blocking=1` → dispatch 下一卷被阻断 + 推人工。

---

## 五、Phase 2：跨卷悬链收敛门禁（纯 Python）

### `orchestration/cross_volume_gate.py`

```python
@dataclass
class CrossVolumeDebtReport:
    volume_id: int
    unresolved_threads: list   # [{thread_id, content, importance}]
    blocking: bool             # 非空 → True

def check_cross_volume_debt(conn, volume_id) -> CrossVolumeDebtReport:
    """dispatch 下一卷前查：suspense_thread WHERE planned_resolve_volume=volume_id
    AND status NOT IN ('resolved','abandoned')。未兑现 → blocking。纯 Python。"""
```

**注意**：SP2 已有 `check_cross_volume_anchors`（advisory），本门禁是**卷间 BLOCKING** 版（dispatch 前查 planned_resolve_volume 未兑现）。两者不冲突——SP2 advisory 在卷内跑，本门禁在卷间跑。

---

## 六、Phase 3：VolumeReview agent（旗驱动 Opus + 修正闭环）

### 流程（Workflow JS `bedrock-volume-review.js`）

```
1. 读 chapter_review_flag（本卷章节中 l2_unresolved/polish_broke_beat/
   forced_persist_failed 非空 或 advisory_drift 非空）+ volume_review.watchdog_findings
2. 派 Opus VolumeReview 复查旗章 paragraphs → 结构化 findings
     - 语义发现（L2 盲区）：代词指代 / 回收真实性 / outline 漂移
     - 结构重诊断：l2_unresolved 的 persisted_violations，Opus 给新根因
3. 对有 actionable findings 的章 → 派 Edit(Opus) with RepairPrompt(findings) → 写回 paragraphs
     （Reviewer=VolumeReview 与 Fixer=Edit 分离，抗博弈）
4. 重跑 L2 验证（Edit 不得破坏已 clean 的 beat；破坏 → polish_broke_beat flag）
5. 仍失败 → 写 review_report_vol{N}.md + flag escalate_human，不阻断（advisory）
6. 报告：旗章清单 + Opus findings + 修正结果（fixed/still_failing）+ 诊断建议
```

### `.claude/templates/bedrock/volume_review.md`（Opus 子代理 prompt）

- 输入：旗章 paragraphs + chapter_review_flag 标记 + watchdog 发现
- 任务：语义判断（代词/回收/outline，Python 做不了的）+ 结构重诊断
- 输出：结构化 findings（每章：issue_type / detail / fix_instruction / is_actionable）
- **不直接写 paragraphs**（Fixer 是独立 Edit agent）

### `review_report_vol{N}.md`（最终交付物之一）

```markdown
# 第 N 卷 VolumeReview 报告

## 旗章清单与修正结果
| 章 | flag 类型 | Opus findings | 修正结果 |
|----|----------|--------------|---------|
| chX | l2_unresolved | 代词"她"指代不明（语义） | fixed（Edit Opus 已修） |
| chY | l2_unresolved | beat 缺角色，3 轮未过（结构死结） | escalate_human（likely_rule_or_model） |

## watchdog 发现
- period_density 贴边走：8/10 章卡 85% 带（systematic_threshold_hugging）

## 跨卷悬链
- ST007 planned_resolve_volume=N 但未兑现（cross_volume_debt，已阻断下一卷）

## 诊断建议（人工判决入口）
- chY：查 beat 兑现规则是否过严，或换更强模型重试
```

**报告只读不写 chapter_review_flag**——Opus 语义判定是 advisory，不污染客观标记。报告是人工判决的输入。

---

## 七、门禁严格度（spec §4.4 确认）

| 门禁 | 类型 | 触发动作 | 所属 |
|------|------|---------|------|
| 强制落盘 | BLOCKING（卷内） | workflow status=failed | SP4 已有 |
| watchdog 贴边走/drift | BLOCKING（卷间） | dispatch 下一卷阻断 + 推人工 | SP5 Phase 1 |
| 跨卷悬链收敛 | BLOCKING（卷间） | dispatch 下一卷阻断 | SP5 Phase 2 |
| VolumeReview LLM 抽查 | ADVISORY | 写报告 + 修正能修的 + escalate 修不了的 | SP5 Phase 3 |

---

## 八、与 SP1-4 接口

**SP5 调用**：
- SP1 `chapter_metrics`（watchdog 读）/ `chapter_runtime`+`agent_invocation`+`llm_call`（runtime_collect 写，封装 record_*）/ `suspense_thread`（跨卷门禁读）/ `volume`（volume_review FK）
- SP2 `BeatViolation`（VolumeReview findings 复用）/ `check_cross_volume_anchors`（卷内 advisory，已有）
- SP3 `generate_repair_prompt`（VolumeReview 修正闭环的 Edit prompt 源）
- SP4 `run_l2`/`L2Report`（VolumeReview 修正后重验）/ `chapter_review_flag` + `mark_*`（旗源）/ `persist_gate`（SP4 已有）/ `bedrock-chapter.js`（Phase 0 接线对象）

**SP5 新增**：`volume_review` 表（§四）、`watchdog.py`/`cross_volume_gate.py`/`runtime_collect.py`、4 个 CLI、VolumeReview prompt + Workflow JS、e2e 测试。

---

## 九、文件结构

```
src/bedrock/
├── db/schema.sql                 # +volume_review 表（Phase 1）
├── orchestration/
│   ├── runtime_collect.py        # Phase 0 ③
│   ├── watchdog.py               # Phase 1
│   └── cross_volume_gate.py      # Phase 2
└── __main__.py                   # +4 CLI（Phase 0 ②）

.claude/templates/bedrock/
└── volume_review.md              # Phase 3 Opus prompt

.claude/workflows/
├── bedrock-chapter.js            # Phase 0 ①④ 改（pythonCli 真跑 + mark-advisory-drift）
└── bedrock-volume-review.js      # Phase 3 新（旗驱动 + 修正闭环）

tests/bedrock/
├── test_runtime_collect.py       # Phase 0
├── test_watchdog.py              # Phase 1
├── test_cross_volume_gate.py     # Phase 2
└── e2e/
    └── test_micro_volume.py      # Phase 4（@pytest.mark.e2e，默认 skip）
```

**schema 改动**：仅新增 `volume_review` 表（§四）。chapter_review_flag 等零改动。

---

## 十、测试策略

**纯 Python 单测（确定性，零 LLM）：**
- `runtime_collect`：断言 chapter_runtime/agent_invocation/llm_call 行写入 + editing_rounds
- `watchdog`：构造已知 chapter_metrics 分布（8/10 章卡阈值带），断言 hug_ratio + flagged；构造 drift 分布断言 drift_flagged；blocking 聚合
- `cross_volume_gate`：seed 悬链 planned_resolve_volume=N，resolved/abandoned 不阻断、developing/planted 阻断
- CLI 新命令：冒烟（薄封装，逻辑在已测函数）

**VolumeReview prompt**：人工 review（结构 + SP3 prompt 嵌入 + 语义检查项）。

**e2e（`tests/bedrock/e2e/test_micro_volume.py`，`@pytest.mark.e2e` 默认 skip，需 `--e2e` 或 env 触发）：**
- seed 微型卷（2 章，每章 2 beat，预填 volume_outline/beat 契约/2 条悬链：1 本卷 planned_resolve、1 跨卷）
- 真跑 bedrock-chapter.js 全链路 ×2 章 + watchdog + cross_volume_gate + VolumeReview
- 断言：chapter_review_flag 行按预期（clean 章无 flag，故意违规章 l2_unresolved=1）、volume_review watchdog 行、review_report_vol{N}.md 存在非空、cross_volume_gate 阻断跨卷悬链
- 负面用例：第二个 seed 卷故意种 1 章缺角色 → 验证 l2_unresolved + VolumeReview 报告含该章

**测试增量预估**：106（SP1-4）→ runtime_collect 3 + watchdog 6 + cross_volume_gate 3 = **118 单测** + 1 e2e。

---

## 十一、最终交付与人工判决

一卷完成后，主编排交付：
1. **完整一卷**（所有章节正文已写 + VolumeReview 能修的语义问题已修）
2. **`review_report_vol{N}.md`**（修不了的建议：结构死结 escalate_human、watchdog 发现、跨卷悬链）
3. **人工判决**：读报告 → 接受 / 手动修 / 调规则 / 换模型 → 决定是否 dispatch 下一卷（卷间 BLOCKING 门禁在此释放）

卷间 BLOCKING 门禁（watchdog + 跨卷悬链）的释放由人工显式确认（写 amendment 或 CLI unlock），不由 VolumeReview 自动放行。

---

## 十二、SP6 边界（明确，SP5 不做）

SP5 **不做**（延后 SP6 工具层）：
- Web 编辑器 / VS Code 插件 / diff viewer / 导出工具
- 多 POV 矩阵 / 灵感池 UI
- 跨项目复用 / 模板化

SP5 是核心管线收尾；SP6 是人机交互层。

---

## 十三、自检

**1. 顶层 spec 覆盖**：
- §4.4 L4 审计 watchdog → Phase 1 ✓；抽查 → Phase 3 VolumeReview ✓；强制落盘 → SP4 已有 ✓；跨卷悬链收敛门禁 → Phase 2 ✓
- §八 待确认 #1（watchdog 阈值 70%/85%、抽查频率）→ Phase 1 常量化（HUG_RATIO=0.70/BAND=0.85/DRIFT_RATIO=0.50）+ Phase 3 旗驱动（抽查频率=旗章数，非每卷固定几章）✓
- §4.5 抗博弈闭环五防线 → 结构/L2/L3(SP4)/L4(SP5 watchdog+VolumeReview)/可见性 各司其职 ✓

**2. SP4 遗留 wiring**：pythonCli subprocess / 3 mark CLI / mark-advisory-drift JS → Phase 0 全覆盖 ✓

**3. 最终交付模型**：完整一卷 + review_report + 人工判决 → §十一 ✓

**4. 范围内聚**：SP5 = 接线 + 治理 + e2e，不卷入 SP6 工具层。一个实现计划可覆盖（Phase 0-4，~6 Python 模块 + 2 agent 文件 + 1 e2e）✓

**5. 待确认起步值**（常量化，plan 可调）：WATCHDOG_HUG_RATIO=0.70 / BAND=0.85 / DRIFT_RATIO=0.50；VolumeReview 用 Opus；e2e 微型卷 2 章 ✓
