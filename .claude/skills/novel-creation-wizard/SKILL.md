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
    {"name": "人物名", "pronoun": "他", "role": "protagonist", "personality": "性格",
     "secrets": [
       {"key": "public_face", "value": "读者早期所见的人设/身份", "reveal_at": null},
       {"key": "true_identity", "value": "逐步揭示的真身/动机", "reveal_at": 9}
     ]}
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
- **角色揭示弧必须显式建模**(防 writer 临场发挥→跨章身世矛盾):凡有"公开身份≠真实身份"或动机/身世需逐步揭示的角色,写进该角色 `secrets[]`——`reveal_at` = 读者/作者得知真相的章号(揭示章前 writer 只见公开面,揭示章才解封真身)。`reveal_at` 缺省或 null = 一直公开。主角通常无 secrets(所见即所得);反派/神秘配角最常需要。**不要把揭示留给 writer 临场编——种子不编码,卷审就会把它当矛盾抓。**
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
