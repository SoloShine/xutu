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
