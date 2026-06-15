# Bedrock V3 — CLAUDE.md 重写 + 旧管线归档 + 向导 V3 化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 CLAUDE.md 重写为 Bedrock V3 唯一操作真相源,归档全部旧管线产物(不删代码),并把 novel-creation-wizard 重写为 V3 种子向导。

**Architecture:** 纯文档/归档/技能改写任务,无产品代码改动(`src/` 不动)。分四段:① 归档旧物 → ② 重写 CLAUDE.md → ③ 重写向导 → ④ 验证(grep 查残留 + 跑一遍向导冒烟)。

**Tech Stack:** Markdown、git mv、`python -m src.bedrock` CLI、Skill 文档。

**Spec:** `docs/superpowers/specs/2026-06-16-bedrock-v3-claude-md-rewrite-design.md`

**分支:** 在 `master` 上开 `docs/bedrock-v3-claude-md` 分支做。每个 Task 结束 commit。

---

## File Structure

| 文件 | 动作 | 责任 |
|------|------|------|
| `CLAUDE.md` | 重写 | V3 操作指南(主编排视角) |
| `archive/legacy-pipeline/CLAUDE_legacy_v2.md` | 新建(旧内容副本) | 旧 CLAUDE.md 全文留档 |
| `archive/legacy-pipeline/templates/*` | git mv | 6 个旧模板 |
| `archive/legacy-pipeline/workflows/*` | git mv | 3 个旧 workflow |
| `archive/legacy-pipeline/skills/novel-creation-wizard/SKILL.md` | 新建(旧副本) | 旧向导留档 |
| `.claude/skills/novel-creation-wizard/SKILL.md` | 重写 | V3 种子向导 |
| `scripts/seed_project.py` | 新建 | 通用 bedrock 项目种子脚本(供向导演用) |

---

## Task 1: 归档旧管线产物

**Files:**
- Create: `archive/legacy-pipeline/` 目录树
- Move: 旧模板/旧 workflow
- Copy: 旧 CLAUDE.md、旧向导 SKILL.md(留档副本)

- [ ] **Step 1: 建归档目录**

```bash
mkdir -p archive/legacy-pipeline/templates archive/legacy-pipeline/workflows archive/legacy-pipeline/skills/novel-creation-wizard
```

- [ ] **Step 2: 复制旧 CLAUDE.md 留档**

```bash
cp CLAUDE.md archive/legacy-pipeline/CLAUDE_legacy_v2.md
```

- [ ] **Step 3: 复制旧向导留档(原地向导稍后重写,先存旧版)**

```bash
cp .claude/skills/novel-creation-wizard/SKILL.md archive/legacy-pipeline/skills/novel-creation-wizard/SKILL.md
```

- [ ] **Step 4: git mv 旧模板到归档**

```bash
git mv .claude/templates/chapter_agent.md        archive/legacy-pipeline/templates/
git mv .claude/templates/chapter_agent_v2.md     archive/legacy-pipeline/templates/
git mv .claude/templates/volume_review.md        archive/legacy-pipeline/templates/
git mv .claude/templates/volume_review_v2.md     archive/legacy-pipeline/templates/
git mv .claude/templates/framework.md            archive/legacy-pipeline/templates/
git mv .claude/templates/handoff.md              archive/legacy-pipeline/templates/
```

- [ ] **Step 5: git mv 旧 workflow 到归档**

```bash
git mv .claude/workflows/chapter-pipeline.js     archive/legacy-pipeline/workflows/
git mv .claude/workflows/volume-pipeline.js      archive/legacy-pipeline/workflows/
git mv .claude/workflows/volume-pipeline-v2.js   archive/legacy-pipeline/workflows/
```

- [ ] **Step 6: 确认 .claude/templates/ 仅剩 bedrock/,workflows/ 仅剩 bedrock-*.js**

```bash
ls .claude/templates/ .claude/workflows/
```
Expected: `templates/` 只有 `bedrock/` 目录;`workflows/` 只有 `bedrock-chapter.js`、`bedrock-volume-review.js`。

- [ ] **Step 7: 确认 juedi 项目没被波及(它的模板引用在项目内,不在 .claude/templates)**

```bash
ls projects/juedi_tiantong_v1/ | head
```
Expected: 项目目录原样 intact(它用的是 graph.json,不依赖刚移走的 .claude/templates)。

- [ ] **Step 8: Commit**

```bash
git add archive/ .claude/templates/ .claude/workflows/
git commit -m "chore(archive): 归档旧管线模板/workflow/向导到 archive/legacy-pipeline

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: 重写 CLAUDE.md 为 Bedrock V3 操作指南

**Files:**
- Modify(全量重写): `CLAUDE.md`

- [ ] **Step 1: 用以下完整内容覆盖 CLAUDE.md**

```markdown
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

- `bedrock-chapter.js` 内部:Boot → Write → L2+Repair(≤3轮) → Polish → Persist+Telemetry
- `bedrock-volume-review.js` 内部:Gather(旗章+watchdog+跨卷欠债) → Review(Opus) → Fix → Reverify → Report

---

## 命令与工具参考

### CLI(`python -m src.bedrock <cmd>`,cwd = D:/novel_test)

| 命令 | 用途 |
|------|------|
| `init <path> --name <作品名> [--force]` | 初始化新作品(建目录+空白 DB) |
| `run-l2 --project <p> --chapter N` | 单章 L2 全量重算(零 LLM),JSON 输出 |
| `boot-context --project <p> --chapter N --volume V` | 装配子代理启动上下文 |
| `verify-persisted --project <p> --chapter N [--export-path]` | 强制落盘门禁 |
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
```

- [ ] **Step 2: 验证 CLAUDE.md 无旧引用**

```bash
grep -nE "src\.novel_kg|mcp_cli|graph\.json|ChapterAgent|volume-pipeline|chapter_agent|framework\.md|handoff\.md|get_writing_prompt|add_outline_entry" CLAUDE.md
```
Expected: 无输出(或仅在"旧管线已归档"那一行出现 `graph.json`/`src/novel_kg` —— 这是允许的明示归档句)。若命中其它行,改掉。

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: 重写 CLAUDE.md 为 Bedrock V3 操作指南(主编排视角)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 写通用种子脚本 scripts/seed_project.py

向导需要一个可执行的种子入口。bedrock CLI 无通用"灌世界设定"写子命令,按 spec 默认走方案 (a):一个通用种子脚本,向导为每个新项目生成参数并调用它。

**Files:**
- Create: `scripts/seed_project.py`

- [ ] **Step 1: 写 scripts/seed_project.py**

```python
"""通用 bedrock 项目种子脚本:从 world_setup JSON 灌入 bedrock.db。

用法:
  python scripts/seed_project.py --project <path> --setup <world_setup.json>

world_setup.json schema(由 novel-creation-wizard 生成):
{
  "title": str, "premise": str,
  "volumes": [{"number":1,"name":"卷名","chapter_start":1,"chapter_end":6,"volume_type":"opening"}],
  "chapters": [{"global_number":1,"volume":1,"title":"章标题","beats":[{"seq":1,"purpose":"...","pov":"角色名"}]}],
  "characters": [{"name":"..","pronoun":"他/她","role":"protagonist|supporting|antagonist","personality":".."}],
  "locations": [{"name":"..","loc_type":"..","description":".."}],
  "themes": [{"name":"..","description":"..","evolution":".."}],
  "motifs": [{"name":"..","meaning":"..","evolution":".."}],
  "time_periods": [{"label":"..","chapter_start":1,"chapter_end":6,"description":".."}],
  "master_outline": {"theme_evolution":"..","key_arcs":[..],"key_milestones":[..],"rhythm_curve":".."}
}

不创建 paragraph —— 正文由 bedrock-chapter.js 的 ChapterWriter 产。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import (
    create_volume, create_chapter, create_beat,
)
from src.bedrock.repositories.character import create_character
from src.bedrock.repositories.worldbook import (
    add_constant, add_location, add_theme, add_motif, add_time_period,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--setup", type=Path, required=True)
    args = ap.parse_args()

    setup = json.loads(args.setup.read_text(encoding="utf-8"))
    conn = get_connection(args.project)
    try:
        add_constant(conn, key="premise", value=setup.get("premise", ""),
                     source_note="seed_project")

        # 角色(先建,beat 的 pov 按名查 id)
        char_id = {}
        for c in setup.get("characters", []):
            cid = create_character(conn, name=c["name"], pronoun=c.get("pronoun", "他"),
                                   role=c.get("role", "supporting"),
                                   personality=c.get("personality", ""))
            char_id[c["name"]] = cid

        # 卷
        vol_id = {}
        for v in setup.get("volumes", []):
            vid = create_volume(conn, v["number"], v["name"], v["chapter_start"],
                                v["chapter_end"], v.get("volume_type", "opening"))
            vol_id[v["number"]] = vid

        # 章 + beat(状态 planned,未写)
        for ch in setup.get("chapters", []):
            cid = create_chapter(conn, volume_id=vol_id[ch["volume"]],
                                 global_number=ch["global_number"],
                                 title=ch["title"], status="planned")
            for b in ch.get("beats", []):
                pov = char_id.get(b.get("pov"))
                create_beat(conn, chapter_id=cid, sequence=b["seq"],
                            purpose=b["purpose"], pov_character_id=pov)

        # worldbook
        for loc in setup.get("locations", []):
            add_location(conn, name=loc["name"], loc_type=loc.get("loc_type", ""),
                         description=loc.get("description", ""))
        for t in setup.get("themes", []):
            add_theme(conn, name=t["name"], description=t.get("description", ""),
                      evolution=t.get("evolution", ""))
        for m in setup.get("motifs", []):
            add_motif(conn, name=m["name"], meaning=m.get("meaning", ""),
                      evolution=m.get("evolution", ""))
        for tp in setup.get("time_periods", []):
            add_time_period(conn, label=tp["label"], chapter_start=tp["chapter_start"],
                            chapter_end=tp["chapter_end"], description=tp.get("description", ""))

        # master_outline
        mo = setup.get("master_outline")
        if mo:
            conn.execute(
                "INSERT OR REPLACE INTO master_outline(id,theme_evolution,key_arcs,key_milestones,rhythm_curve) "
                "VALUES(1,?,?,?,?)",
                (mo.get("theme_evolution", ""),
                 json.dumps(mo.get("key_arcs", []), ensure_ascii=False),
                 json.dumps(mo.get("key_milestones", []), ensure_ascii=False),
                 mo.get("rhythm_curve", "")))

        conn.commit()
        print(f"seeded {args.project}: "
              f"{len(char_id)} chars, {len(vol_id)} vols, "
              f"{len(setup.get('chapters', []))} chapters")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 确认依赖的 repo 函数签名与代码一致**

```bash
grep -n "^def create_volume\|^def create_chapter\|^def create_beat\|^def create_character" src/bedrock/repositories/plot_tree.py src/bedrock/repositories/character.py
```
Expected: 能找到 `create_volume`、`create_chapter`、`create_beat`、`create_character`。若签名(参数名/顺序)与脚本不符,以代码为准修正脚本。

- [ ] **Step 3: Commit**

```bash
git add scripts/seed_project.py
git commit -m "feat(bedrock): 通用项目种子脚本 scripts/seed_project.py

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: 重写 novel-creation-wizard 为 V3 种子向导

**Files:**
- Modify(全量重写): `.claude/skills/novel-creation-wizard/SKILL.md`

- [ ] **Step 1: 用以下完整内容覆盖 .claude/skills/novel-creation-wizard/SKILL.md**

````markdown
---
name: novel-creation-wizard
description: 交互式创建新小说项目(Bedrock V3)。引导用户从创作方向到完整世界观,种入 bedrock.db。
triggers:
  - "创建小说"
  - "新建项目"
  - "开始创作"
  - "创建新作品"
---

# 小说项目创建向导(Bedrock V3)

按以下 4 阶段引导用户创建新小说项目,最终种入 `bedrock.db`。Agent 自身作为 LLM 直接生成世界观,不调用外部 API。

> V3 真相源是 `bedrock.db`,**不生成 framework.md / handoff.md / graph.json**。

## Phase 1 — 需求收集

只问必须的:

- **创作方向**:一句话描述想写什么。
- **篇幅**:默认 1 卷 6 章(可选 6/8/12 章)。
- **作品标识符**:英文蛇形(如 `mohian`),用作 `projects/<标识符>/` 目录名。

可选(用户没提就不问):风格倾向由 Agent 据题材判断。

## Phase 2 — 生成 world_setup JSON

按以下 schema 生成(保存到 `projects/<标识符>/world_setup.json`):

```json
{
  "title": "作品标题",
  "premise": "一句话核心冲突/悬念",
  "volumes": [
    {"number": 1, "name": "卷名", "chapter_start": 1, "chapter_end": 6, "volume_type": "opening"}
  ],
  "chapters": [
    {"global_number": 1, "volume": 1, "title": "章标题",
     "beats": [{"seq": 1, "purpose": "本章核心场景与人物抉择", "pov": "主角名"}]}
  ],
  "characters": [
    {"name": "人物名", "pronoun": "他", "role": "protagonist", "personality": "性格"}
  ],
  "locations": [{"name": "地点", "loc_type": "city", "description": "描述"}],
  "themes": [{"name": "主题", "description": "描述", "evolution": "演变"}],
  "motifs": [{"name": "母题", "meaning": "含义", "evolution": "演变"}],
  "time_periods": [{"label": "时间段", "chapter_start": 1, "chapter_end": 6, "description": "描述"}],
  "master_outline": {
    "theme_evolution": "主题如何演进",
    "key_arcs": ["主线A", "主线B"],
    "key_milestones": ["ch1 觉知", "ch6 抉择"],
    "rhythm_curve": "缓起-急转"
  }
}
```

要求:
- 每章至少 1 个 beat,带 `purpose`(本章叙事目的)与 `pov`(视角角色名,须在 characters 内)。
- `volume_type` 取 `opening|development|climax|resolution`。
- 文风数值**不写进 setup**——由 V3 的 volume_type_matrix + style fingerprint 默认约束。

## Phase 3 — 种入 bedrock.db

```bash
# 1. 初始化空 DB
python -m src.bedrock init "projects/<标识符>" --name "<title>"

# 2. 灌世界设定(通用种子脚本)
python scripts/seed_project.py --project "projects/<标识符>" --setup "projects/<标识符>/world_setup.json"
```

`seed_project.py` 建 volume/chapter(status=planned)/beat 契约/角色/worldbook/master_outline。**不建 paragraph**——正文由 `bedrock-chapter.js` 的 ChapterWriter 产。

## Phase 4 — 验收

```bash
python -m src.bedrock diagnose   --project "projects/<标识符>" --book
python -m src.bedrock boot-context --project "projects/<标识符>" --chapter 1 --volume <卷1的id>
```

- 卷清单用 MCP 工具 `list_volumes` / `list_chapters` 查(CLI 无此子命令,它们是 MCP-only)。
- `diagnose --book` 无报错,章节状态为 planned。
- `boot-context` 返回 beat 契约 + 指纹 + constants(证明第 1 章可装配)。

通过后向用户报告:作品已就绪,可用主编排主循环(CLAUDE.md「实战主循环」)从第 1 章开始写。
````

- [ ] **Step 2: 验证向导无旧引用**

```bash
grep -nE "framework\.md|handoff\.md|graph\.json|src\.novel_kg|add_outline_entry|write_extraction" .claude/skills/novel-creation-wizard/SKILL.md
```
Expected: 无输出。

- [ ] **Step 3: 确认 CLI 表与 `__main__.py` 一致(向导只引用真实存在的子命令)**

```bash
python -m src.bedrock --help
```
Expected: 子命令列表含 `init`、`diagnose`、`boot-context`、`export`、`show-review-report`;**不含** `list-volumes`/`list-chapters`(这两个是 MCP-only,向导 Phase 4 已改用 MCP 工具查卷清单)。若与预期不符,以实际为准修正向导。

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/novel-creation-wizard/SKILL.md
git commit -m "feat(wizard): 重写 novel-creation-wizard 为 Bedrock V3 种子向导

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: 端到端冒烟 + 收尾验证

**Files:** 无修改,只跑命令。

- [ ] **Step 1: 用重写后的向导流程,造一个 throwaway 项目**

手动按向导 Phase 1-3 的命令跑(用最小 setup):先写一个最小 `world_setup.json`(1 卷 2 章、2 角色、1 beat/章),然后:

```bash
python -m src.bedrock init "projects/wizard_smoke" --name "冒烟"
python scripts/seed_project.py --project "projects/wizard_smoke" --setup "<最小 setup 路径>"
```

- [ ] **Step 2: 验收命令**

```bash
python -m src.bedrock diagnose --project "projects/wizard_smoke" --book
python -m src.bedrock boot-context --project "projects/wizard_smoke" --chapter 1 --volume <卷1 id>
```
Expected: `diagnose` 无报错、章节 planned;`boot-context` 返回 JSON 含 `beat_contracts` / `fingerprint` / `constants`。若失败,定位是种子脚本签名不匹配还是 schema 缺字段,回 Task 3/4 修。

- [ ] **Step 3: 清理 throwaway 项目**

```bash
rm -rf projects/wizard_smoke
```

- [ ] **Step 4: 全局残留扫描**

```bash
echo "--- CLAUDE.md ---"
grep -nE "src\.novel_kg|mcp_cli|ChapterAgent|chapter_agent\.md|volume-pipeline\.js|framework\.md|handoff\.md" CLAUDE.md
echo "--- 向导 ---"
grep -nE "framework\.md|handoff\.md|graph\.json|src\.novel_kg" .claude/skills/novel-creation-wizard/SKILL.md
echo "--- 模板/workflow 主路径 ---"
ls .claude/templates/ .claude/workflows/
echo "--- 归档完整性 ---"
ls archive/legacy-pipeline/templates/ archive/legacy-pipeline/workflows/ archive/legacy-pipeline/skills/novel-creation-wizard/
```
Expected:
- CLAUDE.md:仅"旧管线已归档"句可能含 `graph.json`/`src/novel_kg`,无其它。
- 向导:无输出。
- 主路径:`templates/` 只有 `bedrock/`;`workflows/` 只有 `bedrock-chapter.js`、`bedrock-volume-review.js`。
- 归档:6 模板 + 3 workflow + 1 旧向导 SKILL.md。

- [ ] **Step 5: 合并到 master**

```bash
git checkout master
git merge --no-ff docs/bedrock-v3-claude-md -m "docs: CLAUDE.md/向导切换到 Bedrock V3,旧管线归档"
```

- [ ] **Step 6: 更新 memory**

把这次切换写进 `C:\Users\Administrator\.claude\projects\D--novel-test\memory\`:新增 `bedrock-v3-production-cutover.md`(Bedrock V3 为唯一管线,旧管线归档于 archive/legacy-pipeline,CLAUDE.md/向导已 V3 化),并在 `MEMORY.md` 加一行指针。

---

## Self-Review 记录(写计划时已做)

- **Spec 覆盖**:spec §4.1-4.6 → Task 2(CLAUDE.md)+ Task 4(向导);§5 归档 → Task 1;§3 真相基准 → Task 2 内容;§6 验证 → Task 5。✓
- **占位符**:无 TBD/TODO。✓
- **一致性**:铁律第 2 条措辞在 spec §4.2 与计划 Task 2 内容一致;CLI 表 18 条与 `__main__.py` subparser 一致;MCP 8 工具一致;`seed_project.py` 调用的 repo 函数名与 `seed_bedrock_demo.py` 一致(create_volume/create_chapter/create_beat/create_character)。✓
- **已知待执行时确认点**:Task 3 Step 2(repo 函数签名核对,已与 seed_bedrock_demo.py 用法对齐)——执行时若签名不符以代码为准。`list-volumes/list-chapters` 已确认是 MCP-only,向导已改用 MCP 工具。
