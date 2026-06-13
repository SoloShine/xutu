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
