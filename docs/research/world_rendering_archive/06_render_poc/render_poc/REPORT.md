# 渲染层 POC 报告 — 世界冻结→投影器验证

**日期**: 2026-06-13
**目标**: 验证"世界冻结后，渲染端只是投影器（isActive=false），无新 LLM 调用、无新误差"
**verdict**: **投影愿景成立** ⭐ —— 中场景 trace（130×2）成功投影成 HTML 视觉小说 + Ren'Py 脚本，全程零 LLM 调用。
**成本**: 开发 ~1 小时 / 运行 **零新 token**（本研究第一个零成本产出）

---

## §0. 一句话结论

trace 已落盘 = 世界已冻结。渲染端把冻结的 trace 投影成视觉小说，**不需要任何新 LLM 调用**——这验证了用户原始愿景"世界冻结→并行渲染天然成立"的工程基础。误差不累积的机制成立：生成阶段有误差，但 trace 一旦落盘就冻结，渲染阶段纯投影无新误差。

**关键副产物**：这个 POC 逼出了 trace 的最小 schema（=pilot 的 TRACE_SCHEMA），schema 已明确，为写端（agent 选择性召回）铺路。

---

## §1. 验证了什么

| 验证点 | 结果 |
|--------|------|
| **isActive=false 投影** | ✅ trace 落盘后，渲染纯投影，零 LLM 调用 |
| **fabula→sjuzhet 投影链** | ✅ trace（fabula）→ 视觉小说（sjuzhet）通 |
| **异质/同质同渲染器对比** | ✅ tab 切换即看两种配置演化差异 |
| **4 种声部分层呈现** | ✅ narrator(world_will) / collective(L2) / character(L1) / judge(law_enforcer) |

---

## §2. 产物清单（docs/research/render_poc/）

| 文件 | 说明 |
|------|------|
| `render_poc.py` | 投影器（~320 行 Python），输入 .output，输出 HTML + .rpy + event_log.json |
| `event_log.json` | 结构化中间产物（130×2 event），给后续写端召回用 |
| `seal_crisis_visual_novel.html` | 207KB 单文件视觉小说（零依赖，双击即看） |
| `seal_crisis_hetero.rpy` | Ren'Py 脚本（异质，303 行）|
| `seal_crisis_homo.rpy` | Ren'Py 脚本（同质，320 行）|

**本地预览**：`python -m http.server 8766 --directory docs/research/render_poc` → http://localhost:8766/seal_crisis_visual_novel.html

---

## §3. 投影规则

**tick 内排序**（叙事节奏）：
```
L3(世界意志) → L2(集体) → L1(角色) → cross_cut(规律执行者)
命运先显形 → 集体响应 → 角色行动 → 规则裁决
```

**4 种 render_role**（agent_type → 渲染声部）：
| agent_type | render_role | 渲染呈现 | 颜色 |
|-----------|-------------|---------|------|
| world_will | narrator | 全知旁白（命运描写）| 琥珀 #d4881f |
| collective | collective | 集体发言人（集体决议）| 蓝 #5a9fe8 |
| character | character | 角色台词 | 绿 #6cc06c |
| law_enforcer | judge | 裁决旁白 | 红 #d8504a |

**冲突投影**：`conflict_with` 非空 → action 后跟红色 ⚡ 标注块。

---

## §4. 验证证据

- **HTML console**：无错误
- **layer 分布核对**：L3×10 / L2×30 / L1×77 / cross_cut×13 = 130 ✓（与中场景报告吻合）
- **3 张截图**：
  1. 异质 L3 world_will（命运旁白，琥珀色，top_down）
  2. 异质 L2 穿越者小队（集体发言人，蓝色，bottom_up）
  3. 同质"联盟代表（个人）"自标 L3（赋能式修正后同质自主跨层——正是中场景报告的关键发现）
- **tab 切换**：异质↔同质即时切换，idx 重置

---

## §5. 关键发现

### 5.1 trace 已是结构化 JSON——schema 隐式存在

这是最重要的发现。原本担心要"解析 247k chars 非结构化文本"，实际 .output 的 `result.hetero_traces` 已经是结构化 JSON（每条带 tick/layer/agent_type/action/conflict_with/influence_direction）。

**含义**：pilot 阶段的 TRACE_SCHEMA 就是 event schema 的最小集。event log 在 pilot 里已经隐式存在——只是塞在 Workflow 返回值里，**没落盘成独立 event store**。这是写端要补的第一件事。

### 5.2 投影愿景成立——isActive=false 工程价值证实

世界冻结→渲染零 LLM 调用→视觉小说。这条链路通。这验证了用户 6 层原创思考里"痕迹=世界级 event sourcing"+"渲染端投影成小说正文"的工程可行性。

**这是本研究第一个零 token 成本的产出**——后续每次重渲染（换样式 / 换投影规则 / 多 POV）都不花 token。

### 5.3 异质/同质同渲染器对比——研究的对外展示层

tab 切换即看两种配置的演化差异。这比 16.4M token 的 trace 流直观 10 倍。未来说服别人"世界渲染"成立，一个可点击推进的视觉小说比报告有说服力得多。

### 5.4 投影揭示了同质的"个体声明"性质

同质第一条是"联盟代表（个人）"自标 L3。视觉小说里它和异质的 world_will（L3）呈现一样，但语义完全不同——一个是独立命运层实体，一个是 agent 自标。**投影器让这个差异可见**：同质没有 world_will 的琥珀色独立声部，它的"L3"是借绿色角色声部说出来的。

---

## §6. 数据质量问题（不阻塞，待修）

### 6.1 agent_id 不统一 → 同 speaker 多 Character

LLM 返回的 agent_id 字段不统一：
- `world_will` / `L3/world_will` / `L3_will_t0`（label 渗漏）
- `rule_enforcer` / `规律执行者 (Rule Enforcer)` / `cross_law_t0`

导致同一 speaker 被定义成多个 Ren'Py Character（c0/c15/c20...）。

**对策**：投影前加 speaker 规范化层（正则去 label 前缀 + 映射表归并中英文别名）。HTML 端用 collective_name/agent_id 做主键也有同样问题。

### 6.2 action 文本过长（200-500 字）

HTML 用滚动条解决；.rpy 截断到 220 字（Ren'Py 单行过长难看）。

**对策**：未来投影器可按句号/分号分段成多行对话，或做"摘要+展开"两段式。

### 6.3 默认 .output 路径含 8.3 短路径

`ADMINI~1` 在 Python pathlib 不解析。当前需传 `--input` 完整路径。待修：默认值改 `Administrator`，或自动探测最新 .output。

---

## §7. 局限（重要——这是读端验证，不是写端）

### 7.1 读端 ✅ / 写端 ❌

这个 POC 验证的是**读端（投影）**——证明渲染可行。**不解决写端**——agent 生成时如何用选择性记忆替代全量 prompt 注入。**扩大场景的瓶颈仍在写端**（O(N²) token 膨胀）。

### 7.2 trace 仍是 Workflow 返回值，非 append-only event store

pilot 的 trace 还是"对话历史塞进 prompt"，运行结束落到一个 .output 文件。不是真正的 event sourcing——没有 append-only log，没有 snapshot，没有 as-of 查询。**要做世界树（pause/edit/resume/branch）必须把 trace 落盘成独立 event store**。

### 7.3 投影是平铺的，非叙事重组

当前每条 trace → 一行，按 tick 顺序平铺。没有：
- 多 POV 切换（韩峥视角 vs 陆视角）
- 倒叙 / 伏笔（ch5 事件 ch50 才揭示）
- 省略（某些 trace 不给读者看）
- 摘要（多条 trace 合并成一段叙事）

这是 sjuzhet 投影的**最小版**。真正的 sjuzhet 投影器要支持"哪些 trace 在第 N 章揭示给读者"——这正是 thesis 2 被证伪的 transaction_time 语义降级到的"渲染端实现细节"。现在这个实现细节有了载体。

### 7.4 Ren'Py 未实跑

只生成 .rpy 脚本，没在 Ren'Py SDK 里实跑。HTML 已验证投影逻辑成立。Ren'Py 接入是**工程问题不是研究问题**——需要中文字体（NotoSansCJK / SourceHanSans）+ Ren'Py SDK 安装。HTML 已经达到 POC 验证目的。

---

## §8. 下一步（对接记忆 / event sourcing）

渲染 POC 逼出了 trace schema（=TRACE_SCHEMA）。schema 明确后，下一步该写端：

| 步骤 | 内容 | 解决什么 |
|------|------|---------|
| **1. trace 落盘 event store** | pilot 运行时每条 trace append 到 JSONL（不只是 Workflow 返回值）| 世界树基础 / replay |
| **2. agent 选择性召回** | 写端 agent 不再看全量 trace，query event store（按 layer/agent_id/tick/relevance）| **O(N²) 膨胀 / 扩大场景** |
| **3. 接 Mem0/Zep** | 给 event store 配召回引擎。Mem0 做 agent 内长期记忆，Zep context graph 做集体记忆可演化 | 集体记忆演化 |
| **4. 叙事投影器升级** | 当前平铺投影 → 支持多 POV / 倒叙 / 伏笔（哪些 trace 在第 N 章揭示）| sjuzhet 真正投影能力 |

**推荐顺序**：先做 1（trace 落盘 event store）——这是 2/3 的基础，且成本最低（改 pilot 脚本，让每条 trace 写 JSONL）。然后 2（选择性召回）解决扩大场景瓶颈。3/4 是增强。

---

## §9. 对 thesis 的影响

**不影响 thesis 1 的判定**（规模放大 + prompt 公平双验证成立）。这个 POC 是**工程基础设施验证**，证明"世界渲染"的渲染端愿景成立——世界冻结后可投影成视觉小说，零 token 成本。

**强化了用户的研究定位**：世界渲染 = 生成（异质 agent 演化）+ 冻结（event sourcing 落盘）+ 渲染（isActive=false 投影）。三段式中，本 POC 验证了第三段（渲染），第一段（生成）已由 thesis 1 验证，**第二段（冻结/event sourcing）是下一个要攻克的工程核心**。

---

## §10. 决策记录

- **2026-06-13**: 用户提问"agent 记忆如何处理，纯靠上下文吗" → 确认 pilot 是纯 prompt 滚动，O(N²) 膨胀
- **2026-06-13**: 用户提问"多 agent 外部记忆 / event sourcing / 可视化方案" → 调研业界（Mem0/Letta/Zep/LangGraph + deterministic replay + Ren'Py）
- **2026-06-13**: 用户确认"先做渲染 POC 再探索记忆/event sourcing"
- **2026-06-13**: render_poc.py 写成（~1h），生成 HTML + .rpy + event_log.json
- **2026-06-13**: HTML 验证通过（3 截图 + console 无错 + tab 切换正常）
- **2026-06-13**: verdict = 投影愿景成立，零 token 成本，schema 逼出
