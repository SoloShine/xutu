import re

_CN_CHAR = re.compile(r"[一-鿿]")


def compute_word_count(paragraphs):
    """段落文本列表 → 汉字总数（排除标点/ASCII/空白）。空 → 0。"""
    return sum(len(_CN_CHAR.findall(p)) for p in paragraphs)
