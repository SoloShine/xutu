# Handoff: Volume Writing — 《项目名》

## 当前进度

| 卷 | 章数 | 汉字数 | 状态 |
|---|------|-------|------|
| 第一卷·卷名 | N章 | ~X万 | 已完成/进行中/待写 |

**当前卷：** 第X卷·卷名（从第X章开始）

**下一步：** 补充第X卷大纲 → 开始第X卷写作

## 图谱状态（截至会话结束）

```
characters: N  | locations: N  | events: N
themes: N      | style_guides: N | motifs: N
chapter_arcs: N | suspense_threads: N
outline_entries: N | relationships: N
```

## 管线流程（严格串行，每章五步）

```
Step 0: 读框架 → Step 1: 子代理写初稿 → Step 2: 子代理编辑审查 → Step 3: 子代理提取JSON → Step 4: CLI写入图谱+弧线 → Step 5: 遥测注入 → 下一章
```

### Step 0 — 每卷/新会话必读
- `projects/<项目名>/framework.md` — 核心设定 + 全部卷大纲
- `projects/<项目名>/handoff.md` — 本文件（会话交接块）
- `CLAUDE.md` — 管线规则 + 风格约束
- `get_graph_stats --project <项目名>` — 图谱总览
- `get_all_threads --project <项目名>` — 当前悬念线状态
- **`get_derivation_context --project <项目名> --chapter <N> --lookback 3`** — 获取前三章弧线上下文

### Step 1 — 子代理写初稿
向子代理发送：本章定位 + 前章结尾 + 角色状态 + 目标字数(3000-4000) + 风格要求
使用 `get_writing_prompt --project <项目名> --chapter <N> --focused` 生成 prompt（--focused 节省40%+体积，只注入活跃悬念线）

### Step 2 — 子代理编辑审查
使用 `get_editing_prompt --project <项目名> --chapter <N>` 生成编辑 prompt
编辑子代理修改终稿，替换初稿文件

### Step 3 — 子代理提取JSON
使用 `get_extraction_prompt --project <项目名> --chapter <N>` 生成提取 prompt
提取事件/角色/地点/悬念线，写入 `extractions/` 目录

### Step 4 — CLI写入图谱
```bash
cd D:/novel_test
python -m src.novel_kg.mcp_cli write_extraction --project <项目名> --chapter <N>
python -m src.novel_kg.mcp_cli add_chapter_arc --project <项目名> --chapter <N> --purpose "..." --scenes "..." --ending "..." --structure-type "..."
```

### Step 5 — 遥测注入
```bash
python -m src.novel_kg.mcp_cli count_chapter_words --project <项目名> --chapter <N>
python -m src.novel_kg.mcp_cli inject_chapter_metrics --project <项目名> --chapter <N> --word-count <N> --editing-corrections <N> --editing-types "..."
python -m src.novel_kg.mcp_cli inject_agent_phase --project <项目名> --chapter <N> --phase combined --duration-ms <ms> --tool-uses <N>
```

## 风格约束（已在图谱中）

| 编号 | 规则 | 目标值 |
|------|------|--------|
| 1 | 禁止恐怖/阴森/诡异等直接情绪形容词 | 0处 |
| 2 | 段落2-4句为主 | — |
| 3 | 严格第三人称有限视角 | — |
| 4 | 禁止突然/忽然开头描述异常 | 0处 |
| 5 | 对话穿插动作/环境描写 | — |
| 6 | 悬疑感用精确事实制造 | — |
| 7 | 禁止直接解释世界观 | — |
| 8 | 「不是X，是Y」句式 | ≤5处/章 |
| 9 | 破折号（——） | ≤3处/千字 |
| 10 | 句号密度 | 15-25个/千字 |

**关键：改句式，不是换标点。** 碎片句合并为流畅长句，破折号改为逗号/冒号/删除。

## 文件命名

| 类型 | 格式 | 示例 |
|------|------|------|
| 正文 | `output/ch{NN}_generated.txt` | `ch01_generated.txt` |
| 提取JSON | `extractions/extraction_ch{NN}.json` | `extraction_ch01.json` |
| 写作prompt | `prompts/writing_ch{NN}.txt` | `writing_ch01.txt` |
| 提取prompt | `prompts/extraction_ch{NN}.txt` | `extraction_ch01.txt` |
| 编辑prompt | `prompts/editing_ch{NN}.txt` | `editing_ch01.txt` |
| 遥测 | `telemetry/ch{N}_report.json` | `ch1_report.json` |

## 检查清单

- [ ] Step 0 已完成（读框架/handoff/图谱）
- [ ] 编辑审查已完成
- [ ] 汉字数 3000-4000
- [ ] 标题格式：`**第X卷 第N章 标题**`
- [ ] 章末有「参考来源：」
- [ ] 提取JSON已写入图谱（用 get_graph_stats 确认）
- [ ] chapter_arc 已写入
- [ ] prompt已落盘
- [ ] 遥测已注入
- [ ] 新卷时：framework.md / project.yaml / world_setup.json 已同步更新
- [ ] **每卷结束时：校验实写章数 = 大纲计划章数（如不等，更新framework并记录差异原因）**

---

## 会话交接块

### 前卷结尾状态（截至ChN）
<!-- 上一卷最后一章结束时发生了什么，角色在什么位置、什么心态 -->

### 当前全局状态
- **主角身份**：<!-- 当前身份和权限 -->
- **社交圈**：<!-- 关键人物和关系 -->
- **已有情报**：<!-- 已获取的重要信息列表 -->
- **当前位置**：<!-- 角色所在地点 -->
- **时间**：<!-- 故事内时间 -->

### 当前卷待推进的悬念线
- **P0** — <!-- 最关键的悬念线 -->
- **P1** — <!-- 重要悬念线 -->
- **P2** — <!-- 次要悬念线 -->

### 代词注意事项（如有跨性别角色）
<!-- 列出角色性别和对应代词，防止写作子代理跨卷时丢失设定 -->

### 全局章节编号
- Vol1 = ch01-chXX（第一卷·卷名）— 已完成
- Vol2 = chXX-chYY（第二卷·卷名）— 已完成
- VolN = chAA-chBB（第N卷·卷名）— 进行中/待规划

### 核心设定提醒
<!-- 3-5条最关键的世界观规则，子代理容易遗忘的 -->

### 本地文件清单
- `projects/<项目名>/framework.md` — 完整设定+全部卷大纲
- `projects/<项目名>/handoff.md` — 本文件
- `projects/<项目名>/project.yaml` — 项目元数据
- `projects/<项目名>/world_setup.json` — 世界观数据
- `projects/<项目名>/graph.json` — 图谱数据
- `projects/<项目名>/output/` — N章正文
- `projects/<项目名>/extractions/` — N个提取JSON
- `projects/<项目名>/prompts/` — 所有prompt落盘（writing/editing/extraction各N个）
- `projects/<项目名>/telemetry/` — 遥测报告
