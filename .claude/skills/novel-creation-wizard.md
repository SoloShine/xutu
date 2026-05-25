---
name: novel-creation-wizard
description: 交互式创建新小说项目。引导用户从创作方向到完整世界观，一键写入知识图谱。
triggers:
  - "创建小说"
  - "新建项目"
  - "开始创作"
  - "创建新作品"
---

# 小说项目创建向导

按以下4个阶段引导用户创建新小说项目。Agent 自身作为 LLM 直接生成世界观，无需调用外部 API。

## Phase 1 — 需求收集

向用户收集创作方向。**只问必须的信息，不追问可选项。**

必须获得：
- **创作方向**：一句话描述想写什么（如"一个入殓师发现遗体上的神秘缝合线"）

可选（用户没提就不问，用默认值）：
- 篇幅：默认6章（可选 6/8/12）
- 风格倾向：默认由Agent根据题材自动判断

如果用户已经给了足够信息，直接进入 Phase 2。

## Phase 2 — 生成世界观

根据创作方向，生成完整的 world_setup JSON。严格遵循以下 schema：

```json
{
  "title": "作品标题",
  "premise": "一句话核心冲突/悬念",
  "style_guides": [
    {"id": "英文蛇形ID", "rule": "具体可执行的写作规则（禁止什么/要求什么）"}
  ],
  "characters": [
    {"name": "人物名", "role": "主角/配角/关键配角", "personality": "性格描述"}
  ],
  "locations": [
    {"name": "地点名", "type": "类型", "description": "描述"}
  ],
  "themes": [
    {"name": "主题名", "description": "描述", "chapters": "涉及章节范围"}
  ],
  "time_periods": [
    {"label": "时间段名", "chapter_start": 1, "chapter_end": 3, "years": "时间", "theme": "主题"}
  ],
  "first_arc": {
    "purpose": "第1章叙事目的",
    "scenes": "场景A → 场景B → 场景C（箭头连接）",
    "ending": "结尾锚点（具体画面或感受，不抽象概括）",
    "gap_note": ""
  },
  "style_analysis": "50字内描述文学质感"
}
```

### 质量要求

- **风格指南**：6-8条，每条必须具体可执行。好的示例：`"禁止使用「恐怖的」「阴森的」等情绪形容词，用动词和名词推进，让场景本身制造恐惧"`。坏的示例：`"注意氛围营造"`。
- **人物**：3-5个，至少1个主角+1个关键配角。personality 要有矛盾感和具体细节，不要泛泛的性格词。
- **地点**：3-5个，description 要有感官细节（气味、温度、光线）。
- **第1章弧线**：scenes 要有3-5个场景，ending 要是具体的画面而非抽象概括。
- **时间段**：2-3个，覆盖全部章节，每个有自己的主题。

### 展示与确认

生成后向用户展示：
1. 标题 + 核心设定（premise）
2. 风格质感（style_analysis）
3. 人物列表（名-角色-性格一句话）
4. 地点列表（名-类型）
5. 第1章弧线（目的 + 场景 + 结尾）

询问："是否需要调整？可以指出要修改的部分。" 用户确认后进入 Phase 3。

## Phase 3 — 写入图谱

用项目标识符（英文，如 `v17_test`）作为 project 参数。如果用户没指定，根据标题生成一个合理的标识符。

按顺序调用以下 MCP 工具：

1. **初始化项目**：
   - `init_project(project="<标识符>", confirm="I_UNDERSTAND_THIS_IS_DESTRUCTIVE")`

2. **写入风格指南**（每个）：
   - `add_style_guide(project, guide_id, rule)`

3. **写入人物**（每个）：
   - `add_character(project, name, role, personality)`

4. **写入地点**（每个）：
   - `add_location(project, name, type, description)`

5. **写入主题**（每个）：
   - `add_theme(project, name, description, chapters)`

6. **写入时间段**（每个）：
   - `add_time_period(project, label, chapter_start, chapter_end, years, theme)`

7. **写入第1章弧线**：
   - `add_chapter_arc(project, 1, purpose, scenes, ending, gap_note)`

8. **创建 project.yaml**（通过 Bash）：
   ```bash
   cat > D:/novel_test/novel_kg_mvp/projects/<标识符>/project.yaml << 'EOF'
   name: "<标题>"
   identifier: "<标识符>"
   chapters: <章节数>
   language: "简体中文"
   description: "<premise>"
   EOF
   ```

9. **保存 world_setup.json**（通过 Write 工具）：
   - 写入 `D:/novel_test/novel_kg_mvp/projects/<标识符>/world_setup.json`

展示写入统计：
```
项目 <标题> 创建完成！
  ✓ X 条风格指南
  ✓ X 个人物
  ✓ X 个地点
  ✓ X 个主题
  ✓ X 个时间段
  ✓ 第1章弧线
  ✓ project.yaml
  ✓ world_setup.json
```

## Phase 4 — 生成大纲（可选）

询问用户："是否要生成全局大纲？大纲会给每章定义目的、关键事件和悬念线。"

如果用户同意，根据世界观和章节数生成大纲 JSON：

```json
{
  "narrative_arc_summary": "全局叙事弧概要（100字内）",
  "outline": [
    {
      "chapter": 1,
      "purpose": "本章叙事目的",
      "key_events": "事件A;事件B;事件C",
      "threads_to_plant": ["悬念描述1", "悬念描述2"],
      "threads_to_resolve": [],
      "structure_hint": "linear"
    }
  ]
}
```

### 大纲质量要求

- 叙事节奏：开篇(1-2章) → 发展(3-4章) → 转折 → 高潮 → 收束
- 至少2-3条悬念线贯穿全书（跨章埋设和收束）
- 至少安排总章数1/4的章节使用非线性结构（flashback/intercut/parallel）
- structure_hint 是必填：线性填 `linear`，非线性填具体类型
- threads_to_plant 和 threads_to_resolve 要与叙事节奏配合

### 写入大纲

遍历 outline 数组，每条调用：
- `add_outline_entry(project, chapter, purpose, key_events, threads_to_plant, threads_to_resolve, structure_hint)`

展示大纲概览：
```
大纲已写入（X章）：
  Ch1: 目的... [linear]
  Ch2: 目的... [linear]
  Ch3: 目的... [intercut]
  ...
```

## 完成后

项目准备就绪。告诉用户可以开始写作：
- 调用 `get_writing_prompt(project="<标识符>", chapter=1)` 获取第1章续写 prompt
- 或直接说"开始写第1章"

## 错误处理

- 如果 `init_project` 失败，确认 project 标识符是否合法（英文+下划线）
- 如果 MCP 工具调用失败，检查项目是否已在 Phase 3 步骤1中初始化
- 如果用户对世界观不满意，修改对应部分后重新执行 Phase 3（init_project 会清空旧数据）
