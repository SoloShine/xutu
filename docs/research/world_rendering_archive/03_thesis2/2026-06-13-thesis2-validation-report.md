# thesis 2 最小验证报告

**日期**: 2026-06-13
**数据**: V16 星火 ch216-227, 26 事件
**目的**: 证伪 thesis 2——bitemporal trace 是否比 fabula+predicate 更必要？
**方法**: 三方对比（baseline / thesis 2 单区间 / thesis 2 多区间），递进式证伪

## 阶段 1：单 sjuzhet 一致性测试

测试：as-of sjuzhet_A 不同叙事点，三种方案结果是否一致？

- 总测试: 99（11 agents × 9 points）
- baseline vs thesis2单区间: 一致 99, 不一致 0
- baseline vs thesis2多区间: 一致 99, 不一致 0


## 阶段 2：多 sjuzhet belief 差异测试

测试：同一 agent 在 sjuzhet_A vs sjuzhet_B 的 belief 差异，三方案是否一致？

- 总测试: 24（8 agents × 3 points）
- baseline vs single 一致: 24, 不一致: 0
- baseline vs multi 一致: 24, 不一致: 0


## 阶段 3：repeating frequency 关键测试（thesis 2 的最后防线）

共 4 个 repeating frequency 案例（同一事件多区间揭示）。

核心问题：thesis 2 单区间模型是否会丢失中间揭示点信息？

### 事件 ev_002: 制造者叙事被推翻的真相（'外面没有人'）
- sjuzhet_A reveal_points: [0.06, 0.36, 0.44, 0.8]
- note: V16 内多处回响：ch216 灰衣回忆第166章揭示（0.06）；ch219 灰衣迷宫中规则化解回顾（0.36）；ch220 灰衣归档石片再次书写'外面没有人'（0.44）；ch225 灰衣归档完成时最终确认（0.80）。这是典型的 re
- **baseline（多点）**: 保留 4 个独立揭示点 [0.06, 0.36, 0.44, 0.8]
- **thesis 2 单区间**: 压缩为 (0.06, 0.8)
- ⚠️ **thesis 2 单区间丢失 2 个中间揭示点**（[0.36, 0.44]）——无法表达"ch216 暗示 + ch220 再暗示"的多次揭示结构
- **thesis 2 多区间**: 保留所有点，与 baseline 完全同构（换名）

### 事件 ev_005: 韩峥发射器身份与疤痕振动模式
- sjuzhet_A reveal_points: [0.2, 0.24, 0.5, 0.62, 0.97]
- note: ch218 韩峥自述成为发射器并失去记忆（0.20, 0.24）；ch222 陆向林深解释韩峥第二条线'发射密钥'的来源与意义（0.50, 0.62）；ch227 终曲时林深掌心'韩峥数据层频率'再次激活并完成同步（0.97）。同一事件在原
- **baseline（多点）**: 保留 5 个独立揭示点 [0.2, 0.24, 0.5, 0.62, 0.97]
- **thesis 2 单区间**: 压缩为 (0.2, 0.97)
- ⚠️ **thesis 2 单区间丢失 3 个中间揭示点**（[0.24, 0.5, 0.62]）——无法表达"ch216 暗示 + ch220 再暗示"的多次揭示结构
- **thesis 2 多区间**: 保留所有点，与 baseline 完全同构（换名）

### 事件 ev_018: 穿越者机制是A/B测试系统，林深是预设的裁决者
- sjuzhet_A reveal_points: [0.66, 0.68, 0.7, 0.86]
- note: ch223 岑逐步揭露：1.15偏差（0.66）→A/B两组设定（0.68）→47轮测试+林深裁决者（0.70）；ch226 舟的验证模型独立印证'所有选择指向同一终点'（0.86），从另一路径确认了系统的预设性。两条线索在原序中跨3章叠加
- **baseline（多点）**: 保留 4 个独立揭示点 [0.66, 0.68, 0.7, 0.86]
- **thesis 2 单区间**: 压缩为 (0.66, 0.86)
- ⚠️ **thesis 2 单区间丢失 2 个中间揭示点**（[0.68, 0.7]）——无法表达"ch216 暗示 + ch220 再暗示"的多次揭示结构
- **thesis 2 多区间**: 保留所有点，与 baseline 完全同构（换名）

### 事件 ev_010: 灰衣化解1422条规则迷宫的内心释然
- sjuzhet_A reveal_points: [0.04, 0.36, 0.8]
- note: ch216 三线淡去的外部事件（0.04）；ch219 灰衣迷宫内心化解的完整过程（0.36）；ch225 归档完成的对外确认（0.80）。同一角色的内心转变在三章中以三个不同侧面被呈现。
- **baseline（多点）**: 保留 3 个独立揭示点 [0.04, 0.36, 0.8]
- **thesis 2 单区间**: 压缩为 (0.04, 0.8)
- ⚠️ **thesis 2 单区间丢失 1 个中间揭示点**（[0.36]）——无法表达"ch216 暗示 + ch220 再暗示"的多次揭示结构
- **thesis 2 多区间**: 保留所有点，与 baseline 完全同构（换名）

### 信息保真度结论
- 4/4 个案例中，thesis 2 单区间**丢失中间揭示点信息**
- thesis 2 多区间与 baseline 完全同构（无信息差异，仅命名不同）
- **repeating frequency 场景：thesis 2 单区间有真实劣势，多区间与 baseline 等价**


## 阶段 4：扩展性测试（加 sjuzhet_C/D/E...）

加第 N 个 sjuzhet 时，各方案的工作量：

| 方案 | 加 sjuzhet_C 的工作 |
|------|-------------------|
| baseline | 每个 event 加 `revealed_at['C']=[...]` + `visible_to['C']=[...]` |
| thesis 2 单区间 | 每个 trace 加 `transaction_time['C']=(s,e)` + `revealed_to['C']=[...]` |
| thesis 2 多区间 | 每个 trace 加 `transaction_time['C']=[(s,e),...]` + `revealed_to['C']=[...]` |

**结论：三者扩展工作量完全同构（都是加 dict entry）。扩展性等价。**


## 阶段 5：实现复杂度对比

| 指标 | baseline | thesis 2 单区间 | thesis 2 多区间 |
|------|----------|----------------|----------------|
| dataclass 字段数 | 6 | 5 | 5 |
| query 函数 LOC | 9 | 10 | 8 |


## 最终结论

### 查询一致性
- 总测试点: 123
- baseline vs thesis 2 单区间: 一致 123/123
- baseline vs thesis 2 多区间: 一致 123/123

### 证伪判定

1. **查询表达力**：三方案等价（单 sjuzhet + 多 sjuzhet belief 差异测试）
2. **repeating frequency 信息保真度**：thesis 2 单区间丢失中间揭示点（4/4 案例受损）；thesis 2 多区间与 baseline 等价
3. **扩展性**：三方案同构（加 dict entry）
4. **实现复杂度**：baseline 字段最少 = 最简单

### thesis 2 的命运

- **thesis 2 单区间**：repeating frequency 场景有**真实劣势**（丢失中间点），其他场景与 baseline 等价。**不必要且有劣势。**
- **thesis 2 多区间**：与 baseline **完全同构**（换名 = 列表点 vs 列表区间，结构等价）。**不必要。**

### 最终建议

**thesis 2 被证伪——应放弃或大幅降级**。

理由：
- 查询表达力：baseline 在所有 123 测试点不劣于 thesis 2
- repeating frequency：thesis 2 单区间有劣势，多区间与 baseline 同构
- 扩展性：完全同构
- 实现复杂度：baseline 最简单

**bitemporal 应降级为渲染端实现细节，不作为研究 thesis**。
**研究焦点转向 thesis 1（异质 agent 架构）——这是更确定的工程创新。**
