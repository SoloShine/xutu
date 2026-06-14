# src/bedrock/web/__main__.py
"""python -m src.bedrock.web --project <dir> [--port 5000]"""
import argparse
from src.bedrock.web.app import create_app


def main():
    parser = argparse.ArgumentParser(prog="bedrock-web")
    parser.add_argument("--project", required=True, help="项目目录（含 bedrock.db）")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    app = create_app(args.project)
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
