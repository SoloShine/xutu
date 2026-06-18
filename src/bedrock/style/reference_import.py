# src/bedrock/style/reference_import.py
"""外部参考作品 txt → 文风指纹 + 派生文风指令(纯程序,零 LLM)。

支持:
- 多种章节标记(第N章/节/回、Chapter N、卷N);非标准→按字数切块兜底。
- 可选章节范围 [start,end](前后文风不同时,只取代表性中段)。
- 动态抽样:按章数自适应(小作品少抽、大作多抽),可被 chapter_range 覆盖。
- derive_directive:从指纹把数字翻译成定性指令草稿(节奏/对白/破折号/修辞/感官)。
"""
import re

# 多种章节首行标记(任一命中即切章)
_CHAPTER_HEADS = re.compile(
    r"^[\s　]*(?:"
    r"第[一二三四五六七八九十百千零0-9]+[章节回卷]"   # 第3章 / 第三节 / 第十回
    r"|[Cc]hapter\s*\d+"                                # Chapter 3
    r"|[0-9]{1,4}[、.\s]"                               # 3、 / 3. (数字标题)
    r")"
)
_INDENT = "　"
_CHAR_CHUNK = 3000   # 无章节标记时,按此字数切块


def split_chapters(text):
    """全文 → [(title, body)]。先按章节标记;标记太少(<3)→按字数切块兜底。"""
    chapters, cur_title, cur_lines = [], None, []
    for line in text.splitlines():
        if _CHAPTER_HEADS.match(line.strip()):
            if cur_title is not None:
                chapters.append((cur_title, "\n".join(cur_lines)))
            cur_title, cur_lines = line.strip(), []
        else:
            cur_lines.append(line)
    if cur_title is not None:
        chapters.append((cur_title, "\n".join(cur_lines)))
    if len(chapters) < 3:
        # 非标准章名:按字数切块
        return _char_chunks(text)
    return chapters


def _char_chunks(text):
    """无标准章节标记→按字数切块(每块 ~_CHAR_CHUNK 字,按段落边界对齐)。"""
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur, n = [], [], 0
    for p in paras:
        cur.append(p); n += len(p)
        if n >= _CHAR_CHUNK:
            chunks.append((f"块{len(chunks)+1}", "\n".join(cur))); cur, n = [], 0
    if cur:
        chunks.append((f"块{len(chunks)+1}", "\n".join(cur)))
    return chunks or [("全篇", text)]


def chapter_paragraphs(body):
    out = []
    for line in body.splitlines():
        s = line.strip().lstrip(_INDENT).strip()
        if not s:
            continue
        if s.startswith(("搜书吧", "www.", "http", "手机用户", "本章未完", "作者：", "作者:", "简介")):
            continue
        out.append(s)
    return out


def sample_chapter_indices(n_chapters, sample, chapter_range=None, edge_skip=10):
    """抽章节下标。chapter_range=[start,end](1-based 闭区间)→只在范围内均匀抽 sample 章;
    无 range→跳首尾 edge_skip 取中段。sample=None→动态(约 sqrt(n)*2,封 [10,40])。"""
    if chapter_range:
        lo = max(0, min(chapter_range[0] - 1, n_chapters - 1))
        hi = max(lo + 1, min(chapter_range[1], n_chapters))
    else:
        lo = min(edge_skip, max(0, n_chapters - 1))
        hi = max(lo + 1, n_chapters - edge_skip)
    span = hi - lo
    if sample is None:
        sample = max(10, min(40, int(span ** 0.5) * 2))
    if span <= sample:
        return list(range(lo, hi))
    step = span / sample
    return [lo + int(i * step) for i in range(sample)]


def import_and_extract(text, sample=None, chapter_range=None):
    """全文 → (fingerprint, meta)。纯程序。chapter_range=[start,end] 1-based。"""
    from src.bedrock.style.extractor import extract_fingerprint
    chapters = split_chapters(text)
    idxs = sample_chapter_indices(len(chapters), sample, chapter_range)
    paragraphs = []
    for i in idxs:
        paragraphs.extend(chapter_paragraphs(chapters[i][1]))
    fp = extract_fingerprint(paragraphs)
    return fp, {
        "chapter_count": len(chapters),
        "sampled_chapters": len(idxs),
        "paragraph_count": len(paragraphs),
        "sample_range": [idxs[0] + 1, idxs[-1] + 1] if idxs else None,
    }


def pick_reference_sample(text, points=(0.15, 0.4, 0.65, 0.9), per_chapter=1500, max_chars=6000):
    """取代表性正文样本供 LLM 文风分析(持久化)。
    多点分散(默认 15/40/65/90% 四点,跳极首尾的非典型段)+ 每章截 per_chapter,
    共 ~max_chars。实证:分散取样比"连续3中章"更接近全量分布(连续易命中单一弧致偏)。
    """
    chapters = split_chapters(text)
    if not chapters:
        return text[:max_chars]
    n = len(chapters)
    idxs = [min(int(p * n), n - 1) for p in points]
    parts, total = [], 0
    for i in idxs:
        seg = [chapter_paragraphs(chapters[i][1])[:30]]
        chunk = ("【" + chapters[i][0] + "】\n" + "\n".join(seg[0]))[:per_chapter]
        parts.append(chunk)
        total += len(chunk)
        if total >= max_chars:
            break
    return "\n\n".join(parts)[:max_chars]


def preview_chapters(text):
    """预览:切章信息(总章数、是否切片兜底、样章标题、总字数),不提取不存。"""
    chapters = split_chapters(text)
    # 切片兜底判别:标题形如"块N"或"全篇"
    chunked = bool(chapters) and chapters[0][0].startswith(("块", "全篇"))
    titles = [c[0][:30] for c in chapters[:6]]
    return {
        "chapter_count": len(chapters),
        "chunked": chunked,   # True=非标准章名,按字数切片
        "sample_titles": titles,
        "total_chars": len(text),
    }


# 编码探测:utf-8 → gb18030(兼容 gbk),取替换符最少的。
def decode_bytes(raw):
    best, best_repl = None, 1e9
    for enc in ("utf-8", "gb18030", "utf-16"):
        try:
            t = raw.decode(enc)
            repl = t.count("�")
            if repl < best_repl:
                best, best_repl = t, repl
        except Exception:
            continue
    return best or raw.decode("utf-8", errors="replace")


# ── 从指纹派生定性文风指令草稿(纯程序:数字→文字)──
def derive_directive(fp):
    """把 9 维指纹翻译成一段定性文风指令(节奏/段式/对白/破折号/修辞/感官)。
    纯程序派生,作 directive 草稿——比纯数字直观,但不如 LLM 能抓"气质",用户可润色。"""
    if not fp:
        return ""
    bits = []
    sl = fp.get("sentence_length", {})
    st = fp.get("structure", {})
    short = (sl.get("1-8", 0) + sl.get("9-15", 0))
    long_ = sl.get("26-40", 0) + sl.get("40+", 0)
    if short > 0.55:
        bits.append("短句为主、节奏快")
    elif long_ > 0.35:
        bits.append("长句铺陈、节奏舒缓")
    else:
        bits.append("长短句交替、节奏中等")
    pl = fp.get("paragraph_length", {})
    if pl.get("1-50", 0) > 0.8:
        bits.append("一句一段的网文式断行")
    elif pl.get("200+", 0) > 0.1:
        bits.append("长段稠密")
    dlg = fp.get("dialogue_ratio", {}).get("value", 0)
    if dlg > 0.3:
        bits.append("对白驱动")
    elif dlg < 0.15:
        bits.append("叙述为主、对白简省")
    else:
        bits.append("叙对平衡")
    dash0 = fp.get("dash", {}).get("0", 1)
    if dash0 > 0.9:
        bits.append("几乎不用破折号")
    elif dash0 < 0.7:
        bits.append("破折号较多(慎仿)")
    rhet = fp.get("rhetoric", {}).get("value", 0)
    if rhet > 5:
        bits.append("比喻浓密、文气重")
    elif rhet < 2.5:
        bits.append("白描克制")
    sens = fp.get("sensory", {})
    if sens.get("无", 0) > 0.6:
        bits.append("感官克制")
    elif sens.get("视觉", 0) > 0.3:
        bits.append("画面感强")
    notx = st.get("notXisY", 0)
    if notx > 0.01:
        bits.append('注意:少量「不是A是B」句式')
    return "；".join(bits) + "。"
