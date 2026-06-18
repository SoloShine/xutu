# src/bedrock/style/reference_import.py
"""外部参考作品 txt → 文风指纹(纯程序,零 LLM)。

拆章 → 中段抽样 → 段落 → extract_fingerprint。CLI 与工作台 API 共用此模块。
提取即 regex/计数/直方图,不调任何模型,瞬时完成。
"""
import re

_CHAPTER_HEAD = re.compile(r"^[\s　]*第[一二三四五六七八九十百千零0-9]+[章节回][^\n]*$")
_INDENT = "　"


def split_chapters(text):
    """txt 全文 → [(title, body), ...]。按章首行切。无章节标记→整篇作一章。"""
    chapters, cur_title, cur_lines = [], None, []
    for line in text.splitlines():
        if _CHAPTER_HEAD.match(line.strip()):
            if cur_title is not None:
                chapters.append((cur_title, "\n".join(cur_lines)))
            cur_title, cur_lines = line.strip(), []
        else:
            cur_lines.append(line)
    if cur_title is not None:
        chapters.append((cur_title, "\n".join(cur_lines)))
    if not chapters:
        # 无章节标记:整篇当一章
        chapters = [("全篇", text)]
    return chapters


def chapter_paragraphs(body):
    """章正文 → 段落文本列表(剥缩进、弃空行/水印)。"""
    out = []
    for line in body.splitlines():
        s = line.strip().lstrip(_INDENT).strip()
        if not s:
            continue
        if s.startswith(("搜书吧", "www.", "http", "手机用户", "本章未完", "作者：", "作者:")):
            continue
        out.append(s)
    return out


def sample_chapter_indices(n_chapters, sample, edge_skip=10):
    """中段均匀抽样 sample 章(跳首尾 edge_skip,序言/收尾非典型)。"""
    lo = min(edge_skip, max(0, n_chapters - 1))
    hi = max(lo + 1, n_chapters - edge_skip)
    if hi - lo <= sample:
        return list(range(lo, hi))
    step = (hi - lo) / sample
    return [lo + int(i * step) for i in range(sample)]


def import_and_extract(text, sample=25):
    """全文 → (fingerprint, meta)。纯程序提取。"""
    from src.bedrock.style.extractor import extract_fingerprint
    chapters = split_chapters(text)
    idxs = sample_chapter_indices(len(chapters), sample)
    paragraphs = []
    for i in idxs:
        paragraphs.extend(chapter_paragraphs(chapters[i][1]))
    fp = extract_fingerprint(paragraphs)
    return fp, {
        "chapter_count": len(chapters),
        "sampled_chapters": len(idxs),
        "paragraph_count": len(paragraphs),
    }
