import re
from src.bedrock.style.lexicon import SENTENCE_STRUCTURE_PATTERNS

_CN_CHAR = re.compile(r"[一-鿿]")
# 从 SP3 lexicon 取 notXisY（域语义单一真相源，防与指纹提取器静默漂移）
_NOTXISY = re.compile(SENTENCE_STRUCTURE_PATTERNS["notXisY"])
_DASH = "——"
_PERIOD = "。"


def compute_grep_metrics(paragraphs):
    """段落文本列表 → grep 风格指标（authoritative，零 LLM）。
    返回 {
      notXisY_per_kchar: 否定转折句式计数/千字,
      dash_per_kchar: 破折号(——)计数/千字,
      period_density: 句号(。)数/汉字数,
    }。无汉字 → 全 0.0（period_density 防 0 除）。"""
    text = "".join(paragraphs)
    cn = len(_CN_CHAR.findall(text))
    if cn == 0:
        return {"notXisY_per_kchar": 0.0, "dash_per_kchar": 0.0, "period_density": 0.0}
    notxi = len(_NOTXISY.findall(text))
    dash = text.count(_DASH)
    period = text.count(_PERIOD)
    return {
        "notXisY_per_kchar": notxi / (cn / 1000),
        "dash_per_kchar": dash / (cn / 1000),
        "period_density": period / cn,
    }
