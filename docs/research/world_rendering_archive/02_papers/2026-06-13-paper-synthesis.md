# 5 篇论文精读汇总 → 设计输入对照表

**日期**: 2026-06-13
**任务**: 完成 positioning doc §9 选项 C（论文深读）后的综合
**状态**: 论文精读完成，待选下一步（推荐 A：V16 验证 bitemporal）

**精读论文**（比 positioning doc 必读 3 篇多 2 篇补充）:
1. Park et al. 2023 — Generative Agents (arXiv 2304.03442) — trace 基础 + agent 内架构
2. Riedl & Young 2010 — Narrative Planning: Balancing Plot and Character (JAIR) — fabula 形式化（注：原标题不是 "of Suspense"）
3. Martin Fowler — Bitemporal History + Event Sourcing（两篇合一）— trace 工程地基
4. Mark J.P. Wolf — Building Imaginary Worlds（三支柱理论）— 验证层评估底座
5. Michael Mateas PhD — Facade / Drama Manager (CMU-CS-02-206) — thesis 1 工程原型

5 份笔记原文在 session 9692d31b 的 agent 返回中，需要时可重新派 agent 拉取（论文 URL 见 positioning doc §7-§8）。

---

## §1. 5 篇笔记精华

### Park 2023（Generative Agents）
25 个 LLM agent 在 Smallville 沙盘自主生活两天。memory stream + reflection + planning 三件套驱动。
- **直接 adopt**：memory schema（description/created_ts/last_access/importance 1-10/embedding/type/evidence_ptrs）、retrieval 三权重（α·recency `0.995^hours` + β·importance LLM 评分 + γ·relevance cosine，归一化后 α=β=γ=1）、reflection 触发（最近 100 条 importance 累加 > 150）、planning day→hour→5-15min 三层递归、Appendix B 25 题访谈骨架。
- **空白**：无世界级 trace（memory 全在 agent 内）；无异质 agent（只 character 类）；无 bitemporal（memory 一旦写入立即可见）；无世界树。
- **反例**：instruction tuning 让 agent 过度合作（Isabella 接受所有建议）；memory hacking（精心构造的对话能说服 agent 相信从未发生的事）；25 agent × 2 天 = 数千美元。

### Riedl 2010（IPOCL）
**论文标题实际是 "Narrative Planning: Balancing Plot and Character"**——不形式化 suspense，反而在 §6 坦白 suspense 需要 fabula/sjuzhet 联合推理。实际贡献是 IPOCL 算法。
- **关键学术先例**：§2.1 显式采用 Bal(1998) fabula/sjuzhet 二分，假设 sjuzhet 可由 fabula 独立生成。**§6 limitation 主动承认**："to achieve more sophisticated effects such as suspense, one might have to consider how a narrative can be told while the generator is determining what should be told"——**论文主动让出的研究空白正是 thesis 2**。
- **直接 adopt**：STRIPS-like action schema（actors/happening/constraints/precondition/effect）、**frame of commitment**（⟨S', a, g_a, s_f, motivating_step⟩——几乎完全等同我们的"目的驱动收敛"）、三类 flaw detector（open condition / open motivation / intent）、author goal vs character goal 解耦、`intends(a, g)` 元谓词。
- **反例**：纯 backward planner 复杂度 O(c·(b·(e+1)^a)^n)，Aladdin 域单 narrative 12.3 小时（GC 占 11.6h）；角色不能失败（backward planner 剪失败分支）；author 必须预指定 outcome。

### Fowler（Bitemporal + Event Sourcing）
软件工程成熟成果，提供 trace 的工程地基。
- **双时间轴 event schema**：`(record_date, actual_date, action, value)`——actual_time = 事件为真的时间，record_time = 记录何时写入。
- **append-only record history**：actual history 可回填，但 record history 始终 append-only。不"修改"过去，"追加新记录"覆盖认知。
- **fold/reduce 重建**：从空状态逐条 apply event 重建任意时刻状态。`fold(events, upto_record_time, upto_valid_time) -> World`。
- **snapshot 缓存**：存"隔夜 snapshot"，重启用 `snapshot + 增量 events`。并行生成不阻塞。
- **as-of 查询**：`salaryAt(actualDate, recordDate)` 四种组合——渲染端最常用 `(valid_time=故事内时刻, record_time=第N章)`。
- **关键原创空白**：Fowler 的 record_time 是**物理时间戳**（`DateTime.Now`），我们的 transaction_time 是**叙事章号揭示序**（可重排、可延迟、多渲染端各异）。**这个语义桥接是文献空白，是 thesis 2 的核心创新**。
- **trace = bitemporal event**—— Fowler 文末明确："要让 event sourcing 支持 bitemporal，event 本身必须 bitemporal"。
- **反例**：不要让 record_time = transaction_time 物理对齐（致命错误）；不要给渲染端写权限（Gateway isActive=false 模式）；event 必须 delta 风格而非 absolute。

### Wolf（Building Imaginary Worlds）
世界构建的理论框架，提供验证层评估底座。
- **三支柱** Invention（独特性，偏离 Primary World 的程度）/ Completeness（完整度，9 infrastructure 覆盖率 × 互联度）/ Consistency（一致性，内部无矛盾）——对应受众体验 Immersion / Absorption / Saturation。
- **Secondary Belief**（不是 suspension of disbelief，是真正相信二级世界）——Consistency 的目标是触发它。一旦触发，fans 会"work quite hard at explaining away inconsistencies"。
- **9 infrastructures**：maps / timelines / genealogies / nature / culture / language / mythology / philosophy / narrative——completeness 的扫描矩阵。
- **World Gestalten**（ellipsis + logic + extrapolation）——"结构暗示世界存在，受众自动补完"。**Gap 不是 bug，是正面属性**——让世界显得比实际更完整。
- **default + override 模型**：Secondary World 继承 Primary World 全部 default，除作者显式 override 部分。Invention = override 集合的熵。
- **范式冲突**：Wolf 把矛盾当 bug 要最小化；我们当生成动力。**反转合法性**：Wolf 自己承认矛盾可被消化（fans explain away）。**反转边界**：L1 宪法层必须 Consistency（Secondary Belief 底线）；L2/L3 层矛盾是燃料。
- **agent 访谈 15 题模板** + **三支柱可计算分数公式**（详见 agent 笔记）。

### Mateas（Facade / Drama Manager）
drama manager 的第一个工程完整实例。
- **Facade 三层**：drama manager（按 value arc 选 beat）+ beat（一等架构实体，承载声明+过程知识）+ believable agents（ABL reactive planning）。
- **直接 adopt**：beat schema 7 字段（preconditions/priority_tests/weight_tests/effects/select_action/succeed_action/abort_action/beat_variables）、value-arc scoring 算法（`score = 1/e^|slope_n+1 - deltaX_beat|`）、story memory 作为 trace 存储层、ABL joint goal entry/exit negotiation（character-character 协调协议）、priority/specificity/weight 三档非确定性选择、conflict 表 + 行为挂起、**drama manager ↔ character 通过 story memory 弱通信（不是 RPC）**。
- **关键发现**：drama manager 是"**无目的平衡器**"——Facade 终止 = beat 池空，不是某 agent 实现目的。我们的"**目的驱动收敛**"是关键扩展：world-will agent 持 purpose_predicates，达成即 freeze_world()。
- **规律执行者**：Facade 把规则嵌入 beat 内 reaction context；我们抽出独立 agent 跨 beat 持续运行——这是原创。
- **集体 agent**：完全空白。Facade 只有 2 character + 1 player。
- **反例**：beat 数量爆炸（Facade ~30 beats 覆盖 5 分钟，百章级手写不可行）；flat drama manager（必须 hierarchical，Mateas 自己在 Future Work 说未做）；单一线性 story value space（Facade 只有 tension+affinity 两个 value，我们要几十条悬念线）。

---

## §2. 设计输入汇总（按 6 概念组织）

### 概念 1：痕迹（trace）
- **论文给**：Fowler 双时间轴 event + fold + snapshot + as-of；Riedl STRIPS effect；Park memory_stream；Mateas beat effects。
- **我们扩**：trace 是**世界级**（不是 agent 私有 memory）；transaction_time 是**叙事章号**（不是物理时间）；trace 必须含 constraint_check 结果 + 链式 hash（防 memory hacking）。

### 概念 2：异质 agent 生态（4 类）
- **论文给**：Mateas drama manager（世界意志原型）+ believable agent（人物）+ player avatar = 3 类；Riedl actors 字段 + character vs happening 二分；Wolf circles of authorship 5 层。
- **我们扩**：4 类（人物/世界意志/规律执行者/集体）——**集体 agent 完全空白**；规律执行者独立 agent（Facade 嵌入 beat，我们抽出跨 beat）；世界意志从"无目的平衡器"升级为"有目的推动者"（持 purpose_predicates）。

### 概念 3：矛盾即基石
- **论文给**：Wolf fans explain away（合法性）；Riedl open motivation flaw（矛盾生成最小单元）；Mateas priority/weight + beat abort + value arc 软回归（矛盾消化机制）。
- **我们扩（范式反转）**：Wolf 当 bug 修，我们当 feature 累积。**反转边界**：L1 宪法层必须 Consistency；L2/L3 矛盾是燃料。矛盾分类学：良性（击穿 agent 间 Secondary Belief 但不击穿 L1）vs 恶性（击穿 L1）。

### 概念 4：目的驱动收敛
- **论文给**：Riedl frame of commitment 的 final step 执行 ≈ 我们的冻结信号（**几乎完全重合，直接 adopt**）；Mateas drama manager 终止条件（但 Facade 是 beat 池空）；Wolf catalysts of speculation。
- **我们扩**：frame 是单 agent 单目的；我们是**多 agent 多目的并发收敛**。收敛三分：某 agent 实现目的 / 某层约束被打破 / 张力达阈值。

### 概念 5：世界树（git for worlds）
- **论文给**：Fowler snapshot + event log = DAG 雏形 + event replay = git checkout；Wolf retcon/reboot/multiverse（现象，无结构）。
- **我们扩**：完整 DAG 数据结构（commit/checkout/branch/merge/diff/cherry-pick）；异质 agent 各有自己的 record_time 视角（Fowler perspective 扩展）；渲染端 = sjuzhet 投影器（Fowler isActive=false 的 replay 模式）。

### 概念 6：agent 访谈验证
- **论文给**：Wolf 三支柱 + 9 infrastructures（评估底座）；Park 25 题访谈骨架；Riedl QUEST（但访谈读者不是 agent）。
- **我们扩**：访谈对象是**世界内 agent**（不是读者/外部观察者）；访谈答案 → 三支柱可计算分数；双盲访谈（多 agent 对同一问题答案差异是核心信号）。

---

## §3. 原创空白确认表（更新版）

| 原创点 | 论文重合度 | 空白确认（基于 5 篇精读） |
|--------|-----------|---------|
| **transaction_time 叙事化** | **空白** | Fowler record_time 是物理时间；Riedl §6 承认 fabula/sjuzhet 解耦做不了 suspense。**thesis 2 核心，5 篇均未触及叙事化语义** |
| **异质 agent（4 类）** | 极少重合 | Mateas 3 类（无集体）；Riedl 2 类（character vs happening）；Wolf 5 层作者（不是世界内 agent）。**thesis 1 核心** |
| **集体 agent（faction/civilization）** | **完全空白** | 5 篇均未触及集体行动建模 |
| **世界树 DAG** | 极少重合 | Fowler 给 snapshot 但无 DAG 操作；Wolf 列现象无结构 |
| **矛盾作为永久结构** | 部分重合 | Wolf 当 bug；Riedl 当 flaw 修；我们反转当燃料（**有边界：L1 必须 Consistency**） |
| **目的驱动收敛（多 agent 并发）** | 部分重合 | Riedl frame of commitment 是单 agent 单目的；我们多 agent 并发 |
| **trace 世界级** | 部分重合 | Fowler event sourcing 是单系统；Park memory 是 agent 私有；我们世界级共享 + bitemporal + constraint_check |
| **agent 访谈验证丰满度** | 重合 | Wolf 三支柱 + Park 25 题；但访谈世界内 agent 是挪了一步 |

---

## §4. 反例与坑汇总（5 篇揭示的设计陷阱）

1. **memory hacking**（Park §8.2）——精心构造的对话能说服 agent 相信从未发生的事。**对策**：trace 必须 commit-signed（链式 hash）；reflection 写入要校验 evidence_ptrs 真实存在。
2. **instruction tuning 让 agent 过度合作**（Park §7.2）——Isabella 接受所有建议，失去自我。**对策**：character agent 必须配对抗性的意志 agent 或独立目的函数。
3. **物理规范难用 NL 表达**（Park §7.2）——"dorm bathroom 只能一人"被误读为多人。**对策**：hard constraint 编码进 law enforcer agent，不靠 NL 描述。
4. **纯 backward planner 复杂度爆炸**（Riedl §4.5）——IPOCL 12.3 小时/narrative。**对策**：必须 forward simulation + 异质 agent 各自跑。
5. **角色不能失败**（Riedl §6）——backward planner 剪失败分支。**对策**：forward simulation 天然支持 try-fail-try-succeed。
6. **author 必须预指定 outcome**（Riedl §4.6）——planner 无 goal 时生成无意义 narrative。**对策**：用 agent-level goal 代替 author-level goal。
7. **beat 数量爆炸**（Mateas）——Facade ~30 beats 覆盖 5 分钟，百章级手写不可行。**对策**：LLM 在线生成 beat（case-based generation）。
8. **flat drama manager**（Mateas Future Work）——所有决策在 beat 选择层，无 scene/act/volume 层级。**对策**：hierarchical drama manager（多尺度）。
9. **record_time 物理对齐是致命错误**（Fowler）——我们的创新就在于两轴解耦。**对策**：transaction_time 不由系统时钟盖戳，由渲染端分配。
10. **渲染端不能有写权限**（Fowler Gateway isActive 模式）——渲染时 isActive=false，副作用全部 noop。**对策**：渲染端只能投影 sjuzhet，不能改 fabula。
11. **event 必须 delta 风格而非 absolute**（Fowler）——否则 reversal 退化为完全重建。**对策**：state_delta 字段存差分。
12. **L1 宪法层不能容忍矛盾**（Wolf Secondary Belief 底线）——反转"矛盾即基石"有边界。**对策**：L1 硬约束；L2/L3 才允许矛盾累积。

---

## §5. trace schema 统一草案（合并 5 篇设计输入）

```python
@dataclass(frozen=True)
class Trace:
    # 标识与完整性
    id: str
    prev_hash: str                  # 链式完整性（防 Park memory hacking）
    hash: str                       # 本条 trace 的 hash

    # 双时间轴（thesis 2 核心 —— Fowler 直接 adopt，但 transaction_time 语义改写）
    valid_time: int                 # fabula time（故事内时刻 / 世界时钟）
    transaction_time: int           # sjuzhet time（叙事章号，渲染端分配，**非物理时钟！**）

    # 来源 agent（thesis 1 —— Riedl actors 扩展为 4 类）
    agent_id: str
    agent_type: Literal["character", "will", "law_enforcer", "faction"]
    actors: list[str]               # 哪些 agent 有意图（character 才非空）
    is_happening: bool              # Riedl happening 标记（true = 偶发，无需意图归属）

    # 动作（Riedl STRIPS + Mateas beat）
    action_type: str                # speak|move|reveal|enforce|riot|decide...
    payload: dict                   # 动作参数

    # 状态增量（Fowler delta 风格 + Riedl effect）
    preconditions: list[Proposition]
    state_delta: StateDelta         # {"set": {...}, "unset": [...]}，支持 reversal
    effects: list[Proposition]      # 可含 intends(a, g) 元谓词

    # 约束校验（law enforcer —— Wolf 分层 + 我们扩展）
    constraint_check: ConstraintResult  # {ok: bool, violated: [], layer: "L1"|"L2"|"L3"}

    # Park memory 字段（agent 内视角 + retrieval）
    importance: int                 # 1-10，LLM 评分
    embedding: list[float]          # retrieval 用
    last_access_ts: datetime        # recency 计算
    evidence_ptrs: list[str]        # reflection 用，指向被合成的 trace

    # Riedl frame of commitment（目的驱动收敛）
    frame_id: str | None            # 属于哪个 frame of commitment
    is_final_step: bool             # 是否达成 frame 的 internal_goal（→ 触发冻结判定）

    # 世界树（git for worlds）
    world_snapshot_id: str          # 属于哪个世界快照分支
    revealed_by_renderers: list[str] # 哪些渲染端已揭示此 trace
```

**6 条关键设计断言**：
1. `transaction_time` **不由系统时钟盖戳**，由渲染端分配（thesis 2 核心，区别于 Fowler）。
2. `state_delta` 必须 delta 风格（Fowler 教训）。
3. `constraint_check` 必须区分 L1/L2/L3（Wolf 底线 + 我们的分层矛盾处理）。
4. trace 链式 hash（防 Park memory hacking）。
5. `frame_id` + `is_final_step`（Riedl 目的驱动收敛的落地）。
6. `agent_type` 4 类（thesis 1，区别于 Mateas 3 类 / Riedl 2 类）。

---

## §6. 下一步建议

基于 5 篇笔记的发现，重新评估 A/B/D：

### 推荐：A（用 V16 验证 bitemporal）

**理由**：
1. thesis 2 的理论已清晰——transaction_time 叙事化是文献空白，Riedl §6 主动让出。
2. trace schema 已有草案（§5），不必先做 D。
3. 但理论是否成立需要**现实数据检验**——V16（ch216-227）是绝佳测试用例：
   - 8+ 角色多视角切换（拾/舟/韩峥/陆/灰衣/T-1/古神/建造者）
   - V16 爆发 97 处代词错误（拾×61 + 舟×36）——这本质是 **sjuzhet 投影混乱**（不同 POV 章节性别混淆），正是 bitemporal 该解决的
   - 倒叙/伏笔/POV 知识分布是 bitemporal 的核心测试场景
4. 验证方法：手动把 V16 12 章的双时态建出来（fabula 时间序 + sjuzhet 揭示序），看能否表达：
   - POV 切换时知识分布（韩峥 ch218 知道什么 vs 陆 ch220 知道什么）
   - 伏笔回填（ch5 为真的事件 ch50 才揭示）
   - 倒叙（sjuzhet 早于 fabula）
5. 如果能表达 → thesis 2 成立，推进到 D 实施。
6. 如果不能 → 暴露具体哪些场景需要扩展（更宝贵的信息）。

### D（设计 trace 数据结构）现已被预先解决一半
- Fowler SQL schema + fold 算法已在笔记中。
- §5 已合并 5 篇的统一草案。
- 待 A 验证后定稿（V16 实战会暴露需要调整的字段）。

### B（异质 agent 架构）
- Mateas 笔记已给出 4 类 agent 分层协议 + 通信规则。
- 但需要 trace schema 定型后才能 spec agent 留什么痕迹。
- 等 A 验证 + D 定稿后再做。

---

## §7. 关键决策记录（追加到 positioning doc §10）

- **2026-06-13**: 5 篇论文精读完成（3 必读 + 2 补充）。
- **2026-06-13**: thesis 2 获得 Riedl 2010 学术先例——§6 主动承认 fabula/sjuzhet 解耦做不了 suspense，让出研究空白。
- **2026-06-13**: thesis 2 核心空白定位——transaction_time 从物理时间（Fowler）升级为叙事章号揭示序（我们）。
- **2026-06-13**: "目的驱动收敛"被发现等同于 Riedl frame of commitment——直接 adopt，不必自创。
- **2026-06-13**: "矛盾即基石"获得 Wolf 合法性（fans explain away inconsistencies）+ 边界（L1 必须 Consistency，L2/L3 矛盾是燃料）。
- **2026-06-13**: trace schema 统一草案完成（§5），待 V16 验证后定稿。
- **2026-06-13**: 12 条反例与坑汇总（§4），作为后续设计的避坑指南。
