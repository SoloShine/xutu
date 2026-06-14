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

### ③ runtime_collect 后端 — `orchestration/runtime_collect.py`（**新代码，非"封装"**）

> **对抗审核修正**：SP4 的 `telemetry_collect` 被 YAGNI 砍除（SP1 已有 `record_agent_invocation`/`record_llm_call`）。但 SP1 的 `record_agent_invocation` **每次调用建一个新 chapter_runtime 行**（一行/agent，非一行/章），与 `get_chapter_runtime` 的 `ORDER BY id DESC LIMIT 1` 假设冲突。故 `write_runtime` 是**新逻辑**：建恰好**一个** chapter_runtime 聚合行，再批量挂 agent_invocation/llm_call 子行。不复用 record_agent_invocation。

```python
def write_runtime(conn, chapter_id, invocations, llm_calls, editing_rounds):
    """建一个 chapter_runtime 行（聚合 total_black_wall_ms / llm_tokens / editing_rounds），
    再批量挂 agent_invocation + llm_call 子行。
    invocations: [{agent_type, black_wall_ms, start_ts, end_ts}]
    llm_calls: [{phase, model, prompt_tokens, completion_tokens, duration_ms}]
    实现：用 SP1 _create_runtime 建一行 → 累加 total_black_wall_ms → 手插 agent_invocation 行 →
    手插 llm_call 行并累加 llm_tokens/llm_call_count。单元测试断言单行聚合正确。"""
```

### ④ bedrock-chapter.js 接 mark-advisory-drift（**持久化最差轮 drift**）

SP4 的 JS 在 run_l2 后未调 mark-advisory-drift。Phase 0 补：每轮 run_l2 后若 `report.drift` 非空 → `pythonCli("mark-advisory-drift ...", {stdin: JSON.stringify(report.drift)})`。

> **对抗审核修正**：drift 持久化取**最差轮**（max over rounds），非 last-round。实现：JS 跨轮保留 worst-drift（按 drifted 指标数最多），最后一轮落 worst。否则 round-1 大 drift 被 round-3 修好后覆盖，watchdog 看不到系统性造假。
> **drift 覆盖范围**：当前 `_drift_metric` 只覆盖 `word_count`（grep/consumption 的 declared-vs-recomputed 未实现）。watchdog drift 信号因此只反映 word_count 造假。**A1（grep 造假）/A4（多样性谎报）历史病灶不在 drift 覆盖内**——由 L2 重算本身兜底（authoritative 覆盖 declared），drift 仅是额外高亮。Phase 0 可选扩展 `_drift_metric` 到 grep/consumption（若 SP4 declared_json 已含这些 declared 键），起步不强求。

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

**贴边走检测**（**对抗审核修正：单位归一**）：watchdog 用各指标**存储原单位**（chapter_metrics.grep_metrics 已是 per-kchar），**不从 config 的 count-based 阈值换算**（config `notXisY_max=5` 是每章计数、`periods_per_k_range` 是 per-kchar，与 grep_metrics 单位不一致；强行换算会单位错乱使门禁失灵）。起步**只检测两个单位一致的上界指标**：
- `dash_per_kchar`（grep_metrics 输出 per-kchar，config `dashes_per_k_max=3` 同单位）→ 阈值 3.0
- `notXisY_per_kchar`（grep_metrics 输出 per-kchar）→ 模块常量 1.5（≈ 每 4000 字 6 处，config `notXisY_max=5` 量级；不直接读 config 因单位不同）

`period_density`（per-cn-char）vs config `periods_per_k_range`（per-kchar，差 1000×）+ `word_count_target`（区间非上界）的"85% 带"定义不明，**起步不做**（YAGNI，后置）。各章实际值 ≥ 阈值×0.85 算"贴边"；**≥70% 章贴边** → 该 metric `flagged=True`。

**drift 聚合**：读本章 `chapter_review_flag.advisory_drift` 非空（且 ≠ `'{}'`）的占比，**>50%** → `drift_flagged=True`。注意 drift 当前只覆盖 word_count（见 §三 ④）。

**起步常量**（可调，`orchestration/watchdog.py` 模块级）：`WATCHDOG_HUG_RATIO=0.70`、`WATCHDOG_THRESHOLD_BAND=0.85`、`WATCHDOG_DRIFT_RATIO=0.50`、`DASH_PER_KCHAR_MAX=3.0`、`NOTXISY_PER_KCHAR_MAX=1.5`。

> **drift 仅捕获 L2 可重算指标的造假**（word_count）；语义/outline 造假不在 drift 覆盖，由 L2 authoritative 重算本身 + VolumeReview 语义抽查兜底。

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
    """dispatch 下一卷前查：suspense_thread WHERE planned_resolve_volume <= <本卷number>
    AND status NOT IN ('resolved','abandoned') AND importance='high'。
    high 未兑现 → blocking。纯 Python。
    volume_id → SELECT number FROM volume WHERE id=? 映射（planned_resolve_volume 存卷 number）。"""
```

**对抗审核修正（与 SP2 对齐，单一真相）**：
- **`<=` 累积**（非 `=`）：查 planned_resolve_volume ≤ 本卷 number 的所有未兑现，捕获跨卷漏检欠债（一个 vol3 计划悬链到 vol5 仍 open，应在 vol3 门禁挡住；若漏了，`<=` 在 vol5 仍能捕获）。SP2 `check_cross_volume_anchors` 也用 `<=`，两者一致。
- **仅 `importance='high'` BLOCKING**：与 SP2 的 blocking 桶一致（SP2 high→blocking、其他 advisory）。SP5 也只让 high 跨卷欠债阻断下一卷；medium/low 进报告 advisory 不阻断。**单一真相**：一条悬链要么到处 blocking 要么到处 advisory，不出现 SP2 放行、SP5 阻断的矛盾。

SP2（卷内 advisory）与本门禁（卷间 BLOCKING，仅 high）查询同源（`<=` + 未兑现），区别仅在 importance 过滤 + 卷间/卷内时机 + 阻断性。不冲突。

---

## 六、Phase 3：VolumeReview agent（旗驱动 Opus + 修正闭环）

### §六.0 卷级流水线顺序（对抗审核修正：消除 sequencing 歧义）

```
[本卷全部章节：bedrock-chapter.js × N] 
  → run_watchdog（写 volume_review 行：watchdog_findings + blocking）
  → VolumeReview（读 volume_review 行，advisory，【无论 blocking 是否=1 都跑】）
  → check_cross_volume_debt（写/更新 volume_review.blocking）
  → 人工判决（读 review_report + volume_review.blocking）
  → dispatch 下一卷前：若 volume_review.blocking=1 且人工未显式释放 → 阻断
```

**关键**：`volume_review.blocking` 是**下一卷 dispatch 时消费的输出**，**不是 VolumeReview 的前置条件**。VolumeReview 总是跑（即便 watchdog 已 blocking），这样 watchdog 抓到的"最需要语义复查的卷"恰恰能被 VolumeReview 处理。**"完整一卷" = 全章节已 persist + VolumeReview 已跑**，与 blocking 无关。

### 流程（Workflow JS `bedrock-volume-review.js`）

```
1. 读 chapter_review_flag（本卷章节中 l2_unresolved/polish_broke_beat/
   forced_persist_failed 非空 或 advisory_drift 非空）+ volume_review.watchdog_findings
2. 派 Opus VolumeReview 复查旗章 paragraphs → 结构化 findings（每章含 is_actionable）
     - 语义发现（L2 盲区）：代词指代 / 回收真实性 / outline 漂移 → is_actionable=True（首次修）
     - 结构重诊断：l2_unresolved 的 persisted_violations，Opus 给新根因
       → 若 Opus 判 likely_rule_or_model → is_actionable=False（escalate_human，不修）
       → 否则 is_actionable=True（给一次 Opus 新机会）
3. 对 is_actionable=True 的章 → 派 Edit(Opus) with 语义修复 prompt（见下，非 generate_repair_prompt）
     → 写回 paragraphs（Reviewer=VolumeReview ≠ Fixer=Edit，抗博弈）
     【VR_FIX_ROUNDS=1：每章仅一次修正尝试，不无限重试】
4. 重跑 L2（Edit 不得破坏已 clean beat；破坏 → revert Edit 写回 + polish_broke_beat flag）
5. 【抗博弈二次复查】对 step3 编辑过的章，派 VolumeReview(Opus) 第二遍读 → 判语义问题是否真修好
     - 修好 → 报告标 "verified_fixed"（经独立复查）
     - 未修好/引入新语义问题 → revert + 标 "escalate_human (edit_failed_or_regressed)"
     （L2 语义盲，故必须 VolumeReview 复查而非只信 L2；堵 A1/A4 "通过检查而非达标" 漏洞）
6. 写 review_report_vol{N}.md：旗章清单 + Opus findings + 修正结果（verified_fixed / edited_unverified /
   escalate_human）+ 诊断建议。报告只读不写 chapter_review_flag。
```

**三状态诚实标注（对抗审核修正 B5）**：
- `verified_fixed`：Edit 修 + VolumeReview 第二遍确认修好
- `edited_unverified`：Edit 修了但 VolumeReview 第二遍无法确认（如 Opus 不确定）→ 推人工 recheck
- `escalate_human`：结构死结（likely_rule_or_model）/ Edit 引入回归 / 一次修未成 → 不再修，人工判决

**语义修复 prompt（新，非 SP3 generate_repair_prompt）**：SP3 `generate_repair_prompt(violations)` 只接 `BeatViolation[]`（结构违规），无法承载 VolumeReview 的语义 findings。故 Edit 修复用**新 prompt**：从 VolumeReview findings 的 `fix_instruction` 字段构造（每章一段自然语言修复指令 + 对应 paragraphs 上下文）。不喂 BeatViolation。该 prompt 内联在 bedrock-volume-review.js（或新 template `edit_semantic_fix.md`）。

### `.claude/templates/bedrock/volume_review.md`（Opus 子代理 prompt）

- 输入：旗章 paragraphs + chapter_review_flag 标记 + watchdog 发现
- 任务：语义判断（代词/回收/outline，Python 做不了的）+ 结构重诊断 + **is_actionable 自分类**
- **is_actionable 规则**（对抗审核修正 S7）：语义发现 → True；结构重诊断 → likely_rule_or_model 则 False，否则 True
- 输出：结构化 findings（每章：issue_type / detail / fix_instruction / is_actionable）
- **不直接写 paragraphs**（Fixer 是独立 Edit agent）；第二遍复查（step5）也由本 prompt 复用

### `review_report_vol{N}.md`（最终交付物之一）

```markdown
# 第 N 卷 VolumeReview 报告

## 旗章清单与修正结果
| 章 | flag 类型 | Opus findings | 修正结果 |
|----|----------|--------------|---------|
| chX | l2_unresolved | 代词"她"指代不明（语义） | verified_fixed（Edit+复查） |
| chZ | polish_broke_beat | 回收不真实（语义） | edited_unverified（推人工 recheck） |
| chY | l2_unresolved | beat 缺角色，3 轮未过（结构死结） | escalate_human（likely_rule_or_model） |

## watchdog 发现
- dash_per_kchar 贴边走：8/10 章卡 85% 带（systematic_threshold_hugging）

## 跨卷悬链
- ST007 planned_resolve_volume≤N，high，未兑现（cross_volume_debt，已阻断下一卷）

## 诊断建议（人工判决入口）
- chY：查 beat 兑现规则是否过严，或换更强模型重试
```

**报告只读不写 chapter_review_flag**——Opus 语义判定是 advisory，不污染客观标记。报告是人工判决的输入。

**VolumeReview 单卷单次**（对抗审核修正 F6）：VolumeReview 假定每卷只跑一次；re-run 不做幂等（re-run 会重审已修章）。人工工作流是"review 一次 → 归档"。若需可重入，后置加 `chapter_review_flag.volume_review_attempted` 列（SP5 不做）。

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
- SP1 `chapter_metrics`（watchdog 读）/ `chapter_runtime`+`agent_invocation`+`llm_call`（runtime_collect 写，**新逻辑非封装**）/ `suspense_thread`（跨卷门禁读）/ `volume`（volume_review FK）/ `_create_runtime`（runtime_collect 建单行）
- SP2 `BeatViolation`（VolumeReview 结构 findings 复用）/ `check_cross_volume_anchors`（卷内 advisory，已有，SP5 与其 `<=`+high 对齐）
- SP4 `run_l2`/`L2Report`（VolumeReview 修正后重验 + drift 源）/ `chapter_review_flag` + `mark_*`（旗源，含 mark_advisory_drift 已在 SP4 建）/ `persist_gate`（SP4 已有）/ `bedrock-chapter.js`（Phase 0 接线对象）
- **不复用 SP3 `generate_repair_prompt`**（它只接 BeatViolation 结构违规；VolumeReview 语义修复用新 prompt，见 §六）

**SP5 新增**：`volume_review` 表（§四）、`watchdog.py`/`cross_volume_gate.py`/`runtime_collect.py`、4+治理 CLI（含 `unlock-volume` 人工释放，见 §十一）、VolumeReview + 语义修复 prompt + 2 Workflow JS、e2e 测试。

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
- seed 微型卷（2 章，每章 2 beat，预填 volume_outline/beat 契约/2 条悬链：1 本卷 planned_resolve、1 跨卷 high）
- 真跑 bedrock-chapter.js 全链路 ×2 章 + watchdog + cross_volume_gate + VolumeReview
- **触发方式（对抗审核修正 F8）**：e2e 是**人工触发**（人在 Claude 里跑 Workflow JS），pytest 只做**事后状态断言**（读 DB + 报告文件）。不强求 CI 自动跑（需真 LLM token + JS-pytest 桥，非平凡）。`@pytest.mark.e2e` 标记 + 文档说明"手动跑 Workflow 后执行断言"。
- **happy-path 断言**：clean 章无 flag、故意违规章 l2_unresolved=1、volume_review 行写入、review_report_vol{N}.md 存在非空（强制落盘，治 Vol15）
- **负面门禁断言（对抗审核修正 S4，必须）**：
  - watchdog 负面：seed 8/10 章 dash_per_kchar 贴边 → 断言 `volume_review.blocking=1`
  - cross_volume 负面：seed 1 条 high 悬链 planned_resolve_volume≤本卷、未兑现 → 断言 `check_cross_volume_debt().blocking=True`
  - （这两个负面用例可纯 Python seed + 断言，不需 LLM，归入单测而非真跑 e2e）

**测试增量预估**：106（SP1-4）→ runtime_collect 3 + watchdog 6（含负面临界）+ cross_volume_gate 4（含 high-only + `<=` 累积 + 别卷排除）= **119 单测** + 1 e2e（手动触发）。

---

## 十一、最终交付与人工判决

一卷完成后，主编排交付：
1. **完整一卷**（**定义**：所有章节正文已 persist [persist_gate 过] + VolumeReview 已跑。**与 volume_review.blocking 无关**——blocking 卷也"完整"，只是 dispatch 下一卷被阻断。）能 verified_fixed 的语义问题已修；edited_unverified/escalate_human 进报告。
2. **`review_report_vol{N}.md`**（修不了/未验证的建议：结构死结 escalate_human、edited_unverified、watchdog 发现、跨卷悬链）
3. **人工判决**：读报告 + volume_review.blocking 状态 → 接受 / 手动修 / 调规则 / 换模型 → 决定是否 dispatch 下一卷

**卷间 BLOCKING 释放（对抗审核修正 S3）**：`volume_review.blocking` 是 dispatch 下一卷的硬挡。释放 = 人工显式调 **`unlock-volume --project P --volume V --reason "...+"` CLI**（翻 volume_review.blocking=0 + 写 amendment 记录理由）。SP5 新增此 CLI（薄封装 + governance.add_amendment）。不由 VolumeReview 自动放行——blocking 是客观 Python 信号，只有人工判断后才能越权释放。

---

## 十二、SP6 边界（明确，SP5 不做）

SP5 **不做**（延后 SP6 工具层）：
- Web 编辑器 / VS Code 插件 / diff viewer / 导出工具
- 多 POV 矩阵 / 灵感池 UI
- 跨项目复用 / 模板化
- **诊断工具**（rule trace dump / model A-B 比较 / 阈值探针）——escalate_human 仅产报告建议，诊断动作由人工用现有 CLI 手动完成（对抗审核修正 F9）

SP5 是核心管线收尾；SP6 是人机交互层。

---

## 十三、自检（对抗审核后修订）

**1. 顶层 spec 覆盖**：
- §4.4 L4 审计 watchdog → Phase 1 ✓；抽查 → Phase 3 VolumeReview ✓；强制落盘 → SP4 已有 ✓；跨卷悬链收敛门禁 → Phase 2 ✓
- §八 待确认 #1（watchdog 阈值 70%/85%、抽查频率）→ Phase 1 常量化 + 单位归一（§四，仅 dash/notXisY per-kchar，period/word_count 后置）+ Phase 3 旗驱动（抽查频率=旗章数）✓
- §4.5 抗博弈闭环五防线 → 结构/L2/L3(SP4)/L4(SP5 watchdog+VolumeReview 二次复查)/可见性 各司其职 ✓

**2. SP4 遗留 wiring**：pythonCli subprocess / 3 mark CLI / mark-advisory-drift JS（worst-round）/ collect-runtime → Phase 0 全覆盖。**mark_advisory_drift Python 函数已在 SP4 建（commit ada178e），Phase 0 只接 CLI+JS**。

**3. 最终交付模型**：完整一卷（定义含 persist+VolumeReview，与 blocking 无关）+ review_report（三状态诚实标注）+ 人工判决 + unlock-volume CLI 释放 → §十一 ✓

**4. VolumeReview 修正闭环抗博弈**（对抗审核 🔴 修正）：语义修复新 prompt（非 generate_repair_prompt）/ VR_FIX_ROUNDS=1 / Edit 后 VolumeReview 二次复查（堵 L2 语义盲漏洞）/ 三状态标注（verified_fixed / edited_unverified / escalate_human）→ §六 ✓

**5. 卷级 sequencing**（对抗审核 🔴 修正）：chapters→watchdog→VolumeReview(无论 blocking)→cross_volume_gate→人工 → §六.0 ✓

**6. 范围内聚**：SP5 = 接线 + 治理 + e2e，不卷入 SP6 工具层（含诊断工具）。一个实现计划可覆盖 ✓

**7. 待确认起步值**（常量化，plan 可调）：WATCHDOG_HUG_RATIO=0.70 / BAND=0.85 / DRIFT_RATIO=0.50 / DASH_PER_KCHAR_MAX=3.0 / NOTXISY_PER_KCHAR_MAX=1.5 / VR_FIX_ROUNDS=1；VolumeReview+Edit 用 Opus；e2e 微型卷 2 章（手动触发）✓
