# src/bedrock/web/app.py
"""SP6-C SPA 工作台。create_app(projects_root)：挂 /api 蓝图 + 托管编译后 SPA 静态。

语义变更：旧 create_app(project_dir) 收单个 work 目录；现 create_app(projects_root) 收 work 父目录，
  /api/works 扫描其下所有含 bedrock.db 的子目录。projects_root 必须存在且是目录。
静态托管：static_dir = 包内 static/（vite build 产物）。/ 走 index.html；非 /api 路径优先匹配静态文件，
  不命中则 SPA 回退 index.html（支持前端路由）。
路由优先级：/api 蓝图（url_prefix=/api）在注册后比 catch-all /<path:filepath> 更具体，Flask 优先匹配蓝图；
  spa_assets 内额外 `if filepath.startswith("api"): abort(404)` 兜底防 /api/* 误落 SPA。
"""
from pathlib import Path
from flask import Flask, send_from_directory, abort

from src.bedrock.web.api import bp as api_bp


def create_app(projects_root):
    root = Path(projects_root).resolve()
    if not root.is_dir():
        raise SystemExit(f"projects_root 不是目录: {projects_root}")
    app = Flask(__name__, static_folder=None)
    app.config["PROJECTS_ROOT"] = str(root)
    app.register_blueprint(api_bp)

    static_dir = Path(__file__).parent / "static"

    @app.get("/")
    def index():
        idx = static_dir / "index.html"
        if idx.exists():
            return send_from_directory(static_dir, "index.html")
        return ("SPA 未构建。运行 `cd frontend && npm install && npm run build` 后重试。", 503)

    @app.get("/<path:filepath>")
    def spa_assets(filepath):
        # /api 由蓝图处理（更具体，不落此）。静态资源直接伺服；其余回退 index.html。
        if filepath.startswith("api"):
            abort(404)
        full = static_dir / filepath
        if full.is_file():
            return send_from_directory(static_dir, filepath)
        idx = static_dir / "index.html"
        if idx.exists():
            return send_from_directory(static_dir, "index.html")
        return ("SPA 未构建。", 503)

    return app
