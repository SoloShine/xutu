from src.bedrock.checks.prose_hygiene import extract_prose_block


def test_extract_tagged_prose_block_ignores_outside():
    raw = "我先想了一下。\n```prose\n天没亮，林昭就醒了。\n```\n指标：0破折号。"
    assert extract_prose_block(raw) == "天没亮，林昭就醒了。"


def test_multiple_blocks_take_longest():
    raw = "```prose\n短。\n```\n```prose\n这是更长的正文段落。\n```"
    assert extract_prose_block(raw) == "这是更长的正文段落。"


def test_plain_fence_not_counted():
    # 普通三反引号围栏(无 prose 标签)不算,返回 None(触发回退)
    assert extract_prose_block("```\n天没亮。\n```") is None


def test_no_block_returns_none():
    assert extract_prose_block("天没亮，林昭就醒了。") is None
