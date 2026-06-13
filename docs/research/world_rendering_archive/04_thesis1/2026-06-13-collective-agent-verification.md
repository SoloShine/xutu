# 集体 agent 文献查证报告

**日期**: 2026-06-13
**任务**: 确认 thesis 1 最强原创点（集体 agent）的文献空白状态，避免重蹈 thesis 2 覆辙
**结论**: **不是完全空白，是"结构性空白"**——哲学有理论、MAS 有 Holonic、Game AI 有 faction state machine，但叙事/世界模拟场景下从未作为单一 agent 实现

---

## §1. 查证结论（核心判断）

**集体 agent 在叙事生成 / 世界渲染领域是真空白，但在哲学、ABM、MAS、game AI 四个邻近领域都有大量相关工作**——只是没有人在"叙事/世界模拟"场景下把"集体"作为单一 agent 实现并明确为概念。

一句话判断：**"集体 agent" 不是完全空白，是"理论有、计算范式有、叙事/世界模拟场景无"。这是结构性空白而非完全空白，可作 thesis 1 的差异化点，但必须重新论证"为什么叙事场景下的集体 agent 不能被 individual 聚合替代"。**

---

## §2. 关键文献（按领域）

### 哲学（理论最厚但零计算实现）
- **List & Pettit《Group Agency: The Possibility, Design, and Status of Corporate Agents》(Oxford 2011)** [PhilPapers](https://philpapers.org/rec/LISGAT) / [LSE 项目页](https://personal.lse.ac.uk/list/project4.htm)
  - 核心论断：group/corporate agents "over and above their members"——集体作为**不可还原**的单一 agent
  - 明确主张**单一 agent**（功能主义论证：满足 representation + attitude + action 三条件就是 agent）
  - 计算实现：**完全没有**
- **Searle "Collective Intentionality" (1990)** [Stanford Encyclopedia](https://plato.stanford.edu/entries/collective-intentionality/) / [IEP](https://iep.utm.edu/collective-intentionality/)
  - 名言：collective intentional behavior is "**not the same as the summation of individual intentional behavior**"——"集体 ≠ individual 聚合"最经典的论证
- **Tuomela《Social Ontology》(2013)** — we-intentions 理论
- **Coleman "Corporate Actor"** [JSTOR](https://www.jstor.org/stable/27221352) — 理性选择框架下的集体行动者
- **Hindriks "Status Account"** [PDF](https://www.rug.nl/staff/f.a.hindriks/the_status_account_of_corporate_agents.pdf) — 外部状态视角
- **2025 综述** [The Past, Present and Future of the Corporate Actor](https://link.springer.com/article/10.1007/s41471-025-00213-w)

### MAS / Multi-Agent Systems（有"组织模型"但非"单一集体 agent"）
- **Wooldridge & Jennings《Intelligent Agents: Theory and Practice》(1995)** [PDF](https://www.cs.ox.ac.uk/people/michael.wooldridge/pubs/ker95.pdf)
  - Joint responsibility / team formation / cooperative problem solving——团队作为协作单位，**但本质是个体 agent 通过 joint intention 协作**（individual 聚合）
- **Virginia Dignum OperA / OMNI** [JASSS review](https://www.jasss.org/12/3/reviews/remondino.html)
  - "组织模型"框架：roles, norms, deontic temporal logic。组织本身**不是 agent**，是 agent 活动的容器
- **Cohen & Levesque "Joint Intentions" (1991)** + **Grosz & Kraus "SharedPlans"** — collective commitment，仍是 individual + 共享意图

### Holonic Multi-Agent Systems（最接近"集体作为单一 agent"）
- **Gerber et al. "Holonic Multi-Agent Systems" (1999)** [arXiv 综述](https://arxiv.org/html/2401.10839v1) / [Rodriguez 2005 PDF](http://www.sebastianrodriguez.com.ar/files/Rodriguez_2005_From_analysis_to_design_of_holonic_multi-agent_systems.pdf)
  - **关键引言**："when a new super-holon (collective entity) is formed, **a new entity appears in the system — not merely a group of holons in interaction as in 'traditional' MAS theory**"
  - **明确单一 agent**——super-holon 有自主性、有 super-head/representation、可以递归组成
  - **这是和 thesis 1 集体 agent 最接近的工作**——但 HMAS 应用于制造业、调度、e-administration，**从没应用于叙事生成或世界模拟**

### ABM / Agent-Based Modeling（全是 individual 聚合）
- **Sugarscape (Epstein & Axtell)** [Mesa 实现](https://mesa.readthedocs.io/stable/examples/advanced/sugarscape_g1mt.html)
- **Park et al. Smallville (2023)** [arXiv](https://arxiv.org/abs/2304.03442)
- **Project Sid (Altera, 2024)** [arXiv](https://arxiv.org/abs/2411.00114) — 1000+ agent civilization simulation
  - 1000 个独立 PIANO agent 涌现出"civilization"——**纯 individual 聚合**，"civilization"是涌现现象，不是建模实体

### Game AI（faction 是 state machine，不是 agent）
- **Civilization / Total War / Paradox 大战略的 faction AI**：GOAP / 行为树 / 层级 / 资源管理器
- **Vox Deorum (LLM hybrid for Civ V)** — 现代 LLM 加 faction AI
  - 游戏 faction AI 的目的是"play its role convincingly"——**给玩家体验，不是世界渲染或叙事生成**

### 叙事生成（集体 agent 几乎为零）
- Drama management / Storylets / Drama Llama / Story2Game：全是**单一角色**或**单个 drama manager**
- [Gnome Stew "Factions as Characters"](https://gnomestew.com/factions-as-characters/) — TTRPG 设计 tip，把 faction 当 character 处理，**但没有形式化 agent 模型**

---

## §3. "集体作为单一 agent" vs "individual 聚合"的文献区分

文献的区分基本是**两极**：

| 维度 | individual 聚合（主流） | 集体作为单一 agent（边缘） |
|------|------------------|------------------|
| 代表 | ABM、MAS team formation、Project Sid、Smallville | Holonic MAS（super-holon）、List & Pettit group agency、游戏 faction AI |
| 本体论 | 涌现论（emergentism）：civilization = N 个 agent 的统计涌现 | 实体论（substantivism）：集体是 over-and-above 的真实实体 |
| 决策机制 | 每个 agent 独立决策 | 集体通过 super-head / aggregation function 决策 |
| 是否有统一信念/欲望 | 否（只有 mutual belief） | 是（group belief、group desire） |
| 计算实现 | 主流（Mesa、Project Sid、Smallville 全是这种） | 极少（HMAS 有，但不在叙事领域） |

**关键观察**：哲学有完整的"集体 agent"理论（List & Pettit 是金标准），MAS 有 Holonic 这一支线，但**两者从未在"叙事生成/世界模拟"场景下结合实施**。

---

## §4. 集体 agent 的独特行为模式（从 Holonic MAS 和 List & Pettit 提炼）

1. **集体决策机制**：通过 aggregation function（投票、加权、阈值）将成员偏好聚合为单一决策——Searle 1990 强调"集体意图不可还原为个体意图之和"
2. **集体记忆与人格**：group 有独立于成员的 belief store（如"罗马帝国的集体意志"是实体，不是 N 个公民的统计）
3. **成员可替换性**：罗马帝国不因某个公民死亡而消失——集体 agent 的 persistence 不依赖单个成员
4. **集体行动的痕迹**：faction 留下的不是个人行动，是"组织痕迹"（法令、税册、纪念碑、外交照会）
5. **内外双视角**：Hindriks 的 status account——集体 agent 有 internal perspective（成员怎么看）和 external perspective（其他 agent 怎么对待它）

**关键学到**：如果 thesis 1 要做集体 agent，关键设计是"集体信念 + 集体决策聚合 + 集体行动痕迹"，而不是"faction 内部有 100 个 sub-agent"。

---

## §5. 对 thesis 1 的建议

### 结论：集体 agent **值得**作为 thesis 1 的核心，但论证需要重构

**重构后的差异化论证**（替换原 positioning doc 的"完全空白"）：

> "集体 agent 在哲学有完整理论（List & Pettit 2011, Searle 1990），在 MAS 有 Holonic 分支（Gerber 1999），在 game AI 有 faction state machine（Civ / Total War），在叙事生成有 TTRPG 设计 tip（Gnome Stew）。但**没有任何工作在叙事生成/世界模拟场景下把 faction/civilization 实现为具有集体信念、集体决策聚合、集体行动痕迹的单一 agent**。"

### 为什么这个空白值得做（防御 thesis 2 的教训）

1. **不是 baseline 能解决**：baseline（Project Sid / Smallville）是 individual 聚合，**涌现出的 civilization 是统计现象，不是叙事主体**——无法回答"罗马帝国作为主角在做什么决策"
2. **有清晰判别**：当我们要写"教会作为统一力量推动某种叙事"时，individual agent 涌现会失败（每个 NPC 各自决策，"教会"作为实体没有 agency）
3. **最小可证伪假设**：写一个章节，让"教会"作为集体 agent 做一次决策；用 baseline（N 个 NPC 各自决策再统计）对照；如果 baseline 能产生等效叙事，集体 agent 是过度设计

### thesis 1 的支撑度评估

如果集体 agent 因后续验证失败被砍掉，thesis 1 剩余 3 类：
- **人物 agent**：标准，不算 thesis 贡献
- **世界意志 agent**（命运/历史规律作为 agent）：少见，但不算空白（drama manager 类似）
- **规律执行者 agent**（物理/经济/法律作为 agent）：概念性新，但没有具体竞品验证

**判断**：剩余 3 类**勉强**够 thesis，但**集体 agent 是最强差异化点**——建议保留并加严验证（学 thesis 2 教训，先做最小可证伪再扩）。

---

## §6. 立即行动建议

1. **修正 positioning doc**：把"集体 agent 完全空白"改为"集体 agent 在哲学有理论、MAS 有 Holonic、game AI 有 faction state machine，但**叙事/世界模拟场景下从未作为单一 agent 实现**"
2. **设计最小验证**：写一章让"集体 agent"决策，对照"individual 聚合"baseline——如果差异显著（叙事可读性、决策合理性），集体 agent 站住；如果不显著，砍掉
3. **借鉴 Holonic MAS 设计**：super-holon 的 super-head / aggregation function / 递归结构可直接借用
4. **借鉴 List & Pettit 三条件**：representation + attitude + action 作为"集体 agent"的形式定义

---

## §7. 关键对比：thesis 1 集体 agent vs thesis 2 bitemporal

| 维度 | thesis 2（bitemporal） | thesis 1（集体 agent） |
|------|----------------------|----------------------|
| 文献空白 | 真空白（三社区从未相遇） | 结构性空白（理论有、叙事场景无） |
| baseline 能否替代？ | **能**（predicate 够用）→ 过度设计 | **不能**（individual 聚合无法表达集体主体性）→ **有真实价值** |
| 通过 baseline 测试？ | ✗ 失败 | ✓ 初步通过 |
| 命运 | **被证伪** | **值得推进，但需最小验证** |

**核心差异**：thesis 2 的 baseline 能解决它想解决的问题；thesis 1 集体 agent 的 baseline 不能。这是 thesis 1 比 thesis 2 强的根本原因。
