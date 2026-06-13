# src/bedrock/__main__.py
import argparse
from pathlib import Path
from src.bedrock.init_project import init_project


def main():
    parser = argparse.ArgumentParser(prog="bedrock", description="磐石 V3 小说管线 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="初始化新作品项目")
    p_init.add_argument("path", type=Path)
    p_init.add_argument("--name", required=True)
    p_init.add_argument("--force", action="store_true")

    args = parser.parse_args()
    if args.cmd == "init":
        init_project(args.path, work_name=args.name, force=args.force)
        print(f"已初始化作品 '{args.name}' 于 {args.path}")


if __name__ == "__main__":
    main()
