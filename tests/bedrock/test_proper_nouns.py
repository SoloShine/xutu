from src.bedrock.checks.proper_nouns import find_proper_noun_variants


def test_edit_distance_variant_single_target_tier1():
    whitelist = {"chars": ["周执"], "places": ["北原"]}
    canonical_seen = {"周执", "北原"}   # 已在前文确立
    findings = find_proper_noun_variants("周植走了过来。", whitelist, canonical_seen)
    t1 = [f for f in findings if f["tier"] == "tier1"]
    assert any(f["variant"] == "周植" and f["canonical"] == "周执" for f in t1)


def test_ambiguous_common_word_tier2():
    whitelist = {"chars": ["周执"], "places": ["北原"]}
    canonical_seen = {"周执", "北原"}
    findings = find_proper_noun_variants("他去了北院。", whitelist, canonical_seen)
    t2 = [f for f in findings if f["tier"] == "tier2"]
    assert any(f["variant"] == "北院" for f in t2)
    assert not any(f["variant"] == "北院" and f["tier"] == "tier1" for f in findings)


def test_canonical_not_established_demotes_to_tier2():
    # 候选名未在前文出现 → 不自动改(tier2),即便形近
    whitelist = {"chars": ["周执"], "places": []}
    findings = find_proper_noun_variants("周植来了。", whitelist, canonical_seen=set())
    assert all(f["tier"] == "tier2" for f in findings)


def test_correct_name_no_finding():
    whitelist = {"chars": ["周执"], "places": []}
    assert find_proper_noun_variants("周执笑了。", whitelist, {"周执"}) == []
