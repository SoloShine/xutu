# 人机协作 + 大纲合规 设计文档

## 背景

V17（50章规模验证）暴露了一个根本性问题：大纲从Ch27起完全失效，系统靠前章注入+悬念线"自适应"维持叙事，但大纲本身从未被显式修订。这导致大纲形同虚设——prompt里叫"硬约束"，实际上没有任何校验机制。

设计原则：
1. **大纲是铁律** — 不允许静默偏离。要么遵守，要么显式修订
2. **流程介入可配置** — 开启时每章强制审核，关闭时agent自控
3. **事后分析是补救** — 存在但不是主流程

## 一、大纲合规内控（始终生效）

每章写完后、提取写入图谱后，自动执行大纲合规检查。

### 程序化检查

从提取结果中验证 outline_entry 的各字段：

| 检查项 | 方法 | 失败条件 |
|--------|------|----------|
| key_events | 匹配提取事件title/detail中的关键词 | 任意key_event完全无匹配 |
| threads_to_plant | 检查本章新种植的悬念线ID | 列表中的thread未出现在new_threads中 |
| threads_to_resolve | 检查本章thread_updates中的resolved状态 | 列表中的thread未resolved |
| structure_hint | 对比chapter_arc.structure_type | structure_type不匹配 |

实现：遍历提取报告的events/new_threads/thread_updates，与outline_entry各字段做bigram关键词匹配。

### LLM语义检查

Agent读取本章正文 + outline_entry.purpose，判断是否达成。

输出JSON：
```json
{
  "compliance": "followed" | "partial" | "diverged",
  "purpose_achieved": true | false,
  "reason": "...",
  "suggestion": "rewrite" | "revise_outline" | "accept"
}
```

### 结果处理

**compliance = followed** → 标记 `outline_entries[N].compliance = "followed"`，继续

**compliance = partial** → 生成偏离报告：
- agent自控模式：判断是否可修复 → 重写本章 / 提议修订大纲
- 审核模式：输出报告给作者决策

**compliance = diverged** → 必须决策：
- agent自控模式（`auto_revise_outline: true`）：自动修订大纲，标记 `compliance = "overridden"`
- agent自控模式（`auto_revise_outline: false`）：暂停并提示
- 审核模式：输出给作者，提供修订大纲选项

## 二、章节审核关卡（可配置）

### 配置

```yaml
writing:
  review_checkpoint: false    # true=每章审核, false=agent自控
  outline_compliance: true    # 大纲合规检查（始终开启）
  auto_revise_outline: false  # agent是否可自动修订大纲（仅自控模式下）
```

### 审核流程（review_checkpoint: true）

```
AI写chN → 提取+写入图谱 → 大纲合规检查 → 输出给作者
                                              ↓
                                      作者选择（review_chapter工具）：
                                      accept    → 继续chN+1
                                      edit      → chN_edited.txt → 重新提取+对比 → 继续
                                      rewrite   → 作者提供新文本 → 提取+写入 → 继续
                                      revise    → 修订大纲条目 → 继续chN+1
```

### 自控流程（review_checkpoint: false）

```
AI写chN → 提取+写入图谱 → 大纲合规检查 →
        followed → 继续chN+1
        partial/diverged →
                Agent判断可修复 → 重写chN（最多retry_once）
                Agent判断不可修复 + auto_revise_outline → 修订大纲 → 标记偏离 → 继续
                Agent判断不可修复 + !auto_revise_outline → 暂停提示
```

重写上限：每章最多重写1次（避免死循环）。重写后仍不合规则按不可修复处理。

## 三、事后影响分析（补救工具）

场景：作者在AI已跑完多章后回头修改早期章节。

### 流程

1. 作者编辑 chN → 保存为 chN_edited.txt
2. Agent调用 `analyze_edit_impact(project, N)`
3. 系统重新提取edited文本，与图谱中chN数据对比
4. 检查后续章节大纲合规性（chN+1..max）
5. 生成影响报告：
   - 事件变更（新增/删除/修改）
   - 受影响的悬念线
   - 受影响的人物状态
   - 后续章节大纲合规警告
   - 大纲修订建议

6. 作者审阅后调用 `accept_edit(project, N)` 确认采纳
7. 系统清除chN旧数据 → 写入新数据 → 标记受影响的后续大纲为 `needs_revision`

## 四、新增MCP工具

### check_outline_compliance(project, chapter)

大纲合规检查（程序化+LLM）。

输入：项目名、章节号
输出：
```json
{
  "chapter": 5,
  "outline_entry": { ... },
  "programmatic_checks": [
    {"item": "key_events", "status": "passed", "detail": "..."},
    {"item": "threads_to_plant", "status": "failed", "detail": "ST05_01未种植"}
  ],
  "llm_check": {
    "compliance": "partial",
    "purpose_achieved": false,
    "reason": "...",
    "suggestion": "revise_outline"
  },
  "overall": "partial",
  "action_required": true
}
```

无outline_entry的章节返回 `{"overall": "no_outline", "action_required": false}`。

### review_chapter(project, chapter, action, edited_text?)

审核关卡操作。

action:
- `accept` — 通过，继续下一章
- `edit` — 小修，edited_text为修改后文本
- `rewrite` — 重写，edited_text为新文本
- `revise_outline` — 需要修订大纲，触发后续的revise_outline流程

edited_text在accept/revise_outline时不需要。

### revise_outline(project, chapter, purpose?, key_events?, threads_to_plant?, threads_to_resolve?, structure_hint?, reason)

显式修订大纲条目。只传需要修改的字段。

写入时：
- 更新outline_entry中指定的字段
- 设置 `compliance = "overridden"`
- 设置 `revision_reason` = reason
- 设置 `revised_chapter` = 当前最新章节号

### analyze_edit_impact(project, chapter)

事后影响分析。对edited文本重新提取，与图谱对比，检查后续大纲合规性。

输入：项目名、编辑的章节号（需要有chN_edited.txt存在）
输出：
```json
{
  "edited_chapter": 3,
  "event_changes": {
    "added": [{"id": "E3_04", "title": "..."}],
    "removed": [{"id": "E3_02", "title": "..."}],
    "modified": [{"id": "E3_01", "changes": "..."}]
  },
  "affected_threads": [
    {"id": "ST03_01", "impact": "关联事件被删除", "severity": "high"}
  ],
  "affected_characters": ["林可心"],
  "downstream_warnings": [
    {"chapter": 4, "outline_key": "key_events", "issue": "依赖已删除事件E3_02"}
  ],
  "outline_revision_suggestions": [
    {"chapter": 4, "field": "key_events", "suggestion": "将E3_02替换为E3_04"}
  ]
}
```

### accept_edit(project, chapter, confirm)

采纳事后编辑。清除旧数据 → 写入新数据 → 标记后续大纲。

confirm需要传入 `"I_UNDERSTAND_THIS_IS_DESTRUCTIVE"`（覆盖已有数据）。

## 五、数据模型变更

### outline_entry 新增字段

```json
{
  "chapter": 5,
  "purpose": "...",
  "key_events": "...",
  "threads_to_plant": "...",
  "threads_to_resolve": "...",
  "structure_hint": "",
  "compliance": "followed" | "partial" | "diverged" | "overridden" | "needs_revision" | null,
  "compliance_detail": "程序化: passed; LLM: partial - 目的部分达成",
  "revision_reason": null,
  "revised_chapter": null
}
```

`compliance = null` 表示未检查（旧数据兼容）。

### 新增文件约定

- `projects/<project>/output/chN_edited.txt` — 作者编辑后的版本
- 系统通过 `chN_generated.txt`（原版）和 `chN_edited.txt`（编辑版）的共存判断是否需要分析

## 六、验证计划（V19）

### 目标

验证人机协作+大纲合规的完整闭环。

### 方法

1. 创建6章测试项目，设置6条大纲
2. 跑3章后，对ch3进行事后编辑（删除一个关键事件、新增一个人物）
3. 调用 `analyze_edit_impact` 验证影响检测准确性
4. 调用 `accept_edit` 验证图谱更新
5. 检查后续大纲合规警告
6. 验证 `revise_outline` 修订大纲流程
7. 开启 `review_checkpoint: true` 重跑ch4-6，验证审核关卡

### 成功标准

- 事后编辑影响检测准确（删除事件 → 关联悬念线被标记）
- 大纲合规检查能区分 followed/partial/diverged
- 审核关卡正确暂停并等待作者操作
- 大纲修订后后续章节正确引用新大纲
