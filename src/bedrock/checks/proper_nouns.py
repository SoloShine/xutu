# src/bedrock/checks/proper_nouns.py
"""专名硬校验(确定性,零 LLM)。Unit D。

白名单=character.name+location.name;检测形近/音近变体;分层 Tier-1 自动改 / Tier-2 escalate。
原则:auto-edit 只在【单一候选 + 规范名已在前文/本章确立 + 非歧义常用词】时执行,且必留 flag 痕迹供卷审。

候选生成只认【精选 confusable 映射】(同偏旁/同音字),**不**用裸 edit-distance-1 —— 否则中文 2 字
专名会把每个恰好差 1 字的常用词都当变体(如 昼夜→沈夜、钟声→钟摆),整章 prose 被自动改坏。
裸 edit-distance-1 仍会触发检测(进 escalate,tier2,不自动改),兼顾召回与安全。
"""
import re

# 精选 confusable(可扩展):规范字 → 易混淆变体字集(同偏旁/同音)
_CONFUSABLE = {
    "执": {"植", "直"},
    "原": {"院", "苑"},
    "韩": {"寒", "含"},
    "峥": {"争", "铮"},
    "渊": {"深"},
}
# 歧义词:本身是常用词,即便形近白名单也只 escalate 不自动改(Tier-2)
_AMBIGUOUS = {"北院", "北苑", "中原", "南院", "南山"}


def _edit_distance_one(a: str, b: str) -> bool:
    """长度相同且恰好差 1 字(专名多 2-3 字够用)。"""
    if len(a) != len(b) or a == b:
        return False
    return sum(1 for x, y in zip(a, b) if x != y) == 1


def _confusable_of(canon: str):
    """canon 经 confusable 替换能生成的变体集合(如 周执→{周植,周直})。"""
    out = set()
    for i, ch in enumerate(canon):
        for good, bads in _CONFUSABLE.items():
            if ch == good:
                for b in bads:
                    out.add(canon[:i] + b + canon[i + 1:])
    return out


def _candidates_for(tok, canon_all):
    """tok 形近哪些白名单名。

    confusable 命中 → 可作 tier-1 自动改候选(精选映射,误伤低)。
    裸 edit-distance-1 命中 → 仅 tier-2 escalate(太宽,易把常用词当变体,不自动改)。
    返回 (confusable_cands, ed1_cands)。"""
    conf, ed1 = [], []
    for c in canon_all:
        if c == tok:
            continue
        if tok in _confusable_of(c):
            conf.append(c)
        if _edit_distance_one(tok, c):
            ed1.append(c)
    return conf, ed1


def find_proper_noun_variants(text, whitelist, canonical_seen):
    """扫 text,返回变体 finding 列表。

    whitelist={"chars":[...],"places":[...]}; canonical_seen=本章/前序已出现的规范名集合。
    finding={variant, canonical, tier}。tier1=【confusable单目标+已确立+非歧义】;tier2=其余(多义/未确立/歧义词/裸ed1)。
    """
    canon_all = list(whitelist.get("chars", [])) + list(whitelist.get("places", []))
    findings = []
    seen = set()  # 同一变体只报一次
    for canon in canon_all:
        L = len(canon)
        if L == 0:
            continue
        for i in range(len(text) - L + 1):
            tok = text[i:i + L]
            if tok in seen:
                continue
            conf, ed1 = _candidates_for(tok, canon_all)
            if not conf and not ed1:
                continue
            seen.add(tok)
            # 自动改(tier1)只认 confusable 命中:单目标 + 规范名已确立 + 非歧义常用词
            if len(conf) == 1 and conf[0] in canonical_seen and tok not in _AMBIGUOUS:
                findings.append({"variant": tok, "canonical": conf[0], "tier": "tier1"})
            else:
                # 多候选 / 未确立 / 歧义词 / 仅裸 ed1 命中 → escalate
                all_cands = conf or ed1
                findings.append({"variant": tok, "canonical": "|".join(all_cands), "tier": "tier2"})
    return findings

