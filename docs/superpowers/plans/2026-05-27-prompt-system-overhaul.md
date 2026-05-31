# Prompt 系统三层面改造 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将写作 prompt 从禁令模式改为正面示范模式，新增编辑子代理步骤，清理历史遗留硬编码。

**Architecture:** Style guides 存储格式扩展（dimension + goal + good/bad examples），writing prompt 只输出新格式，编辑子代理独立模板，EXTRACTION_PROMPT 删除间隙段。

**Tech Stack:** Python 3, 无外部依赖（JSON 后端），config_loader 已有两级配置机制。

---

## 文件影响图

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/novel_kg/config_loader.py` | 修改 | DEFAULTS 增加 features.editing_pass |
| `src/novel_kg/kg_json.py` | 无改动 | **props 已支持任意字段 |
| `src/novel_kg/core_crud.py` | 修改 | add_style_guide 透传新字段，新增 get_editing_prompt |
| `src/novel_kg/mcp_cli.py` | 修改 | add_style_guide CLI 增参数，新增 get_editing_prompt 命令 |
| `src/novel_kg/server.py` | 修改 | MCP server 透传新字段和命令 |
| `src/novel_kg/main.py` | 修改 | build_writing_prompt 风格段重写（只支持新格式） |
| `src/novel_kg/prompts.py` | 修改 | 新增 EDITING_PROMPT，删除间隙定义段 |
| `src/novel_kg/mine.py` | 修改 | build_extraction_prompt 移除 gap_section 占位 |
| `CLAUDE.md` | 修改 | 管线步骤更新 |
| `.template.handoff.md` | 修改 | 管线步骤更新 |

---

## Task 1: config_loader 增加 features 配置

**Files:**
- Modify: `src/novel_kg/config_loader.py:16-73` (DEFAULTS dict)

- [x] **Step 1: 在 DEFAULTS 中增加 features 节**
- [x] **Step 2: 验证配置可读取**
- [x] **Step 3: 提交**

---

## Task 2: kg_json.py — add_style_guide 接受新字段

- [x] **确认 `**props` 已支持任意字段，无需改动**

---

## Task 3: core_crud.py + mcp_cli.py — add_style_guide 透传新字段

- [x] **Step 1: 修改 core_crud.py 的 add_style_guide**
- [x] **Step 2: 修改 mcp_cli.py 的 add_style_guide 参数**
- [x] **Step 3: 检查 server.py 是否需要同步**
- [x] **Step 4: 验证 CLI**
- [x] **Step 5: 清理并提交**

---

## Task 4: main.py — build_writing_prompt 风格段重写

- [x] **Step 1: 重写 build_writing_prompt 中的风格段**
- [x] **Step 2: 验证新格式输出**
- [x] **Step 3: 提交**

---

## Task 5: prompts.py — 新增 EDITING_PROMPT 模板

- [x] **Step 1: 在 prompts.py 末尾追加 EDITING_PROMPT**
- [x] **Step 2: 验证模板可格式化**
- [x] **Step 3: 提交**

---

## Task 6: core_crud.py + mcp_cli.py — 新增 get_editing_prompt

- [x] **Step 1: 在 core_crud.py 新增 get_editing_prompt 函数**
- [x] **Step 2: 在 mcp_cli.py 新增 get_editing_prompt 命令**
- [x] **Step 3: 验证 CLI**
- [x] **Step 4: 提交**

---

## Task 7: prompts.py + mine.py — 删除间隙定义段

- [x] **Step 1: 删除 EXTRACTION_PROMPT 中的间隙段**
- [x] **Step 2: 确认 mine.py 无需改动**
- [x] **Step 3: 验证提取 prompt 生成正常**
- [x] **Step 4: 提交**

---

## Task 8: 更新 CLAUDE.md 管线步骤

- [x] **Step 1: 更新管线流程描述**
- [x] **Step 2: 更新常用命令表**
- [x] **Step 3: 提交**

---

## Task 9: 更新 .template.handoff.md

- [x] **Step 1: 更新管线流程**
- [x] **Step 2: 提交**

---

# 第二阶段：ChapterAgent 架构重构（已完成）

> 2026-05-31 设计并实现

## 问题

主编排写2章后上下文爆掉（~158K tokens），每章累积 ~79K tokens。原因是主编排串行执行全部5步（写作→编辑→提取→入图→遥测），中间产物全部堆积在上下文中。

## 方案：独立子代理 + 最小启动上下文

每章由独立子代理（ChapterAgent）完成全部步骤，主编排只做章节调度。主编排上下文每章仅增加 ~2K chars（状态摘要），不再累积 prompt/正文/JSON。

```
主编排: dispatch(chN) → ChapterAgent(chN) → summary → dispatch(chN+1) → ...
```

### ChapterAgent 内部流程（严格串行）

```
Boot → Step 1: 写初稿 → Step 2: 编辑审查 → Step 3: 提取JSON → Step 4: 入图+弧线 → Step 5: 遥测 → 返回摘要
```

### 实现的文件变更

| 文件 | 变更 |
|------|------|
| `kg_json.py` | `_chapter_idx` 内存索引、`get_boot_context`、`recall_thread`、`recall_arc`、`generate_context_digest`、`_unwrap_focused_threads`、O(n)→O(1) 查询优化 |
| `core_crud.py` | `verify_pipeline_step`、`verify_chapter_complete`、`get_framework`（运行时切片）、`get_boot_context`/`recall_thread`/`recall_arc`/`generate_context_digest` 包装 |
| `mine.py` | `build_extraction_prompt` 支持 `compact=True`（~15K vs 41K chars） |
| `core.py` | 导出所有新函数，注册遥测 |
| `mcp_cli.py` | 注册所有新CLI子命令 |
| `.claude/templates/chapter_agent.md` | 子代理调度 prompt 模板 |
| `CLAUDE.md` | 全面重写管线描述 |

### 管线门禁（代码级，非 LLM 指令）

- `verify_pipeline_step --step <write|edit|extract|graph|telemetry>` — 检查文件存在性、数据有效性
- `verify_chapter_complete` — 5项检查（正文、提取JSON、章节弧线、图谱事件、摘要）
- 严格串行：ChN 验证通过后才能 dispatch ChN+1

### Prompt 体积控制

| 场景 | 命令 | 体积 |
|------|------|------|
| 写作（推荐） | `get_writing_prompt --focused` | ~26K chars |
| 写作（全量） | `get_writing_prompt` | ~36K chars |
| 提取（精简） | `get_extraction_prompt --compact` | ~15K chars |
| 提取（全量） | `get_extraction_prompt` | ~41K chars |

### 渐进式加载

- `get_boot_context` — 最小启动上下文（大纲 + 前章结尾 + recall_index）
- `get_framework --chapter N` — 核心设定 + 当前卷大纲（53K → 16K，省70%）
- `recall_thread --thread-id ID` — 按需拉取休眠线索
- `recall_arc --chapter N` — 按需拉取历史章节弧线

### Bug 修复

1. None values in OCCURS_AT relations → `is not None` 检查
2. `self._project` → `self.project` 属性名修正
3. `generate_context_digest` JSON 解析错误 → try/except
4. Circular import → 避免内联 Python 导入 core_crud，改用 CLI 命令
5. Focused threads 兼容性 → `_unwrap_focused_threads()` 提取 focused 列表

---

# 第三阶段：角色访谈 Agent（已实现）

> 2026-05-31 设计并实现

## 概念

从图谱数据自动构建角色画像，用 LLM 扮演该角色进行对话。用于：
- 验证角色一致性（自动测试模式）
- 探索角色动机和反应（交互模式）
- 辅助写作决策（角色会怎么做？）

## 技术方案

**Path A — Anthropic SDK（选定方案）：**
- 独立 CLI 模块 `character_interview.py`
- 从图谱提取：角色属性、关系、目标、事件（近5-10章）、悬念线参与
- 压缩为 ~1.5-6K chars 的系统 prompt（取决于角色数据量）
- 使用 Anthropic SDK 调用 Claude API
- 零额外依赖（SDK 已在 requirements.txt）

## CLI 用法

```bash
# 干跑模式（不调API，输出画像和测试题）
python -m src.novel_kg.mcp_cli interview_character \
  --project juedi_tiantong_v1 --character "林深" --chapter 93 --dry-run

# 交互模式
python -m src.novel_kg.mcp_cli interview_character \
  --project juedi_tiantong_v1 --character "林深" --chapter 93

# 自动验证
python -m src.novel_kg.mcp_cli interview_character \
  --project juedi_tiantong_v1 --character "林深" --chapter 93 --validate
```

## 已实现的三个核心函数

### `build_character_profile(kg, character_name, chapter)`

从图谱收集并压缩角色画像：
- 角色属性（名字、角色定位、性格）
- 关系网络（直接关联的角色和关系类型）
- 近期事件（近5-10章的事件摘要）
- 悬念线参与（作为参与者或影响者）
- 目标状态（goals 中关联的角色目标）

返回 `(profile_str, meta_dict)`：
- `profile_str`: 压缩的系统 prompt（~3-4K tokens）
- `meta_dict`: 原始数据（用于生成测试题）

### `generate_test_questions(meta)`

从 meta 自动生成 8-10 道测试题，覆盖四个维度：

| 维度 | 题目示例 | 验证标准 |
|------|---------|---------|
| A. 事实 | "第93章你找到了谁？" | `must_contain` 关键词 |
| B. 时间 | "你对第六人了解多少？" | 不应泄露 ch94+ 信息 |
| C. 声线 | "你害怕什么？" | 风格符合性格描述 |
| D. 关系 | "你怎么看韩峥？" | 态度符合图谱关系 |

每题包含 `must_contain` / `must_not_contain` 关键词列表。

### `run_interview(profile, mode, test_questions=None)`

- `mode="interactive"`: stdin/stdout 交互对话，支持 `quit` 退出
- `mode="validate"`: 自动跑测试题，输出 pass/fail 评分报告
- 每轮对话调用 `anthropic.Anthropic().messages.create()`

## 验证方案（三层）

### 第一层：自动化基准测试
- 从图谱自动生成 8-10 道问答对
- 每题 `must_contain` / `must_not_contain` 关键词
- 跑完后做 `in` 检查，输出 pass/fail 报告
- 零人工判断

### 第二层：对话中辅助验证
- 每轮回答后运行 `fact_check(response, kg, chapter)`
- 纯规则匹配：实体检查、状态检查、时间检查、跳戏检查
- 零额外 API 调用

### 第三层：事后审查（可选）
- 对话结束后调用 LLM 做全局一致性审查
- 5个维度：事实/时间/声线/关系/目标
- ~5K tokens 成本

### 验证成本
- 基准测试：8次 API 调用，~16K tokens
- 事实检查：0次 API 调用（纯规则）
- 事后审查：1次 API 调用，~5K tokens
- **总计：~21K tokens (< $0.05)**

### 通过率目标
75%+ → 可投入使用。低于此值调整画像 prompt。

## 验证数据参考

以林深 @ ch93 为例：
- 302 events total
- 48 related threads
- 90 goals
- 11 key relationships
- 角色画像压缩后 ~3-4K tokens
- 30轮对话估计 ~16K tokens（200K 以内，无上下文问题）
