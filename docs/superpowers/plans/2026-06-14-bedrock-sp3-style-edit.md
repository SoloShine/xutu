# 磐石 Bedrock SP3 — 风格指纹 + 编辑回归 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** StyleTemplate 提取器（全 7 维度直方图）+ 两级指纹管理 + 结构化 prompt 生成器。纯 Python，SP4 派生 Edit agent 用。

**Architecture:** `src/bedrock/style/` 4 模块（lexicon 静态词表/regex → extractor 直方图提取 → template_repo 两级指纹 → prompt_gen 结构化 prompt）。复用 SP1 style_template 表（不加表），两级 scope 用 fingerprint JSON 内 _scope/_volume_id。

**Tech Stack:** Python 3.10+ stdlib（re/json/dataclasses/sqlite3），pytest。

**前置:** SP1/SP2 完成（src/bedrock/ 59 测试，分支 bedrock-sp1）。spec: `docs/superpowers/specs/2026-06-14-bedrock-sp3-style-edit-design.md`。

---

## 文件结构

```
src/bedrock/style/
├── __init__.py
├── lexicon.py           # Task 1: 感官词表 + 句式 regex
├── extractor.py         # Task 2: 7 维度直方图提取器
├── template_repo.py     # Task 3: 两级指纹管理
└── prompt_gen.py        # Task 4: 结构化 prompt
tests/bedrock/
├── test_lexicon.py
├── test_extractor.py
├── test_template_repo.py
└── test_prompt_gen.py
```

依赖链：Task 1（lexicon）→ Task 2（extractor 用 lexicon）→ Task 3（template_repo 用 extractor）→ Task 4（prompt_gen 用 template_repo + SP2 BeatViolation）。

---

## Task 1: 静态词表/regex（lexicon）

**Files:**
- Create: `src/bedrock/style/__init__.py`（空）
- Create: `src/bedrock/style/lexicon.py`
- Test: `tests/bedrock/test_lexicon.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_lexicon.py
import re
from src.bedrock.style.lexicon import SENSORY_LEXICON, SENTENCE_STRUCTURE_PATTERNS


def test_sensory_lexicon_has_five_senses():
    for sense in ("视觉", "听觉", "触觉", "嗅觉", "味觉"):
        assert sense in SENSORY_LEXICON
        assert len(SENSORY_LEXICON[sense]) > 0


def test_notXisY_pattern_compiles_and_matches():
    pat = re.compile(SENTENCE_STRUCTURE_PATTERNS["notXisY"])
    assert pat.search("不是因为他累，是因为他想家")
    assert not pat.search("今天天气很好")
```

- [ ] **Step 2: 跑确认失败**（ModuleNotFoundError）

- [ ] **Step 3: 实现 `style/lexicon.py`**

```python
# src/bedrock/style/lexicon.py
"""静态词表 + 句式 regex（提取器依赖）。起步内容，可扩展。"""

SENSORY_LEXICON = {
    "视觉": ["看", "望", "瞧", "光", "色", "影", "亮", "暗", "闪", "凝视", "注视", "瞥"],
    "听觉": ["听", "声", "响", "音", "鸣", "嗡", "寂静", "轰", "低语", "回响"],
    "触觉": ["摸", "触", "冷", "热", "痛", "冰", "烫", "粗糙", "柔软", "颤抖"],
    "嗅觉": ["闻", "香", "臭", "腥", "气味", "芬芳", "刺鼻"],
    "味觉": ["尝", "甜", "苦", "咸", "酸", "涩", "咽下"],
}

# 感官优先级（平局时取顺序第一个）
SENSORY_PRIORITY = ["视觉", "听觉", "触觉", "嗅觉", "味觉"]

SENTENCE_STRUCTURE_PATTERNS = {
    "notXisY": r"不是.{1,15}[，。].{0,5}是",
}
```

- [ ] **Step 4: 跑确认通过**（2 passed）+ Commit
```
git add src/bedrock/style/__init__.py src/bedrock/style/lexicon.py tests/bedrock/test_lexicon.py
git commit -m "feat(bedrock): style lexicon (sensory words + sentence patterns)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: 7 维度直方图提取器

**Files:**
- Create: `src/bedrock/style/extractor.py`
- Test: `tests/bedrock/test_extractor.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_extractor.py
from src.bedrock.style.extractor import extract_fingerprint


def test_empty_paragraphs_returns_zero_fingerprint():
    fp = extract_fingerprint([])
    for dim in ("sentence_length", "paragraph_length", "dash", "period",
                "dialogue", "structure", "sensory"):
        assert dim in fp


def test_all_short_sentences():
    fp = extract_fingerprint(["他来了。她走了。天黑了。"])
    # 全短句（<=8字）→ 句长 "1-8" 占比 1.0
    assert fp["sentence_length"]["1-8"] == 1.0


def test_paragraph_length_distribution():
    fp = extract_fingerprint(["短。", "这是一段中等长度的段落文字用于测试。", "短。"])
    # 至少有 "1-50" 和 "51-120" 两类
    assert fp["paragraph_length"]["1-50"] > 0
    assert fp["paragraph_length"]["51-120"] > 0


def test_dash_distribution():
    fp = extract_fingerprint(["无破折号段落。", "有——破折号。", "两——个——破折号。"])
    assert fp["dash"]["0"] > 0
    assert fp["dash"]["1"] > 0
    assert fp["dash"]["2"] > 0


def test_dialogue_detection():
    fp = extract_fingerprint(["他说："你好。"然后转身。", "纯叙述没有引号。"])
    assert fp["dialogue"]["混合"] > 0 or fp["dialogue"]["纯对话"] > 0
    assert fp["dialogue"]["纯叙述"] > 0


def test_notXisY_structure():
    fp = extract_fingerprint(["不是因为他累，是因为他想家。普通的句子。"])
    assert fp["structure"]["notXisY"] > 0


def test_sensory_dominance():
    fp = extract_fingerprint(["他看见远处的光。", "听到一声巨响。"])
    assert fp["sensory"]["视觉"] > 0
    assert fp["sensory"]["听觉"] > 0
```

- [ ] **Step 2: 跑确认失败**（ModuleNotFoundError）

- [ ] **Step 3: 实现 `style/extractor.py`**

```python
# src/bedrock/style/extractor.py
import re
from src.bedrock.style.lexicon import SENSORY_LEXICON, SENSORY_PRIORITY, SENTENCE_STRUCTURE_PATTERNS

_SENTENCE_SPLIT = re.compile(r"[。！？]")
_CN_CHAR = re.compile(r"[一-鿿]")
_QUOTE_CHARS = set("「」“”\"'")
_NOTXISY = re.compile(SENTENCE_STRUCTURE_PATTERNS["notXisY"])


def _cn_len(text):
    """中文字符数（排除标点/空白）。"""
    return len(_CN_CHAR.findall(text))


def _split_sentences(text):
    """按 [。！？] 切分，去空。"""
    return [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _continuous_histogram(values, bounds, labels):
    """values 按上界 bounds 分到 labels 区间，返回 {label: 占比}。"""
    if not values:
        return {l: 0.0 for l in labels}
    bins = [0] * len(labels)
    for v in values:
        idx = len(bounds)
        for i, b in enumerate(bounds):
            if v <= b:
                idx = i
                break
        bins[idx] += 1
    total = len(values)
    return {labels[i]: bins[i] / total for i in range(len(labels))}


def _categorical_histogram(categories, all_labels):
    """categories: 类别列表；返回 {label: 占比}（含 0 占比类）。"""
    if not categories:
        return {l: 0.0 for l in all_labels}
    counts = {l: 0 for l in all_labels}
    for c in categories:
        if c in counts:
            counts[c] += 1
    total = len(categories)
    return {l: counts[l] / total for l in all_labels}


def _paragraph_dialogue_type(text):
    """段落对话类型：纯对话/混合/纯叙述（按引号字符占比）。"""
    n = len(text)
    if n == 0:
        return "纯叙述"
    quote_count = sum(1 for ch in text if ch in _QUOTE_CHARS)
    ratio = quote_count / n
    if ratio > 0.15:
        return "纯对话"
    if ratio > 0.03:
        return "混合"
    return "纯叙述"


def _sentence_structure(sentence):
    """句子句式：notXisY/短句/长句/其他。"""
    if _NOTXISY.search(sentence):
        return "notXisY"
    length = _cn_len(sentence)
    if length < 8:
        return "短句"
    if length > 25:
        return "长句"
    return "其他"


def _paragraph_sensory(text):
    """段落主导感官：词表命中最多者；平局取 SENSORY_PRIORITY 顺序第一个；无=无。"""
    counts = {}
    for sense in SENSORY_PRIORITY:
        counts[sense] = sum(text.count(w) for w in SENSORY_LEXICON[sense])
    max_count = max(counts.values()) if counts else 0
    if max_count == 0:
        return "无"
    for sense in SENSORY_PRIORITY:  # 平局取顺序第一个
        if counts[sense] == max_count:
            return sense
    return "无"


def extract_fingerprint(paragraphs):
    """paragraphs: 段落文本列表（跨章节所有 paragraph.text）。返回 7 维度直方图指纹。"""
    dims = ["sentence_length", "paragraph_length", "dash", "period",
            "dialogue", "structure", "sensory"]
    if not paragraphs:
        return {d: {} for d in dims}

    # 句子级
    all_sentences = []
    for p in paragraphs:
        all_sentences.extend(_split_sentences(p))
    sentence_lengths = [_cn_len(s) for s in all_sentences]

    # 段落级
    para_lengths = [_cn_len(p) for p in paragraphs]
    dash_counts = [p.count("——") for p in paragraphs]
    period_counts = [p.count("。") for p in paragraphs]

    return {
        "sentence_length": _continuous_histogram(
            sentence_lengths, [8, 15, 25, 40], ["1-8", "9-15", "16-25", "26-40", "40+"]),
        "paragraph_length": _continuous_histogram(
            para_lengths, [50, 120, 200], ["1-50", "51-120", "121-200", "200+"]),
        "dash": _continuous_histogram(
            dash_counts, [0, 1, 2], ["0", "1", "2", "3+"]),
        "period": _continuous_histogram(
            period_counts, [2, 4, 6], ["1-2", "3-4", "5-6", "7+"]),
        "dialogue": _categorical_histogram(
            [_paragraph_dialogue_type(p) for p in paragraphs], ["纯对话", "混合", "纯叙述"]),
        "structure": _categorical_histogram(
            [_sentence_structure(s) for s in all_sentences],
            ["notXisY", "短句", "长句", "其他"]),
        "sensory": _categorical_histogram(
            [_paragraph_sensory(p) for p in paragraphs],
            SENSORY_PRIORITY + ["无"]),
    }
```

- [ ] **Step 4: 跑确认通过**（7 passed）+ 全量回归
`python -m pytest tests/bedrock/ -v` → 59 + 2(lexicon) + 7(extractor) = 68

- [ ] **Step 5: Commit**
```
git add src/bedrock/style/extractor.py tests/bedrock/test_extractor.py
git commit -m "feat(bedrock): 7-dimension fingerprint extractor (histograms)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 两级指纹管理

**Files:**
- Create: `src/bedrock/style/template_repo.py`
- Test: `tests/bedrock/test_template_repo.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_template_repo.py
from src.bedrock.db.connection import get_connection
from src.bedrock.style.template_repo import (
    save_fingerprint, get_effective_fingerprint, list_fingerprints,
)
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_paragraph


def _seed_paragraphs(conn, texts):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    for i, t in enumerate(texts):
        create_paragraph(conn, chapter_id=cid, seq=i + 1, text=t,
                         content_hash=f"h{i}", beat_id=None, role="narrative")
    return vid, cid


def test_save_and_get_work_fingerprint(tmp_project):
    conn = get_connection(tmp_project)
    vid, cid = _seed_paragraphs(conn, ["他来了。她走了。", "看见远处的光。"])
    save_fingerprint(conn, scope="work", chapter_ids=[cid])
    fp = get_effective_fingerprint(conn, volume_id=vid)
    assert fp is not None
    assert "sentence_length" in fp
    assert fp["_scope"] == "work"
    conn.close()


def test_volume_fallback_to_work(tmp_project):
    """无卷级指纹时 fallback 作品级。"""
    conn = get_connection(tmp_project)
    vid, cid = _seed_paragraphs(conn, ["他来了。"])
    save_fingerprint(conn, scope="work", chapter_ids=[cid])
    # 无卷级指纹 → fallback work
    fp = get_effective_fingerprint(conn, volume_id=vid)
    assert fp["_scope"] == "work"
    conn.close()


def test_volume_overrides_work(tmp_project):
    """有卷级指纹时用卷级。"""
    conn = get_connection(tmp_project)
    vid, cid = _seed_paragraphs(conn, ["他来了。", "她走了。"])
    save_fingerprint(conn, scope="work", chapter_ids=[cid])
    save_fingerprint(conn, scope="volume", chapter_ids=[cid], volume_id=vid)
    fp = get_effective_fingerprint(conn, volume_id=vid)
    assert fp["_scope"] == "volume"
    assert fp["_volume_id"] == vid
    conn.close()


def test_no_fingerprint_returns_none(tmp_project):
    conn = get_connection(tmp_project)
    vid, _ = _seed_paragraphs(conn, ["x"])
    assert get_effective_fingerprint(conn, volume_id=vid) is None
    conn.close()


def test_list_fingerprints(tmp_project):
    conn = get_connection(tmp_project)
    vid, cid = _seed_paragraphs(conn, ["他来了。"])
    save_fingerprint(conn, scope="work", chapter_ids=[cid])
    fps = list_fingerprints(conn)
    assert len(fps) >= 1
    conn.close()
```

- [ ] **Step 2: 跑确认失败**（ModuleNotFoundError）

- [ ] **Step 3: 实现 `style/template_repo.py`**

```python
# src/bedrock/style/template_repo.py
import json
from src.bedrock.repositories.plot_tree import list_paragraphs_in_chapter
from src.bedrock.repositories.telemetry import save_style_template
from src.bedrock.style.extractor import extract_fingerprint


def _gather_paragraphs(conn, chapter_ids):
    """收集这些章节的所有 paragraph.text。"""
    paragraphs = []
    for cid in chapter_ids:
        for p in list_paragraphs_in_chapter(conn, cid):
            paragraphs.append(p["text"])
    return paragraphs


def save_fingerprint(conn, scope, chapter_ids, volume_id=None):
    """提取并写回 style_template。fingerprint JSON 内嵌 _scope/_volume_id。"""
    paragraphs = _gather_paragraphs(conn, chapter_ids)
    fingerprint = extract_fingerprint(paragraphs)
    fingerprint["_scope"] = scope
    if scope == "volume" and volume_id is not None:
        fingerprint["_volume_id"] = volume_id
    save_style_template(
        conn,
        fingerprint=fingerprint,
        source_works=[scope],
        sample_chapters=chapter_ids,
    )


def get_effective_fingerprint(conn, volume_id):
    """两级 fallback：卷级 → 作品级 → None。"""
    # 1. 卷级
    rows = conn.execute("SELECT fingerprint FROM style_template").fetchall()
    for r in rows:
        fp = json.loads(r["fingerprint"])
        if fp.get("_scope") == "volume" and fp.get("_volume_id") == volume_id:
            return fp
    # 2. 作品级
    for r in rows:
        fp = json.loads(r["fingerprint"])
        if fp.get("_scope") == "work":
            return fp
    # 3. 都无
    return None


def list_fingerprints(conn, scope=None):
    """列指纹（可选按 scope 过滤）。返回 fingerprint dict 列表。"""
    rows = conn.execute("SELECT fingerprint FROM style_template").fetchall()
    out = []
    for r in rows:
        fp = json.loads(r["fingerprint"])
        if scope is None or fp.get("_scope") == scope:
            out.append(fp)
    return out
```

- [ ] **Step 4: 跑确认通过**（5 passed）+ 全量回归 → 68 + 5 = 73

- [ ] **Step 5: Commit**
```
git add src/bedrock/style/template_repo.py tests/bedrock/test_template_repo.py
git commit -m "feat(bedrock): two-level fingerprint management (work/volume + fallback)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: 结构化 prompt 生成器

**Files:**
- Create: `src/bedrock/style/prompt_gen.py`
- Test: `tests/bedrock/test_prompt_gen.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/bedrock/test_prompt_gen.py
from src.bedrock.db.connection import get_connection
from src.bedrock.style.prompt_gen import (
    PolishPrompt, RepairPrompt, generate_polish_prompt, generate_repair_prompt,
)
from src.bedrock.checks.beat_fulfillment import BeatViolation
from src.bedrock.repositories.plot_tree import create_volume, create_chapter, create_beat, create_paragraph
from src.bedrock.repositories.outline import save_volume_outline, lock_volume_outline, unlock_volume_outline, update_beat_contract
from src.bedrock.style.template_repo import save_fingerprint


def _seed(conn):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    bid = create_beat(conn, chapter_id=cid, sequence=1, purpose="林深发现旧书摊的注记")
    create_paragraph(conn, chapter_id=cid, seq=1, text="他来了。她走了。",
                     content_hash="h", beat_id=bid, role="narrative")
    save_volume_outline(conn, vid, beat_contracts=[])
    lock_volume_outline(conn, vid)
    unlock_volume_outline(conn, reason="setup", author="system")
    update_beat_contract(conn, vid, beat_id=bid,
                         new_contract={"purpose": "林深发现注记", "participating_characters": ["林深"], "advance_threads": []})
    save_fingerprint(conn, scope="work", chapter_ids=[cid])
    return vid, cid, bid


def test_generate_polish_prompt_structure(tmp_project):
    conn = get_connection(tmp_project)
    vid, cid, bid = _seed(conn)
    p = generate_polish_prompt(conn, chapter_id=cid, volume_id=vid)
    assert isinstance(p, PolishPrompt)
    assert "sentence_length" in p.target_distribution
    assert len(p.beat_contracts) >= 1
    assert p.beat_contracts[0]["purpose"] == "林深发现注记"
    s = p.to_string()
    assert "目标分布" in s
    assert "林深发现注记" in s
    conn.close()


def test_generate_repair_prompt_from_violations():
    violations = [
        BeatViolation(beat_id=1, kind="missing_character", detail="角色 林深 未出场", fix_hint="加入林深出场"),
        BeatViolation(beat_id=2, kind="thread_not_advanced", detail="悬链 ST001 未推进", fix_hint="推进 ST001"),
    ]
    p = generate_repair_prompt(violations, chapter_context="第1章")
    assert isinstance(p, RepairPrompt)
    assert len(p.violations) == 2
    assert "加入林深出场" in p.fix_hints
    s = p.to_string()
    assert "林深" in s
    assert "ST001" in s
    assert "只修改违规段落" in s


def test_polish_prompt_no_fingerprint(tmp_project):
    """无指纹时 target_distribution 为空 dict，仍生成 prompt（不抛）。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    save_volume_outline(conn, vid, beat_contracts=[])
    p = generate_polish_prompt(conn, chapter_id=cid, volume_id=vid)
    assert p.target_distribution == {}
    conn.close()
```

- [ ] **Step 2: 跑确认失败**（ModuleNotFoundError）

- [ ] **Step 3: 实现 `style/prompt_gen.py`**

```python
# src/bedrock/style/prompt_gen.py
from dataclasses import dataclass, field
from src.bedrock.repositories.plot_tree import list_beats_in_chapter
from src.bedrock.repositories.outline import get_beat_contract
from src.bedrock.style.template_repo import get_effective_fingerprint


@dataclass
class PolishPrompt:
    target_distribution: dict
    beat_contracts: list
    requirements: list = field(default_factory=lambda: [
        "对准目标分布（句长/段落长/感官等）", "保持剧情完整", "不压缩字数", "输出完整章节"])

    def to_string(self):
        lines = ["【风格润色任务】"]
        if self.target_distribution:
            lines.append("目标分布（对准此分布）：")
            for dim, dist in self.target_distribution.items():
                if dim.startswith("_"):
                    continue
                items = " | ".join(f"{k} {v:.0%}" for k, v in dist.items()) if isinstance(dist, dict) else str(dist)
                lines.append(f"  {dim}：{items}")
        else:
            lines.append("（无目标分布指纹——按通用网文风格）")
        lines.append("本章 beat 契约：")
        for c in self.beat_contracts:
            lines.append(f"  beat{c.get('beat_id')}: {c.get('purpose', '')}")
        lines.append("要求：" + " / ".join(self.requirements))
        return "\n".join(lines)


@dataclass
class RepairPrompt:
    violations: list
    fix_hints: list
    chapter_context: str = ""
    requirements: list = field(default_factory=lambda: [
        "只修改违规段落，不动其他", "不引入新的违规", "不压缩剧情", "输出完整章节"])

    def to_string(self):
        lines = [f"【定向修复任务】{self.chapter_context}"]
        lines.append("违规清单：")
        for v in self.fix_hints:
            lines.append(f"  - {v}")
        lines.append("要求：" + " / ".join(self.requirements))
        return "\n".join(lines)


def generate_polish_prompt(conn, chapter_id, volume_id):
    """正向润色 prompt：effective fingerprint + 本章 beat 契约。"""
    fp = get_effective_fingerprint(conn, volume_id) or {}
    # 去掉 _scope/_volume_id 元字段（to_string 已过滤，这里也清）
    target = {k: v for k, v in fp.items() if not k.startswith("_")} if fp else {}
    beat_contracts = []
    for beat in list_beats_in_chapter(conn, chapter_id):
        c = get_beat_contract(conn, volume_id, beat["id"])
        if c:
            beat_contracts.append(c)
    return PolishPrompt(target_distribution=target, beat_contracts=beat_contracts)


def generate_repair_prompt(violations, chapter_context=""):
    """定向修复 prompt：SP2 BeatViolation[]（含 fix_hint）。"""
    fix_hints = [v.fix_hint for v in violations if v.fix_hint]
    return RepairPrompt(violations=violations, fix_hints=fix_hints, chapter_context=chapter_context)
```

- [ ] **Step 4: 跑确认通过**（3 passed）+ 全量回归 → 73 + 3 = 76

- [ ] **Step 5: Commit**
```
git add src/bedrock/style/prompt_gen.py tests/bedrock/test_prompt_gen.py
git commit -m "feat(bedrock): structured polish/repair prompt generator

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review 自检

**1. Spec 覆盖**：
- §① lexicon → Task 1（感官词表 5 类 + notXisY regex）✓
- §② extractor 全 7 维度 → Task 2（句长/段落长/破折号/句号/对话/句式/感官直方图）✓
- §③ template_repo 两级 → Task 3（save_fingerprint 取数 chapter_ids→paragraph→extract；get_effective_fingerprint 两级 fallback _scope/_volume_id；list_fingerprints）✓
- §④ prompt_gen 结构化 → Task 4（PolishPrompt/RepairPrompt dataclass + to_string；generate_polish 取数 list_beats_in_chapter→get_beat_contract；generate_repair 用 BeatViolation.fix_hint）✓
- 句/段切分规则（[。！？]、paragraph.text）、感官平局（SENSORY_PRIORITY）、空输入全零 → Task 2 ✓

**2. Placeholder 扫描**：无 TBD/TODO；所有步骤完整代码 + 命令。

**3. 类型/签名一致性**：
- `extract_fingerprint(paragraphs: list[str]) -> dict`（Task 2；注意 spec 说 chapter_texts，plan 细化为 paragraphs 段落列表更准确——spec §四"跨段聚合=所有 paragraph.text 列表"支撑此细化）
- `save_fingerprint(conn, scope, chapter_ids, volume_id=None)` / `get_effective_fingerprint(conn, volume_id) -> dict|None` / `list_fingerprints(conn, scope=None)`（Task 3）
- `PolishPrompt(target_distribution, beat_contracts, requirements)` / `RepairPrompt(violations, fix_hints, chapter_context, requirements)` + `to_string()`（Task 4）
- `generate_polish_prompt(conn, chapter_id, volume_id) -> PolishPrompt` / `generate_repair_prompt(violations, chapter_context) -> RepairPrompt`（Task 4）
- SP1 `save_style_template(conn, fingerprint, source_works, sample_chapters)`（telemetry.py，Task 3 复用）
- SP1 `list_paragraphs_in_chapter` / `list_beats_in_chapter`、SP2 `get_beat_contract` / `BeatViolation`（均存在）✓

**4. 依赖顺序**：Task 1（lexicon）→ Task 2（extractor 用 lexicon）→ Task 3（template_repo 用 extractor + SP1）→ Task 4（prompt_gen 用 template_repo + SP2）。满足依赖。

**5. spec 细化说明**：extractor 输入从 spec 的 `chapter_texts` 细化为 `paragraphs`（段落列表）——spec §四"段落定义/跨段聚合"支撑，段落级维度（段落长/破折号/句号/对话/感官）需要段落列表，非章文本。save_fingerprint 内部 _gather_paragraphs 取 paragraph.text 列表传给 extractor。

---

## 执行交接

计划完成，保存于 `docs/superpowers/plans/2026-06-14-bedrock-sp3-style-edit.md`。两种执行方式：

**1. Subagent-Driven（推荐）** — 每 Task 派新子代理，任务间 review

**2. Inline Execution** — 当前会话用 executing-plans 批量 + checkpoint

选哪种？
