# 字数下限硬门禁 — 设计文档

- **日期**:2026-06-20
- **背景**:vigilia《长明》全书 ~6.2 万汉字,远低于 ~10 万目标;多章 1600-2800 字(ch6/13/17/22/24)。根因:字数下限在整个管线无执行点——writer 软指令(LLM 不遵守)→ L2 不卡(`l2_pipeline.py:34,40` 显式豁免:空稿才算 drift,短稿不算,`unwritten_beat` 只抓空 beat)→ 编辑代理被 prompt 绑死"保持字数/不增删段落"(`bedrock-chapter.js:218,381`)→ style-polish 削减修辞可能再缩短。四关口全放过。
- **目标**:让字数下限成为可执行的硬约束,欠产章在写作管线内被拦截并扩写达标。

---

## 缺陷根因(已代码核实)

| 关口 | 现状 | 证据 |
|------|------|------|
| Writer | 拿到目标但软指令 | `chapter_writer.md:15` "字数 3000-5000 汉字";LLM 频繁欠产 |
| L2 | 计算字数但**不卡**,且显式豁免短稿 | `l2_pipeline.py:34,40` "空初稿不算 drift(硬门禁兜底)";违规类仅 unwritten_beat/missing_character/empty_beat/thread_not_advanced/non_prose |
| Repair/Consistency | 被 prompt 绑"保持字数/不增删段落" | `bedrock-chapter.js:218,381` |
| style-polish | 聚焦修辞/对白/破折号,削减可能再缩短 | `bedrock-chapter.js` style 阶段 |

`compute_word_count`(`src/bedrock/checks/word_count.py`)= **汉字数**(仅 `[一-鿿]`,排除标点/ASCII),与 `word_count_target=(3000,5000)` 单位一致。

---

## 设计

### 1. L2 加 `word_count_below_floor` 硬违规(主)

**落点**:`src/bedrock/orchestration/l2_pipeline.py` `run_l2(conn, chapter_id)`。
- `run_l2` 已在 line 77 计算 `wc = compute_word_count(paragraphs)`,已建 `L2Report`。
- 它能经既有 `_volume_id_of_chapter(conn, chapter_id)` 拿 volume_id,再 `get_style_config(conn, volume_id)["word_count_target"]` 拿 `(floor, ceiling)`。

**逻辑**(在 `run_l2` line 82 之后、`return L2Report(...)` 之前追加;`volume_id`/`wc`/`beat_violations` 均已在作用域):
```python
from src.bedrock.checks.beat_fulfillment import BeatViolation
from src.bedrock.style.template_repo import get_style_config
_DEFAULT_FLOOR = 3000  # 兜底:style config 无目标时
floor = _DEFAULT_FLOOR
if volume_id is not None:
    try:
        wc_target = get_style_config(conn, volume_id)["word_count_target"]  # [low, high]
        if wc_target:
            floor = int(wc_target[0])
    except Exception:
        pass
total_beats = total_beats or 1
if 0 < wc < floor:   # 空稿(wc==0)由 unwritten_beat 兜,不重复报
    beat_violations.append(BeatViolation(
        beat_id=beat_violations[0].beat_id if beat_violations else 0,  # 章级违规
        kind="word_count_below_floor",
        detail=f"实测 {wc} 汉字 < 下限 {floor} 汉字",
        fix_hint=f"扩写至 {floor} 汉字以上:增场景细节/感官/心理/对白展开;禁灌水/重复/注水"))
```
`passed_hard_gate=(len(beat_violations)==0)`(line 109)自动生效——追加后即 `False`。`import` 提到文件头(勿函数内重复 import)。

**效果**:`wc < floor` → `passed_hard_gate=False` → 进既有 Repair 循环(`bedrock-chapter.js` 的 `while (!passed && round<3)`),不达标不落盘,与其他 L2 违规完全同构。

**与现有 drift 豁免的关系**:`l2_pipeline.py:34,40` 的"空稿不算 drift"是 **advisory drift** 语义,正交于本硬门禁;保留不动。空稿现在会同时被 `unwritten_beat` + (wc==0 跳过) 处理,无重复报。

### 2. `editRepairPrompt` 条件扩写 + 防灌水

**落点**:`.claude/workflows/bedrock-chapter.js` `editRepairPrompt(report, prevProse)`。

当前:`"只改与违规相关段落,不压缩剧情,保持其余原文"`。

改:检测 `report.beat_violations` 含 `kind==="word_count_below_floor"` 时,切换为扩写指令:
```js
const needExpand = (report.beat_violations || []).some(v => v.kind === 'word_count_below_floor')
// 通用约束行:
const baseRule = needExpand
  ? '本章字数不足(见 word_count_below_floor 违规),须【扩写】至下限以上:在现有剧情骨架上增场景细节/感官/心理/对白展开,丰富而非重复。'
  : '只改与违规相关段落,不压缩剧情,保持其余原文。'
const antiPad = needExpand
  ? '【禁灌水】不得无信息扩写、不得重复同一意思、不得堆砌形容词、不得注水对话;扩写须服务于人物/氛围/情节推进。扩写后仍须过文风门禁(修辞密度/对白比/破折号)。'
  : ''
```
拼进 prompt(替换原"保持其余原文"行,`antiPad` 非空时追加)。

**防灌水三重**:(a) prompt 明禁(上);(b) 扩写后重跑 style 门禁(既有,修辞/对白会卡填充式堆砌——rhetoric_per_k 是 upper bound);(c) L2 重检字数必须真到 floor。

### 3. Writer prompt 自检(次要,软辅助)

`.claude/templates/bedrock/chapter_writer.md` 第 15 行附近,把"字数 3000-5000 汉字"强化为:
```markdown
4. 字数 3000-5000 汉字(**交稿前自检汉字数 ≥ 3000,系统硬卡,不足会被打回扩写**)
```
硬门禁是保障,此为前置提醒。

### 4. 边界与目标源

- **floor 源**:现有 `word_count_target`(style config,已按卷可配)。**不新建 volume_type matrix**(YAGNI)。无 style config 时兜底 3000。
- **只卡下限,不卡上限**(全书问题是欠产;超产罕见,且 style 门禁间接约束)。
- **Repair 3 轮仍不达标** → `mark-unresolved`(既有路径,与其他不可解违规一致;`likely_rule_or_model` 判定同样适用)。
- **既有作品**:对新写章生效;vigilia 偏短章可经 `bedrock-chapter-edit rewrite` 或重跑 chapter 管线批量补字(行为变化:短章现在会失败直到达标)。

---

## 测试策略

- **单元**(`tests/bedrock/test_l2_word_count.py`,新):
  - 章 < floor → `word_count_below_floor` 违规,`passed_hard_gate=False`。
  - 章 = floor / > floor → 不报该违规。
  - 空稿(wc==0)→ 不报 word_count_below_floor(由 unwritten_beat 兜),不重复。
  - 无 style config → 兜底 floor=3000。
- **prompt**(`tests/bedrock/` 或 JS 抽测):editRepairPrompt 含该违规 → 输出含"扩写"+"禁灌水";不含 → 维持"保持原文"。(JS 沙箱难直测,可抽纯函数或靠端到端。)
- **端到端回归**:vigilia ch6(1714 字)重跑 chapter 管线 → 现在被 word_count_below_floor 拦 → Repair 扩写 → 终态 ≥3000 字且 L2 全绿。证明闭环。

## 影响面与回退

- 改动文件:`src/bedrock/orchestration/l2_pipeline.py`、`.claude/workflows/bedrock-chapter.js`(editRepairPrompt)、`.claude/templates/bedrock/chapter_writer.md`、新 `tests/bedrock/test_l2_word_count.py`。
- 既有已落盘正文不动;新写/重写章生效。
- 回退:独立 commit,可单独 revert。
