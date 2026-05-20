"""
后置校验模块：生成后程序化检查约束，替代prompt中的威慑指令
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Violation:
    constraint_type: str   # "character_name" | "structure" | "style" | "length"
    severity: str          # "error" | "warning"
    detail: str
    fix: Optional[str] = None


@dataclass
class ValidationResult:
    passed: bool
    violations: List[Violation] = field(default_factory=list)
    fixed_text: Optional[str] = None


# ========== 人名校验 ==========

# 对话标记提取：从"XX说/道"等模式中提取人名
# 要求动词后紧跟冒号/引号，排除"第二道划痕"等量词用法
_DIALOG_NAME_RE = re.compile(
    r'([一-鿿]{2,4})'
    r'(说|道|喊|问|回答|笑|低声|沉声|叫|吼|叹|应)'
    r'[:：“""]'
)


def _extract_names_from_dialogue(text):
    """从对话标签中提取人名（高精度）"""
    candidates = set()
    for m in _DIALOG_NAME_RE.finditer(text):
        candidates.add(m.group(1))
    return candidates


def _fuzzy_match(name, known_names):
    """模糊匹配：子串包含 + 单字编辑距离"""
    for kn in known_names:
        if name == kn:
            return kn
        if kn in name or name in kn:
            return kn
        if len(name) == len(kn):
            diffs = sum(1 for a, b in zip(name, kn) if a != b)
            if diffs == 1:
                return kn
    return None


def validate_character_names(text, known_names):
    """校验文本中的人名是否与图谱一致"""
    violations = []
    if not known_names:
        return violations

    known_set = set(known_names)

    # 已知人物出现检查
    for kn in known_names:
        if kn not in text:
            violations.append(Violation(
                constraint_type="character_name",
                severity="warning",
                detail=f"已知人物'{kn}'未在本章出现",
            ))

    # 对话标签提取（高精度）
    found = _extract_names_from_dialogue(text)
    for name in found:
        if name in known_set:
            continue
        matched = _fuzzy_match(name, known_set)
        if matched:
            violations.append(Violation(
                constraint_type="character_name",
                severity="error",
                detail=f"人名'{name}'与图谱不一致",
                fix=matched,
            ))
        else:
            violations.append(Violation(
                constraint_type="character_name",
                severity="warning",
                detail=f"对话中出现未知人名'{name}'（不在图谱人物列表中）",
            ))

    return violations


def apply_name_fixes(text, violations):
    """自动替换人名"""
    for v in violations:
        if v.fix:
            text = text.replace(v.detail.split("'")[1], v.fix)
    return text


# ========== 结构校验 ==========

def _count_timeline_switches(text, known_characters=None):
    """统计时间线切换次数（基于人物在段落中的出现模式）
    intercut章节的特征：不同人物交替出现（A→B→A→B来回切换）
    linear章节的特征：人物连续出现或单向切换（A→B→C）
    """
    paragraphs = [p.strip() for p in text.split('\n') if p.strip() and len(p.strip()) > 30]
    if len(paragraphs) < 3:
        return 0

    # 提取每段中出现的人物
    char_sequence = []
    for p in paragraphs:
        if known_characters:
            chars = frozenset(name for name in known_characters if name in p)
        else:
            chars = frozenset()
        if chars:
            char_sequence.append(chars)

    if len(char_sequence) < 3:
        return 0

    # 检测来回切换：某人物消失后再次出现
    # 对每个人物，统计其"重新出现"次数（出现→消失→再出现算1次切换）
    switches = 0
    for name in (known_characters or []):
        was_present = False
        disappeared = False
        for chars in char_sequence:
            present = name in chars
            if present and disappeared:
                switches += 1
                disappeared = False
            elif not present and was_present:
                disappeared = True
            was_present = present

    return switches


def validate_structure(text, arc, known_characters=None, config=None):
    """校验非线性叙事结构是否实际执行"""
    structure_cfg = (config or {}).get("structure", {})
    violations = []
    if not arc:
        return violations

    structure_type = arc.get("structure_type", "linear")
    if not structure_type or structure_type == "linear":
        return violations

    switches = _count_timeline_switches(text, known_characters)

    if structure_type == "intercut":
        if switches < structure_cfg.get("intercut_min", 2):
            violations.append(Violation(
                constraint_type="structure",
                severity="error",
                detail=f"intercut结构要求至少2次场景切换，实际检测到{switches}次",
            ))

    elif structure_type == "flashback":
        if switches < structure_cfg.get("flashback_min", 1):
            violations.append(Violation(
                constraint_type="structure",
                severity="error",
                detail=f"flashback结构要求至少1次时间跳转，未检测到场景切换",
            ))

    elif structure_type == "parallel":
        if switches < structure_cfg.get("parallel_min", 2):
            violations.append(Violation(
                constraint_type="structure",
                severity="error",
                detail=f"parallel结构要求至少2条交替线索，实际检测到{switches}次切换",
            ))

    return violations


# ========== 风格校验 ==========

_STYLE_PATTERNS = {
    "ban_inner_monologue": [
        (r'他想(起|到|着)?', '内心独白标记"他想"'),
        (r'她想(起|到|着)?', '内心独白标记"她想"'),
        (r'心想', '内心独白标记"心想"'),
        (r'暗想', '内心独白标记"暗想"'),
        (r'(他|她)觉得', '内心感受标记"觉得"'),
        (r'(他|她)感到', '内心感受标记"感到"'),
        (r'心中(暗|一)?(想|惊|喜|怒|悲|叹|明白|清楚)', '内心活动标记'),
        (r'内心(深处)?(涌起|泛起|升起|闪过)', '内心活动标记'),
    ],
    "hardboiled_dialogue": [
        (r'["""].*?["""].*?(愤怒地|悲伤地|惊讶地|恐惧地|高兴地|激动地|冷淡地|温柔地|阴沉地).{0,4}(说|回答|问|喊|低声|沉声)', '带情绪副词的对话标签'),
    ],
}


def validate_style(text, style_rules):
    """校验风格指南遵守情况（仅warning）"""
    violations = []
    if not style_rules:
        return violations

    rule_ids = [r.get("id", "") for r in style_rules]

    for rule_id, patterns in _STYLE_PATTERNS.items():
        if rule_id not in rule_ids:
            continue
        for pattern, desc in patterns:
            matches = re.findall(pattern, text)
            if matches:
                violations.append(Violation(
                    constraint_type="style",
                    severity="warning",
                    detail=f"{desc}：出现{len(matches)}次",
                ))

    return violations


# ========== 禁用句式校验 ==========

def validate_forbidden_patterns(text, config):
    """校验禁用句式模式（error级别）"""
    violations = []
    patterns = (config or {}).get("validation", {}).get("forbidden_patterns", [])
    if not patterns:
        return violations

    for fp in patterns:
        pattern = fp.get("pattern", "")
        max_count = fp.get("max_per_chapter", 1)
        desc = fp.get("description", pattern)
        matches = re.findall(pattern, text)
        if len(matches) > max_count:
            violations.append(Violation(
                constraint_type="forbidden_pattern",
                severity="error",
                detail=f"禁用句式超标：「{desc}」出现{len(matches)}次（上限{max_count}次）",
            ))
    return violations


# ========== 篇幅校验 ==========

def _count_chinese_chars(text):
    """统计中文字符数（去空白标点）"""
    # Remove whitespace, punctuation, and special characters
    cleaned = re.sub(r'[\s　-〿＀-￯ -⁯-ÿ\n\r\t]', '', text)
    return len(cleaned)


def validate_length(text, min_words=2500, max_words=3500):
    """校验篇幅"""
    violations = []
    count = _count_chinese_chars(text)
    if count < min_words:
        violations.append(Violation(
            constraint_type="length",
            severity="warning",
            detail=f"篇幅不足：{count}字（目标{min_words}-{max_words}字）",
        ))
    return violations


# ========== 编排 ==========

def validate_chapter(text, context, arc=None, config=None):
    """运行全部校验"""
    violations = []

    # 人名
    known_names = [c["name"] for c in context.get("characters", [])]
    violations.extend(validate_character_names(text, known_names))

    # 结构
    if arc:
        violations.extend(validate_structure(text, arc, known_characters=known_names,
                                             config=config))

    # 风格
    violations.extend(validate_style(text, context.get("style_guides", [])))

    # 禁用句式
    violations.extend(validate_forbidden_patterns(text, config))

    # 篇幅
    writing_cfg = (config or {}).get("writing", {})
    violations.extend(validate_length(text,
                                      min_words=writing_cfg.get("min_words", 2500),
                                      max_words=writing_cfg.get("max_words", 3500)))

    # 自动修复人名
    fixed_text = None
    name_fixes = [v for v in violations if v.constraint_type == "character_name" and v.fix]
    if name_fixes:
        fixed_text = apply_name_fixes(text, name_fixes)

    has_errors = any(v.severity == "error" for v in violations)
    return ValidationResult(
        passed=not has_errors,
        violations=violations,
        fixed_text=fixed_text,
    )
