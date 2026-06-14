from src.bedrock.checks.word_count import compute_word_count


def test_empty_returns_zero():
    assert compute_word_count([]) == 0


def test_counts_chinese_chars_only():
    # 7 汉字（他来了然后走了）+ 标点 → 只计汉字
    assert compute_word_count(["他来了，然后走了。"]) == 7


def test_multiple_paragraphs_summed():
    assert compute_word_count(["他来了。", "她走了。"]) == 6


def test_no_chinese_returns_zero():
    assert compute_word_count(["abc 123 !!!"]) == 0
