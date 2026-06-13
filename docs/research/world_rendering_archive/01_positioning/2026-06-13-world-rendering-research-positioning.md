# 世界渲染（World Rendering）— 研究方向定位文档

**日期**: 2026-06-13
**状态**: 研究方向已定位，待选切入点
**作者**: novel-kg + Claude（作为研究伙伴）
**入口用途**: 本文档是 /compact 后恢复 context 的锚点。所有后续讨论从本文档续起。

---

## 0. 一句话定位

**用多 agent 在基础约束下对抗"具现化"一个包含时间维度的完整小说世界，世界冻结后用可迭代的渲染端把它投影成小说正文。核心红利是并行渲染（因世界已冻结，渲染无副作用，可反复重跑）。**

这个方向有扎实的学术地基（不是空想），但 **"异质 agent + 症迹世界 + 版本化演化 + 并行渲染"四者组合用于长篇小说生产，是文献空白**。

---

## 1. 范式背景：为什么放下工程化方案

之前设计了"声明式工作台"（`docs/superpowers/specs/2026-06-13-declarative-novel-workbench-design.md`），但它本质是工程优化——别人也在做。本研究方向是**真正原创的研究**：业界（Stanford AI Town / drama management）都只到原型，没人产出过长篇小说。

声明式工作台 design doc 不废弃，**重新定位为"工程基础设施"**（SQLite / FastAPI / Web 编辑器 / 分层约束依然是基础），但研究核心是"时间维度的世界"。

---

## 2. 用户的 6 层原创思考（核心思想，详细记录）

### 2.1 表示层
- 小说的本质：将一个设计的"世界"表现出来的一种手法（抽象→具象）
- 表现前世界只存在于人脑意识中
- 重新抽象不容易，**只能简化，无法实现所有信息**（物理规律、数理逻辑等）
- 信息量很大，不是个人研究能完全实现的
- → 衍生研究问题：**选择性建模原则**——哪些必须建模（对叙事有因果效力的状态），哪些可省略（背景性恒定写宪法即可）

### 2.2 具现化层（最有原创性的部分，4 个可命名概念）

**概念 1：痕迹（Trace）**
- agent 对抗要留下"痕迹"，痕迹要符合预先设计的约束
- 靠痕迹来填充世界
- 区别：**行动（action）是短暂的；痕迹（trace）是行动在世界里留下的、符合约束的、持久的状态增量**
- 痕迹是世界状态的增量单位；agent 对抗的产物不是对话日志，是结构化的、累积成世界的痕迹流
- ≈ Event Sourcing，但强调"符合约束"和"填充世界"的语义

**概念 2：异质 agent 生态（Heterogeneous Agent Ecology）**
- 不同 agent 成分可以不一样：
  - **世界意志**（命运、因果、叙事引力）→ 推动走向必然 → 留大尺度轨迹
  - **规律执行者**（物理法则、魔法系统、社会规则）→ 约束其他 agent 的可能空间 → 留规则触发记录
  - **个体**（角色）→ 追求目的、做选择 → 留个人状态/关系变化
  - **集体**（势力、组织、文明、物种）→ 集体行动、演化 → 留集体状态变化、势力消长
- 让世界丰满的来源多元化

**概念 3：矛盾即基石（Contradiction as Foundation）**
- 矛盾本身是构建世界的基石，矛盾产生故事，丰满世界
- 传统系统把矛盾当 bug（要 consistency），本研究把矛盾当特性（要生发故事）
- 呼应黑格尔辩证法 + 戏剧冲突理论，但 AI 生成里罕见
- **矛盾的累积本身是世界丰满的指标，不是要消灭的误差**
- 边界：死锁矛盾（agent 该退场不退场）需外部编排层裁决——人在环中关键介入点

**概念 4：目的驱动收敛（Purpose-Driven Convergence）**
- 世界丰满到设计好的程度就收敛冻结
- 收敛条件是**叙事事件**（非技术阈值）：
  - 某 agent 实现核心目的（主角完成弧线）
  - 某层约束被打破（世界规则被颠覆，新秩序建立）
  - 累积矛盾张力达设计阈值

### 2.3 冻结层
- 收敛判据：**目的达成（语义）+ 时间切片完整（技术）**，缺一不可
- 技术路线需专门设计（猜测用到 bitemporal 快照 + 日志回放验证完备性）

### 2.4 渲染层
- 只要世界信息足够多，不断优化就能渲染出满意作品
- **把"写作"从一次性创作降级为"可迭代的渲染工艺"**——把高风险环节（写作时一致性）转化成可重复优化的稳定环节
- 渲染可 A/B 测试、换风格、换视角、反复重跑

### 2.5 验证层
- 好坏难判断，完整作品出来前只能拿大纲/脚本等概括
- **agent 访谈**：通过某一视角（角色/势力代言人）了解世界
  - agent 答不上来 → 世界有空洞
  - 不同 agent 对同一事件认知冲突 → 判断是良性矛盾（故事张力）还是恶性矛盾（世界不一致）
- 用户项目已有 `interview_character` 命令，是此范式的雏形，可复用扩展

### 2.6 人机协作层：世界树（World Tree = git for worlds）
- 像种子，发芽、生长，逐渐长成"世界树"，不需要人为干预
- 但产生内容不一定让作者满意
- 世界要支持**暂存**：暂停演变 → 作者介入（访谈/导出大纲）→ 主观修正 → 从指定点重新演化

**世界树 = git for worlds 的工程对应**：

| git 操作 | 世界树对应 | 含义 |
|---------|-----------|------|
| commit | 暂存点 snapshot | 世界演化到某状态，冻结检查点 |
| checkout | 回到检查点 | 从该点重新演化 |
| branch | 平行演化 | 同种子世界演化出不同结局 |
| merge | 合并演化线 | 多分支世界状态融合 |
| diff | 世界状态对比 | 两次演化/两分支差异 |
| cherry-pick | 迁移事件 | 把某分支特定事件搬到主线 |

**世界树不是比喻，是数据结构**——DAG，节点是世界快照，边是演化痕迹流。

---

## 3. 文献调研精华（agent a11111fa69aa0c3c1 产出，2026-06-13）

### 3.1 学术借力点（成熟工具，不重新发明）

| 工具 | 用途 | 来源 |
|------|------|------|
| **Event Sourcing** | 痕迹基础设施（append-only log + snapshot 重放） | [Fowler](https://martinfowler.com/eaaDev/EventSourcing.html) |
| **Bitemporal DB** | valid_time / transaction_time 双轴 | [Fowler](https://martinfowler.com/articles/bitemporal-history.html) |
| **Generative Agents 架构** | memory/reflection/planning 三件套 | [Park et al. 2023](https://arxiv.org/pdf/2304.03442) |
| **Narrative Planning (IPOCL)** | fabula = (domain, initial state, goal) + intentionality 约束 | [Riedl & Young 2010 JAIR](https://faculty.cc.gatech.edu/~riedl/pubs/jair.pdf) |
| **Drama Manager** | "世界意志 agent" 工程参考 | [Mateas PhD](https://www.cs.cmu.edu/~dgroup/papers/CMU-CS-02-206.pdf) + [L4D AI Director](https://steamcdn-a.akamaihd.net/apps/valve/2009/ai_systems_of_l4d_mike_booth.pdf) |
| **时态 KG (T-SPARQL)** | 时态查询语言 | [CEUR](https://ceur-ws.org/Vol-639/021-grandi.pdf) |
| **RE-GCN / RE-Net** | 时态 KG 链接预测（"下一个该发生的事件"） | [INK Lab](http://inklab.usc.edu/renet/) |

### 3.2 真正的原创空间（文献空白，按强度排序）

| 原创点 | 重合度 | 空白说明 |
|--------|--------|---------|
| **异质 agent 架构**（人物/意志/规律/集体） | 极少重合 | "agent as world/environment" 字面搜索零命中。最强原创 |
| **版本化世界演化**（git for worlds） | 极少重合 | versioned world evolution + branching + human intervention 无学术对应 |
| **矛盾作为永久结构**（非待解 bug） | 部分重合 | Ware 2014 把 conflict 当约束但仍要"解决"；永久张力是空白 |
| **痕迹（世界级、约束可读）** | 部分重合 | Smallville 只做个体痕迹；世界级 + 约束可读是空白。= Event Sourcing 叙事化嫁接 |
| **bitemporal fabula/sjuzhet 桥接** | 空白（已核验 2026-06-13） | 三个社区（叙事生成/数据库 bitemporal/叙事分析）从未相遇。CEUR Vol-3290 核验为情况 (a)。**但"空白" ≠ "值得做"——必要性待证伪验证**。详见 [transaction-time-verification.md](2026-06-13-transaction-time-verification.md) |
| **agent 访谈验证世界丰满度** | 重合 | 已有 PICon/Character-LLM，但用于世界丰满度（而非角色一致）是挪了一步 |

---

## 4. 两个核心 Thesis（研究锚点）

### Thesis 1（工程创新）：异质 agent 架构
agent 从"都是角色"扩展为 4 类——**人物 / 世界意志 / 规律执行者 / 集体**。每类有不同行为模式、留不同性质的痕迹，共同填充世界。文献几乎完全空白。

**⭐ 架构修正（2026-06-13 晚，用户洞察）**：异质的真正核心不是"4 个并列类型"，而是**多层级规则相互影响系统**：
- L3 世界意志（世界规则）→ L2 集体（集体规则）→ L1 角色（角色规则）+ 横切规律执行者
- 三种影响方向：上→下约束 / 下→上涌现 / 横切校验
- 真正价值在**层级间冲突**情节（同质 character 系统产生不了的）

架构详情：[thesis1-architecture.md](2026-06-13-thesis1-architecture.md)（已含 §2.0 层级总览 + §3.1 三种影响机制 + §4 trace 层级字段）

**⭐ H4 数据驱动验证设计已出**：[h4-systemic-validation-design.md](2026-06-13-h4-systemic-validation-design.md)——绝地天通场景 + 4 客观指标 + 严格证伪（异质在 ≥30% 场景明显优 → 站住）。下一步实现脚本 + 跑数据。H1（还原论对比）已废除。

### Thesis 2（理论创新，**必要性待验证**）：Bitemporal Fabula/Sjuzhet 桥接

**⚠️ 状态：文献空白已确认（无竞品），但"空白 ≠ 值得做"——必要性必须通过证伪实验验证**

**修正记录（2026-06-13）**：原方案用"章号"做 transaction_time 有根本缺陷（章节是出版/装订单位，切片会切在叙事单元中间——详见 [transaction-time-verification.md](2026-06-13-transaction-time-verification.md)）。修正为 interval-based：transaction_time 是**连续叙事行进距离**，不是离散章号。

**修正后的 thesis 2**：
- `valid_time` = 故事内时间区间（事件在世界中为真的时间区间）= **fabula**
- `transaction_time` = 叙事行进距离区间（读者/agent 穿越叙事到某点时此事件已知）= **sjuzhet**
- **核心 killer query**：「在叙事行进到某点时，agent X 知道什么？」（as-of transaction_time 查询 + revealed_to 过滤）
- **与"agent 访谈验证"概念融合**——访谈本质就是 belief 查询

**关键差异化（三者组合，文献空白）**：
1. **single-trace**：sjuzhet 是同一 trace 的字段，不是独立 plan（vs BiPOCL 两个独立 plan）
2. **bitemporal**：valid_time + transaction_time 双时间戳（vs VNPA 单一时间轴）
3. **叙事化 transaction_time**：连续叙事行进距离（vs Fowler bitemporal 的物理时钟）

**文献查证结论（2026-06-13）**：三个社区从未相遇（叙事生成 Riedl/BiPOCL / 数据库 bitemporal Fowler / 叙事分析 Konle CEUR Vol-3290）。CEUR Vol-3290 核验为情况 (a)，没做 bitemporal，无竞品。

**⚠️ 必要性风险（诚实标注）**：最强反对是"渲染端独立查 fabula + 自己决定揭示序可能就够了"。transaction_time 的唯一可能真实价值是 sjuzhet 决策的版本化/共享/审计（多渲染端协作时）。**如果最小验证显示 fabula+predicate 能解决 killer query，thesis 2 是过度设计，应放弃**。

---

**🔴 证伪结果（2026-06-13，最小验证完成）**：

最小验证（V16 数据，123 测试点）确认 thesis 2 **被证伪**：

1. **查询表达力完全等价**——baseline（fabula + `dict[sjuzhet, list[float]]`）在所有 123 测试点不劣于 thesis 2
2. **thesis 2 单区间有真实劣势**——repeating frequency 场景（伏笔多次暗示）丢失中间揭示点（4/4 案例受损）
3. **thesis 2 多区间与 baseline 完全同构**——`list[float]` vs `list[(start,end)]` 结构等价，换名不是创新

**结论**：thesis 2 作为研究 thesis **不成立**。bitemporal 降级为渲染端实现细节（可选优化，非核心）。**研究焦点转向 thesis 1（异质 agent 架构）**。

详见 [thesis2-validation-report.md](2026-06-13-thesis2-validation-report.md)。

---

## 5. 概念词汇表（建议固定）

| 我们的概念 | 学术对应 | 备注 |
|-----------|---------|------|
| 故事时间 / 叙事时间 | **fabula / sjuzhet**（俄国形式主义） | Jockers 的 Syuzhet R 包已用，现成词，直接 adopt |
| valid_time / transaction_time | bitemporal DB 术语 | 数据库界标准 |
| 痕迹 | **trace** | 自创，区别于 event sourcing 的 event，强调约束可读 |
| 异质 agent | heterogeneous agent ecology | 自创 |
| 世界树 | versioned world evolution | 自创 |
| 丰满度三维度 | **Invention / Completeness / Consistency**（[Wolf 2012](https://books.google.com/books/about/Building_Imaginary_Worlds.html?id=rc6HgH34s0wC)） | 直接 adopt |
| intentionality 约束 | IPOCL（[Riedl 2010](https://faculty.cc.gatech.edu/~riedl/pubs/jair.pdf)） | 直接 adopt |

---

## 6. 必须避免的坑

1. **不要重做 Smallville**——它是 2D 沙盘 + 个体位置，对长篇太浅。要做**抽象层**（事件/关系/时态），不是空间模拟
2. **渲染端不要做成"再调一次 LLM 创作"**——会丢掉并行优势。渲染 = **读冻结世界状态 → 投影成 sjuzhet**，类似 DB 视图。LLM 只是渲染器的一种实现
3. **必须有执行前校验防 hallucinated mutation**——LLM agent 会产生不可逆有害状态突变（[OpenKedge arXiv 2604.08601](https://arxiv.org/html/2604.08601v1)）。基础约束层是硬墙，trace 写入前必须通过校验
4. **agent 访谈验证要用 Wolf 三维度**——不只查 consistency，**Invention 和 Completeness 的可计算指标是空白**，可以做
5. **bitemporal 跨界需自己造词**——论文搜索零命中，需清楚论证为何双轴对并行渲染是必要而非冗余

---

## 7. 最值得深读的资源

### 必读 3 篇
1. **[Park et al. 2023 — Generative Agents (arXiv 2304.03442)](https://arxiv.org/pdf/2304.03442)** — 世界状态树、memory stream、reflection 的原典。"痕迹"概念要从此处对比定位原创性
2. **[Riedl & Young 2010 — Narrative Planning (JAIR)](https://faculty.cc.gatech.edu/~riedl/pubs/jair.pdf)** — fabula = (domain, initial state, goal) 形式化，叙事世界建模绕不开的基石
3. **[Martin Fowler — Bitemporal History](https://martinfowler.com/articles/bitemporal-history.html) + [Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html)** — 两篇短文，软件工程成熟成果引入叙事的核心原创机会

### 推荐补充
4. **[Mateas PhD Thesis (CMU-CS-02-206)](https://www.cs.cmu.edu/~dgroup/papers/CMU-CS-02-206.pdf)** — Facade 的 drama manager + beat 架构，"世界意志 agent"最完整的工程参考。配合 [Valve AI Director GDC talk](https://steamcdn-a.akamaihd.net/apps/valve/2009/ai_systems_of_l4d_mike_booth.pdf)
5. **[Mark J.P. Wolf — Building Imaginary Worlds (Routledge 2012)](https://books.google.com/books/about/Building_Imaginary_Worlds.html?id=rc6HgH34s0wC)** — Invention/Completeness/Consistency 三支柱是评估"世界丰满度"的理论框架
6. **[ACM Computing Surveys — Automatic Story Generation Survey](https://dl.acm.org/doi/fullHtml/10.1145/3453156)** — 整个领域的全景图，作为地图

### 前沿技术
- **[RE-GCN / RE-Net (INK Lab USC)](http://inklab.usc.edu/renet/)** — 时态 KG 链接预测
- **[LLM as World Model (arXiv 2411.08794)](https://arxiv.org/html/2411.08794v2)** — LLM 直接当世界模拟器
- **[Genie 3 / GameNGen](https://deepmind.google/blog/genie-3-a-new-frontier-for-world-models/)** — 神经世界模拟器（视觉领域）

---

## 8. 完整参考文献（调研报告全量）

### Generative Agent Worlds
- [Generative Agents: Interactive Simulacra (arXiv)](https://arxiv.org/pdf/2304.03442) / [ACM UIST 2023](https://dl.acm.org/doi/fullHtml/10.1145/3586183.3606763) / [GitHub](https://github.com/joonspk-research/generative_agents) / [Stanford HAI](https://hai.stanford.edu/news/computational-agents-exhibit-believable-humanlike-behavior)
- [AgentSociety (arXiv 2502.08691)](https://arxiv.org/html/2502.08691v1) / [GitHub](https://github.com/tsinghua-fib-lab/agentsociety/)
- [LARP (arXiv 2312.17653)](https://arxiv.org/abs/2312.17653)

### Temporal KG
- [T-SPARQL (CEUR)](https://ceur-ws.org/Vol-639/021-grandi.pdf)
- [Building Narrative Structures from KG (ESWC 2022)](https://2022.eswc-conferences.org/wp-content/uploads/2022/05/phd_Blin_paper_181.pdf)
- [Modelling Temporal Data in KG (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10907873/)
- [OpenAI Temporal Agents Cookbook](https://developers.openai.com/cookbook/examples/partners/temporal_agents_with_knowledge_graphs/temporal_agents)

### Bitemporal
- [Martin Fowler — Bitemporal History](https://martinfowler.com/articles/bitemporal-history.html)
- [Temporal Database (Wikipedia)](https://en.wikipedia.org/wiki/Temporal_database)
- [Time Maps: Theory/Fabula](https://culturalanalytics.org/article/id/802/)
- [Syuzhet R Package (Jockers)](https://www.matthewjockers.net/2015/02/02/syuzhet/)
- [Towards an Event Based Plot Model (JCLS)](https://jcls.io/article/id/110/print/)

### Narrative Planning / Story Generation
- [TALE-SPIN, MINSTREL and ChatGPT](https://www.marilaur.info/talespingeneva.pdf) / [Minstrel Remixed (AAAI)](https://cdn.aaai.org/ojs/12419/12419-52-15947-1-2-20201228.pdf) / [Story Generation After TALE-SPIN (IJCAI)](https://www.ijcai.org/Proceedings/81-1/Papers/004/Papers/004.pdf)
- [Mark Riedl — Intro to AI Story Generation](https://mark-riedl.medium.com/an-introduction-to-ai-story-generation-7f99a450f615)
- [Riedl & Young 2010 (JAIR)](https://jair.org/index.php/jair/article/view/10669/25501) / [PDF](https://faculty.cc.gatech.edu/~riedl/pubs/jair.pdf) / [Riedl Dissertation](https://faculty.cc.gatech.edu/~riedl/pubs/dissertation.pdf)
- [Ware 2014 — Conflict Model](http://ciigar.csc.ncsu.edu/files/bib/Ware2014-ConflictModel.pdf)
- [Automatic Story Generation Survey (ACM CSUR)](https://dl.acm.org/doi/fullHtml/10.1145/3453156)

### Multi-agent Narrative
- [Multi-Agent Character Simulation (ACL 2025)](https://aclanthology.org/2025.in2writing-1.9.pdf)
- [StoryWriter (ACM)](https://dl.acm.org/doi/10.1145/3746252.3761616)
- [StoryVerse (arXiv 2405.13042)](https://arxiv.org/html/2405.13042v1)
- [Collaborative Multi-Agent Simulation (AAAI)](https://ojs.aaai.org/index.php/AAAI/article/view/40288/44249)

### Drama Management
- [Mateas PhD (CMU)](https://www.cs.cmu.edu/~dgroup/papers/CMU-CS-02-206.pdf)
- [Facade Content Structuring (AAAI)](https://ojs.aaai.org/index.php/AIIDE/article/view/18722)
- [Declarative Optimization-Based Drama Management](https://users.soe.ucsc.edu/~michaelm/publications/nelson-cga-2006.pdf)
- [Valve AI Director (GDC)](https://steamcdn-a.akamaihd.net/apps/valve/2009/ai_systems_of_l4d_mike_booth.pdf)

### World Building
- [Mark J.P. Wolf — Building Imaginary Worlds](https://books.google.com/books/about/Building_Imaginary_Worlds.html?id=rc6HgH34s0wC)
- [Henry Jenkins interview with Wolf](http://henryjenkins.org/blog/2013/09/building-imaginary-worlds-an-interview-with-mark-j-p-wolf-part-one.html)

### Event Sourcing / Engineering
- [Martin Fowler — Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html)
- [Microsoft Azure — Event Sourcing Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing)
- [Microservices.io](https://microservices.io/patterns/data/event-sourcing.html)
- [Game Loop · Sequencing Patterns](https://gameprogrammingpatterns.com/game-loop.html)
- [Deterministic Lockstep (Glenn Fiedler)](https://gafferongames.com/post/deterministic_lockstep/)

### LLM World Models
- [DeepMind Genie 3](https://deepmind.google/blog/genie-3-a-new-frontier-for-world-models/)
- [GameNGen](https://gamengen.github.io/) / [DIAMOND (arXiv 2405.12399)](https://arxiv.org/abs/2405.12399)
- [LLM-Based World Models (arXiv 2411.08794)](https://arxiv.org/html/2411.08794v2)

### Neural Temporal KG
- [RE-Net (INK Lab)](http://inklab.usc.edu/renet/) / [RE-GCN PDF](https://jiafengguo.github.io/2021/2021-Temporal%20Knowledge%20Graph%20Reasoning%20Based%20on%20Evolutional%20Representation%20Learning.pdf)
- [Temporal Inductive Path NN (arXiv 2309.03251)](https://arxiv.org/html/2309.03251v3)

### Agent Interview / Persona
- [PICon (arXiv 2603.25620)](https://arxiv.org/html/2603.25620v1)
- [Character-LLM (ICLR)](https://openreview.net/pdf?id=AptTXihnhH)
- [Stanford HAI — 1052 Individuals Simulation](https://hai.stanford.edu/news/ai-agents-simulate-1052-individuals-personalities-with-impressive-accuracy)

### 其他
- [OpenKedge — Governing Agentic Mutation (arXiv 2604.08601)](https://arxiv.org/html/2604.08601v1)
- [Dialectical Thinking and Creativity (APA)](https://psycnet.apa.org/record/2018-09015-009)
- [Awesome-Story-Generation (GitHub)](https://github.com/yingpengma/Awesome-Story-Generation)

---

## 9. 下一步选项（压缩后从这里选一个继续）

### 立即可做
- **A. 深入 Thesis 2（bitemporal fabula/sjuzhet）** — 最干净的理论贡献。用绝地天通 V16（ch216-227，8+ 角色多视角）做小规模验证：手动把 12 章的双时态建出来，看能否表达倒叙/伏笔/POV 知识分布。如果能且暴露现有 graph.json 盲区，方向成立
- **B. 深入 Thesis 1（异质 agent）** — 设计 4 类 agent（意志/规律/个体/集体）的架构、行为协议、痕迹 schema、通信方式
- **C. 深读 3 篇必读论文** — 派 agent 拉取 Park 2023 / Riedl 2010 / Fowler bitemporal+event sourcing 精读，产出更细的设计输入
- **D. 设计"痕迹"数据结构** — Event Sourcing 的叙事化版本，定义 trace schema、约束校验、世界状态折叠算法

### 工程基础（并行可做）
- 声明式工作台的 SQLite/FastAPI 基础（见 `docs/superpowers/specs/2026-06-13-declarative-novel-workbench-design.md`）依然是底层依赖

### Phase 0 前置任务（沿用 v3 计划，迁移阶段仍需）
- 清理 v2 脏数据（184-244 events 缺 chapter / 247 vs 239 extraction / world_setup total=215→239）
- 标注 Vol1-17 卷类型（opening/advancing/climax/epilogue/multi-pov）
- 补全 109 角色 gender（已确认 拾=男/舟=男/陆=女/灰衣=女/T-1=无）

---

## 10. 关键决策记录

- **2026-06-13**: 放下声明式工作台的工程优化路线，转向"世界渲染"研究方向
- **2026-06-13**: 用户的 6 层思考成型（痕迹/异质 agent/矛盾基石/目的收敛/世界树/agent 访谈）
- **2026-06-13**: 文献调研确认两个核心 thesis（异质 agent + bitemporal 桥接）+ 4 个原创空白
- **2026-06-13**: 术语词汇表固定（fabula/sjuzhet + valid/transaction_time + Wolf 三维度 adopt；trace/heterogeneous agent/world tree 自创）
- **2026-06-13**: thesis 2 修正——transaction_time 从"章号"改为"连续叙事行进距离/event-interval"（双 agent 查证 + Chatman/Genette/Yeager 文献支持）。核心价值重新定位为 reader/agent belief 双时态追踪。
- **2026-06-13**: thesis 2 文献查证完成——三个社区从未相遇，CEUR Vol-3290 核验无竞品。但用户指出"竞品空白 ≠ 值得做"，必要性必须通过严格证伪实验验证。
- **2026-06-13**: thesis 2 最小验证完成——**被证伪**。V16 数据 123 测试点，baseline（fabula + dict[sjuzhet, list[float]]）在所有维度不劣于 thesis 2。thesis 2 单区间 repeating frequency 场景有劣势（4/4 案例丢失中间点）；多区间与 baseline 同构。**thesis 2 作为研究 thesis 不成立，降级为渲染端实现细节。研究焦点转向 thesis 1（异质 agent 架构）**。
- **2026-06-13 晚**: thesis 1 架构草案完成（4 类 agent + trace 事件总线 + 集体 agent 借鉴 Holonic MAS + List & Pettit）。集体 agent 文献查证为"结构性空白"（哲学有理论 / MAS 有 Holonic / Game AI 有 faction，但叙事场景从未作为单一 agent 实现）。
- **2026-06-13 晚**: ⭐ thesis 1 架构修正——用户给出多层级洞察：异质 = 多层级规则相互影响系统（非"4 个并列类型"）。架构文档加 §2.0 层级总览 + §3.1 三种影响机制 + §4 trace 层级字段（layer / influence_direction / conflict_with）。H1 废除（还原论错误）。
- **2026-06-13 晚**: ⭐ H4 数据驱动验证设计完成——绝地天通 Vol1-12 场景 + 3 agent 交叉提取 + 4 客观指标 + ≥30% 证伪阈值。学 thesis 2 的客观查询对比模式。用户强调"实际要靠数据说话"，下一步必须跑出真实数字。
- **2026-06-13 晚**: 关键技术验证——Claude Code agent teams（Agent/Workflow 工具）**可以**实现真正的多 agent 通信。架构：4 类 subagent + 文件系统 trace 总线 + Workflow simulation loop。我之前说"不能直接做 generation test"是错的，用户纠正了。工程量修正为 1-2 天（非周级）。
- **2026-06-13 晚**: ⭐⭐ **H4 generation pilot 跑完，verdict = 异质明显优**。用 Workflow 跑封印危机场景，异质（4 类 agent）vs 同质（4 character）各 4 ticks。37 agent 调用 / 1.58M token / 210 秒。异质 16 trace 横跨 4 层，同质 16 trace 全在 L1。**4 个涌现现象**：L2 集体四 tick 自我进化（阻止→延迟→见证→承载）/ L3 世界意志主动裁定（"最先闭环者触发"规则）/ cross_cut↔L3 可执行校验回路 / 集体"对价悬置"制度创新（用集体存在置换牺牲对价，只有集体作为实体才能产生）。thesis 1 初步站住（条件性）。详见 [h4-generation-pilot-report.md](2026-06-13-h4-generation-pilot-report.md)。pilot 局限：单场景 / 场景偏向 / LLM 随机性 / prompt 引导，需扩展验证。

---

## 附录：之前的设计文档（仍有效，作为工程基础）

- `docs/superpowers/specs/2026-06-13-declarative-novel-workbench-design.md` — 声明式工作台顶层设计（SQLite/FastAPI/Web/分层约束）。重新定位为"工程基础设施"，研究核心是"时间维度的世界"
- `docs/pipeline-evolution/` — v0→v2.1 管线演进文档 + bug 目录 + 17 卷回读报告
- `docs/pipeline-evolution/final-report.md` — 绝地天通全书完成报告（239 章 / 87.8 万字 / 17 卷）
- Workflow `wgjw7h8hq` 产出 — v3 综合方案（5 根因 + 契约/IVA/规则引擎），其设计被吸收为本研究方向的 L4-L5 部分
