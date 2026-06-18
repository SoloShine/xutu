# src/bedrock/style/extractor.py
import re
from src.bedrock.style.lexicon import (
    SENSORY_LEXICON, SENSORY_PRIORITY, SENTENCE_STRUCTURE_PATTERNS, RHETORIC_LEXICON,
)

_SENTENCE_SPLIT = re.compile(r"[。！？]")
_CN_CHAR = re.compile(r"[一-鿿]")
_QUOTE_CHARS = set("「」「」“”\"‘’''")
_NOTXISY = re.compile(SENTENCE_STRUCTURE_PATTERNS["notXisY"])
_RHETORIC_RE = re.compile("|".join(RHETORIC_LEXICON))


def count_notxisy(text):
    """段落级数 notXisY 命中(四变体:无标点/而是/逗号/句号分割)。
    须在整段上跑(非逐句),否则句号切句后"不是X。是Y"看不到。"""
    return len(_NOTXISY.findall(text))

# 维度定义(公式/含义/解读)。供 API/前端可解释化展示,也作开发者文档。
DIM_DEFINITIONS = {
    "sentence_length": {
        "label": "句子长度", "unit": "中文字数/句",
        "formula": "按 [。！？] 切句,统计每句中文字数分布",
        "interpret": "1-8字占比高=节奏快、短促;40+多=长句铺陈",
    },
    "paragraph_length": {
        "label": "段落长度", "unit": "中文字数/段",
        "formula": "每段中文字数分布",
        "interpret": "1-50字占比高=网文式一句一段;200+多=稠密长段",
    },
    "period": {
        "label": "句号(按段)", "unit": "。/段",
        "formula": "每段 。 个数(直方图;长度耦合,仅展示)",
        "interpret": "长段天然含更多。;跨作品不可靠。看 period_density 或 sentence_length",
    },
    "period_density": {
        "label": "句号密度", "unit": "。/千字",
        "formula": "全文 。 数 / 中文字数 × 1000(长度归一)",
        "interpret": "高=短句多(一句一段);与 sentence_length 互补(句号密度≈1/平均句长)",
    },
    "dialogue": {
        "label": "对白类型", "unit": "段落分类",
        "formula": "按引号字符占比: >15%=纯对话, >3%=混合, else 纯叙述",
        "interpret": "纯对话/混合/纯叙述 三类段占比",
    },
    "dialogue_ratio": {
        "label": "对白字数占比", "unit": "%",
        "formula": "引号内中文字数 / 全文中文字数",
        "interpret": "高=对白驱动;低=叙述驱动。比 dialogue 类型更精确",
    },
    "dash": {
        "label": "破折号(按段)", "unit": "——个数/段",
        "formula": "每段 —— 出现次数(直方图;长度耦合,仅展示)",
        "interpret": "长段天然含更多——跨作品不可靠。看 dash_density",
    },
    "dash_density": {
        "label": "破折号密度", "unit": "——/千字",
        "formula": "全文 —— 数 / 中文字数 × 1000(长度归一)",
        "interpret": "style-check 实际用这个;长度无关,跨作品可比。低=克制",
    },
    "structure": {
        "label": "句式", "unit": "句子分类",
        "formula": "notXisY=匹配'不是…是'句式;短句<8字;长句>25字;其余=其他",
        "interpret": "notXisY 应≈0(参考0.15%),偏高=偷懒句式",
    },
    "rhetoric": {
        "label": "修辞密度", "unit": "明喻词/千字",
        "formula": "明喻标记词(像/仿佛/宛如…)命中数 ÷ 千字",
        "interpret": "高=比喻密集(文气重);低=白描克制",
    },
    "sensory": {
        "label": "感官", "unit": "段落主导感官",
        "formula": "段内感官词表命中最多者(视/听/触/嗅/味),平局取优先级;无=无",
        "interpret": "无占比高=感官克制;视觉为主=画面感",
    },
}


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


def _dialogue_char_ratio(text):
    """引号内中文字数 / 全文中文字数(0-1)。无引号或无中文→0。"""
    total = _cn_len(text)
    if total == 0:
        return 0.0
    # 抓引号对内的文本(「」/“”/‘’/'')
    inner = []
    for op, cl in (("「", "」"), ("“", "”"), ("‘", "’"), ("'", "'"), ('"', '"')):
        i = 0
        while True:
            a = text.find(op, i)
            if a < 0:
                break
            b = text.find(cl, a + 1)
            if b < 0:
                break
            inner.append(text[a + 1:b])
            i = b + 1
    if not inner:
        return 0.0
    return _cn_len("".join(inner)) / total


def _rhetoric_density(text):
    """明喻标记词命中数 / 千字(浮点)。"""
    total = _cn_len(text)
    if total == 0:
        return 0.0
    return len(_RHETORIC_RE.findall(text)) / total * 1000


def extract_fingerprint(paragraphs):
    """paragraphs: 段落文本列表（跨章节所有 paragraph.text）。返回 9 维度直方图指纹。"""
    dims = ["sentence_length", "paragraph_length", "dash", "period",
            "dialogue", "dialogue_ratio", "rhetoric", "structure", "sensory"]
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
    dialogue_ratios = [_dialogue_char_ratio(p) for p in paragraphs]
    rhetoric_densities = [_rhetoric_density(p) for p in paragraphs]
    full_text = "".join(paragraphs)
    total_chars = _cn_len(full_text) or 1
    overall_dialogue_ratio = round(_dialogue_char_ratio(full_text), 4)
    overall_rhetoric = round(_rhetoric_density(full_text), 2)
    # dash/period 按【每千字】归一(长度无关),非按段——按段会与段落长度耦合(长段天然含更多)。
    overall_dash_per_k = round(full_text.count("——") / total_chars * 1000, 2)
    overall_period_per_k = round(full_text.count("。") / total_chars * 1000, 2)

    return {
        "sentence_length": _continuous_histogram(
            sentence_lengths, [8, 15, 25, 40], ["1-8", "9-15", "16-25", "26-40", "40+"]),
        "paragraph_length": _continuous_histogram(
            para_lengths, [50, 120, 200], ["1-50", "51-120", "121-200", "200+"]),
        "dash": _continuous_histogram(
            dash_counts, [0, 1, 2], ["0", "1", "2", "3+"]),
        "dash_density": {"value": overall_dash_per_k},   # /千字,长度归一(style-check 用这个,非 dash 直方图)
        "period": _continuous_histogram(
            period_counts, [2, 4, 6], ["1-2", "3-4", "5-6", "7+"]),
        "period_density": {"value": overall_period_per_k},  # /千字,长度归一
        "dialogue": _categorical_histogram(
            [_paragraph_dialogue_type(p) for p in paragraphs], ["纯对话", "混合", "纯叙述"]),
        # dialogue_ratio/rhetoric 给整体单一值(跨段汇总),非分段直方图
        "dialogue_ratio": {"value": overall_dialogue_ratio},
        "rhetoric": {"value": overall_rhetoric},
        "structure": _categorical_histogram(
            [_sentence_structure(s) for s in all_sentences],
            ["notXisY", "短句", "长句", "其他"]),
        "sensory": _categorical_histogram(
            [_paragraph_sensory(p) for p in paragraphs],
            SENSORY_PRIORITY + ["无"]),
    }
