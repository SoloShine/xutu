"""从外部参考作品 txt 提取文风指纹 → 写入目标项目的 style_template。

用途:给作品指定一个"对标文风"——extractor 从参考样章算 7 维度分布(句长/段长/破折号/
句号/对白/句式[含 notXisY]/感官),Polish 阶段据此把正文往参考文风微调。

用法:
  python scripts/extract_reference_style.py \
      --txt "D:/tmp/某作品.txt" --project projects/voidwright \
      [--sample 25] [--scope work|volume] [--volume-id 1] [--encoding utf-8]

拆分:按 `^第N章` 切章;章内按行切段(剥全角空格缩进、弃空行/标题行)。
抽样:跳过首尾各 10 章(序言/收尾非典型),从中段均匀取 --sample 章,凑足代表性语料。
"""
import argparse
import json
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.telemetry import save_style_template
from src.bedrock.style.extractor import extract_fingerprint

_CHAPTER_HEAD = re.compile(r"^[\s　]*第[一二三四五六七八九十百千零0-9]+[章节回][^\n]*$")
_INDENT = "　"  # 全角空格


def split_chapters(text):
    """txt 全文 → [(title, body), ...]。按章首行切。"""
    chapters = []
    cur_title, cur_lines = None, []
    for line in text.splitlines():
        if _CHAPTER_HEAD.match(line.strip()):
            if cur_title is not None:
                chapters.append((cur_title, "\n".join(cur_lines)))
            cur_title, cur_lines = line.strip(), []
        else:
            cur_lines.append(line)
    if cur_title is not None:
        chapters.append((cur_title, "\n".join(cur_lines)))
    return chapters


def chapter_paragraphs(body):
    """章正文 → 段落文本列表(剥缩进、弃空行)。"""
    out = []
    for line in body.splitlines():
        s = line.strip().lstrip(_INDENT).strip()
        if not s:
            continue
        # 弃章首重复标题、作者声明、搜书吧水印行
        if s.startswith(("搜书吧", "www.", "http", "手机用户", "本章未完")):
            continue
        out.append(s)
    return out


def sample_chapter_indices(n_chapters, sample, edge_skip=10):
    """中段均匀抽样 sample 章(跳首尾 edge_skip)。"""
    lo = min(edge_skip, max(0, n_chapters - 1))
    hi = max(lo + 1, n_chapters - edge_skip)
    if hi - lo <= sample:
        return list(range(lo, hi))
    step = (hi - lo) / sample
    return [lo + int(i * step) for i in range(sample)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--txt", type=Path, required=True)
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--sample", type=int, default=25, help="抽样章数(中段)")
    ap.add_argument("--scope", choices=["work", "volume"], default="work")
    ap.add_argument("--volume-id", type=int, default=None)
    ap.add_argument("--encoding", default="utf-8")
    ap.add_argument("--dry-run", action="store_true", help="只提取打印,不写库")
    args = ap.parse_args()

    text = args.txt.read_text(encoding=args.encoding, errors="replace")
    chapters = split_chapters(text)
    if not chapters:
        sys.exit("未切出任何章节(检查章节正则/编码)")
    idxs = sample_chapter_indices(len(chapters), args.sample)
    paragraphs = []
    for i in idxs:
        paragraphs.extend(chapter_paragraphs(chapters[i][1]))
    print(f"参考《{args.txt.name}》: {len(chapters)} 章, 抽样 {len(idxs)} 章 → {len(paragraphs)} 段")

    fp = extract_fingerprint(paragraphs)
    fp["_scope"] = args.scope
    if args.scope == "volume" and args.volume_id is not None:
        fp["_volume_id"] = args.volume_id
    fp["_source_work"] = args.txt.stem

    print("\n提取指纹(7维度,粗略比例):")
    for dim, dist in fp.items():
        if dim.startswith("_"):
            continue
        top = ", ".join(f"{k}:{v}" for k, v in sorted(dist.items(), key=lambda x: -x[1])[:4])
        print(f"  {dim:18} {top}")

    if args.dry_run:
        print("\n(dry-run, 未写库)")
        return

    conn = get_connection(args.project)
    save_style_template(conn, fingerprint=fp,
                        source_works=[args.txt.stem],
                        sample_chapters=idxs)
    conn.commit()
    conn.close()
    print(f"\n已写入 {args.project}/style_template (scope={args.scope})")


if __name__ == "__main__":
    main()
