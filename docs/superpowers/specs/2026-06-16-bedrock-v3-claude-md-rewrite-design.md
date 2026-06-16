# Bedrock V3 — CLAUDE.md 重写 + 旧管线归档 设计

**日期**: 2026-06-16
**状态**: 待用户审核
**背景**: V3(代号 Bedrock)开发基本完成(SP1-6C,274 测试),进入实战。现 CLAUDE.md 描述的整套(v1/v2 管线、graph.json、`src/novel_kg` CLI、ChapterAgent 架构、悬链驱动)对 Bedrock V3 几乎全错,且未提及 V3。本设计把 CLAUDE.md 重写为 Bedrock V3 操作指南,旧内容归档不删。

---

## 1. 目标与非目标

**目标**
- CLAUDE.md 成为 Bedrock V3 的唯一操作真相源(主编排视角)。
- 消除 CLAUDE.md 与 V3 代码的所有矛盾(数据后端、信任锚、写面、命令、披露模型)。
- 旧管线文档/模板/workflow 归档保留(git 历史 + juedi 维护可回溯),但不出现在主路径。

**非目标**
- 不删除任何代码(`src/novel_kg/` 原地不动)。
- 不在 CLAUDE.md 重复列文风数值(字数/句式/破折号)——委托给 V3 的 beat 契约 + fingerprint 机制,单一真相源。
- 不重写 V3 workflow / template 文件本身(它们已就绪)。
- 不迁移 juedi 历史(旧数据留在 graph.json,不动)。

---

## 2. 关键决策(已与用户确认)

| 决策 | 选择 |
|------|------|
| 新旧关系 | 彻底切换,Bedrock V3 为唯一管线 |
| 旧物处置 | 全部归档,不删代码 |
| 文风数值 | 委托 V3 机制,不在 CLAUDE.md 重复列 |
| CLAUDE.md 结构 | 方案 A:操作手册型(主编排视角) |
| 归档位置 | `archive/legacy-pipeline/` |
| novel-creation-wizard | 本次顺带重写为 V3 版(`bedrock init` + 种 DB,不再生成 framework/handoff) |

---

## 3. V3 真相基准(写进 CLAUDE.md 的事实,均经代码核实)

- **数据后端**: `bedrock.db`(SQLite)。正文 SSOT = `paragraph` 表。导出文件单向,绝不回填。
- **信任锚**: L2 硬门禁(`run-l2`,零 LLM,beat 契约)。`verify-persisted` 不过则拒绝落盘。
- **写面**: 写操作走 `python -m src.bedrock` CLI(mark-*/unlock-volume/init)及 repo 函数封装。MCP 8 工具**全只读** = 抗博弈。
- **披露模型**: boot-context 从 bedrock.db 取(beat 契约 + reader 披露的秘密 + style 指纹 + constants)。framework.md / handoff.md **不再使用**。
- **文风**: 由 beat 契约 + fingerprint(target_distribution)约束;`word_count_target=(3000,5000)` 在 boot constants,不在 CLAUDE.md。
- **amendment**: 自动审计日志,各 repo 函数 mutate 时自动 `record_amendment`;agent 不手写 amendment 表。
- **实战 workflow**: `bedrock-chapter.js`(Boot→Write→L2→Edit≤3轮→Persist→Telemetry)、`bedrock-volume-review.js`(旗驱动 Opus 复查+修正+报告)。
- **模板源**: `.claude/templates/bedrock/{chapter_writer,edit_agent,volume_review}.md`。
- **新项目种子模型**(`scripts/seed_bedrock_demo.py` 为参照): `init_project` → `create_volume`/`create_chapter`(status=planned)→ `create_beat`(purpose + pov_character_id)→ `create_character`(pronoun/role/personality)→ worldbook(`add_location`/`add_theme`/`add_motif`/`add_faction`/`add_time_period`/`add_constant`)→ outline(`master_outline`/`volume_outline`/beat_contracts)→ style fingerprint。**paragraph 表不由种子写入**,由 ChapterWriter 在 bedrock-chapter.js 里产。

---

## 4. 新 CLAUDE.md 内容设计

### 4.1 章节结构

1. **Bedrock V3 是什么**(3-4 句:SSOT / 信任锚 / 写面抗博弈)
2. **⚠️ 铁律(V3 版)** — 见 4.2
3. **主编排实战主循环** — 见 4.3
4. **命令与工具参考** — 见 4.4
5. **渐进披露(V3 版)** — 见 4.5

### 4.2 铁律(V3 版,8 条,替换旧全部)

1. L2 不过 → `verify-persisted` 拒绝落盘,该章不能进下一章。
2. **写入 bedrock.db 只能经 repo 函数(update_*/override_*/set_*/mark-* 等)或其 CLI/web 封装——它们自动记 amendment 审计。禁止 agent 直连 sqlite 或裸 SQL 改任何表(含 paragraph / chapter_review_flag / beat / worldbook)。**
3. drift 取**最差轮**(watchdog 看系统性造假,非末轮修好的假象)。
4. Edit 软门禁 ≤3 轮;耗尽 `mark-unresolved` 并判 `likely_rule_or_model`。
5. Polish 后必须重跑 L2;破 beat 要 `mark-polish-broke-beat`。
6. 卷末必跑 `bedrock-volume-review.js`;跨卷悬链欠债 BLOCKING 需 `unlock-volume` 留痕。
7. **禁止并行派生 ChapterWriter**;严格串行,章间看 status。
8. Reviewer ≠ Fixer,每章修正 ≤1 轮,不无限重试。

### 4.3 主编排实战主循环

```
对卷内每章 N(串行):
  Workflow({scriptPath:".claude/workflows/bedrock-chapter.js",
            args:{project, chapter:N, volume, exportPath}})
  → status=="ok" 才进 N+1;"failed"(forced_persist_failed)停,人工介入

全卷 done:
  Workflow({scriptPath:".claude/workflows/bedrock-volume-review.js",
            args:{project, volume, chapterRange:[start,end]}})
  → show_review_report --escalate-only 读 escalate_human 项 → 人工判决
```

### 4.4 命令与工具参考

**CLI** (`python -m src.bedrock <cmd>`):
init / run-l2 / boot-context / verify-persisted / mark-unresolved / mark-polish-broke-beat / mark-forced-persist-failed / mark-advisory-drift / collect-runtime / run-watchdog / cross-volume-debt / get-review-flag / write-review-report / unlock-volume / export / diagnose / show-review-report / diff

**MCP 只读 8 工具**:
export_project / diagnose / show_review_report / diff_drift / run_l2_check / get_chapter_flag / list_volumes / list_chapters

### 4.5 渐进披露(V3 版)

- 真相源 = `bedrock.db`;framework.md / handoff.md 不再用。
- 子代理启动靠 `boot-context`(beat 契约 + reader 披露的秘密 + style 指纹 + constants)。
- 文风由 beat 契约 + fingerprint 约束,数值不在本文件列,调参看 `volume_type_matrix` / config。
- 新作品:`bedrock init` → 向 DB 灌 worldbook/outline/beat_contracts/volume_type/style。
- 子代理 prompt 细节指向 `.claude/templates/bedrock/*.md`(不复制进 CLAUDE.md)。

### 4.6 novel-creation-wizard 重写(V3 版)

旧向导生成 framework.md/handoff.md + 写 graph.json,全废。重写为 bedrock 种子向导:

- **Phase 1 需求收集**(不变):创作方向一句话 + 篇幅默认(改默认 = 1 卷 6 章,可 6/8/12)+ 风格倾向。
- **Phase 2 生成世界观**(schema 重映射到 bedrock 表):
  - `characters[]` → `create_character(name, pronoun, role, personality)` + 可选 `add_secret`
  - `locations[]` → `add_location(name, loc_type, description)`
  - `themes[]` → `add_theme(name, description, evolution)`
  - `motifs[]` → `add_motif(name, meaning, evolution)`
  - `time_periods[]` → `add_time_period(label, chapter_start, chapter_end, description)`
  - `style_guides[]` → style fingerprint(目标分布,委托 volume_type_matrix 默认,不手填数值)
  - `premise/title` → `add_constant(work_name 已由 init 写)` + master_outline
- **Phase 3 种入 bedrock.db**(替换旧"写图谱"):
  - `python -m src.bedrock init <path> --name <title>`
  - 用 repo 函数(经一个种子脚本或直接 `python -m src.bedrock` 无写封装时,落一个 `scripts/seed_project.py` 通用种子)灌入:volume(s)、chapter(s)(status=`planned`)、beat 契约、角色、worldbook、master_outline
  - **不创建 paragraph**(写作由 bedrock-chapter.js 产)
- **Phase 4 验收**:`python -m src.bedrock diagnose --project <path> --book` + `list-volumes` 确认结构齐;`boot-context --chapter 1 --volume 1` 确认可装配。

> 注:bedrock CLI 目前无通用"灌世界设定"写子命令(只有 init + mark-* + unlock)。种子写入要么(a)直接调 repo 函数写一个 `scripts/seed_project.py`,要么(b)扩 CLI 加 `seed` 子命令。**默认走 (a)**(与 seed_bedrock_demo.py 一致,零 CLI 改动),向导生成一个项目专属种子脚本并执行。

---

## 5. 归档设计

```
archive/legacy-pipeline/
├── CLAUDE_legacy_v2.md          ← 现 CLAUDE.md 全文(只读副本)
├── skills/
│   └── novel-creation-wizard/   ← 旧向导全文(SKILL.md 旧版)
├── templates/                   ← chapter_agent.md, chapter_agent_v2.md,
│                                   volume_review.md, volume_review_v2.md,
│                                   framework.md, handoff.md
└── workflows/                   ← chapter-pipeline.js, volume-pipeline.js,
                                    volume-pipeline-v2.js
```

**不动的**:
- `src/novel_kg/` 原地(juedi 项目仍依赖读 graph.json)。
- `projects/juedi_tiantong_v1/` 不动。
- `.claude/templates/bedrock/` 成为唯一模板源。
- `novel-creation-wizard` 原地重写(不归档;归档的是改写前的旧版副本)。

**归档后 CLAUDE.md 不再提及** 旧 CLI(`python -m src.novel_kg.mcp_cli ...`)、旧 workflow、旧模板路径。

---

## 6. 验证(实施后)

- [ ] CLAUDE.md 中无任何 `src.novel_kg` / `graph.json` / `mcp_cli` / `ChapterAgent`(旧架构) / `volume-pipeline`(旧) 引用。
- [ ] 铁律第 2 条措辞与 4.2 一致。
- [ ] CLI 命令表与 `src/bedrock/__main__.py` 的 subparser 完全一致(18 个)。
- [ ] MCP 工具表与 `mcp_server.py` 注册的 8 工具一致。
- [ ] `archive/legacy-pipeline/` 含旧 CLAUDE.md 全文 + 6 模板 + 3 workflow + 旧向导副本。
- [ ] 旧模板/原 `.claude/templates/` 下旧文件已移走(`.claude/templates/bedrock/` 唯一留存)。
- [ ] `bedrock init` + boot-context 的描述与代码一致。
- [ ] novel-creation-wizard SKILL.md 无 framework.md/handoff.md/graph.json 引用,改为 `bedrock init` + 种 DB。
- [ ] 跑一遍重写后的向导生成一个 throwaway 项目,`diagnose --book` + `boot-context --chapter 1` 通过。

---

## 7. 风险与对策

- **风险**: juedi 项目维护时找不到旧文档。**对策**: `archive/legacy-pipeline/CLAUDE_legacy_v2.md` 完整保留,git 历史可追溯。
- **风险**: 新 CLAUDE.md 漏掉某条 V3 门禁,agent 实战犯错。**对策**: 铁律 8 条对照 workflow `bedrock-chapter.js` / `bedrock-volume-review.js` 逐条核实(已做)。
- **风险**: 归档移动导致 `.claude/skills/` 或其他引用断链。**对策**: 实施前 grep 全仓引用旧模板/workflow 路径,确认无 agent skill 依赖。
