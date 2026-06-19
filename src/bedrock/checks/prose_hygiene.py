# src/bedrock/checks/prose_hygiene.py
"""正文卫生:检测并剥离 agent 泄入 paragraph 的元文本(指标自评/润色汇报/路径/分隔符)。
确定性,零 LLM。Unit A1 —— A0 定界提取的兜底,commit-paragraphs 与 L2 non_prose 共用。"""
import re

# 实测泄漏签名(vigilia ch2/3/6/8/10 + ch12 分隔符)
_META_PATTERNS = [
    re.compile(r"指标|破折号|对话占比|修辞.{0,3}密度|明喻.{0,4}像|检查破折号"),
    re.compile(r"草案.{0,6}符合|润色版本|符合.{0,4}要求|唯一的顾虑|我(删除|修改|调整)"),
    re.compile(r"[A-Za-z]:[\\/]|projects/[^ ]*\.db|\.db\b"),
    re.compile(r"^(-{3,}|\*{3,}|\* \* \*|—{2,})$"),          # 纯分隔符段
    re.compile(r"^```|```$"),                                  # 围栏残留
]

MIN_PROSE_CHARS = 500  # 清洗后正文下限(与 spec 阈值一致)


def is_meta_paragraph(text: str) -> bool:
    """单段是否为元文本(非正文)。空段视为 meta(将被剥除)。"""
    t = (text or "").strip()
    if not t:
        return True
    return any(p.search(t) for p in _META_PATTERNS)


def sanitize_prose(raw: str):
    """剥离所有 meta 段(leading/trailing/mid),返回 (cleaned, removed_count, preview)。
    preview = 移除段前 3 段截断,供日志。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", raw.strip()) if p.strip()]
    kept = [p for p in paras if not is_meta_paragraph(p)]
    removed = len(paras) - len(kept)
    preview = [p[:40] for p in paras if is_meta_paragraph(p)][:3]
    cleaned = "\n\n".join(kept)
    return cleaned, removed, preview
