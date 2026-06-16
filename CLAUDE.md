# CLAUDE.md — 小说创作系统(Bedrock V3)

## Bedrock V3 是什么

V3(代号 Bedrock)是当前唯一管线。三件事记住:

- **正文 SSOT = `bedrock.db` 的 `paragraph` 表。** 导出文件单向,绝不回填。
- **信任锚 = L2 硬门禁**(`run-l2`,零 LLM,beat 契约)。L2 不过,章节不落盘。
- **写面只走 `python -m src.bedrock` CLI;MCP 8 工具全只读** = 抗博弈。

旧管线(graph.json / `src/novel_kg` / framework.md / handoff.md)已归档至 `archive/legacy-pipeline/`,仅维护已完成的 juedi(239 章)时回看。**新作品一律走 V3。**

---

## ⚠️ 铁律(V3)

1. **L2 不过 → `verify-persisted` 拒绝落盘,该章不能进下一章。**
2. **写入 bedrock.db 只能经 repo 函数(`update_*`/`override_*`/`set_*`/`mark-*` 等)或其 CLI/web 封装——它们自动记 `amendment` 审计。禁止 agent 直连 sqlite 或裸 SQL 改任何表(含 `paragraph` / `chapter_review_flag` / `beat` / `worldbook`)。** `amendment` 是这些函数的自动副产物,不是 agent 手写的。
3. **drift 取最差轮**(watchdog 看系统性造假,不是末轮修好的假象)。
4. **Edit 软门禁 ≤3 轮;耗尽 `mark-unresolved` 并判 `likely_rule_or_model`。**
5. **Polish 后必须重跑 L2;破 beat 要 `mark-polish-broke-beat`。**
6. **卷末必跑 `bedrock-volume-review.js`;跨卷悬链欠债 BLOCKING 需 `unlock-volume` 留痕。**
7. **禁止并行派生 ChapterWriter;严格串行,章间看 status。**
8. **Reviewer ≠ Fixer,每章修正 ≤1 轮,不无限重试。**

---

## 主编排实战主循环

```text
对卷内每章 N(串行):
  Workflow({ scriptPath: ".claude/workflows/bedrock-chapter.js",
             args: { project, chapter: N, volume, exportPath } })
  → status=="ok" 才进 N+1;"failed"(forced_persist_failed)停,人工介入

全卷 done:
  Workflow({ scriptPath: ".claude/workflows/bedrock-volume-review.js",
             args: { project, volume, chapterRange: [start, end] } })
  → show-review-report --escalate-only 读 escalate_human 项 → 人工判决
```

- `bedrock-chapter.js` 内部:Boot → Write(ChapterWriter→`commit-paragraphs` 入库) → L2+Repair(≤3轮) → Polish(重 `commit-paragraphs`) → Persist+Telemetry
- `bedrock-chapter-edit.js` 内部(已落盘章节编辑,四模式):`mode=rewrite`(指令重写)/`polish`(按需润色)/`surgical`(段落外科,出 ops→`edit-paragraphs`)/`recheck`(重检+修复)。全复用精简 relay,L2/verify 信任锚不破。
- `bedrock-volume-review.js` 内部:Gather(旗章+watchdog+跨卷欠债) → Review(Opus) → Fix(**ops,经 edit-paragraphs**;agent 吐叙述/正文→解析失败→escalate,章节不动) → Reverify → Report。**Reviewer≠Fixer,每章1轮**。各 checkpoint 自动出 JSON 备份(章写→draft / 章编辑→first_review / 卷审→final)。

> **卷 Fix 必须 ops,禁整章 prose-return**(2026-06-17 教训):prose-return 时 Fix agent 会吐工作日志/思考过程当正文,commit-paragraphs 覆盖毁章(L2 语义盲曾静默放行)。现 Fix 走 edit-paragraphs ops,叙述无法解析→escalate 不碰章;加 commit-paragraphs 工作日志拒绝 + L2 pov 绑定(missing_character)+ empty_beat 规则三层兜底。

> **工作流运行时模型(2026-06-16 修正)**:Workflow 引擎是无 Node 沙箱(`require`/`process`/`execFileSync`/静态 `import`/`export default` 全不可用)。三个工作流(`bedrock-chapter.js` / `bedrock-chapter-edit.js` / `bedrock-volume-review.js`)均已按沙箱模型重写:`export const meta` 必须第一条;入参全局 `args` 在本 harness 以**字符串**传入须 `JSON.parse`;`pythonCli` 改派 Bash-runner 子代理执行 CLI;**模块级 `const`(schemas/worstDrift 等)必须声明在主流程之前,否则 TDZ**。

---

## 命令与工具参考

### CLI(`python -m src.bedrock <cmd>`,cwd = D:/novel_test)

| 命令 | 用途 |
|------|------|
| `init <path> --name <作品名> [--force]` | 初始化新作品(建目录+空白 DB) |
| `run-l2 --project <p> --chapter N` | 单章 L2 全量重算(零 LLM),JSON 输出 |
| `boot-context --project <p> --chapter N --volume V` | 装配子代理启动上下文 |
| `verify-persisted --project <p> --chapter N [--export-path]` | 强制落盘门禁 |
| `commit-paragraphs --project <p> --chapter N`(stdin=本章正文纯文本) | 正文入库 paragraph 表 + beat→written + 章→writing(幂等重写;可选 `@@beat:N@@` 标记分 beat) |
| `show-paragraphs --project <p> --chapter N` | 读章节段落 JSON(para_id/seq/beat_id/text),编辑定位用 |
| `edit-paragraphs --project <p> --chapter N`(stdin=ops JSON) | 段落级编辑写面:update/insert/delete/reorder 多 op 事务化(补铁律"写面只走 CLI"的段落编辑缺口) |
| `export-chapter-json --project <p> --chapter N --stage {draft\|first_review\|final}` | 章节结构化 JSON 备份(写完=draft / 编辑后=first_review / 卷审后=final),冗余备份 |
| `import-chapter-json --project <p> --chapter N --stage <s>` | 从 JSON 备份忠实恢复章节(清空重建,保 seq/beat_id/role);备份-恢复闭环的恢复端 |
| `mark-unresolved --project <p> --chapter N --rule-or-model {0\|1}` | 3轮耗尽(违规 JSON 走 stdin) |
| `mark-polish-broke-beat --project <p> --chapter N` | polish 引入 beat 违规 |
| `mark-forced-persist-failed --project <p> --chapter N` | 落盘失败 |
| `mark-advisory-drift --project <p> --chapter N` | 最差轮 drift(stdin JSON) |
| `collect-runtime --project <p> --chapter N [--editing-rounds R]` | 遥测(stdin: invocations/llm_calls) |
| `run-watchdog --project <p> --volume V` | 跨章 statistical watchdog |
| `cross-volume-debt --project <p> --volume V` | 跨卷悬链收敛门禁 |
| `get-review-flag --project <p> --chapter N` | 读 chapter_review_flag + has_flag |
| `write-review-report --project <p> --volume V` | 拼 review_report_vol{N}.md 落盘(stdin JSON) |
| `unlock-volume --project <p> --volume V --reason <r>` | 人工释放卷间 BLOCKING(留 amendment) |
| `export --project <p> (--chapter N\|--volume V\|--book) [--format md\|txt] [--final] [--out]` | 导出正文(单向) |
| `diagnose --project <p> (--volume V\|--book) [--with-l2] [--out]` | 体检报告(flag-only 快 / with-l2 慢) |
| `show-review-report --project <p> --volume V [--escalate-only] [--plain]` | 读整卷回读报告 |
| `diff --project <p> (--chapter N\|--volume V\|--book) [--format] [--final]` | DB↔文件漂移检测 |

`<p>` = 项目目录路径(含 bedrock.db)。`V` = `volume.id`(不是卷号)。`N` = global_number。

### MCP 只读 8 工具(抗博弈:无任何写/治理暴露)

`export_project` / `diagnose` / `show_review_report` / `diff_drift` / `run_l2_check` / `get_chapter_flag` / `list_volumes` / `list_chapters`

---

## 渐进披露(V3)

- **真相源 = `bedrock.db`。** `framework.md` / `handoff.md` 不再用。
- 子代理启动靠 `boot-context`:beat 契约 + reader 披露的秘密 + style 指纹 + constants。**不读 framework/handoff。**
- **文风由 beat 契约 + fingerprint(target_distribution)约束,数值不在本文件列。** 调参看 `src/bedrock/config/volume_type_matrix.py` 与 `src/bedrock/style/`。`word_count_target=(3000,5000)` 在 boot constants。
- **新作品**:`bedrock init` → 向 DB 灌 worldbook/outline/beat 契约/volume_type/style。用 `/novel-creation-wizard` 引导(它会落 `scripts/seed_project.py` 并执行)。
- 子代理 prompt 细节指向 `.claude/templates/bedrock/{chapter_writer,edit_agent,volume_review}.md`,**不复制进本文件**。

---

## 项目结构(V3)

```
novel_test/
├── CLAUDE.md                          # 本文件
├── src/bedrock/                       # V3 代码(管线/DB/repo/orchestration/web/mcp)
├── src/novel_kg/                      # 旧管线代码(juedi 维护用,不动)
├── projects/<作品>/
│   ├── bedrock.db                     # V3 唯一数据源
│   ├── exports/                       # 正文单向导出
│   └── review_report_vol{N}.md        # 整卷回读报告
├── .claude/
│   ├── templates/bedrock/             # V3 唯一模板源
│   ├── workflows/bedrock-chapter.js, bedrock-volume-review.js
│   └── skills/novel-creation-wizard/  # V3 种子向导
└── archive/legacy-pipeline/           # 旧管线归档(只读)
```

旧 v1/v2 工作流与铁律的演进记录见 `docs/pipeline-evolution/`。
