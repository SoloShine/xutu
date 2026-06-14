# 磐石 Bedrock SP6-A 设计：给人用的只读 CLI 工具集

> SP6 = 工具层（A+B+C 三子项目）。本 spec 仅覆盖 **SP6-A：只读 CLI 工具集**（export / diagnose / show-review-report / diff）。
> SP6-B（MCP Server）、SP6-C（本地 Web UI）各自独立 spec。
> 前置：SP1-5 核心管线全部完成（数据骨架 / 防漂移校验 / 风格指纹 / 抗博弈管线 / 治理层）。

## 1. 目标与范围

SP1-5 的 15 个 CLI 全部是**管线内部信号/门禁**（run-l2 / mark-* / watchdog / verify-persisted / cross-volume-debt / get-review-flag / write-review-report / unlock-volume / init / boot-context / collect-runtime）。**零个"给人读/给人导出"的命令。** SP6-A 填这个洞。

**SP6-A 范围 = 四族只读命令：**

1. **export** — paragraph 表（正文 SSOT）→ 正文文件（单向，绝不回填），写 export_manifest 留痕。
2. **diagnose** — 聚合既有信号（旗 / status / volume_review / 跨卷欠债，可选 live L2 重算），输出自标注的体检报告。
3. **show-review-report** — 读已落盘的 review_report_vol{N}.md，原样 / 仅 escalate_human / 纯文本三种模式。
4. **diff** — DB 段落聚合内容 ↔ 已导出文件 的漂移检测（RC3 防双写的反向校验），三路 hash 对比区分"谁动了"。

**不在 SP6-A 范围**：MCP 暴露（SP6-B）、Web 可视化（SP6-C）、任何写 DB 业务数据（仅 export 写留痕表 export_manifest）、agent 编排触发、e2e 测试。

## 2. 关键设计决策

- **正文 SSOT = paragraph 表**，按 (chapter_id, seq) 排序。export 只读 paragraph → 写文件，**绝不回填**。这是 RC3（防双写）的强制约束，diff 命令是其反向校验。
- **纯函数 + 薄 CLI 封装**分层：逻辑放 `cli/reader_commands.py`（接收 conn，返回 dataclass/str），`__main__.py` 只做 argparse + print + 落盘。与既有 run_l2 / run_watchdog 的分层一致。
- **全部只读**——SP6-A 不写 DB 业务数据。唯一例外：export 写 `export_manifest`（设计内的留痕表，非正文 SSOT）。
- **零新依赖**：hash 用 hashlib（stdlib），markdown 渲染手写字符串拼接，报告解析用 stdlib re 行级正则。不引 markdown 解析库。
- **抗博弈精神延续**：live L2 重算（信任锚）必须显式触发（`--with-l2`），不静默大批量调用；全书 diagnose 必须显式 opt-in（`--book`）。

## 3. 架构与文件落点

```
src/bedrock/
├── cli/
│   ├── __init__.py
│   └── reader_commands.py    # 新增：export/diagnose/show_review_report/diff 纯函数
└── __main__.py               # 新增 4 个子命令的薄封装 argparse
tests/bedrock/
└── test_reader_commands.py   # 新增测试
```

`cli/reader_commands.py` 导出的纯函数（均接收 conn 为首参，便于测试）：

- `render_chapter(conn, chapter_id, fmt) -> str` — 单章渲染（export 与 diff 共用，DRY）
- `do_export(conn, project_path, scope, target, fmt, final, out) -> ExportResult`
- `diagnose(conn, project_path, scope, with_l2) -> str`（返回完整 markdown 报告）
- `show_review_report(project_path, volume, escalate_only, plain) -> str`
- `detect_drift(conn, project_path, scope, fmt) -> DriftReport`

## 4. export 命令

### 4.1 签名

```
bedrock export --project P (--chapter N | --volume N | --book) [--format md|txt] [--final] [--out PATH]
```

### 4.2 行为

- **三级 scope 三选一**（缺一/多选 → 报错）：
  - `--chapter N`：单章（N = global_number）
  - `--volume N`：卷内所有 `status='completed'` 的章，按 global_number 升序
  - `--book`：全书所有卷的所有 completed 章
- **渲染**：
  - **md**：`# 书名`（从 constants 表读，无则省略）→ `## 第X卷 卷名` → `### 第N章 标题` → 段落（按 seq，段间空行）。
  - **txt**：纯正文，无任何 markdown 标记；卷/章标题作为正文行保留（`第N章 标题`），章与章之间空行分隔。
- **跳过非 completed 章**，stderr 打印跳过清单（不进正文）。
- **留痕**（每次 export 写一行 export_manifest）：
  - `scope` = chapter/volume/book
  - `target_id` = chapter.id / volume.id / NULL(book)
  - `format`、`content_hash`（导出文件全文 sha256）
  - `status` = `final`（带 --final）/ `draft`（默认）
  - `source_snapshot` = JSON：`{chapter_count, global_numbers:[...], paragraph_total, rendered_at_iso}`
- **输出位置**（`--out` 可覆盖）：
  - 默认 `projects/<项目>/exports/`（**新建目录，与 output/ 管线中间态分离**）
  - 文件名：`ch{NN}.md` / `vol{NN}.md` / `book.md`（txt 换扩展名）
  - `--final` 时另复制一份到 `exports/final/`（同名），作为定稿快照
- **stdout**：打印最终文件绝对路径。

### 4.3 防双写

export 只从 paragraph 表读 → 写文件，**绝不回填 DB**。paragraph 表始终是 SSOT。

## 5. diagnose 命令

### 5.1 签名与模式矩阵

```
bedrock diagnose --project P --volume N            # 单卷留痕体检（默认推荐）
bedrock diagnose --project P --volume N --with-l2  # 单卷 + 当前正文 live 重算信任检查
bedrock diagnose --project P --book                # 全书留痕体检（显式 opt-in）
bedrock diagnose --project P                       # 报错：必须指定 --volume 或 --book
```

约束：
- 无 `--volume`/`--book` → SystemExit（不静默全书）
- `--book --with-l2` → SystemExit（互斥；全书逐章重算太重）

### 5.2 数据源

| 报告段 | 数据源 | 复用 |
|--------|--------|------|
| 卷级门禁 | `volume_review`（blocking） | 直查 |
| 跨卷悬链欠债 | `check_cross_volume_debt(conn, volume_id)` | 已有（SP5） |
| 章级 status | `chapter.status` | 直查 |
| 落盘 | `verify_chapter_persisted(conn, cid)`（行数=0 即 False） | 已有（SP4） |
| 四旗 | `chapter_review_flag`（l2_unresolved / polish_broke_beat / forced_persist_failed / advisory_drift） | 已有（SP4） |
| L2 hard_gate | `run_l2(conn, cid).passed_hard_gate` | 已有（SP4），仅 `--with-l2` 时现场跑 |

### 5.3 现场跑 L2 vs 读旗的差别（设计依据）

| 维度 | 现场 run_l2 重算 | 读 chapter_review_flag |
|------|------------------|------------------------|
| 回答的问题 | 此刻 DB 正文过不过硬约束 | 管线跑这章时出过什么要留痕的问题 |
| 数据来源 | 对当前 paragraph.text 重新算 | 管线当时写入的 4 个布尔位 |
| 时效 | 永远反映最新正文 | 反映管线跑那一刻；正文事后改则 stale |
| 能抓到的 | 正文被手改后变短/超阈/破坏 beat | 管线过程事件（3 轮重试耗尽、编辑破坏 beat、强制落盘失败） |
| 成本 | 每章一次纯读重算 | 1 条 SQL |

**两者不可互替**——抓的是不同种类的病。默认用旗（快、覆盖过程事件），live L2 走显式 `--with-l2`（重算层是信任锚，不静默大批量调用）。

### 5.4 报告结构

```markdown
> **⚠️ 体检模式标记 — 请先读本块**
> - **模式**：flag-only  *(或 `flag + live-L2`)*
> - **范围**：volume 3（global ch07–ch18）  *(或 `book 全书 N 卷`)*
> - **生成时间**：<ISO>
> - **章节覆盖**：12 章（completed 10 / writing 1 / 未落盘 1）
>
> **可信度声明**：本报告基于【管线留痕旗 + chapter.status + volume_review + 跨卷欠债】，
> **未对当前正文做 L2 重算**。正文在管线跑完后若被手改，本报告**不会**反映。
> 如需对当前正文的独立信任检查，请用 `--volume N --with-l2` 重跑。

## 卷级门禁
- 卷 N (id=X): volume_review.blocking = 0/1

## 跨卷悬链欠债
- [BLOCKING] 悬链 #12「...」应于卷3回收，status=developing, importance=high

## 章级状态矩阵
| ch | global | status | 落盘 | l2_unresolved | polish_broke | forced_fail | advisory_drift | L2 hard_gate | L2 来源 |
|----|--------|--------|------|---------------|--------------|-------------|----------------|--------------|---------|
| 1 | 1 | completed | ✓ | 0 | 0 | 0 | {} | pass | live（当前正文）|
| 2 | 2 | completed | ✓ | 0 | 0 | 0 | {} | - | flag（留痕）|
| 3 | 3 | writing | ✗ | - | - | - | - | - | n/a |

（flag-only 模式：L2 hard_gate 列全 `-`，L2 来源列 `flag（留痕）`；writing/planned 章：全 `-`，L2 来源 `n/a`。with-l2 模式：completed 章的 L2 hard_gate 有 fresh pass/fail，L2 来源 `live（当前正文）`。）

## 需关注清单
- 未落盘：ch2, ch5
- l2_unresolved：ch7（likely_rule_or_model=1）
- polish_broke_beat：ch9
- advisory_drift：ch3

## 完成度
- 卷 N：completed 12/14 章

<!-- diagnose-trace: mode=flag-only scope=volume:3 project=<名> generated_at=<ISO> -->
```

### 5.5 自标注规范（导出标记）

- **文件名编码模式**：`diagnose_vol{N}.md` / `diagnose_vol{N}_l2.md` / `diagnose_book.md`
- **顶部强制元数据块**：声明模式 / 范围 / 时间 / 章节覆盖 / 可信度声明（flag-only 与 with-l2 文案不同）
- **矩阵表 "L2 来源" 列**：`flag（留痕）` / `live（当前正文）` / `n/a`，杜绝混读
- **trace 注释**：报告末尾 HTML 注释 `<!-- diagnose-trace: mode=... scope=... -->`（不污染渲染，可 grep 召回）

## 6. show-review-report 命令

### 6.1 签名

```
bedrock show-review-report --project P --volume N [--escalate-only] [--plain] [--out PATH]
```

### 6.2 输入

读 `review_report_vol{N}.md`（SP5 write-review-report 生成）。文件不存在 → SystemExit（不静默生成空报告）。

### 6.3 三种模式

- **默认**：原样输出全文（UTF-8 安全）。
- **`--escalate-only`**：只提取 escalate_human 项，精简清单（章号 + actionable fix_instruction 原文 + 结果状态=escalate_human）。review_report 无独立"建议"字段，人不被捏造的建议误导，基于"发现 + 状态"自行判决。
- **`--plain`**：strip markdown（去 `#`/`**`/反引号/表格管道符）。喂对话上下文省 token。
- `--escalate-only --plain` 可叠加。

### 6.4 解析策略

- **stdlib re 行级正则**，不引 markdown 解析库。
- outcomes 段：`- ch{N}: (verified_fixed|edited_unverified|escalate_human)` → `{ch: state}` 映射。
- actionable 段：`- ch{N} [is_actionable=...]: ...` → `{ch: 发现}` 映射。
- escalate-only = 两表 join（ch 在 actionable 且 state=escalate_human）。
- **容错**：报告格式不符预期 → 返回空清单 + stderr `⚠️ 解析到 0 条 escalate（报告格式可能已变，请核对 write-review-report 模板）`，**不崩溃**。

### 6.5 --out

默认 stdout；`--out` 落盘（如 `review_escalate_vol{N}.md`）。

## 7. diff 命令（DB↔文件漂移检测）

### 7.1 签名

```
bedrock diff --project P (--chapter N | --volume N | --book) [--format md|txt] [--out PATH]
```

### 7.2 比对算法（两路直接重算 + 可选三路定位）

1. **DB 侧 hash**：用 render_chapter（§4 渲染器）生成该章"应然的文件内容"，sha256 → `db_hash`。
2. **文件侧 hash**：读 `exports/ch{NN}.{md|txt}` 全文，sha256 → `file_hash`。
3. **比对**：
   - `db_hash == file_hash` → `ok`
   - 文件不存在 → `missing_file`
   - `db_hash != file_hash` → `drifted`
   - 该章 paragraph 行数=0 → `missing_db`

### 7.3 漂移定位（drifted 时增值）

查 `export_manifest` 该章最近一行的 `content_hash` → `manifest_hash`，三路对比：
- `db_hash == manifest_hash` 且 `file_hash != manifest_hash` → **文件侧被手改**
- `file_hash == manifest_hash` 且 `db_hash != manifest_hash` → **DB 侧被改后未重导**
- 三者都不同 → 两边都动过
- manifest 缺失（从未 export）→ 降级两路（只报 drifted，不定位）

### 7.4 --format 默认

默认 md（与 export 默认一致）；可 `--format txt` 对比 txt 件。

### 7.5 输出

markdown 表（ch / global / DB段落数 / 文件 / 状态）+ 漂移详情（含三路定位）+ 汇总（ok/drifted/missing_file/missing_db 计数）。

### 7.6 与 export 的关系

diff 复用 render_chapter（DRY）生成 DB 侧内容，但**不调用 export、不写任何文件**——纯只读。manifest 只读不写。

## 8. 测试策略

`tests/bedrock/test_reader_commands.py`，延续 pytest + tmp_project fixture（已有，零新基础设施）。

**纯函数测试（主体）**：
- export：单章 md/txt 渲染、卷跳过非 completed、--final 快照、--out 覆盖、manifest 字段
- diagnose：必须指定 scope（否则 SystemExit）、--book --with-l2 互斥、flag-only 模式标记块、with-l2 模式 + L2 来源列、trace 注释
- show-review-report：默认原样、escalate-only 与 actionable join、plain strip、文件缺失 SystemExit、格式漂移容错
- diff：ok、drifted（DB 改 / 文件改，三路定位区分）、missing_db、missing_file

**CLI 薄封装测试**：仅测参数解析与 stdout 路径打印，不重复纯函数逻辑（DRY）。

**不写 e2e**：SP6-A 是只读导出/检测层，不触发 agent 编排，纯单测足够。

## 9. 与既有命令的边界

- export 不替代 verify-persisted（后者是管线门禁，检查"是否落盘"；export 是"把落盘的内容导成文件"）。
- diagnose 不替代 write-review-report（后者是 VolumeReview agent 的结论落盘；diagnose 是聚合管线级信号的体检，两者数据源不同）。
- diff 不替代 run-l2（后者是单章正文合规重算；diff 是 DB↔文件一致性，跨"正文状态"和"导出件状态"两个维度）。

## 10. 验收标准

- 4 个命令各自可独立运行，纯只读（export 仅写 export_manifest + 文件）。
- 全部测试通过（预计 ~20 个新单测，SP1-5 既有 121 测试不受影响）。
- 零新依赖（hashlib/re/stdlib only）。
- diagnose 报告的自标注规范（文件名 + 元数据块 + L2 来源列 + trace 注释）全部落实。
- diff 三路定位正确区分"DB 改 / 文件改 / 两边改"。
