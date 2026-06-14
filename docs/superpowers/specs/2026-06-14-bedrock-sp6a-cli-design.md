# 磐石 Bedrock SP6-A 设计：给人用的只读 CLI 工具集

> SP6 = 工具层（A+B+C 三子项目）。本 spec 仅覆盖 **SP6-A：只读 CLI 工具集**（export / diagnose / show-review-report / diff）。
> SP6-B（MCP Server）、SP6-C（本地 Web UI）各自独立 spec。
> 前置：SP1-5 核心管线全部完成（数据骨架 / 防漂移校验 / 风格指纹 / 抗博弈管线 / 治理层）。
>
> **修订记录**：经两路子代理对抗审核（数据源真实性 + 完备性/抗博弈），已吸收 8 项 🔴 与 9 项 🟡。关键修订：diagnose 不再调有写副作用的 `check_cross_volume_debt`（改纯读 SQL）；diff 三路定位的 manifest 查询 key 锁定 `scope='chapter' AND target_id=该章id`；`--final` 覆盖漏洞用 status 分流堵；escalate-only 改 outcomes 为主表；命名补零统一。

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
- **只读层诚实声明**：diagnose / show-review-report / diff **完全不写 DB**。export 是唯一写 DB 的命令，且只写 `export_manifest`（留痕表，非正文 SSOT）。export 写 manifest 用**独立短事务**，写失败降级为 stderr 警告（导出文件已生效，不回滚文件写入）。
- **【审核修订】diagnose 不得调用有写副作用的函数**：SP5 的 `check_cross_volume_debt(conn, volume_id)` 在 blocking 时会 `INSERT ... ON CONFLICT DO UPDATE SET blocking=1` 写 `volume_review`（`cross_volume_gate.py:36-41`）。diagnose 复用它做"读体检"会把卷副作用地标 blocking、破坏只读声称。diagnose 的跨卷欠债段改用**纯读 SQL**（见 §5.2），读 `volume_review.blocking` 的已落盘值 + 直查 `suspense_thread` 列欠债。
- **纯函数 + 薄 CLI 封装**分层：逻辑放 `cli/reader_commands.py`（接收 conn，返回 dataclass/str），`__main__.py` 只做 argparse + print + 落盘。与既有 run_l2 / run_watchdog 的分层一致。
- **零新依赖**：hash 用 hashlib（stdlib），markdown 渲染手写字符串拼接，报告解析用 stdlib re 行级正则。不引 markdown 解析库。
- **抗博弈精神延续**：live L2 重算（信任锚）必须显式触发（`--with-l2`），不静默大批量调用；全书 diagnose 必须显式 opt-in（`--book`）。

## 3. 架构与文件落点

```
src/bedrock/
├── cli/
│   ├── __init__.py
│   └── reader_commands.py    # 新增：export/diagnose/show_review_report/diff 纯函数 + 命名工具
└── __main__.py               # 新增 4 个子命令的薄封装 argparse
tests/bedrock/
└── test_reader_commands.py   # 新增测试
```

### 3.1 纯函数入参契约

`cli/reader_commands.py` 导出（均接收 conn 为首参，便于测试）：

| 函数 | 签名 | 职责 |
|------|------|------|
| `chapter_filename(global_number)` | `-> str` | 命名工具：`f"ch{global_number:02d}"`（≥2 位补零，与既有 output/ 一致）。export 写文件、diff 读文件共用，DRY。 |
| `render_chapter_body(conn, chapter_id, fmt)` | `-> str` | **单章正文 + 章标题**（md：`### 第N章 标题` + 段落；txt：`第N章 标题` + 段落）。**不含卷/书标题**。export 与 diff 共用，DRY。 |
| `do_export(conn, project_path, scope, target, fmt, final, out)` | `-> ExportResult` | scope∈`{'chapter','volume','book'}`；target：chapter→chapter.id，volume→volume.id，book→None。卷/书标题由本函数外层拼接（调用 render_chapter_body 得单章，再套 `## 第X卷` / `# 书名`）。 |
| `diagnose(conn, project_path, scope, with_l2)` | `-> str` | scope∈`{('volume', volume_id), ('book', None)}`。返回完整 markdown 报告。 |
| `show_review_report(project_path, volume, escalate_only, plain)` | `-> str` | 不接 conn（纯文件读）。volume=volume.id。 |
| `detect_drift(conn, project_path, scope, fmt)` | `-> DriftReport` | scope 同 do_export。 |

## 4. export 命令

### 4.1 签名

```
bedrock export --project P (--chapter N | --volume N | --book) [--format md|txt] [--final] [--out PATH]
```

**参数语义（与既有 CLI 惯例严格一致，【审核修订】显式声明）**：
- `--chapter N`：N = **global_number**（与 run-l2/boot-context/verify-persisted/mark-*/get-review-flag 一致，经 `_chapter_id(conn, global_number)` 解析为 chapter.id）。
- `--volume N`：N = **volume.id**（与 run-watchdog/cross-volume-debt/write-review-report/unlock-volume 一致，`help="volume.id"`），**非卷号 number**。用户拿卷号 1 恰好碰对 volume.id=1 是巧合，查别的卷会错——CLI 在 --help 与 --volume 参数 help 里明写 "volume.id"。
- `--book`：全书，无 target。
- 三级 scope 三选一（缺一/多选 → 报错）。

### 4.2 行为

- **渲染**（职责拆分，【审核修订】M6）：
  - `render_chapter_body(conn, chapter_id, fmt)` 只渲染**单章正文 + 章标题**（md：`### 第N章 标题` + 段落按 seq 空行分隔；txt：`第N章 标题` 作为正文行 + 段落）。paragraph 主键是 `para_id`（非 `id`），渲染只取 `text` 按 `seq` 排序，不读 `role`。
  - `do_export` 外层拼接卷/书标题：md 顶层 `# 书名`（读 constants 表 `key='work_name'`，无则省略），卷层 `## 第X卷 卷名`（X=volume.number，名=volume.name）。txt 不带 markdown 标记，卷/章标题作为正文行。
- **scope 处理**：
  - `--chapter N`：单章。
  - `--volume N`：该卷所有 `status='completed'` 的章，按 global_number 升序。
  - `--book`：全书所有卷的所有 completed 章，**按 chapter.global_number 全局升序，忽略卷边界**（不依赖 volume.chapter_start/end，两者无 schema 约束只是约定）。【审核修订】M5
- **跳过非 completed 章**，stderr 打印跳过清单（不进正文）。
- **空卷报错【审核修订】M4**：`--volume` 若该卷 0 章 completed → SystemExit 提示"卷 N(id=X) 无已完成章节"，不产出空文件（空 md 易被误当有效导出）。
- **书名键【审核修订】H6**：`constants` 表通用 KV，书名固定读 `key='work_name'`（`init_project.py:27` 已写此键）。无此键则省略顶层 `# 书名` 行。
- **留痕**（每次 export 写一行 export_manifest，**独立短事务**，失败降级 stderr 警告不阻断文件导出【审核修订】M1）：
  - `scope` = chapter/volume/book
  - `target_id` = chapter.id / volume.id / NULL(book)
  - `format`、`content_hash`（**导出文件全文 sha256**）
  - `status` = `final`（带 --final）/ `draft`（默认）。**SP6-A 只产生 `draft`/`final`；`published` 是 schema CHECK 预留值，本 spec 不产生**【审核修订】H2
  - `source_snapshot` = JSON：`{chapter_count, global_numbers:[...], paragraph_total, rendered_at_iso}`
- **输出位置**（`--out` 可覆盖默认）：
  - 默认 `projects/<项目>/exports/`（**新建目录，与 output/ 管线中间态分离**）
  - 文件名：`ch{NN}.{ext}` / `vol{NN}.{ext}` / `book.{ext}`（ext=md|txt）。**chapter 用 `chapter_filename(global_number)` = `f'ch{n:02d}'`（≥2 位补零）；volume 用 `f'vol{volume.number}'` 不补零**（卷号小，且与既有报告 `review_report_vol{N}.md` 一致）【审核修订】H7
  - `--final` 时另复制一份到 `exports/final/`（同名），作为定稿快照
- **stdout**：打印最终文件绝对路径。
- **防双写**：export 只从 paragraph 表读 → 写文件，**绝不回填 DB**。

### 4.3 不变量（测试断言，【审核修订】M9e）

export 写入的 `export_manifest.content_hash` **必须等于** 导出文件实际内容的 sha256。这是整个 diff 三路定位可信度的根基，必有 round-trip 测试。

## 5. diagnose 命令

### 5.1 签名与模式矩阵

```
bedrock diagnose --project P --volume N            # 单卷留痕体检（默认推荐，N=volume.id）
bedrock diagnose --project P --volume N --with-l2  # 单卷 + 当前正文 live 重算信任检查
bedrock diagnose --project P --book                # 全书留痕体检（显式 opt-in）
bedrock diagnose --project P                       # 报错：必须指定 --volume 或 --book
```

`--volume N` 的 N = volume.id（同 §4.1）。约束：
- 无 `--volume`/`--book` → SystemExit（不静默全书）
- `--book --with-l2` → SystemExit（互斥；全书逐章重算太重）

### 5.2 数据源（【审核修订】H1：全部纯读，不调有写副作用的函数）

| 报告段 | 数据源 | 方式 |
|--------|--------|------|
| 卷级门禁 | `volume_review.blocking`（已落盘值，由 watchdog/cross_volume 写入） | 直查 SELECT，**只读** |
| 跨卷悬链欠债（单卷） | **纯读 SQL**：`SELECT id,content,importance,status FROM suspense_thread WHERE planned_resolve_volume<=? AND importance='high' AND status NOT IN ('resolved','abandoned')`（? = 该卷 volume.number） | **不调 `check_cross_volume_debt`**（它有写副作用） |
| 跨卷悬链欠债（--book） | 逐卷循环跑上述纯读 SQL，聚合；任一卷有 high 未兑现 → 全书标 BLOCKING，列出具体哪几卷哪几条 | 同上，循环 |
| 章级 status | `chapter.status` | 直查 |
| 落盘 | `verify_chapter_persisted(conn, cid)`（行数=0 即 False） | 复用（**该函数纯读**，安全） |
| 四旗 | `chapter_review_flag` 表 | 直查 SELECT（**真实列名**：l2_unresolved / polish_broke_beat / forced_persist_failed / advisory_drift） |
| L2 hard_gate | `run_l2(conn, cid).passed_hard_gate` | 仅 `--with-l2` 时现场跑（纯读重算） |

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
| ch | global | status | 落盘 | l2_unresolved | polish_broke_beat | forced_persist_failed | advisory_drift | L2 hard_gate | L2 来源 |
|----|--------|--------|------|---------------|-------------------|-----------------------|----------------|--------------|---------|
| 1 | 1 | completed | ✓ | 0 | 0 | 0 | {} | pass | live（当前正文）|
| 2 | 2 | completed | ✓ | 0 | 0 | 0 | {} | n/a（flag-only） | flag（留痕）|
| 3 | 3 | writing | ✗ | - | - | - | - | n/a | n/a |

（flag-only 模式：completed 章 L2 hard_gate 填 `n/a（flag-only）`、L2 来源 `flag（留痕）`；writing/planned 章：全 `-`、L2 来源 `n/a`。with-l2 模式：completed 章 L2 hard_gate 有 fresh pass/fail、L2 来源 `live（当前正文）`。矩阵列名用**真实字段名** polish_broke_beat / forced_persist_failed，防实现方照简称写错 SQL【审核修订】reviewer1#6；flag-only 的 L2 hard_gate 列填 `n/a（flag-only）` 而非裸 `-`，防截取丢失上下文误读为"未知"【审核修订】M2。）

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

- **文件名编码模式**：`diagnose_vol{N}.md`（N=volume.number，不补零）/ `diagnose_vol{N}_l2.md` / `diagnose_book.md`
- **顶部强制元数据块**：声明模式 / 范围 / 时间 / 章节覆盖 / 可信度声明（flag-only 与 with-l2 文案不同）
- **矩阵表 "L2 来源" 列 + "L2 hard_gate" 列**：见 §5.4 模式说明
- **trace 注释**：报告末尾 HTML 注释 `<!-- diagnose-trace: mode=... scope=... -->`（不污染渲染，可 grep 召回）

## 6. show-review-report 命令

### 6.1 签名

```
bedrock show-review-report --project P --volume N [--escalate-only] [--plain] [--out PATH]
```

`--volume N` 的 N = volume.id（同 §4.1）。**报告文件名用 volume.id 定位**：既有 `write-review-report` 落盘 `review_report_vol{args.volume}.md`（`__main__.py:258`，args.volume = volume.id），show-review-report 用同一 id 拼文件名，保证读写一致。

### 6.2 输入与格式信任边界（【审核修订】H5）

读 `review_report_vol{N}.md`。**声明**：show-review-report **只解析 SP5 `_write_review_report` 生成的格式**（含 `## 旗章发现（actionable）` / `## 修正结果（三状态）` 等固定段标题 + `- ch{N}: <state>` / `- ch{N} [is_actionable=...]: ...` 行）。既有 V2 管线手写的人话报告（如 `projects/juedi_tiantong_v1/review_report_vol3.md`）**不保证解析**——`--escalate-only` 对 V2 报告返回空清单 + 明确警告（"未检测到 SP5 格式 actionable/outcomes 段，可能是 V2 手写报告或空卷"），是预期行为，不报错。

文件不存在 → SystemExit（不静默生成空报告）。

### 6.3 三种模式

- **默认**：原样输出全文（UTF-8 安全）。
- **`--escalate-only`**：见 §6.4 新逻辑。
- **`--plain`**：strip markdown（去行首 `#`/`*`/反引号/表格管道符 `|`）。**对 json 代码块**（` ```json ... ``` `）：去围栏反引号、保留 JSON 内容为纯文本行【审核修订】M7。喂对话上下文省 token。
- `--escalate-only --plain` 可叠加。

### 6.4 escalate-only 解析逻辑（【审核修订】reviewer1#9/H5：outcomes 为主表）

旧 spec 用"actionable ∩ outcomes join"——**漏掉 polish_broke_beat/hard_gate 触发的 escalate**（这类章进 outcomes 但 actionable findings 里可能无对应行）。改为：

1. 解析 **outcomes 段**：`- ch{N}: (verified_fixed|edited_unverified|escalate_human)` → `{global_number: state}` 映射。
2. **主表 = outcomes 中 state=escalate_human 的所有 ch**（不再要求在 actionable 有行）。
3. 解析 **actionable 段**：`- ch{N} [is_actionable=...]: ...` → `{global_number: fix_instruction}` 映射。
4. **左连**：对每个 escalate 的 ch，从 actionable 取 fix_instruction；无则注 "escalate via polish_broke_beat/hard_gate，无 fix_instruction"。

输出：
```
## 卷 N — 需人工判决（escalate_human）

### ch7
- 原发现（actionable fix_instruction）：[报告原文，无则注"无 fix_instruction"]
- 修正结果状态：escalate_human
```

review_report 无独立"建议"字段；人基于"发现 + 状态"自行判决，不捏造建议。

**解析容错**：用 stdlib re 行级正则。报告格式不符预期（段标题缺失/state 值非标准三态）→ 返回空清单 + stderr 警告（§6.2 文案），**不崩溃**。state 值是脆弱契约（`_write_review_report` 对 state 无 CHECK，全靠 JS 端纪律产出三态），无 DB 层兜底——容错是必须的。

### 6.5 --out

默认 stdout；`--out` 落盘（如 `review_escalate_vol{N}.md`）。

## 7. diff 命令（DB↔文件漂移检测）

### 7.1 签名

```
bedrock diff --project P (--chapter N | --volume N | --book) [--format md|txt] [--final] [--out PATH]
```

参数语义同 §4.1（--chapter=global_number，--volume=volume.id）。`--format` 默认 md。`--final`（新增，【审核修订】H3）：比对 `exports/final/` 区文件而非默认 `exports/`（draft 区）。

### 7.2 比对算法（两路直接重算 + 可选三路定位）

**文件定位【审核修订】H7**：diff 由 global_number 经 `chapter_filename(global_number)` 推导文件名（与 export 写文件共用同一函数，DRY），保证读写一致。

1. **DB 侧 hash**：用 `render_chapter_body(conn, chapter_id, fmt)`（§4 单章渲染器）生成该章"应然的正文内容"，sha256 → `db_hash`。
2. **文件侧 hash**：读 `exports/ch{NN}.{ext}`（默认）或 `exports/final/ch{NN}.{ext}`（`--final`）全文，sha256 → `file_hash`。
3. **比对**：
   - `db_hash == file_hash` → `ok`
   - 文件不存在 → `missing_file`
   - `db_hash != file_hash` → `drifted`
   - 该章 paragraph 行数=0 → `missing_db`

### 7.3 漂移定位（drifted 时增值，【审核修订】H4/H3）

**manifest 查询 key 锁定**：diff 单章漂移定位**只查** `scope='chapter' AND target_id=<该章 chapter.id> AND format=<fmt>` 的最新 manifest 行，得 `manifest_hash`。**绝不用 volume/book scope 的 hash 顶替**（整卷/全书导出的 content_hash 是整卷/全书文件的 hash，与单章 db_hash 不可比）。该章从未以 chapter scope 单独导出 → manifest 缺失 → 降级两路（只报 drifted，不定位）。

**status 分流【审核修订】H3**：默认（draft 区）查 `status='draft'` 最新行；`--final`（final 区）查 `status='final'` 最新行。堵 draft 覆盖漏洞——draft 区文件只对 draft manifest 行，final 快照只对 final manifest 行，两者各自独立校验，draft 覆盖 draft 区不会让 final 快照脱节无人校验（diff --final 仍会发现 final 快照与 DB 的偏离）。

三路对比：
- `db_hash == manifest_hash` 且 `file_hash != manifest_hash` → **文件侧被手改**（DB 与上次导出一致，文件被人改了）
- `file_hash == manifest_hash` 且 `db_hash != manifest_hash` → **DB 侧被改后未重导**（文件还是上次导出的，DB 正文变了）
- 三者都不同 → 两边都动过

**信任边界声明【审核修订】M3**：manifest 是"留痕"非"密码学证据"。三路定位的信任假设是 manifest 未被直接 SQLite UPDATE 篡改；防篡改靠 DB 权限/审计层，不在 SP6-A 范围。

### 7.4 输出

markdown 表（ch / global / DB段落数 / 文件 / 状态）+ 漂移详情（含三路定位）+ 汇总（ok/drifted/missing_file/missing_db 计数）。

### 7.5 与 export 的关系

diff 复用 `render_chapter_body` 与 `chapter_filename`（DRY）生成 DB 侧内容与文件名，但**不调用 export、不写任何文件**——纯只读。manifest 只读不写。

## 8. 测试策略

`tests/bedrock/test_reader_commands.py`，延续 pytest + tmp_project fixture（已有，零新基础设施）。

**纯函数测试（主体）**：
- export：
  - 单章 md/txt 渲染（章标题层级、段落 seq、空行）
  - 卷跳过非 completed + stderr 跳过清单
  - **空卷报错（0 completed → SystemExit）**【审核修订】M4
  - `--final` 写 `exports/final/` 快照 + manifest status=final
  - `--out` 覆盖默认路径
  - manifest 字段正确（scope/format/content_hash/status/source_snapshot/target_id）
  - **round-trip 不变量：manifest.content_hash == 文件实际 sha256**【审核修订】M9e
  - **--book 跨卷按 global_number 全局升序**【审核修订】M5
- diagnose：
  - 必须 scope（否则 SystemExit）
  - `--book --with-l2` 互斥（SystemExit）
  - flag-only 模式标记块 + L2 hard_gate 列填 `n/a（flag-only）` + L2 来源 `flag（留痕）` + trace 注释
  - with-l2 模式 + L2 来源 `live（当前正文）` + 调 run_l2
  - **diagnose 不写 volume_review（只读断言：调用前后 blocking 字段不变）**【审核修订】H1
  - **--book 逐卷欠债聚合：任一卷 high 未兑现 → 全书标 BLOCKING**【审核修订】H1
- show-review-report：
  - 默认原样输出
  - escalate-only：fixture 报告含 escalate_via_actionable + escalate_via_polish_broke（outcomes 有、actionable 无）→ 两者都列出，后者注"无 fix_instruction"【审核修订】reviewer1#9
  - plain：markdown 标记 + json 围栏 strip【审核修订】M7
  - 文件缺失 SystemExit
  - **V2 手写报告容错：喂 V2 格式 → 空清单 + 明确警告，不崩溃**【审核修订】H5
- diff：
  - ok（export 后 diff 全 ok）
  - drifted_db_changed（export 后改 DB 段落 → drifted，三路定位指向"DB 侧被改"）
  - drifted_file_changed（export 后手改文件 → drifted，三路定位指向"文件侧被改"）
  - missing_db / missing_file
  - **manifest 查询 key：该章仅 volume scope 导出过 → diff 降级两路（不拿 volume hash 顶替）**【审核修订】H4
  - **--final 分流：draft 覆盖 draft 区后，diff --final 仍发现 final 快照与 DB 偏离**【审核修订】H3

**CLI 薄封装测试**：仅测参数解析与 stdout 路径打印，不重复纯函数逻辑（DRY）。

**不写 e2e**：SP6-A 是只读导出/检测层，不触发 agent 编排，纯单测足够。

## 9. 与既有命令的边界

- export 不替代 verify-persisted（后者是管线门禁，检查"是否落盘"；export 是"把落盘的内容导成文件"）。
- diagnose 不替代 write-review-report（后者是 VolumeReview agent 的结论落盘；diagnose 是聚合管线级信号的体检，两者数据源不同）。
- diff 不替代 run-l2（后者是单章正文合规重算；diff 是 DB↔文件一致性，跨"正文状态"和"导出件状态"两个维度）。

## 10. 验收标准

- 4 个命令各自可独立运行。**diagnose/show-review-report/diff 完全不写 DB；export 仅写 export_manifest（短事务，失败降级警告）**。
- 全部测试通过（预计 ~25 个新单测，含审核新增的 round-trip / manifest key / final 分流 / 空卷 / book 排序 / V2 容错等，SP1-5 既有 121 测试不受影响）。
- 零新依赖（hashlib/re/stdlib only）。
- diagnose 报告的自标注规范（文件名 + 元数据块 + L2 来源列 + L2 hard_gate 模式值 + trace 注释）全部落实。
- diff 三路定位正确区分"DB 改 / 文件改 / 两边改"，且 manifest 查询严格按 `(scope='chapter', target_id, format, status)` 过滤。
