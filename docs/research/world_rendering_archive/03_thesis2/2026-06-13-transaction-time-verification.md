# transaction_time 查证报告 — thesis 2 的修正与重新定位

**日期**: 2026-06-13
**任务**: 回应用户对"叙事章号揭示序"的质疑（章节范围/关联性/切片完整性）
**方法**: 派 2 个 agent 并行查证（先例查证 + 章节问题查证）
**结论**: **thesis 2 站得住，但必须修正**——transaction_time 从离散章号改为连续叙事行进距离/event-interval，核心价值重新定位为 reader/agent belief 双时态追踪

---

## §1. 双 agent 查证结论汇合（强证据）

两份报告从不同视角**独立得出相同结论**：放弃离散章号，用连续/interval。

| Agent | 视角 | 查证问题 | 结论 |
|-------|------|---------|------|
| A（先例查证） | 文献有没有人做过 bitemporal narrative | thesis 2 是真空白还是伪需求 | 用 **event-interval** 替代 chapter-stamp → "interval-based bitemporal" |
| B（章节问题查证） | 章节作为时间单位的问题 | 用户的三个问题（范围/关联/切片） | 用 **连续叙事行进距离** 替代章号 → "continuous bitemporal" |

**两个不同视角（先例 + 问题）独立指向同一解法**——这是强证据，不是单一来源的偏见。

---

## §2. 用户的三个问题：文献回答

### 问题 1：章节的范围如何定义？
**文献共识：章节是"结构容器"，不是稳定叙事单位。**

多个来源独立印证：
> "A scene is a unit of story. A chapter is a structural container." — [April Davila](https://aprildavila.com/scene-chapter-or-both/)
> "The chapter is NOT the structural unit of a story — the scene is. Chapters can begin mid-scene." — [Nanci Panuccio](https://nancipanuccio.com/280-chapters-vs-scenes-what-most-writers-get-wrong/)

**结论**：章节是出版/装订单位，边界由作者商业/节奏判断决定（悬念钩、阅读体验、字数控制），**不是叙事内部时间逻辑的自然产物**。

### 问题 2：章节关联性如何保证？
**文献分两层处理**：
- **fabula 层**（事件序）：Allen 时间代数（before/after/overlaps/contains 等 13 种关系）
- **discourse 层**（揭示序）：Genette 的 order/duration/frequency 表达 anachrony

[Gervás & López Calle (Text2Story 2024)](https://ceur-ws.org/Vol-3671/paper6.pdf) 的 "action unit" 模型精确捕捉：每个 action unit 携带 (Universe, Narrative Level, Mode, Relative Order via Allen)。

**结论**："ch5 埋伏笔 → ch50 揭示"本质上不是 ch5 和 ch50 的关联，**而是两个 action unit 通过 Allen 关系 + 叙事层级建立的关联——章号只是这个关联在文本流中的投影坐标**。

### 问题 3：切片能确保完整吗？
**章号切片会切在叙事单元中间。**

[Yeager "Time Maps"](https://kb.osu.edu/bitstreams/92f30cca-c9fc-4bff-afaa-1a63b504a8be/download) 给出直接证据：
> "a single scene can correspond to multiple line segments by simultaneously portraying multiple moments in the fabula"

[Kearns 2020 narrative level annotation guidelines](https://ceur-ws.org/Vol-3671/paper6.pdf)：
> "changes may occur in the middle of a sentence and the new narrative level may carry on into another sentence, paragraph or even chapter"

**结论**：对比 valid_time 切片（某时刻世界状态确定），**章号切片在叙事单元内部完整性上没有对应确定性**。

---

## §3. 离散 vs 连续不对称的文献讨论（用户核心洞察的对应物）

**用户的洞察"两轴本质不对称"在文献中是被识别但被系统性回避的真实问题。**

### 经典叙事学明确承认不对称
- **Chatman 1978**：story-time 是 continuous underlying timeline，discourse-time 是 discrete and selective——通过 Genette 的 four ratios（scene/summary/stretch/ellipsis/pause）描述 discourse 如何对 story 做"采样"
- **Genette 1972**：order / duration / frequency 三维全是描述 story/discourse **不对称关系**——frequency 的 "singulative / repeating / iterative" 就是说"discourse 提到 N 次，story 发生 1 次"
- **Genette 自承 pseudo-duration**：discourse time 没有自然单位，只能用文本长度（行/页）"伪测量"——这正是用户说的"粒度 arbitrary"

### 计算叙事学系统性回避
- 搜索 `"narrative time" granularity discrete chapter scene` 在英文文献中**几乎没有专门讨论**
- **没有一篇把"discourse time 用章/scene 离散化"作为已知问题列出**
- VNPA 在哲学层承认 "parallel architecture"，但计算实现里 Event Structure 仍是 HTN plan（离散 action），Narrative Structure 嵌在 decomposition method 里（也是离散 task）——**两轴都离散了，没意识到 valid_time 应该连续**

### Yeager 2020 的反转（关键发现）
**Yeager 论证 Genette 把 syuzhet 当成"文本长度"是错误**：
> "syuzhet is not a physical length, but an abstract span of time... In novels, page numbers serve as a rough proxy for this timeline — this was the source of Genette's confusion."

**Yeager 的解决方案：把 syuzhet 也视为连续时间轴**（用读者/观众穿越叙事的"行进时间"度量），fabula 在 y 轴、syuzhet 在 x 轴，NC 的斜率 = 叙事速度。**这就消解了 valid/discourse 的不对称——两者都是连续时间。**

### "Telling Time" (Poetics Today 2024) 进一步区分两层 discourse
- **text order**：读者穿越叙事的旅程（连续）
- **telling order**：虚构叙述者讲述行为的时长（连续）
- **两层都是连续的，没有任何一层是"章号"这种离散单位**

---

## §4. thesis 2 修正方案

| 维度 | 原方案（有问题） | 修正方案 |
|------|----------------|---------|
| transaction_time 单位 | 章号（离散） | **连续叙事行进距离** 或 **event-interval** |
| transaction_time 语义 | "第几章揭示" | "读者/agent 在叙事行进到某点时的 belief 状态" |
| 核心价值 | "揭示序"（有缺陷） | **reader/agent belief 双时态追踪** |
| killer query | "ch50 揭示了什么" | **"在叙事行进到 ch218 对应位置时，韩峥知道什么？"** |
| 与现有概念对接 | 平行 | **与"agent 访谈验证"完美融合**——访谈本质就是 belief 查询 |

### 修正后的 trace schema（interval-based bitemporal）

```python
@dataclass(frozen=True)
class Trace:
    id: str
    prev_hash: str
    hash: str

    # 双时间轴（修正后：都是 interval，不是离散章号）
    valid_time: TimeInterval          # 故事内时间区间（fabula）
    transaction_time: TimeInterval    # 叙事行进距离区间（sjuzhet，连续坐标）
    # TimeInterval = (start: float, end: float)，归一化到 [0, 1] 或绝对叙事行进距离

    # 来源 agent（thesis 1）
    agent_id: str
    agent_type: Literal["character", "will", "law_enforcer", "faction"]

    # 动作 + 状态增量（不变）
    action_type: str
    payload: dict
    state_delta: StateDelta

    # 约束校验（不变）
    constraint_check: ConstraintResult

    # reader-belief tracking（新增，thesis 2 修正后的核心）
    revealed_to: list[str]            # 哪些 agent/reader 视角已知此 trace
    belief_impact: dict               # 对 reader-belief 的影响
```

**关键变化**：
1. `valid_time` 和 `transaction_time` 都是 **TimeInterval**（区间），不是离散整数
2. 章号只作为 **human-readable label** / **chunk_id**，不作为时间戳
3. 新增 `revealed_to` + `belief_impact`，把 reader/agent belief tracking 显式化

---

## §5. thesis 2 的真正价值（重新定位）

**原定位（有问题）**：用章号做 transaction_time，"第几章揭示"——这有问题（用户的三个质疑）。

**修正后定位**：**reader/agent belief 的双时态追踪**——这是 bitemporal 在叙事里的杀手应用。

### Killer Query（thesis 2 的核心价值证明）

> "在叙事行进到第 K 章对应位置时，agent X 知道什么？"

这个查询：
- 用 fabula 单时间轴 + predicate 也能做（agent_knows(X, event_id)），但需要额外维护 belief 状态
- 用 bitemporal 自然成立：as-of transaction_time=K 的所有 trace 中，revealed_to 包含 X 的子集
- **与"agent 访谈验证"概念完美对接**——访谈本质就是 belief 查询

### Chatman 的 "repeating frequency" 测试（不对称验证）

故意构造一个"同一 fabula 事件在多章反复暗示"的场景（Genette 的 repeating frequency）：
- 离散章号无法表达"valid_time 固定 / transaction_time 多区间"
- interval-based bitemporal 能优雅表达（transaction_time 是区间列表）

这是离散模型无法表达、连续模型天然支持的结构——**thesis 2 修正版的差异化证据**。

---

## §6. 关键差异化（vs 现有工作）

| 现有工作 | 它们怎么做 | 我们的差异 |
|---------|-----------|-----------|
| **BiPOCL (Winer & Young 2016)** | 两个独立 plan（story plan + discourse plan），通过 requirement binding | **single-trace 双时间戳**——同一个 event 在同一个 trace 里同时有 valid_time 和 transaction_time |
| **VNPA (Martens 2020)** | 声称 parallel，实现仍是 HTN plan + decomposition method metadata | **trace 数据结构原生支持双时间戳**，不需要 plan/syntax tree 双层包装 |
| **Tripartite Model (AAAI 2020)** | 三层独立（discourse / narration / story） | 我们合一进单一 trace |
| **Possible Worlds Belief (Shirvani)** | reader belief 嵌进 state-space，但仍是单一时间轴 | 我们用双时间轴，belief 是 transaction_time 的投影 |
| **数据库 bitemporal (Fowler)** | valid_time + transaction_time，但 transaction_time 是物理时钟 | 我们把 transaction_time 叙事化（叙事行进距离）|

**核心差异化**：**single-trace + bitemporal + 叙事化 transaction_time**——三者组合没人做过。

---

## §7. 已核验竞品：CEUR Vol-3290（Konle & Jannidis 2022）

**核验结论：情况 (a)——论文没做 bitemporal，thesis 2 差异化完全成立。**

**论文详情**：
- 作者：Leonard Konle, Fotis Jannidis（Würzburg 大学）
- 发表：CHR 2022 (Computational Humanities Research Conference)
- 领域：**CLS 叙事分析**（不是叙事生成），目标是用 temporal graph 算作品相似度

**为什么没威胁**：
1. **只有单时间轴**（scene sequence）——没有 valid_time，没有 transaction_time
2. **论文自己承认只能做 sjuzhet 层**（line 194-202）："we are not really talking about plot here, but rather about syuzhet, the plot as it is narrated"——fabula 层留给 future work
3. **future work 建议是 bipartite graph（分层）**——与我们 single-trace 路线相反
4. **三个社区隔阂进一步证实**：叙事生成（Riedl）/ 数据库 bitemporal（Fowler）/ 叙事分析（Konle）互不重叠

**重叠度评估**：
| 我们的差异化 | 论文是否做了 | 重叠度 |
|------------|------------|--------|
| single-trace | 否（单层 scene 序列，scene 元数据 external） | 0% |
| bitemporal | 否（只有 scene sequence 单时间轴） | 0% |
| 叙事化 transaction_time | 否（连 transaction_time 都没有） | 0% |

**论文反而是好的"负向 Related Work"**——强化"三个社区从未相遇"论证。在 thesis 2 的 Related Work 章节：即使最 "graph-friendly" 的 CLS 工作，也没把双时间戳编码进同一 trace。

**可选补查**：Teneto 库（论文用的 temporal graph 库，脑科学领域）follower 是否扩展到 bitemporal——预期 No（脑科学不需要 as-of query），30 分钟可确认，堵 reviewer 攻击面。

---

## §8. 替代方案评估（Agent B 产出）

| 单位 | 粒度稳定性 | 边界清晰度 | 关联表达 | 切片完整性 | 适用性 |
|------|-----------|-----------|---------|-----------|--------|
| 章号 | 差（出版单位） | 差（人为） | 不能 | 差（切中间） | 低——只适合宏观索引 |
| scene 号 | 中 | 中 | 需额外机制 | 中 | 中——叙事学标准单位 |
| beat 号 | 好 | 好（Façade 形式化） | 好 | 好（最小完整单元） | 高——但需先拆解 |
| NC/事件序号 | 好 | 好（temporal operators） | 好（Allen 编码） | 好 | 高——学术金标 |
| **连续叙事时间** | 好（自然单位） | 好（坐标连续） | 优（二维平面） | 优（任意精度） | **最高——Yeager 方案，符合 bitemporal** |
| 段落/句子号 | 中 | 中 | 差 | 差 | 低 |

**推荐**：连续叙事时间（Yeager 方案）或 event-interval（Agent A 方案）——两者本质一致。

---

## §9. 下一步建议

### 立即必做
1. **核验 CEUR Vol-3290**（派 agent 拉全文）——决定 thesis 2 是否需要重新差异化
2. **修正 positioning doc 的 thesis 2**：章号 → 连续/interval；重新定位为 belief tracking

### 验证设计（修正后）
不再用 V16 测"bitemporal 能否表达"（这个测试设计有问题）。改测：
1. **Killer query**：在 ch218 对应的叙事行进位置，韩峥 belief 状态是什么？（as-of transaction_time 查询）
2. **不对称验证**：构造 repeating frequency 场景（同一 fabula 事件多章暗示），看 interval 能否表达而离散不能
3. **对比 baseline**：用 BiPOCL 风格的两 plan 分离实现同一查询，证明 single-trace 更优（如 O(N) vs O(N×M)）

### 工程基础（并行）
- 声明式工作台 SQLite/FastAPI 依然是底层依赖
- trace schema 改为 interval-based（§4）

---

## §10. 关键决策记录（追加）

- **2026-06-13**: 用户质疑 transaction_time（章号）——章节范围/关联/切片三个问题
- **2026-06-13**: 双 agent 查证独立得出相同结论：放弃离散章号，用连续/interval
- **2026-06-13**: 用户洞察被文献证实——Chatman 1978 论述不对称；Genette 识别 pseudo-duration；Yeager 2020 独立发现 syuzhet 应连续
- **2026-06-13**: thesis 2 修正——transaction_time 从章号改为连续叙事行进距离/event-interval
- **2026-06-13**: thesis 2 重新定位——核心价值是 reader/agent belief 双时态追踪（killer query），不是"揭示序"
- **2026-06-13**: 关键差异化确认——single-trace + bitemporal + 叙事化 transaction_time，三者组合无人做过
- **2026-06-13**: 待核验竞品——CEUR Vol-3290 "Modeling Plots as Temporal Graphs"
- **2026-06-13**: CEUR Vol-3290 核验完成——情况 (a)，论文没做 bitemporal。是 CLS 叙事分析（非生成），单时间轴 scene 序列，自承只能做 sjuzhet 层。thesis 2 三个差异化（single-trace / bitemporal / 叙事化 transaction_time）重叠度全部 0%，全部成立。论文反而强化"三个社区从未相遇"论证（叙事生成 / 数据库 bitemporal / 叙事分析）。

---

## 附录：完整参考文献

### 先例查证（Agent A）
- [Winer & Young 2016 "Discourse-Driven Narrative Generation with Bipartite Planning"](https://aclanthology.org/W16-6602.pdf)
- [Riedl & Young 2010 "Narrative Planning" (JAIR)](https://faculty.cc.gatech.edu/~riedl/pubs/jair.pdf)
- [AAAI 2020 "A Tripartite Plan-Based Model of Narrative"](https://cdn.aaai.org/ojs/12839/12839-52-16355-1-2-20201228.pdf)
- [Martens et al. 2020 VNPA](https://advancesincognitivesystems.github.io/acs/data/ACS2020_paper_40.pdf)
- [Shirvani, Ware & Farrell "Possible Worlds Belief Model"](https://ojs.aaai.org/index.php/AIIDE/article/view/12928/12776)
- [Chatman 1978 "Story and Discourse"](https://ia902900.us.archive.org/4/items/StoryAndDiscourseNarrativeStructureInFictionAndFilm/chatman.seymour_story.and.discourse_narrative.structure.in.fiction.and.film1.pdf)
- [Fowler "Bitemporal History"](https://martinfowler.com/articles/bitemporal-history.html)
- [Modeling Plots as Temporal Graphs (CEUR Vol-3290)](https://ceur-ws.org/Vol-3290/long_paper2313.pdf) — **待核验**
- [Winer et al. 2015 "Good Timing for Computational Models of Narrative Discourse"](https://drops.dagstuhl.de/storage/01oasics/oasics-vol045-cmn2015/OASIcs.CMN.2015.152/OASIcs.CMN.2015.152.pdf)

### 章节问题查证（Agent B）
- [Yeager 2020 "Time Maps" (Cultural Analytics)](https://kb.osu.edu/bitstreams/92f30cca-c9fc-4bff-afaa-1a63b504a8be/download) — **核心**，NC 单位 + syuzhet 连续
- [Gervás & López Calle 2024 (Text2Story)](https://ceur-ws.org/Vol-3671/paper6.pdf) — action unit + Allen 代数
- [Genette 1972 "Narrative Discourse"](https://15orient.com/files/genette-on-narrative-discourse.pdf)
- [NarrativeTime (LREC 2024)](https://aclanthology.org/2024.lrec-main.1054.pdf) — dense timeline，放弃离散
- [Jockers syuzhet R 包](https://www.matthewjockers.net/2015/02/02/syuzhet/) — 句子级
- [Mateas & Stern 2005 "Structuring Content in Façade"](https://users.soe.ucsc.edu/~michaelm/publications/mateas-aiide2005.pdf) — beat 形式化
- [GOLEM Ontology (MDPI 2025)](https://www.mdpi.com/2076-0787/14/10/193)
- ["Telling Time" (Poetics Today 2024)](https://read.dukeupress.edu/poetics-today/article/45/4/615/392767/)
- [TimeML (Pustejovsky 2003)](https://www.researchgate.net/publication/221441154_TimeML_Robust_Specification_of_Event_and_Temporal_Expressions_in_Text)
