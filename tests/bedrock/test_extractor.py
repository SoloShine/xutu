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
    fp = extract_fingerprint(["短。", "这是一段中等长度的段落文字，必须超过五十个汉字才能落入中段区间，所以这里继续补充一些描述性内容用于确保测试通过。", "短。"])
    # 至少有 "1-50" 和 "51-120" 两类
    assert fp["paragraph_length"]["1-50"] > 0
    assert fp["paragraph_length"]["51-120"] > 0


def test_dash_distribution():
    fp = extract_fingerprint(["无破折号段落。", "有——破折号。", "两——个——破折号。"])
    assert fp["dash"]["0"] > 0
    assert fp["dash"]["1"] > 0
    assert fp["dash"]["2"] > 0


def test_dialogue_detection():
    fp = extract_fingerprint(["他说：“你好。”然后转身。", "纯叙述没有引号。"])
    assert fp["dialogue"]["混合"] > 0 or fp["dialogue"]["纯对话"] > 0
    assert fp["dialogue"]["纯叙述"] > 0


def test_notXisY_structure():
    fp = extract_fingerprint(["不是因为他累，是因为他想家。普通的句子。"])
    assert fp["structure"]["notXisY"] > 0


def test_sensory_dominance():
    fp = extract_fingerprint(["他看见远处的光。", "听到一声巨响。"])
    assert fp["sensory"]["视觉"] > 0
    assert fp["sensory"]["听觉"] > 0
