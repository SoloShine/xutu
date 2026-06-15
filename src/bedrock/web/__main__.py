# src/bedrock/web/__main__.py
"""python -m src.bedrock.web --projects-root <dir> [--port 5050]"""
import argparse
from src.bedrock.web.app import create_app


def main():
    parser = argparse.ArgumentParser(prog="bedrock-web")
    parser.add_argument("--projects-root", required=True, help="作品根目录（子目录各含 bedrock.db）")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    app = create_app(args.projects_root)
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
