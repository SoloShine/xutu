# 声明式小说创作工作台 — 顶层设计

**日期**: 2026-06-13
**状态**: 顶层设计（待 user review）
**项目位置**: `D:\novel_test`，新 package `src/novel_workbench/`（命名待确认）
**前置**: v0→v2.1 管线演进（`docs/pipeline-evolution/`）、v3 综合方案（Workflow wgjw7h8hq 产出，本设计取代其作为 v3 管线修复的实现路径）

---

## 一、背景与动机

### 1.1 现状

《绝地天通》已完成 **239 章 / ~87.8 万字 / 17 卷**。管线演进 v0→v2.1，tokens/章从 ~536K（Vol12 最差）优化至 ~120K（Vol17）。但稳定性未达预期：

- V16 代词错误爆发 **97 处**（拾×61 + 舟×36）
- V17 悬链 mature 终卷仍 **200**（通胀未解决，反增 +7）
- V17 句号密度 **11/12 章超标**（规范 15-25/K，实际 27-30/K）
- `graph.json` ↔ `world_setup.json` **双写漂移**（total_chapters=215 vs 实际 239）
- self-report vs JSON 消费数据**系统性偏差**（B3 bug 未根治）

### 1.2 v3 修复方案的局限

v3 综合方案（契约 + IVA + 规则引擎 + 卷类型矩阵）在 L4-L5 加约束，本质是**命令式**：告诉 LLM 怎么写、事后 grep/IVA 抓谎。局限：

- 约束在应用层，LLM 仍可产生不合规数据（**事后抓，不事前消**）
- grep/IVA 是**负约束**（禁止错误），缺乏**正约束源**（应该怎么写）
- 约束分散在 prompt 模板 / Python 代码 / JSON 校验，**无 single source**

### 1.3 根因诊断（RC1-RC5）

| RC | 根因 | 表现 |
|----|------|------|
| **RC1** | 数据非结构化 | gender 缺字段 → 代词靠 prompt 提示 → 遗忘即错（V16 爆发） |
| **RC2** | 约束在应用层 | grep 事后抓谎，LLM 可绕过/造假（A1 grep_after 伪造） |
| **RC3** | 双写漂移 | graph.json ↔ world_setup.json 不一致（C1 bug 族） |
| **RC4** | 悬念消费非节点属性 | 靠事后统计，ChapterAgent 可"忘记"消费（E1 通胀） |
| **RC5** | 风格无正约束源 | grep 负约束，无"应该怎么写"的模板（G1 句号超标） |

### 1.4 范式转换：命令式 → 声明式

**核心洞察**：真正的稳定性来自让 LLM **不需要"决定"**——结构已经替它决定了。这是数据库设计原则：**约束在 schema 层，不在应用层**。

| 维度 | 命令式（v3） | 声明式（本设计） |
|------|-------------|----------------|
| 上下文来源 | prompt 模板 | DB 结构化查询 |
| 约束位置 | 应用层（grep/校验器） | schema 层（NOT NULL/CHECK/FK）+ 应用层 |
| 失败时机 | 事后（抓谎） | 事前（DB 拒绝）+ 事后（业务校验） |
| 正约束源 | 无 | StyleTemplate 指纹 |

---

## 二、设计原则

1. **Single Source of Truth** —— 所有结构化数据在 SQLite，消灭双写漂移（治 RC3）
2. **约束分层** —— 硬约束(DB)物理拒绝 / 业务约束(Python)拦截+修复 / 软约束(prompt)记录。LLM 撒谎的层级决定后果（治 RC2）
3. **声明式上下文** —— ChapterAgent Boot 是"查 DB 结构"，不是"读 prompt 模板"。gender NOT NULL → 不存在"忘记提示代词"（治 RC1）
4. **悬念消费作为节点属性** —— 剧情树节点显式声明 `responsibilities`，Boot 时强制加载（治 RC4）
5. **风格正约束源** —— StyleTemplate 从 239 章提取指纹，writing prompt 有"应该怎么写"的模板（治 RC5）

---

## 三、7 层架构

| 层 | 名称 | 核心对象 | 结构化的根本变化 |
|---|------|---------|----------------|
| **L0** | 灵感 | 灵感池、风格指纹 | 风格从"自然语言描述"→"可量化分布" |
| **L1** | 宪法 | Constitution / Worldbook / StyleTemplate | 宪法是硬约束，不是 prompt 一段话 |
| **L2** | 结构 | Volume→Arc→Chapter→Beat | 悬念消费从"事后统计"→"节点属性" |
| **L3** | 实体 | Character / Location / Item + POV 矩阵 | 代词从"prompt 提示"→"NOT NULL 字段" |
| **L4** | 创作 | ChapterAgent Pool + 联合校审 | 单 agent 串行 → 多 agent 并行 |
| **L5** | 治理 | IVA + CrossChapterReviewer | 单章合规 → 跨章语义连贯 |
| **L6** | 工具 | Web 编辑器 / diff / 导出 | UI 改结构，AI 保持一致 |

---

## 四、数据流

```
┌─────────────────────────────────────────────────────────────┐
│  Web 编辑器 (L6)  — 你在 UI 编辑结构                          │
│  剧情树 / 关系网 / 宪法 / 风格模板 / 悬念线                    │
└────────────────────────┬────────────────────────────────────┘
                         │ 结构化写入 (REST/WS)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  SQLite (L1-L3 Single Source of Truth)                       │
│  Constitution │ Characters(gender NOT NULL) │ PlotTree       │
│  Locations/Items │ Relations │ SuspenseThreads               │
│  StyleTemplate │ VolumeType 矩阵 │ SceneMetadata             │
└────────────────────────┬────────────────────────────────────┘
                         │ 结构化查询 (SQL)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  ChapterAgent v4 (L4)                                        │
│  Boot = 查 DB：                                              │
│   · 出场角色 gender/关系  ← 硬约束已保证 NOT NULL，无需"提示" │
│   · 本章 responsibilities ← 剧情树节点属性，必须回收的悬念     │
│   · 卷类型消费配额       ← VolumeType 矩阵查表               │
│   · StyleTemplate       ← 正约束源（句长/句式/感官密度分布）  │
│  Write = 拼 prompt → Agent SDK → 正文                        │
└────────────────────────┬────────────────────────────────────┘
                         │ 正文 + 提取 JSON
              ┌──────────┴───────────┐
              ▼                      ▼
   ┌──────────────────┐    ┌─────────────────────────────────┐
   │ 文件系统          │    │ 分层校验器 (L5)                  │
   │ output/ch{NN}.txt│    │ 1. 硬约束: DB schema 物理拒绝     │
   │ extractions/*.json│   │ 2. 业务约束: 字数/悬链/风格校验   │
   │ scene 索引        │    │ 3. 软约束: 风格偏离只记录         │
   │ (git diff 友好)   │    │ 失败 → 修复 prompt → 重写循环    │
   └──────────────────┘    └────────────┬────────────────────┘
                                        │ 通过
                                        ▼
                           回写 SQLite (事件/关系/悬念消费/场景元数据)
                           + 文件系统 (正文)
```

---

## 五、技术栈选型

| 层 | 选型 | 理由 |
|---|------|------|
| 后端 | Python + FastAPI | 复用现有 `novel_kg` 代码，异步友好，OpenAPI 自动生成 |
| 前端 | Next.js + TypeScript + shadcn/ui | 生态最大，SSR/CSR 灵活，组件库成熟 |
| 结构化存储 | SQLite（WAL 模式）+ SQLite FTS5 | 单机零运维，跟文件系统同目录，事务 + 全文检索 |
| 文件存储 | 正文 / 提取JSON / prompt 存档 | git diff 友好，版本可追溯 |
| Agent 引擎 | Claude Agent SDK（嵌入后端） | 比 subprocess 调 Claude Code 更紧密，可直接控制 prompt/tool |
| 迁移源 | 现有 `graph.json` + 239 章 | 结构化数据迁移 + 风格指纹提取 |

---

## 六、约束分层架构（B 分层声明式）

约束按"硬度"分三层，每层用最合适的工具：

| 层 | 约束类型 | 实现方式 | 失败行为 | 治理的 RC |
|---|---------|---------|---------|----------|
| **硬约束** | 结构完整性（gender、FK、UNIQUE、必填字段） | SQLite schema（NOT NULL/CHECK/FK） | DB 物理拒绝写入 | RC1, RC3 |
| **业务约束** | 创作规则（字数范围、悬念消费平衡、卷类型矩阵） | Python 校验器（dataclass + validator） | 拒绝 + 返回修复 prompt | RC2, RC4 |
| **软约束** | 风格偏好（感官密度、句式多样性） | StyleTemplate 注入 prompt | 记录偏离，不阻断 | RC5 |

**关键性质**：
- 硬约束**物理不可绕过**——LLM 输出 gender 为空时，DB 直接拒绝 INSERT
- 业务约束**可演进**——改 Python 代码即可，不用 ALTER TABLE
- 软约束**不阻断创作**——只记录偏离，避免过度刚性

---

## 七、正文存储（M2：文件 + 场景级 DB + 段落索引）

**核心思路**：用"场景"作为结构化的稳定单元，"段落"作为派生索引。

| 存储层 | 内容 | 形态 | 说明 |
|--------|------|------|------|
| **文件系统** | 正文（`ch{NN}.txt`） | 连续文本 | source of truth，git diff 友好 |
| **SQLite 场景表** | 场景级元数据 | 结构化 | 每章 2-4 场景，含 POV/在场角色/悬念推进/时间戳 |
| **SQLite 段落索引** | 段落 offset/hash | 派生 | 后台解析正文建索引，可重建，用于全文检索 |

**为什么不选全段落 DB（M1）**：
- 网文高产（日均万字级），写作流畅性是生命线
- 段落边界主观，自动分段不可靠
- git diff 是长篇创作不可让渡的工作流
- M2 用场景元数据 + 段落索引已覆盖 M1 的 80% 校审查询能力

**为什么不选纯文件（M4）**：失去结构锚点，跨章连贯性校验（角色情绪轨迹、悬念推进密度）做不了。

---

## 八、Sub-project 分解

6 个可独立交付的 sub-project，按依赖顺序：

| SP | 层 | 内容 | 工程量 | 依赖 |
|----|---|------|--------|------|
| **SP1 数据骨架** | L1+L3 | Constitution schema + 实体 schema（Character NOT NULL gender / 关系网 / POV 矩阵）+ 校验器 + 从 graph.json 迁移 | ~2 周 | 无 |
| **SP2 剧情树** | L2 | Volume→Arc→Chapter→Beat 树 + 悬念消费作为节点属性（`responsibilities`）+ 从 outline_entries 迁移 | ~2 周 | SP1 |
| **SP3 风格指纹** | L0+L1 | 从 239 章提取 StyleTemplate（句长/句式/感官密度分布）+ 注入 writing prompt | ~1.5 周 | SP1 |
| **SP4 创作管线 v4** | L4 | ChapterAgent v4 消费 SP1-3 结构化输入，输出结构化正文；v3 管线作初版参考；分层校验；第一卷验证 | ~3 周 | SP1,2,3 |
| **SP5 治理层** | L5 | IVA + CrossChapterReviewer，基于结构做跨章连贯校审 | ~2 周 | SP4 |
| **SP6 工具层** | L6 | Web 编辑器（剧情树/关系网/宪法/风格模板视图）+ diff + 导出 | ~6-8 周 | SP1-5 |

**依赖图**：
```
SP1 ←── SP2
SP1 ←── SP3
SP1+SP2+SP3 ←── SP4 ←── SP5
        SP1-5 ←── SP6
```

**总计 ~15-20 周（3.5-5 月）**，符合预算。SP1-SP5 是核心管线（串行），SP6 工具层最独立（可并行起步）。

---

## 九、迁移策略

### 9.1 现有数据迁移

| 源数据 | 目标 | 处理方式 |
|--------|------|---------|
| `graph.json`（1617 events / 109 characters / 368 threads / 5217 relations） | SQLite（实体/关系/悬念表） | 一次性迁移脚本 |
| 239 章正文（`output/`） | 文件系统（保留）+ 场景元数据提取 | 文件不动，提取场景入 SQLite |
| `outline_entries`（239） | PlotTree（Volume→Arc→Chapter） | 一次性迁移脚本 |
| 239 章风格特征 | StyleTemplate | SP3 的风格提取器产出 |

### 9.2 迁移阶段前置任务（Phase 0）

以下任务在声明式工作台的迁移阶段依然需要（保留自 v3 计划）：

- **清理 v2 脏数据**：184 events 缺 chapter / 154 arcs 缺 structure_type / 247 vs 239 extraction orphans / world_setup total=215→239
- **标注 Vol1-17 卷类型**：opening / advancing / climax / epilogue / multi-pov（领域判断，需用户介入）
- **补全 109 角色 gender 字段**：已确认 拾=男 / 舟=男 / 陆=女 / 灰衣=女 / T-1=无（领域判断，需用户介入）
- **风格提取**：从 239 章生成 StyleTemplate（SP3 自动产出）

### 9.3 分档处理（用户已决策）

- **高质量历史数据**：直接迁移
- **脏数据**：dry-run diff 报告 → 人工确认 → 修复或标记 `historical_skip`
- **缺失数据**（digests 93 章缺失）：标记 `historical_skip`，不补生成

---

## 十、待确认假设

以下假设在顶层设计阶段未深入，留待对应 SP 的独立 brainstorm 确认：

1. **项目命名**：暂用 `novel_workbench`，可在 SP1 启动时定
2. **绝地天通是否作为新系统首项目**：选项——(a) Vol18+ 直接用新系统（边建边用）；(b) 新系统先用测试项目验证，稳了再接绝地天通。推荐 (a)，现有 239 章是宝贵的迁移源 + 风格训练数据，且 Vol18 尚未开始正好接上
3. **剧情树粒度**：默认 Volume→Arc→Chapter→Beat，Beat 可选（SP2 确认）
4. **多视角矩阵表示**：Character×Chapter 的 POV 矩阵（SP1 确认）
5. **并行写作冲突策略**：SP4 起步仍串行，并行作为 SP4 后期目标（SP4 确认）
6. **风格提取方法**：统计指纹 + LLM 总结混合（SP3 确认）
7. **diff 粒度**：结构 diff（schema）+ 文本 diff（正文）（SP6 确认）
8. **导出格式**：Markdown（默认）/ EPUB / PDF（SP6 确认）
9. **v3 管线代码处置**：保留作为 L4 参考实现，v4 是新实现（不强行复用代码，借鉴设计）

---

## 十一、风险与现实评估

### 11.1 预期收益（基于 v3 综合方案的现实评估）

| 指标 | v2.1 现状 | v3 预期 | 声明式预期 |
|------|----------|---------|-----------|
| 单章 pass rate | ~80% | 85%→95% | 90%→97% |
| 整卷 first-pass | ~50% | 60%→85% | 70%→90% |
| 数据漂移率 | ~15% | <5% | <2% |
| 代词错误/卷 | V16 爆发 97 | 持续监控 | 结构消除（NOT NULL） |

### 11.2 非银弹声明

- **LLM 进化博弈持续存在**：声明式降低博弈空间（约束在 schema），但不消除。需每 3-5 卷扩展规则集
- **Web 编辑器增加工程量**：SP6 占总工程量 ~30%，但提升结构可见性，降低长期维护成本
- **迁移阶段成本不可忽略**：~1-2 周（Phase 0 前置任务 + 数据迁移）
- **schema 设计过早固化风险**：用业务约束层（Python）承载易变规则，schema 只放稳定结构

### 11.3 关键风险与缓解

| 风险 | 概率 | 缓解 |
|------|------|------|
| schema 设计过早固化 | 中 | 业务约束层承载易变规则；schema 只放稳定结构 |
| Web 编辑器复杂度膨胀 | 高 | SP6 起步只做核心视图（剧情树/关系网/宪法），diff/导出后置 |
| 多 agent 并行写作冲突 | 中 | SP4 起步仍串行，并行作为后期目标 |
| 迁移阶段发现历史数据更脏 | 中 | 分档处理（dry-run → 人工确认 → historical_skip） |
| LLM 在结构化输入下依然博弈 | 高（必然） | 分层校验 + IVA 跨核验；接受 3-5 卷扩展一次规则集 |

---

## 十二、下一步

1. **用户 review 本顶层 doc**（当前）
2. review 通过后，启动 **SP1（数据骨架）** 的独立 brainstorm → spec → plan → implementation
3. SP1 完成后，按依赖顺序启动 SP2-SP6，每个 sub-project 走完整流程
4. Phase 0 前置任务（清理脏数据 / 标注卷类型 / 补 gender）可与 SP1 并行启动

---

## 附录：与 v3 综合方案的对应关系

v3 综合方案的核心设计被吸收为声明式工作台的组成部分：

| v3 设计 | 声明式工作台对应 |
|---------|----------------|
| 契约层（contracts.py） | L1 宪法 + L3 实体 schema（SP1） |
| 规则引擎（rules.yaml + validators） | 业务约束层（Python 校验器，SP1/SP4） |
| 门禁（gates.py） | ChapterAgent 分层校验流程（SP4） |
| IVA（独立核验） | L5 治理层 IVA（SP5） |
| 卷类型矩阵 | L2 VolumeType 矩阵（SP2） |
| SHA256 文件锁 | L5 文件完整性校验（SP5） |
| auto_prune | L2 悬念修剪（SP2，作为剧情树节点属性） |

**关键差异**：v3 是在 L4-L5 加约束（命令式），声明式是把约束下沉到 L1-L3 的 schema（声明式）。v3 的契约/IVA 设计依然有效，但它们守护的是上层，而下层的结构化是让上层工作量大幅减少的根本。
