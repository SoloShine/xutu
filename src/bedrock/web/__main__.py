# src/bedrock/web/__main__.py
"""python -m src.bedrock.web --projects-root <dir> [--port 5050]"""
import argparse
from pathlib import Path
from src.bedrock.web.app import create_app
from src.bedrock.db.migrate import apply_migrations


def _migrate_all(projects_root):
    """启动时给所有项目 DB 跑迁移(自愈:新列/表自动补,免逐个手动)。"""
    for db in Path(projects_root).glob("*/bedrock.db"):
        try:
            apply_migrations(db.parent)
        except Exception as e:
            print(f"[migrate] {db.parent.name}: {e}")


def main():
    parser = argparse.ArgumentParser(prog="bedrock-web")
    parser.add_argument("--projects-root", required=True, help="作品根目录（子目录各含 bedrock.db）")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    _migrate_all(args.projects_root)
    app = create_app(args.projects_root)
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
