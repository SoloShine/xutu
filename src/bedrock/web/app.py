# src/bedrock/web/app.py
"""SP6-C Flask app。create_app(project_dir) 工厂。每请求开/关 conn，不缓存。
唯一写点 = advance_inspiration（POST /inspirations/<id>/advance，校验 HX-Request）——本 task 先不加 advance 端点（Task 5）。"""
from pathlib import Path
from flask import Flask, render_template, request, abort

from src.bedrock.db.connection import get_connection
from src.bedrock.web.queries import pov_matrix, list_volumes_simple
from src.bedrock.repositories.outline import list_inspirations, advance_inspiration
from src.bedrock.cli.reader_commands import parse_review_outcomes


def create_app(project_dir):
    """project_dir 含 bedrock.db。校验存在（不创建空 db）。"""
    if not (Path(project_dir) / "bedrock.db").exists():
        raise SystemExit(f"项目目录无 bedrock.db: {project_dir}")
    app = Flask(__name__)
    app.config["PROJECT_DIR"] = project_dir   # 只存路径，不存 conn

    @app.route("/")
    def index():
        conn = get_connection(Path(app.config["PROJECT_DIR"]))
        try:
            volumes = list_volumes_simple(conn)
            return render_template("base.html", volumes=volumes, content="<p>选择一个视图</p>")
        finally:
            conn.close()

    @app.route("/matrix")
    def matrix():
        conn = get_connection(Path(app.config["PROJECT_DIR"]))
        try:
            volumes = list_volumes_simple(conn)
            volume_id = request.args.get("volume", type=int)
            if volume_id is None and volumes:
                volume_id = volumes[0]["id"]
            data = pov_matrix(conn, volume_id) if volume_id else None
            return render_template("matrix.html", volumes=volumes,
                                   volume_id=volume_id, matrix=data)
        finally:
            conn.close()

    @app.route("/inspirations")
    def inspirations():
        conn = get_connection(Path(app.config["PROJECT_DIR"]))
        try:
            type_f = request.args.get("type") or None
            status_f = request.args.get("status") or None
            items = list_inspirations(conn, type_filter=type_f, status_filter=status_f)
            return render_template("inspirations.html", items=items,
                                   type_f=type_f, status_f=status_f)
        finally:
            conn.close()

    @app.route("/report/<int:volume_id>")
    def report(volume_id):
        report_path = Path(app.config["PROJECT_DIR"]) / f"review_report_vol{volume_id}.md"
        if not report_path.exists():
            abort(404)
        text = report_path.read_text(encoding="utf-8")
        import markdown
        html = markdown.markdown(text, extensions=["extra", "sane_lists"])
        outcomes = parse_review_outcomes(text)
        escalate_chs = {ch for ch, st in outcomes.items() if st == "escalate_human"}
        return render_template("report.html", html_body=html, volume_id=volume_id,
                               escalate_chs=escalate_chs, has_escalate=bool(escalate_chs))

    @app.route("/matrix/beats")
    def matrix_beats():
        conn = get_connection(Path(app.config["PROJECT_DIR"]))
        try:
            chapter_id = request.args.get("chapter", type=int)
            character_id = request.args.get("character", type=int)
            beats = conn.execute(
                "SELECT sequence, purpose FROM beat WHERE chapter_id=? AND pov_character_id=? ORDER BY sequence",
                (chapter_id, character_id)).fetchall()
            return render_template("_beats.html", beats=[dict(b) for b in beats])
        finally:
            conn.close()

    @app.route("/inspirations/<int:iid>/advance", methods=["POST"])
    def inspirations_advance(iid):
        if not request.headers.get("HX-Request"):
            abort(403)   # 弱 CSRF
        target = request.form.get("target")
        conn = get_connection(Path(app.config["PROJECT_DIR"]))
        try:
            try:
                row = advance_inspiration(conn, iid, target)
            except ValueError as e:
                return render_template("_inspiration_card.html",
                                       item={"id": iid, "status": "error",
                                             "type": "", "content": "", "source": ""},
                                       error=str(e))
            return render_template("_inspiration_card.html", item=row)
        finally:
            conn.close()

    return app
