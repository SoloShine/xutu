# tests/bedrock/test_prose_hygiene.py
from src.bedrock.checks.prose_hygiene import is_meta_paragraph, sanitize_prose

def test_detects_metric_self_report():
    assert is_meta_paragraph("草案现在符合指标要求：0个破折号，对话占比 35.7%")

def test_detects_polish_narration():
    assert is_meta_paragraph("润色版本已完成，剔除了所有“不是A是B”句式，删除了非必要的破折号。")

def test_detects_file_path():
    assert is_meta_paragraph("D:\\novel_test\\projects\\vigilia\\bedrock.db (truth source")
    assert is_meta_paragraph("导出路径 C:/x/y.db")

def test_detects_separator_only():
    assert is_meta_paragraph("---")
    assert is_meta_paragraph("***")

def test_does_not_flag_real_prose():
    assert not is_meta_paragraph("林昭把第十六个小时的工牌翻了过去。")
    assert not is_meta_paragraph("“准点。”她说，“您的窗口还有四十七分钟。”")

def test_sanitize_strips_leading_trailing_mid_meta_keeps_prose():
    raw = ("草案符合指标：0破折号。\n\n"
           "天没亮，林昭就醒了。\n\n"
           "她照了照镜子。\n\n"
           "D:\\novel_test\\projects\\vigilia\\bedrock.db")
    cleaned, removed, preview = sanitize_prose(raw)
    assert "天没亮" in cleaned and "照了照镜子" in cleaned
    assert "草案符合指标" not in cleaned and "bedrock.db" not in cleaned
    assert removed == 2
