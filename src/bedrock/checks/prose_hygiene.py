# src/bedrock/checks/prose_hygiene.py
"""正文卫生:检测并剥离 agent 泄入 paragraph 的元文本(指标自评/润色汇报/路径/分隔符)。
确定性,零 LLM。Unit A1 —— A0 定界提取的兜底,commit-paragraphs 与 L2 non_prose 共用。"""
import re

# 实测泄漏签名(vigilia ch2/3/6/8/10 + ch12 分隔符)
_META_PATTERNS = [
    # 指标自评:必须带"计数/达标/占比"语境,避免误伤正文里提到"破折号/指标"的叙述
    re.compile(r"符合指标|指标.{0,8}(达标|符合|为|占比|个|率)|对话占比|修辞.{0,3}密度|"
               r"明喻.{0,6}(密度|个|处|过多|降低|删除|率)|检查破折号|"
               r"破折号.{0,6}(个|率|达标|符合|过多|删除|降低|为\d)"),
    # 草案/润色汇报 + 风格编辑动作(须涉及文风元素,避免误伤"我修改了主意")
    re.compile(r"草案.{0,6}符合|润色版本|符合.{0,4}要求|"
               r"我(删除|修改|调整)了?.{0,12}(破折号|句式|段|明喻|修辞|占比|指标|分隔符)|"
               r"删除.{0,6}(分隔符|---|`{3})|剔除.{0,8}(句式|破折号|修辞)"),
    # 文件路径(盘符+至少2字符路径,或 .db 文件)
    re.compile(r"[A-Za-z]:[\\/]\S{2,}|projects/[^ ]*\.db|\.db\b"),
    # 纯分隔符段
    re.compile(r"^(-{3,}|\*{3,}|\* \* \*|—{2,})$"),
    # 围栏残留
    re.compile(r"^```|```$"),
]

_PROSE_BLOCK = re.compile(r"```prose[ \t]*\n(.*?)\n```", re.DOTALL)


def extract_prose_block(raw: str):
    """提取 ```prose 标签围栏区内容。多个取最长;无标签区返回 None(由调用方回退 sanitize)。"""
    matches = _PROSE_BLOCK.findall(raw or "")
    if not matches:
        return None
    return max(matches, key=len).strip()


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
