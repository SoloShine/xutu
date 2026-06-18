"""从外部参考作品 txt 提取文风指纹 → 写入目标项目的 style_template(纯程序,零 LLM)。

用法:
  python scripts/extract_reference_style.py \
      --txt "D:/tmp/某作品.txt" --project projects/voidwright \
      [--sample 25] [--scope work|volume] [--volume-id 1] [--encoding utf-8]

拆分/抽样/提取逻辑在 src.bedrock.style.reference_import(工作台 API 共用)。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bedrock.db.connection import get_connection
from src.bedrock.style.template_repo import save_fingerprint_from_text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--txt", type=Path, required=True)
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--sample", type=int, default=None, help="抽样章数(缺省=动态)")
    ap.add_argument("--range", dest="chapter_range", type=int, nargs=2, metavar=("START", "END"),
                    default=None, help="章节范围 1-based 闭区间(前后文风不同时只取代表性段)")
    ap.add_argument("--scope", choices=["work", "volume"], default="work")
    ap.add_argument("--volume-id", type=int, default=None)
    ap.add_argument("--encoding", default="utf-8")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    text = args.txt.read_text(encoding=args.encoding, errors="replace")
    if args.dry_run:
        from src.bedrock.style.reference_import import import_and_extract
        fp, meta = import_and_extract(text, sample=args.sample)
        print(f"参考《{args.txt.name}》: {meta['chapter_count']} 章, 抽样 {meta['sampled_chapters']} 章 → {meta['paragraph_count']} 段")
        for dim, dist in fp.items():
            top = ", ".join(f"{k}:{v}" for k, v in sorted(dist.items(), key=lambda x: -x[1])[:4])
            print(f"  {dim:18} {top}")
        print("\n(dry-run, 未写库)")
        return

    conn = get_connection(args.project)
    rid, meta, seeded = save_fingerprint_from_text(
        conn, scope=args.scope, text=text,
        volume_id=args.volume_id if args.scope == "volume" else None,
        source_work=args.txt.stem, sample=args.sample, chapter_range=args.chapter_range)
    conn.commit()
    conn.close()
    print(f"参考《{args.txt.name}》: {meta['chapter_count']} 章, 抽样 {meta['sampled_chapters']} 章[{meta.get('sample_range')}], {meta['paragraph_count']} 段")
    print(f"已写入 {args.project}/style_template (scope={args.scope}, row={rid})")
    if seeded:
        print("并自动派生文风指令草稿(可润色)。")


if __name__ == "__main__":
    main()
