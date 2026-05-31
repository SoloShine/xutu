# Handoff: Volume Writing — 《绝地天通》

## 当前进度

| 卷 | 章数 | 汉字数 | 状态 |
|---|------|-------|------|
| 第一卷·萌动 | 12章 | ~4.5万 | 已完成+校审+风格修复 |
| 第二卷·降临 | 20章 | ~7.9万 | 已完成+校审+风格修复 |
| 第三卷·暗流 | 20章 | ~7.8万 | 已完成+风格修复 |
| 第四卷·较量 | 14章 | ~4.2万 | 已完成 |
| 第五卷·闭环 | 14章 | ~4.2万 | 已完成 |
| 第六卷·前夜 | 12章 | ~3.6万 | 已完成 |
| 第七卷·集结 | 16章 | ~6.5万 | 已完成 |
| 第八卷·封锁 | 18章 | ~7.5万 | 已完成+回读校验 |
| 第九卷·余烬 | 12章 | ~4.3万 | 已完成+回读校验 |

**总计：137章，约50.3万字**

**下一步：** 开始第十卷「苏醒」写作（ch138-ch151，14章）

> 2026-05-31 重构说明：原V7「集结」(20章)+V8「暗战」(12章)+V9「破局」(16章)+V10「代价」(12章)在V4-V6写作中被提前完成。未做要素重新组织为新V7「集结」(16章)+新V8「封锁」(18章)。原V11「封锁」→新V8，原V12-V20→新V9-V17。全书从20卷305章调整为17卷257章。

## 图谱状态（截至会话结束）

```
characters: 83  | locations: 165  | events: 891
themes: 3       | style_guides: 10 | motifs: 4
chapter_arcs: 137 | suspense_threads: 207
outline_entries: 137 | relationships: 3070
```

## 管线流程（严格串行）

```
Step 0: 读框架 → 循环[Step 1: 子代理写初稿 → Step 2: 子代理编辑审查 → Step 3: 子代理提取JSON → Step 4: CLI写入图谱+弧线 → Step 5: 遥测注入 → 下一章] → Step 6: 整卷回读校验
```

### Step 6 — 整卷回读校验（全部章节完成后，主编排执行）
- 使用 Agent 工具派生 VolumeReviewAgent，prompt 来自 `.claude/templates/volume_review.md`
- VolumeReviewAgent 逐章通读、发现问题、修复问题、写入报告
- 报告写入 `projects/juedi_tiantong_v1/review_report_vol{N}.md`
- 主编排读取报告后更新本文件的会话交接块

### Step 0 — 每卷/新会话必读
- `projects/juedi_tiantong_v1/framework.md` — 核心设定 + 全部卷大纲（20卷）
- `projects/juedi_tiantong_v1/handoff.md` — 本文件
- `CLAUDE.md` — 管线规则 + 风格约束

### Step 1 — 子代理写初稿
向子代理发送：本章定位 + 前章结尾 + 角色状态 + 目标字数(3000-4000) + 风格要求
使用 `get_writing_prompt --project juedi_tiantong_v1 --chapter <N> --focused` 生成 prompt（--focused 节省40%+体积，只注入活跃悬念线）

### Step 2 — 子代理编辑审查
使用 `get_editing_prompt --project juedi_tiantong_v1 --chapter <N>` 生成编辑 prompt
编辑子代理修改终稿，替换初稿文件

### Step 3 — 子代理提取JSON
使用 `get_extraction_prompt --project juedi_tiantong_v1 --chapter <N>` 生成提取 prompt
提取事件/角色/地点/悬念线，写入 `extractions/` 目录

### Step 4 — CLI写入图谱
```bash
cd D:/novel_test
python -m src.novel_kg.mcp_cli write_extraction --project juedi_tiantong_v1 --chapter <N> --json-file "projects/juedi_tiantong_v1/extractions/extraction_ch{NN}.json"
python -m src.novel_kg.mcp_cli add_chapter_arc --project juedi_tiantong_v1 --chapter <N> --purpose "..." --scenes "..." --ending "..." --structure-type "..."
```

### Step 5 — 遥测注入
```bash
python -m src.novel_kg.mcp_cli count_chapter_words --project juedi_tiantong_v1 --chapter <N>
python -m src.novel_kg.mcp_cli inject_agent_phase --project juedi_tiantong_v1 --chapter <N> --phase combined --duration-ms <ms> --tool-uses <N>
```

## 风格约束（10条，已在图谱中）

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
| 9 | 破折号（——） | ≤1处/千字，尽量为0 |
| 10 | 句号密度 | 15-20个/千字 |

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
- [ ] **每卷结束时：派生 VolumeReviewAgent 执行整卷回读校验，报告写入 review_report_vol{N}.md**

---

## 会话交接块

### 九卷结尾状态（截至Ch137）

第九卷终章（Ch137「余烬」）：林深已进入冬眠，沉睡在设施最深层。城市继续变冷但降温趋缓。绥接管人族全部管理责任。陆留在底层通道守护，发现新温度异常（未追查）。渊的信息备份系统持续运行（千年时间戳）。拾在安全屋墙上画了地图标注冬眠仓位置。掌心低频共振仍在运行。

### 第九卷核心进展
- 林深从安全阀总协调人→守望者→记录者→沉睡者，完成角色转换
- 穿越通道全部关闭，信息切断层封死跨时空窗口
- 因果闭环机制揭示：先有果再种因，等待选择了他
- 韩嶂数据层最终功能：为冬眠仓提供频率翻译，最后一丝脉动在启动瞬间闪了一下
- 记忆宫殿完整封存（索引、封锁数据、第七人信号、韩嶂数据层衰减曲线）
- 年轮共鸣：上一个循环记录者的碎片，传承序列暗示
- 全部核心角色告别（绥/拾/渊/陆/陈默/芬/许巍），不煽情，用动作和对话
- 城市视角终章：余烬不灭，掌心共振仍在运行

### 当前全局状态
- **林深状态**：冬眠中，沉睡在设施最深层冬眠仓
- **掌心状态**：不可逆低频共振持续运行（在冬眠仓中）
- **韩嶂数据层**：最后一丝脉动在冬眠仓启动时闪了一下，此后频率翻译功能锁定，数据层不再独立振动
- **社交圈**：绥（全权管理人族）、拾（地图标注/后勤）、陆（底层守护，发现温度异常）、渊（信息备份持续运行）、陈默/芬/许巍（常规维护）
- **已有情报**：穿越通道已关闭、因果闭环需要未来时间点、冬眠仓通过频率翻译适配、年轮记录了循环历史、第七人信号被封存未调查
- **当前位置**：设施最深层冬眠仓（林深）；安全屋/信息核心区/底层通道（其余角色）
- **时间**：封锁完成后约70-80个标准周期

### 第十卷待推进的悬念线
- **P0** — 第七穿越者信号（已封存，频率特征和方向记录在记忆宫殿，V10苏醒后可能重新感知）
- **P0** — 陆发现的温度异常（底层通道新异常，可能只是波动，也可能是什么在醒来）
- **P1** — 传承序列第十位（年轮共鸣中的暗示，林深可能是序列中的一环）
- **P1** — 干扰派残余（退入深层通道，未清除，可能与温度异常有关）
- **P2** — 人族独立生存（绥接管，80周期窗口中已过约70-80周期）
- **P2** — 荒寂（城市外围什么都没有）
- **P2** — 拾留下的地图（如果将来有人需要找到冬眠仓）

### 全局章节编号
- Vol1 = ch01-ch12（第一卷·萌动）— 已完成
- Vol2 = ch13-ch32（第二卷·降临）— 已完成
- Vol3 = ch33-ch52（第三卷·暗流）— 已完成
- Vol4 = ch53-ch66（第四卷·较量）— 已完成
- Vol5 = ch67-ch79（第五卷·闭环）— 已完成
- Vol6 = ch80-ch91（第六卷·前夜）— 已完成
- Vol7 = ch92-ch107（第七卷·集结）— 已完成
- Vol8 = ch108-ch125（第八卷·封锁）— 已完成
- Vol9 = ch126-ch137（第九卷·余烬）— **已完成**
- Vol10 = ch138-ch151（第十卷·苏醒）— **待写**
- Vol11-17 = ch152-ch257 — 待规划

### 核心设定提醒
- **文明周期律**：超自然路线与科技路线交替主导
- **绝地天通**：文明周期交替时的封锁机制（物理+信息双层），已循环上百次
- **穿越者**：来自多个时间点，促成派vs干扰派博弈（封锁已完成，干扰派残余未清除）
- **主角定位**：不是天选者，是在合适的时间做了合适的事——Vol8中从被动升级为主动选择
- **荒寂**：外界可能从来没有存在过（古神沉睡前暗示，不揭底）
- **三层封锁**：已完成。反馈回路层+物理屏蔽层+信息切断层全部运行
- **必然之环**：封锁必要但终将被打破，消耗加速不可逆转
- **核心年轮**：封锁核心有循环痕迹层层叠加，暗示记录者传承序列与核心本身有关

### 代词注意事项（历史教训）
- **拾** — 女性，代词"她"
- **许巍** — 男性，代词"他"
- **陆** — 女性，代词"她"
- **陈默** — 男性，代词"他"
- **周** — 男性，代词"他"（TR-05，记忆碎片化）
- **芬** — 女性，代词"她"（TR-06，1.3倍深层频率）
- **渊** — 男性，代词"他"
- **绥** — 人族组织调度者（性别待确认）
- **写作子代理在跨卷时偶尔丢失角色性别设定，每卷回读校验时必须检查代词**

### 本地文件清单
- `projects/juedi_tiantong_v1/framework.md` — 完整设定+全部卷大纲
- `projects/juedi_tiantong_v1/handoff.md` — 本文件
- `projects/juedi_tiantong_v1/project.yaml` — 项目元数据
- `projects/juedi_tiantong_v1/world_setup.json` — 世界观数据
- `projects/juedi_tiantong_v1/graph.json` — 图谱数据
- `projects/juedi_tiantong_v1/output/` — 125章正文
- `projects/juedi_tiantong_v1/extractions/` — 125个提取JSON
- `projects/juedi_tiantong_v1/prompts/` — 所有prompt落盘
- `projects/juedi_tiantong_v1/telemetry/` — 遥测报告
- `projects/juedi_tiantong_v1/digests/` — 章节增量摘要
- `projects/juedi_tiantong_v1/review_report_vol8.md` — 第八卷回读校验报告
