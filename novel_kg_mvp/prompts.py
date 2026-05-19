"""
Novel Knowledge Graph MVP
提取prompt模板 — 用于从章节文本中提取结构化信息回写图谱
"""

EXTRACTION_PROMPT = """你是一个小说结构化数据提取器。请从以下章节文本中提取结构化信息。

## 已有图谱中的人物
{characters}

## 已有悬念线
{suspense_threads}

## 粒度控制（最重要）

事件按"场景"粒度提取，每章目标5-8个事件。

**合并规则：**
- 同一地点、同一时段 = 1个事件。如"渡口坐一下午"是1个事件，不要拆成"坐下"+"看河"+"想A"+"想B"
- 同一场景内的回忆内容放进detail，回忆中涉及的人物放进event_relations（不设location或只设回忆发生的地点）
- 心理活动和内心变化：如果发生在同一场景中，合并到该场景事件，放进detail

**拆分规则：**
- 不同地点 = 不同事件。如"渡口坐一下午"和"回家修椅子"是2个事件
- 同一地点但有明确时间跳跃 = 可拆分。如"渡口下午"和"大巴离开"是2个事件
- 独立的gap体验 = 独立事件，不管发生在什么场景中

**细节归档：**
- 人物回忆的具体内容 → character_updates
- 微小日常细节（如尝到菜味、某个新习惯）→ character_updates
- 象征性细节、伏笔 → motif_mentions 或 notes
- 不要为了保留细节而拆分场景

## 间隙的精确定义

间隙（gap）= 意识在停顿中滑出身体，从外部看到自己。特征：世界静音、看到自己的身体、感受到密度/重量。

以下**不是**间隙：
- 活在当下的觉醒（如尝到菜的味道、第一次注意到某个细节）→ 这是character_updates中的state_change
- 情感波动或内心变化 → 这是turning事件但is_gap=false
- 普通的走神或回忆 → 归入所在场景的detail

## 地点规则

- 只使用已有地点或new_locations中声明的新地点
- 回忆中出现的人物不设location（回忆没有物理地点）
- 新地点必须在new_locations中同时声明
- 地点名称保持一致（不要"大巴"和"大巴上"混用）

## 悬念线检测

识别本章中悬念线索的变化：
- **planted（埋下）**：引入新的未解问题、神秘细节或暗示未来发展的信息
- **advanced（推进）**：已有悬念出现新的线索或转折
- **resolved（解决）**：之前的悬念得到了明确答案或收束
- **隐含解决检测**：如果本章情节使某个悬念线的问题得到回答（即使文中未直接提及该悬念线），也应标记
- 判断标准：读者读完后是否已经知道答案
- 例如：悬念"胶卷记录了什么"——本章展示了冲洗后的照片内容，即使没写"胶卷之谜解开了"，也应标记resolved
- 如果本章没有悬念变化，返回空数组

## 因果链

每个事件不是孤立的，要识别事件之间的因果关系：
- **causal_links** 记录哪个事件导致了哪个事件，以及因果类型
- 因果类型：reaction（被动反应）、investigation（主动调查）、escalation（冲突升级）、revelation（真相揭露）、decision（角色决定）、consequence（自然后果）
- 只记录本章内的事件间因果关系（跨章因果关系已由事件时序隐含）
- 如果本章事件之间没有明确因果，返回空数组

## 证据链

追踪悬念线的证据支撑：
- **evidence_links** 记录本章哪些事件为哪些悬念线提供了证据/线索
- 证据类型：clue（直接线索）、connection（关联发现）、misdirection（误导性线索）、confirmation（确认性证据）
- 即使悬念线本章没有被推进或解决，也可能产生了新证据
- 例如：老孟看到排污记录（事件），为"排污持续"这个悬念提供了clue（证据）

## 角色目标

识别本章中角色驱动力：
- **character_goals** 记录角色的追求或恐惧
- 目标类型：pursue（主动追求）、fear（害怕/回避）、protect（保护某物/某人）、duty（责任义务）
- 只记录本章新出现的目标或发生重大变化的目标（已在图谱中的不需要重复）

## 返回格式

返回严格合法的JSON：
{{
  "events": [
    {{
      "id": "E{{chapter}}_01",
      "chapter": {chapter},
      "title": "场景标题",
      "type": "gap|daily|turning|character|background|climax",
      "gap_level": 0,
      "is_gap": false,
      "detail": "一句话描述这个场景发生了什么（可包含该场景内的回忆和思考）"
    }}
  ],
  "event_relations": [
    {{"event_id": "E{chapter}_01", "character": "陆沉", "location": "渡口"}},
    {{"event_id": "E{chapter}_01", "character": "回忆中的人物名"}}
  ],
  "character_updates": [
    {{
      "name": "人物名",
      "field": "new_habit|new_attitude|new_detail|new_relationship|state_change",
      "content": "具体内容"
    }}
  ],
  "new_locations": [
    {{"name": "地点名", "type": "类型", "description": "描述"}}
  ],
  "new_characters": [
    {{"name": "人物名", "role": "角色类型", "personality": "性格描述"}}
  ],
  "motif_mentions": [
    {{"motif": "手|渡口|水|灰尘|程序|速度", "context": "场景描述"}}
  ],
  "thread_updates": [
    {{"thread_id": "ST01", "action": "advanced", "evidence": "文本中的依据", "new_status": "planted|partially_resolved|resolved"}}
  ],
  "new_threads": [
    {{"content": "悬念内容描述", "importance": "high|medium|low", "thread_type": "foreshadowing|clue|mystery|character_arc", "planted_event_id": "E{{chapter}}_01"}}
  ],
  "causal_links": [
    {{"from": "E{{chapter}}_01", "to": "E{{chapter}}_02", "type": "reaction|investigation|escalation|revelation|decision|consequence", "detail": "简述因果关系"}}
  ],
  "evidence_links": [
    {{"event_id": "E{{chapter}}_01", "thread_id": "ST01_01", "type": "clue|connection|misdirection|confirmation", "detail": "该事件为悬念提供了什么证据"}}
  ],
  "character_goals": [
    {{"character": "人物名", "goal": "目标描述", "type": "pursue|fear|protect|duty", "status": "new|advanced|achieved|abandoned"}}
  ],
  "notes": "值得记录的新细节：新的人物习惯（如对猫过敏）、新的物品设定、伏笔、环境细节变化等"
}}

## 章节文本

{chapter_text}

请返回纯JSON，不要包含任何其他文字。"""


WORLD_BUILD_PROMPT = """你是一个小说世界观设计师。根据用户的创作方向，生成完整的世界观设定。

## 创作方向

{direction}

## 约束

1. 生成一个6章短篇的完整世界观，有明确的叙事弧线（开篇→发展→转折→高潮→收束）
2. 人物3-5个，每个有明确的性格和功能（不能全是工具人）
3. 地点3-5个，有足够的场景空间
4. 风格指南6-8条，要具体可执行（禁止什么、要求什么），避免空泛建议
5. 时间段2-3个，覆盖6章
6. 第1章arc要足够具体，能直接驱动第1章的写作

## 返回格式

返回严格合法的JSON：
{{
  "title": "作品标题",
  "premise": "一句话概括核心冲突/悬念",
  "style_guides": [
    {{"id": "规则ID（英文蛇形）", "rule": "具体的风格规则"}}
  ],
  "characters": [
    {{"name": "人物名", "role": "主角/配角/关键配角", "personality": "性格描述"}}
  ],
  "locations": [
    {{"name": "地点名", "type": "类型", "description": "描述"}}
  ],
  "themes": [
    {{"name": "主题名", "description": "描述", "chapters": "涉及章节范围"}}
  ],
  "time_periods": [
    {{"label": "时间段名", "chapter_start": 1, "chapter_end": 3, "years": "时间", "theme": "此段主题"}}
  ],
  "first_arc": {{
    "purpose": "第1章叙事目的",
    "scenes": "场景A → 场景B → 场景C",
    "ending": "结尾锚点（具体画面）",
    "gap_note": ""
  }},
  "style_analysis": "简要说明这个风格组合会产出什么样的文学质感（50字以内）"
}}

请返回纯JSON，不要包含任何其他文字。"""


ARC_DERIVATION_PROMPT = """你是一个小说叙事结构规划器。根据已有章节的结构化数据，推演下一章的叙事弧线。

## 本章大纲约束
{outline_entry}

## 未解决的悬念线
{suspense_threads}

## 近几章的叙事弧线
{recent_arcs}

## 近几章的事件
{recent_events}

## 当前人物状态
{characters}

## 主题线
{themes}

## 核心意象演变
{motifs}

## 上一章最后一个事件
{last_event}

## 推演规则

1. **大纲约束优先**：如果存在大纲条目，其purpose和key_events是硬约束——必须执行，不能替代
2. **叙事结构硬约束**：如果大纲条目的structure_hint非空且不是"linear"，则本章的structure_type必须与之匹配，且必须生成对应的time_jumps。这是与purpose同级别的硬约束
3. **悬念线管理**：根据未解悬念的重要性和种植时间，决定本章应推进或解决哪些线索
4. **叙事连贯性**：新章节的purpose必须承接前一章结尾的状态变化，不能跳跃
5. **主题递进**：参考主题线的演变方向，推断下一步
6. **意象延续**：参考motif的evolution字段，意象应有新发展但不能凭空出现
7. **人物一致**：人物的行为必须与其已有性格和发展方向一致
8. **间隙处理**：参考近几章的gap_note和gap_level趋势，决定本章是否需要间隙
9. **场景控制**：scenes列出3-5个场景，粒度与已有章节一致（一个场景=一段连续时空）

## 返回格式

返回严格合法的JSON：
{{
  "purpose": "一句话描述本章的叙事目的",
  "scenes": "场景A → 场景B → 场景C（用箭头连接，每个场景一句话）",
  "ending": "一句话描述本章结尾的锚点状态（具体的画面或感受，不要抽象概括）",
  "gap_note": "间隙处理说明",
  "reasoning": "简要说明推演依据（50字以内）",
  "structure_type": "linear|flashback|intercut|parallel",
  "time_jumps": [{{"position": "场景位置", "target": "目标时间/事件", "type": "flashback|flashforward"}}],
  "thread_plan": {{
    "to_plant": ["新悬念描述"],
    "to_advance": ["ST01"],
    "to_resolve": ["ST02"]
  }}
}}"""


OUTLINE_GENERATION_PROMPT = """你是一个小说大纲规划师。根据世界观设定和总章数，生成每章的大纲条目。

## 世界观设定

{world_setup}

## 总章数
{total_chapters}

## 要求

1. 每章一个条目，包含：目的、关键事件、要埋下的悬念、要解决的悬念
2. 悬念线要跨章节埋设和收束（至少2-3条贯穿全书的主线）
3. 考虑叙事节奏：开篇→发展→转折→高潮→收束
4. 至少安排总章数1/4的章节使用非线性叙事结构（flashback或intercut），且必须在structure_hint中明确指定
5. structure_hint是必填字段：如果是线性叙事填"linear"，如果需要非线性则填"flashback"/"intercut"/"parallel"并附上简要说明
6. 全局叙事弧概要：用一段话（100字内）概括整体走向

## 返回格式

返回严格合法的JSON：
{{
  "narrative_arc_summary": "全局叙事弧概要（100字内，描述从开篇到结尾的整体走向）",
  "outline": [
    {{
      "chapter": 1,
      "purpose": "本章目的",
      "key_events": "事件A;事件B;事件C",
      "threads_to_plant": ["悬念1描述", "悬念2描述"],
      "threads_to_resolve": [],
      "structure_hint": ""
    }}
  ]
}}

请返回纯JSON，不要包含任何其他文字。"""


PREQUERY_PLANNING_PROMPT = """你是一个小说写作规划助手。根据简要信息，判断生成下一章需要哪些额外上下文。

## 本章大纲
{outline}

## 未解悬念线
{threads}

## 涉及人物
{characters}

## 近章弧线摘要
{recent_arc_summary}

请返回JSON：
{{
  "context_needs": ["需要查询的具体信息，如：'ST02的具体内容'、'第3章E03_01事件的细节'"],
  "chapter_plan": {{
    "focus": "本章核心焦点",
    "key_decisions": ["需要在写作中做出的叙事决定"]
  }}
}}"""
