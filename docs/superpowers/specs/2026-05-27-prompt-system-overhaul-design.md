# Prompt 系统三层面改造设计

## 问题

子代理通过句号、破折号、嵌入长句等方式绕过写作禁令，导致「禁止-绕过」循环。根因在三个层面：

1. **写作 prompt** — 只禁不教，禁令越具体绕过越多
2. **子代理流程** — 一次写到底，无编辑环节
3. **写作观念** — 排除法作为默认叙事模式（否定对比被当作修辞习惯）

附加问题：prompt 模板大量硬编码（间隙定义、禁令列表），不随项目配置变化。

## 方案：混合式（范文 + 维度清单）

### Layer 1: Style Guide 格式重写

**当前格式**（graph.json 中）：
```json
{"guide_id": "no_not_xy", "rule": "禁止「不是X，是Y」句式"}
```

**新格式**：
```json
{
  "guide_id": "narrative_negation",
  "dimension": "叙事声",
  "goal": "直接呈现感受，否定前缀不作为修辞入口",
  "good_examples": ["胸口一阵灼热，从内脏表面扩散开来。"],
  "bad_examples": ["不是痛，是灼烧感。", "不是痛。是灼烧感。", "不是痛——是灼烧感。"]
}
```

变更点：
- 新增 `dimension` 字段，6 类：叙事声、对话、描写、节奏、过渡、情感表达
- `rule` → `goal`（正面目标）
- 新增 `good_examples`（1-3 条）和 `bad_examples`（1-3 条，含已知变体）
- bad_examples 覆盖所有绕过路径（逗号版、句号版、破折号版、嵌入长句版）

需要改动的文件：
- `kg_json.py` — `add_style_guide` 接受新字段，`get_context_for_chapter` 输出新格式
- graph.json 中的现有 style_guides 需要迁移（一次性脚本或手动重录）

### Layer 2: Writing Prompt 重写

**删除**：`build_writing_prompt` 中的【绝对禁止】整段（main.py:232-236）

**替换为**：【风格示范】段，按维度展开：

```
【风格示范】（严格对照以下范例写作）

叙事声 — 直接呈现，否定前缀不作为修辞入口
  ✓ 胸口一阵灼热，从内脏表面扩散开来。
  ✓ 他记住了。
  ✗ 不是痛，是灼烧感。
  ✗ 不是痛。是灼烧感。
  ✗ 不是好转——是融合的推进。

对话 — 用动作替代标签，每人一句不超30字
  ✓ "三千。"老头还是摇头。
  ✗ "三千。"老头缓缓开口说道。

描写 — 每场景至少2种感官，用具体物理感受
  ✓ 一股陈年纸张特有的气味扑面而来——霉味、灰尘味
  ✗ 她今天穿了一件浅蓝色的衬衫，看起来很清爽。

节奏 — 关键转折处用单句段落，场景切换用 ***
  ✓ 今年是丙午年。
  ✗ （长段落中埋没关键信息）

过渡 — 直接进入感官/动作/位置，不解释前情
  ✓ 回到住处已经快六点了。楼道里灯光昏暗。
  ✗ 接下来的两个周期，林深被分配到了城市核心区的边缘。

情感 — 通过身体反应传递，不直接命名情绪
  ✓ 他攥紧了那张纸条，手指在微微发抖。
  ✗ 他感到恐惧。
```

上面的 ✓/✗ 范例是示意，正式内容由用户审核后写入 graph 的 style_guides。模板提供通用默认范例集，项目可覆盖。`build_writing_prompt` 从 graph 中的 style_guides 动态构建此段。

需要改动的文件：
- `main.py` — `build_writing_prompt` 风格输出段重写

### Layer 3: 编辑子代理

管线从三步变四步：

```
Step 1: 写作子代理 → 初稿
Step 2: 编辑子代理 → 审查+修改 → 终稿（新步骤）
Step 3: 提取子代理 → JSON
Step 4: CLI 写入图谱
```

编辑子代理 prompt 模板（`EDITING_PROMPT`，新增于 `prompts.py`）：

```
你是小说风格编辑。对照以下维度清单逐项审查正文，输出修改后的完整文本。

## 维度清单
{style_checklist}  ← 从 graph 的 style_guides 动态生成，格式同 Layer 2

## 审查规则
1. 逐维度扫描正文，找出所有 ✗ 模式（含已知变体）
2. 用 ✓ 模式替换，保持上下文连贯
3. 引号统一（""或「」，全文选一种）
4. 对话标签：出现"他说/她问"且有动作可替代时，改用动作
5. 输出修改后的完整正文，不省略任何段落
6. 如果初稿已符合要求，原样输出不做修改

## 正文
{draft}
```

需要改动的文件：
- `prompts.py` — 新增 `EDITING_PROMPT` 模板
- `core_crud.py` — 新增 `get_editing_prompt(project, chapter, draft)` 函数
- `CLAUDE.md` — 管线步骤从3步改为4步
- `.template.handoff.md` — 同步更新管线说明

### Layer 4（横切）：减少硬编码

当前 `EXTRACTION_PROMPT` 中硬编码了「间隙的精确定义」（~10 行），部分项目不使用间隙概念，属于纯噪音。

**改造**：将 prompt 模板中的条件段落改为可配置。

项目配置文件（`projects/<项目名>/config.yaml` 或嵌入 graph.json 的 config 节点）：

```yaml
features:
  gap_detection: false      # 禁用时 EXTRACT_PROMPT 中不包含间隙定义
  editing_pass: true        # 启用编辑子代理步骤

style:
  quote_style: ""           # 对话引号风格："" 或 「」
  prev_text_chars: 500      # 前章文本回显字数
```

`prompts.py` 中的模板构建函数根据配置决定是否包含条件段落。具体方式：模板中用 `{gap_section}` 占位，代码层根据 `gap_detection` 决定填充内容还是空字符串。

需要改动的文件：
- `prompts.py` — `EXTRACTION_PROMPT` 中间隙段改为条件占位
- `kg_json.py` 或 `config_loader.py` — 读取 features 配置
- `core_crud.py` — `get_extraction_prompt` 传递配置

## 实现优先级

| 顺序 | 内容 | 影响面 |
|------|------|--------|
| P0 | Style guide 新格式 + writing prompt 重写 | main.py, kg_json.py |
| P1 | 编辑子代理 prompt + 函数 | prompts.py, core_crud.py |
| P2 | 间隙定义条件化 | prompts.py, config_loader |
| P3 | CLAUDE.md + handoff 模板更新 | 文档 |

## 风格样本来源

风格范例（✓/✗）不由任何特定项目的输出自动生成。绝地天通的生成内容存在 AI 幻觉问题，不宜作为金标准。范例应：

1. **✓ 范例**：手写或从多个来源中精选的最佳段落，经用户审核确认
2. **✗ 范例**：从实际生成中提取的典型问题模式（含已知绕过变体）

每个项目的 style_guides 由用户在项目初始化时配置，模板只提供默认范例集（通用），项目可覆盖。

## graph.json 拆分（后续优化，不在本 PR 范围）

当前 graph.json 随章节增长膨胀严重。后续应拆分为多文件结构：

```
projects/<项目名>/graph/
├── characters.json
├── locations.json
├── events/
│   ├── ch01.json
│   ├── ch02.json
│   └── ...
├── threads.json
├── style_guides.json
├── arcs.json
├── outline.json
└── meta.json          # config, motifs, themes, time_periods
```

本 PR 不做拆分，但 style_guides 的新 schema 设计应兼容未来的文件级拆分。

## 不改什么

- 提取 prompt 的整体结构（粒度控制、因果链、证据链等段落保持不变）
- 图谱 JSON 存储格式（style_guides 的 schema 扩展，不是重写）
- 管线中的 Step 3（CLI 写入图谱）和 Step 4（原 Step 3）不变
