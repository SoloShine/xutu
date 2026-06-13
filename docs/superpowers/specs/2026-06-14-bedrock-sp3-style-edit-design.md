# 磐石 Bedrock SP3 — 风格指纹 + 编辑回归 设计

**日期**: 2026-06-14
**状态**: SP3 设计（待 user review → writing-plans）
**代号**: 磐石 Bedrock（V3 小说管线）
**范围**: StyleTemplate 提取器（全 7 维度直方图）+ 两级指纹管理 + 结构化 prompt 生成器。纯 Python，SP4 派生 Edit agent 用。
**依赖**: SP1（StyleTemplate/ChapterMetrics 表）、SP2（BeatViolation.fix_hint 喂修复 prompt）
**前置 spec**: `docs/superpowers/specs/2026-06-14-bedrock-design.md`（§3.10 StyleTemplate、§4.3 L3 编辑子代理）

---

## 一、背景

SP1/SP2 已落地数据骨架 + 防漂移校验库。SP3 提供 **Edit agent 的弹药**——StyleTemplate 量化指纹（正约束源）+ 结构化 prompt（润色/修复）。SP4 编排派生 Edit agent 时调用 SP3 的 prompt。

**形态**：`src/bedrock/style/` 纯 Python 库（提取 + 两级管理 + prompt 生成），**不派生 agent**（SP4 负责）、不依赖 Workflow/Agent SDK。

**SP3 vs SP4 边界**：
- **SP3**：StyleTemplate 提取（章节文本→指纹）+ 两级指纹管理 + 结构化 prompt 生成（dataclass + to_string）
- **SP4**：编排——派生 ChapterWriter/Edit agent，用 SP3 的 prompt + SP2 的校验，跑重试循环

---

## 二、设计原则

1. **纯 Python prompt 生成库** —— SP3 只产 prompt（结构化对象 + 字符串），不派生 agent。可纯单元测试。
2. **全维度指纹一次性做** —— 纯统计 + 语义维度都做（语义属基础数据处理，后面补麻烦）。依赖静态词表/regex。
3. **结构化 prompt** —— 输出 dataclass（PolishPrompt/RepairPrompt），`to_string()` 转自然语言。结构化清晰可测，SP4 按需用结构化或字符串。
4. **直方图表征** —— 每维度用区间占比直方图（Edit agent 能直接对准"目标分布"）。
5. **两级指纹** —— 作品级基础 + 卷级覆盖 + fallback。

---

## 三、组件设计

### ① 静态词表/regex — `style/lexicon.py`

代码内静态常量（类似 `config/volume_type_matrix.py`），提取器的依赖。

```python
# 感官词表（起步，可扩展）
SENSORY_LEXICON = {
    "视觉": ["看", "望", "瞧", "光", "色", "影", "亮", "暗", "闪", "凝视"],
    "听觉": ["听", "声", "响", "音", "鸣", "嗡", "寂静", "轰"],
    "触觉": ["摸", "触", "冷", "热", "痛", "冰", "烫", "粗糙", "柔软"],
    "嗅觉": ["闻", "香", "臭", "腥", "气味", "芬芳"],
    "味觉": ["尝", "甜", "苦", "咸", "酸", "涩"],
}

# 句式 regex（起步）
SENTENCE_STRUCTURE_PATTERNS = {
    "notXisY": r"不是.{1,15}[，。].{0,5}是",   # "不是X，是Y" 否定转折
    # 短句/长句由句长判定，不在此
}
```

### ② StyleTemplate 提取器 — `style/extractor.py`

```python
def extract_fingerprint(chapter_texts: list[str]) -> dict:
    """输入章节正文列表，输出全 7 维度直方图指纹。
    返回 {维度名: {区间/类别: 占比}}。"""
```

**7 维度**（见 §四 区间定义）：
- 纯统计（5）：句长分布、段落长分布、破折号分布、句号分布、对话占比
- 语义（2）：句式结构、感官密度

提取器内部用 `lexicon.py` 的感官词表 + 句式 regex。

### ③ 两级指纹管理 — `style/template_repo.py`（SP3 新增；SP1 只有 `save_style_template`，无读函数）

```python
def save_fingerprint(conn, scope: str, chapter_ids: list[int], volume_id=None):
    """提取并写回 style_template。
    1. 对每个 chapter_id 取 list_paragraphs_in_chapter 的 paragraph.text，聚合成 chapter_texts（每章一字符串）
    2. extract_fingerprint(chapter_texts) → 指纹 dict
    3. 写 style_template：fingerprint JSON 内嵌 _scope（'work'|'volume'）+ _volume_id（卷级时）
       sample_chapters = chapter_ids（写表字段，便于溯源）"""

def get_effective_fingerprint(conn, volume_id) -> dict | None:
    """两级 fallback：
    1. 查 json_extract(fingerprint,'$._scope')='volume' AND json_extract(fingerprint,'$._volume_id')=volume_id → 卷级
    2. 无则查 _scope='work' → 作品级
    3. 都无 → None"""

def list_fingerprints(conn, scope=None) -> list:
    """列指纹（SP3 新增读函数）。"""
```

**卷级寻址**：style_template 无 scope/volume_id 列，两级 scope 用 fingerprint JSON 内 `_scope`+`_volume_id` 区分，`json_extract` 查询。约束：一个 volume 最多一行卷级指纹（save_fingerprint 应用层 upsert 保证）。

### ④ 结构化 prompt 生成器 — `style/prompt_gen.py`

```python
@dataclass
class PolishPrompt:
    target_distribution: dict     # 指纹直方图（目标分布）
    beat_contracts: list          # 本章 beat 契约
    requirements: list[str]       # 润色要求（对准分布、保持剧情、不压缩字数）
    def to_string(self) -> str: ...

@dataclass
class RepairPrompt:
    violations: list              # SP2 BeatViolation[]
    fix_hints: list[str]          # 各 violation 的 fix_hint
    requirements: list[str]       # 修复要求（只改违规段落、不引入新问题、不压缩剧情）
    def to_string(self) -> str: ...

def generate_polish_prompt(conn, chapter_id, volume_id) -> PolishPrompt
def generate_repair_prompt(violations, chapter_context) -> RepairPrompt
```

`generate_polish_prompt`：取 effective fingerprint（两级 fallback）+ 本章 beat 契约 → PolishPrompt。
`generate_repair_prompt`：SP2 violations + fix_hint → RepairPrompt。

SP4 派生 Edit agent 时用 `prompt.to_string()` 或读结构化字段构造 agent prompt。

---

## 四、指纹维度 + 直方图区间定义

| 维度 | 类别 | 直方图区间/类别 |
|------|------|----------------|
| 句长分布 | 纯统计 | 句子字数：`[1-8, 9-15, 16-25, 26-40, 40+]` 占比 |
| 段落长分布 | 纯统计 | 段落字数：`[1-50, 51-120, 121-200, 200+]` 占比 |
| 破折号分布 | 纯统计 | 段落破折号（——）数：`[0, 1, 2, 3+]` 占比 |
| 句号分布 | 纯统计 | 段落句号（。）数：`[1-2, 3-4, 5-6, 7+]` 占比 |
| 对话占比 | 纯统计 | 段落类型：`{纯对话, 纯叙述, 混合}` 占比（对话=含引号"") |
| 句式结构 | 语义 | `{notXisY, 短句(<8字), 长句(>25字), 其他}` 占比 |
| 感官密度 | 语义 | 段落主导感官：`{视觉, 听觉, 触觉, 嗅觉, 味觉, 无}` 占比 |

**句子切分**：按全角标点 `[。！？]` 切分（去掉分隔符）；破折号/换行不算句界。
**段落定义**：`paragraph.text` 本身是一段（SP1 schema）；段落长直方图按 paragraph.text 字数分区间；跨段聚合 = 所有 paragraph.text 列表。
**对话判定**：段落含中文引号（"「）视为含对话。
**感官主导**：段落里各感官词表命中计数，取最多者；**平局取词表顺序第一个**（视觉>听觉>触觉>嗅觉>味觉）；无命中=无。
**句式 notXisY**：regex `不是.{1,15}[，。].{0,5}是` 命中。
**空输入边界**：chapter_texts 为空 → 返回全零指纹（各区间占比 0），不抛异常。

区间值在 `extractor.py` 内常量（可调），起步用上表。

---

## 五、结构化 prompt 字段

**PolishPrompt**（正向润色）：
- `target_distribution`：effective fingerprint（7 维度直方图）
- `beat_contracts`：本章 beat 契约（**取数路径**：`list_beats_in_chapter(chapter_id)` → beat_id 集 → 对每个调 `get_beat_contract(volume_id, beat_id)`）
- `requirements`：`["对准目标分布（句长/段落长/感官等）", "保持剧情完整", "不压缩字数", "输出完整章节"]`
- `to_string()`：目标分布表格化 + 要求列表。样例：
  ```
  【风格润色任务】
  目标分布（对准此分布）：
    句长：1-8字 20% | 9-15字 40% | 16-25字 25% | 26-40字 10% | 40+ 5%
    感官：视觉 30% | 听觉 20% | 触觉 15% | 无 35%
  本章 beat 契约：[beat1: 林深发现注记 / beat2: ...]
  要求：对准分布 / 保持剧情 / 不压缩字数 / 输出完整章节
  ```

**RepairPrompt**（定向修复）：
- `violations`：SP2 `BeatViolation[]`（字段 beat_id/kind/detail/**fix_hint**）
- `fix_hints`：各 violation 的 `fix_hint`（从 violations 提取，不单独传）
- `requirements`：`["只修改违规段落，不动其他", "不引入新的违规", "不压缩剧情", "输出完整章节"]`
- `to_string()`：违规清单（每个 beat 缺什么 + fix_hint）+ 要求

`generate_polish_prompt(conn, chapter_id, volume_id)`：取 effective fingerprint（两级 fallback）+ 本章 beat 契约（上述取数路径）→ PolishPrompt。
`generate_repair_prompt(violations, chapter_context)`：violations（含 fix_hint）→ RepairPrompt。

---

## 六、与 SP1/SP2 接口

SP3 用：
- SP1 `style_template` 表（写回/读指纹，扩展 scope/volume_id 字段语义）
- SP1 `paragraph`（读章节正文，提取器输入）
- SP1 `volume_outline.beat_contracts`（PolishPrompt 的 beat 契约源）
- SP2 `BeatViolation`（RepairPrompt 的 violations 源，含 fix_hint）

**SP1 style_template 表字段**（已存在）：`source_works`/`sample_chapters`/`fingerprint`(JSON)/`extracted_at`。SP3 **不改表结构**，两级 scope 用 fingerprint JSON 内 `_scope`（work|volume）+ `_volume_id`（卷级）区分，`json_extract(fingerprint,'$._scope')` 查询。详见 §三 ③。SP1 `telemetry.save_style_template` 仅写无读，SP3 `template_repo.py` 新增 `save_fingerprint`（封装 + 取数 + 加 _scope）/`get_effective_fingerprint`/`list_fingerprints`。

---

## 七、文件结构

```
src/bedrock/style/
├── __init__.py
├── lexicon.py           # ① 感官词表 + 句式 regex（静态常量）
├── extractor.py         # ② 提取器（全 7 维度直方图）
├── template_repo.py     # ③ 两级指纹管理（扩展 style_template）
└── prompt_gen.py        # ④ 结构化 prompt（PolishPrompt/RepairPrompt + to_string）
tests/bedrock/
├── test_lexicon.py
├── test_extractor.py
├── test_template_repo.py
└── test_prompt_gen.py
```

无新表（复用 SP1 style_template）。

---

## 八、测试策略

**SP3 测试 = 组件级单元测试**（确定性）：
- lexicon：词表/regex 非空、regex 可编译
- extractor：构造已知章节文本，断言各维度直方图占比正确（如全短句→句长 [1-8] 占比 100%）；**+ 空章节文本 → 全零指纹不抛**
- template_repo：作品级/卷级写入 + fallback（卷级有则用、无则 fallback 作品级、都无则 None）
- prompt_gen：PolishPrompt/RepairPrompt 字段正确 + to_string 含关键片段（目标分布/违规 beat/fix_hint/要求）

**系统性测试在 SP5**（真派 Edit agent 跑润色/修复，验证指纹驱动效果）。

---

## 九、SP4 边界（明确）

SP3 **不**做：
- 派生 Edit agent（SP4 编排）
- 调用 LLM（SP4 派生 agent 时调）
- 重试循环（SP4）
- 风格偏离的实际判定/阻断（SP3 只提供指纹 + prompt，判定逻辑在 SP4/SP5）

SP3 只产 prompt（结构化 + 字符串），SP4 拿去派生 agent。
